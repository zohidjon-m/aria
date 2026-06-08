from __future__ import annotations

import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
DEPS = os.path.join(ROOT, ".codex_deps")
for path in (SRC, DEPS):
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

from compliance_agent.adapters.fake_source import FakeBankSourceRepository
from compliance_agent.adapters.sidecar_store import SidecarStore
from compliance_agent.agents.confidence import ENGINE_VERSION, ConfidenceEngine
from compliance_agent.agents.pre_screen import PreScreenGate
from compliance_agent.agents.react_runtime import (
    CRITICAL_SIGNAL_FOUND,
    MAX_STEPS_EXHAUSTED,
    NO_PROGRESS,
    PlannerAction,
    ReActRuntime,
    ReActRuntimeConfig,
)
from compliance_agent.agents.tooling import DataCompleteness, ToolLimitation, ToolObservation
from compliance_agent.orchestrator import ComplianceOrchestrator


class RepeatingPlanner:
    def next_action(self, state):
        return PlannerAction(
            thought="Repeat a tool call to force no-progress confidence behavior.",
            next_tool="get_alert_context",
            tool_args={},
        )


class Phase10ConfidenceEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = FakeBankSourceRepository()
        self.gate = PreScreenGate()
        self.engine = ConfidenceEngine()

    def test_obvious_clear_uses_consistent_baseline_and_prior_dismissals(self) -> None:
        result = self.gate.run(self.source, 1003)
        breakdown = result.confidence_breakdown
        factor_names = {factor["name"] for factor in breakdown["factors"]}

        self.assertEqual(breakdown["engine_version"], ENGINE_VERSION)
        self.assertEqual(breakdown["mode"], "pre_screen_gate")
        self.assertEqual(breakdown["signals"]["baseline_assessment"], "consistent")
        self.assertGreater(result.confidence, 0.80)
        self.assertIn("baseline_consistent_false_positive", factor_names)
        self.assertIn("prior_similar_dismissals", factor_names)

    def test_obvious_escalation_red_flags_raise_confidence(self) -> None:
        context = self.source._alert_contexts[1001]
        context["sanctions_matches"] = [
            {
                "sanction_id": 99001,
                "full_name": context["customer"]["full_name"],
                "program": "OFAC",
                "match_score": 1.0,
            }
        ]
        transaction = dict(context["transaction"])
        context["recent_transactions"] = [
            {
                **transaction,
                "transaction_id": 98000 + index,
                "created_at": f"2026-06-06T08:{index:02d}:00+00:00",
            }
            for index in range(10)
        ]

        result = self.gate.run(self.source, 1001)
        signals = result.confidence_breakdown["signals"]
        factor_names = {factor["name"] for factor in result.confidence_breakdown["factors"]}

        self.assertEqual(result.recommended_disposition, "escalate")
        self.assertGreaterEqual(result.confidence, 0.90)
        self.assertEqual(signals["sanctions_match_count"], 1)
        self.assertTrue(signals["geography_signal"])
        self.assertTrue(signals["velocity_threshold_met"])
        self.assertIn("hard_red_flags_confirm_escalation", factor_names)
        self.assertIn("sanctions_match_certainty", factor_names)

    def test_ambiguous_insufficient_history_lowers_confidence(self) -> None:
        clear_result = self.gate.run(self.source, 1003)
        ambiguous_result = self.gate.run(self.source, 1005)
        factor_names = {
            factor["name"] for factor in ambiguous_result.confidence_breakdown["factors"]
        }

        self.assertEqual(ambiguous_result.gate_decision, "ambiguous")
        self.assertLess(ambiguous_result.confidence, clear_result.confidence)
        self.assertIn("baseline_insufficient_data", factor_names)
        self.assertIn("warning_limitations", factor_names)

    def test_react_critical_signal_is_more_confident_than_control_failures(self) -> None:
        critical_pre_screen = self.gate.run(self.source, 1001)
        critical = ReActRuntime().run_triage(
            self.source,
            1001,
            pre_screen_result=critical_pre_screen,
        )
        exhausted = ReActRuntime(
            config=ReActRuntimeConfig(max_steps=1, max_tool_calls=5)
        ).run_triage(self.source, 1003)
        no_progress = ReActRuntime(
            config=ReActRuntimeConfig(max_steps=3, max_tool_calls=3),
            planner=RepeatingPlanner(),
        ).run_triage(self.source, 1002)

        self.assertEqual(critical.details["react_runtime"]["stop_reason"], CRITICAL_SIGNAL_FOUND)
        self.assertEqual(exhausted.details["react_runtime"]["stop_reason"], MAX_STEPS_EXHAUSTED)
        self.assertEqual(no_progress.details["react_runtime"]["stop_reason"], NO_PROGRESS)
        self.assertGreater(critical.confidence, exhausted.confidence)
        self.assertGreater(critical.confidence, no_progress.confidence)

    def test_incomplete_observations_and_limitations_reduce_confidence(self) -> None:
        complete = self.engine.compute_pre_screen(
            recommendation="likely_false_positive",
            gate_decision="obvious_clear",
            observations={
                "compute_behavioral_baseline": ToolObservation(
                    computed_features={
                        "baseline_assessment": "consistent",
                        "similar_dismissed_count": 2,
                        "similar_escalated_count": 0,
                    }
                )
            },
            reason_codes=["baseline_consistent"],
        )
        incomplete = self.engine.compute_pre_screen(
            recommendation="likely_false_positive",
            gate_decision="obvious_clear",
            observations={
                "compute_behavioral_baseline": ToolObservation(
                    computed_features={
                        "baseline_assessment": "consistent",
                        "similar_dismissed_count": 2,
                        "similar_escalated_count": 0,
                    },
                    data_completeness=DataCompleteness(
                        complete=False,
                        missing_segments=["transaction_patterns"],
                    ),
                    limitations=[
                        ToolLimitation(
                            code="insufficient_history",
                            message="Fewer than 5 rows were available.",
                            severity="warning",
                        )
                    ],
                )
            },
            reason_codes=["baseline_consistent"],
        )
        factor_names = {factor["name"] for factor in incomplete.factors}

        self.assertLess(incomplete.final_confidence, complete.final_confidence)
        self.assertIn("evidence_incomplete", factor_names)
        self.assertIn("missing_data_segments", factor_names)
        self.assertIn("warning_limitations", factor_names)

    def test_graph_red_flags_contribute_to_investigate_confidence(self) -> None:
        base_observations = {
            "compute_behavioral_baseline": ToolObservation(
                computed_features={"baseline_assessment": "consistent"}
            )
        }
        graph_observations = {
            **base_observations,
            "trace_money_flow": ToolObservation(
                computed_features={
                    "signals": {
                        "rapid_pass_through": False,
                        "cycle_detected": False,
                        "fan_out": True,
                        "many_to_one": False,
                        "high_risk_endpoint": False,
                        "linked_alert_count": 0,
                        "linked_open_case_count": 0,
                    }
                }
            ),
        }

        without_graph = self.engine.compute_react(
            recommendation="investigate",
            stop_reason="completed",
            observations=base_observations,
        )
        with_graph = self.engine.compute_react(
            recommendation="investigate",
            stop_reason="completed",
            observations=graph_observations,
        )
        factor_names = {factor["name"] for factor in with_graph.factors}

        self.assertGreater(with_graph.final_confidence, without_graph.final_confidence)
        self.assertIn("graph_red_flags", factor_names)

    def test_confidence_breakdown_is_persisted_for_react_triage(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        os.remove(path)
        try:
            orchestrator = ComplianceOrchestrator(
                source=FakeBankSourceRepository(),
                sidecar=SidecarStore(path),
            )

            response = orchestrator.triage_alert(1005)
            details = response["result"]["details"]
            stored = orchestrator.sidecar.get_run(response["run_id"])

            self.assertEqual(
                details["confidence_breakdown"]["engine_version"],
                ENGINE_VERSION,
            )
            self.assertEqual(
                details["pre_screen_gate"]["confidence_breakdown"]["engine_version"],
                ENGINE_VERSION,
            )
            self.assertIsNotNone(stored)
            self.assertEqual(
                stored["output"]["details"]["confidence_breakdown"]["engine_version"],
                ENGINE_VERSION,
            )
        finally:
            if os.path.exists(path):
                os.remove(path)


if __name__ == "__main__":
    unittest.main()
