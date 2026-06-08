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
from compliance_agent.orchestrator import ComplianceOrchestrator


class Phase4PreScreenGateTest(unittest.TestCase):
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

    def test_high_cash_alert_is_obvious_clear_and_persisted_as_false_positive(self) -> None:
        gate_result = self.gate.run(self.source, 1003)

        self.assertEqual(gate_result.gate_decision, "obvious_clear")
        self.assertEqual(gate_result.recommended_disposition, "likely_false_positive")
        self.assertEqual(gate_result.baseline_assessment, "consistent")
        self.assertIn("prior_similar_dismissals_exceed_escalations", gate_result.reason_codes)

        response = self.orchestrator.triage_alert(1003)

        self.assertEqual(response["result"]["recommendation"], "likely_false_positive")
        self.assertEqual(response["validation"]["status"], "passed")
        self.assertEqual(
            response["result"]["details"]["pre_screen_gate"]["gate_decision"],
            "obvious_clear",
        )
        stored = self.orchestrator.sidecar.get_run(response["run_id"])
        self.assertIsNotNone(stored)
        self.assertEqual(stored["output"]["recommendation"], "likely_false_positive")

    def test_low_cash_alert_is_obvious_escalate(self) -> None:
        gate_result = self.gate.run(self.source, 1004)

        self.assertEqual(gate_result.gate_decision, "obvious_escalate")
        self.assertEqual(gate_result.recommended_disposition, "escalate")
        self.assertEqual(gate_result.baseline_assessment, "strong_deviation")
        self.assertIn("strong_deviation_with_structuring_signal", gate_result.reason_codes)

        response = self.orchestrator.triage_alert(1004)

        self.assertEqual(response["result"]["recommendation"], "escalate")
        self.assertEqual(response["validation"]["status"], "passed")

    def test_insufficient_history_is_ambiguous_and_enters_react_runtime(self) -> None:
        gate_result = self.gate.run(self.source, 1005)

        self.assertEqual(gate_result.gate_decision, "ambiguous")
        self.assertEqual(gate_result.recommended_disposition, "investigate")
        self.assertEqual(gate_result.baseline_assessment, "insufficient_data")

        response = self.orchestrator.triage_alert(1005)

        self.assertEqual(
            response["result"]["details"]["triage_path"],
            "pre_screen_ambiguous_react",
        )
        self.assertEqual(
            response["result"]["details"]["pre_screen_gate"]["gate_decision"],
            "ambiguous",
        )
        self.assertIn("react_runtime", response["result"]["details"])
        self.assertEqual(response["validation"]["status"], "passed")
        self.assertNotEqual(response["result"]["recommendation"], "likely_false_positive")

    def test_high_risk_geography_alert_is_obvious_escalate(self) -> None:
        gate_result = self.gate.run(self.source, 1001)

        self.assertEqual(gate_result.gate_decision, "obvious_escalate")
        self.assertEqual(gate_result.recommended_disposition, "escalate")
        self.assertIn("sanctioned_or_blacklisted_country", gate_result.reason_codes)

        response = self.orchestrator.triage_alert(1001)

        self.assertEqual(response["result"]["recommendation"], "escalate")
        self.assertEqual(response["validation"]["status"], "passed")

    def test_gate_agent_result_contains_auditable_fields(self) -> None:
        gate_result = self.gate.run(self.source, 1003)
        agent_result = gate_result.to_agent_result()

        self.assertTrue(agent_result.reasoning)
        self.assertTrue(agent_result.claims)
        self.assertTrue(agent_result.evidence)
        self.assertEqual(agent_result.details["human_required"], True)
        self.assertIn("reason_codes", agent_result.details)
        self.assertIn("baseline_assessment", agent_result.details)
        self.assertIn("selected_typology_signals", agent_result.details)
        self.assertIn("tool_observations", agent_result.details["pre_screen_gate"])


if __name__ == "__main__":
    unittest.main()
