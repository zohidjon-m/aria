from __future__ import annotations

import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from compliance_agent.adapters.fake_source import FakeBankSourceRepository
from compliance_agent.adapters.sidecar_store import SidecarStore
from compliance_agent.agents.validation import ComplianceValidationAgent
from compliance_agent.domain import AgentResult, Claim, EvidenceItem, SourceRef
from compliance_agent.orchestrator import ComplianceOrchestrator


class AgentWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        os.remove(path)
        self.db_path = path
        self.orchestrator = ComplianceOrchestrator(
            source=FakeBankSourceRepository(),
            sidecar=SidecarStore(path),
        )

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_triage_escalates_high_risk_alert_and_persists_run(self) -> None:
        response = self.orchestrator.triage_alert(1001)

        self.assertEqual(response["result"]["recommendation"], "escalate")
        self.assertEqual(response["validation"]["status"], "passed")

        stored = self.orchestrator.sidecar.get_run(response["run_id"])
        self.assertIsNotNone(stored)
        self.assertEqual(stored["run"]["agent_name"], "triage_agent")

    def test_risk_score_is_proposed_for_human_review(self) -> None:
        response = self.orchestrator.score_customer(501)

        self.assertEqual(response["validation"]["status"], "passed")
        self.assertEqual(response["result"]["details"]["human_required"], True)
        self.assertIn(response["result"]["details"]["level"], {"high", "critical"})

    def test_sar_draft_is_not_a_submission(self) -> None:
        response = self.orchestrator.draft_sar(9001)

        self.assertEqual(response["validation"]["status"], "passed")
        self.assertEqual(response["result"]["recommendation"], "draft_for_human_review")
        self.assertIn("HUMAN REVIEW REQUIRED", response["result"]["details"]["narrative"])

    def test_validation_fails_unsupported_claim(self) -> None:
        result = AgentResult(
            agent_name="test_agent",
            subject_type="alert",
            subject_id=1,
            recommendation="test",
            confidence=0.1,
            score=0,
            reasoning=[],
            claims=[
                Claim(
                    statement="Unsupported transaction claim.",
                    source_refs=[SourceRef("transactions", "missing")],
                )
            ],
            evidence=[
                EvidenceItem(
                    evidence_id="transactions:1",
                    source_ref=SourceRef("transactions", "1"),
                    payload={"transaction_id": 1},
                )
            ],
        )

        validation = ComplianceValidationAgent().validate(result)

        self.assertEqual(validation.status, "failed")
        self.assertEqual(validation.unsupported_count, 1)


if __name__ == "__main__":
    unittest.main()
