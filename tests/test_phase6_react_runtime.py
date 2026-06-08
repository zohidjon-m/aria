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
from compliance_agent.agents.pre_screen import PreScreenGate
from compliance_agent.agents.react_runtime import (
    CRITICAL_SIGNAL_FOUND,
    INSUFFICIENT_EVIDENCE,
    MAX_STEPS_EXHAUSTED,
    NO_PROGRESS,
    PlannerAction,
    ReActRuntime,
    ReActRuntimeConfig,
)
from compliance_agent.orchestrator import ComplianceOrchestrator


class RepeatingPlanner:
    def next_action(self, state):
        return PlannerAction(
            thought="Deliberately repeat the same tool for runtime-control testing.",
            next_tool="get_alert_context",
            tool_args={},
        )


class Phase6ReActRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        os.remove(path)
        self.db_path = path
        self.source = FakeBankSourceRepository()
        self.gate = PreScreenGate()
        self.orchestrator = ComplianceOrchestrator(
            source=self.source,
            sidecar=SidecarStore(path),
        )

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_ambiguous_triage_alert_uses_react_runtime_and_persists_trace(self) -> None:
        response = self.orchestrator.triage_alert(1005)
        result = response["result"]
        runtime_details = result["details"]["react_runtime"]

        self.assertEqual(result["recommendation"], "investigate")
        self.assertEqual(result["details"]["triage_path"], "pre_screen_ambiguous_react")
        self.assertEqual(runtime_details["planner"], "heuristic")
        self.assertEqual(runtime_details["stop_reason"], INSUFFICIENT_EVIDENCE)
        self.assertTrue(runtime_details["steps"])
        self.assertEqual(response["validation"]["status"], "passed")

        stored = self.orchestrator.sidecar.get_run(response["run_id"])
        self.assertIsNotNone(stored)
        stored_runtime = stored["output"]["details"]["react_runtime"]
        self.assertEqual(stored_runtime["stop_reason"], INSUFFICIENT_EVIDENCE)
        self.assertTrue(stored_runtime["steps"])

    def test_runtime_uses_routed_registry_and_does_not_call_skipped_geography(self) -> None:
        response = self.orchestrator.triage_alert(1005)
        runtime_details = response["result"]["details"]["react_runtime"]
        route = response["result"]["details"]["typology_route"]
        executed_tools = {
            step["tool_name"]
            for step in runtime_details["steps"]
            if step.get("tool_name")
        }

        self.assertIn("geography", route["skipped"])
        self.assertNotIn("run_geography_check", route["allowed_tools"])
        self.assertNotIn("run_geography_check", executed_tools)

    def test_runtime_stops_on_critical_signal_and_escalates(self) -> None:
        pre_screen = self.gate.run(self.source, 1001)
        result = ReActRuntime().run_triage(
            self.source,
            1001,
            pre_screen_result=pre_screen,
        )

        self.assertEqual(result.recommendation, "escalate")
        self.assertEqual(
            result.details["react_runtime"]["stop_reason"],
            CRITICAL_SIGNAL_FOUND,
        )

    def test_max_steps_exhaustion_fails_safe_to_investigate(self) -> None:
        result = ReActRuntime(
            config=ReActRuntimeConfig(max_steps=1, max_tool_calls=5)
        ).run_triage(self.source, 1003)

        self.assertEqual(result.recommendation, "investigate")
        self.assertEqual(
            result.details["react_runtime"]["stop_reason"],
            MAX_STEPS_EXHAUSTED,
        )

    def test_repeated_tool_call_detection_fails_safe_to_investigate(self) -> None:
        result = ReActRuntime(
            config=ReActRuntimeConfig(max_steps=3, max_tool_calls=3),
            planner=RepeatingPlanner(),
        ).run_triage(self.source, 1002)

        self.assertEqual(result.recommendation, "investigate")
        self.assertEqual(
            result.details["react_runtime"]["stop_reason"],
            NO_PROGRESS,
        )


if __name__ == "__main__":
    unittest.main()
