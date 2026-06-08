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
from compliance_agent.agents.validation import ComplianceValidationAgent
from compliance_agent.domain import AgentResult, Claim, EvidenceItem, ReasoningItem, SourceRef
from compliance_agent.orchestrator import ComplianceOrchestrator


class Phase9GroundedReasoningTest(unittest.TestCase):
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

    def test_triage_result_serializes_structured_reasoning(self) -> None:
        response = self.orchestrator.triage_alert(1005)

        self.assertEqual(response["validation"]["status"], "passed")
        reasoning = response["result"]["reasoning"]
        self.assertTrue(reasoning)
        self.assertIsInstance(reasoning[0], dict)
        self.assertIn("statement", reasoning[0])
        self.assertIn("source_refs", reasoning[0])
        self.assertTrue(reasoning[0]["source_refs"])

    def test_risk_and_sar_outputs_validate_structured_reasoning(self) -> None:
        risk_response = self.orchestrator.score_customer(501)
        sar_response = self.orchestrator.draft_sar(9001)

        self.assertEqual(risk_response["validation"]["status"], "passed")
        self.assertEqual(sar_response["validation"]["status"], "passed")
        self.assertTrue(risk_response["result"]["reasoning"][0]["source_refs"])
        self.assertTrue(sar_response["result"]["reasoning"][0]["source_refs"])

    def test_free_text_reasoning_fails_validation(self) -> None:
        result = AgentResult(
            agent_name="test_agent",
            subject_type="alert",
            subject_id=1,
            recommendation="test",
            confidence=0.1,
            score=0,
            reasoning=["legacy free text reasoning"],  # type: ignore[list-item]
            claims=[
                Claim(
                    statement="Supported transaction claim.",
                    source_refs=[SourceRef("transactions", "1")],
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
        self.assertEqual(validation.findings[0].kind, "reasoning")
        self.assertIn("not structured", validation.findings[0].issue)

    def test_unsupported_reasoning_source_ref_fails_validation(self) -> None:
        result = AgentResult(
            agent_name="test_agent",
            subject_type="alert",
            subject_id=1,
            recommendation="test",
            confidence=0.1,
            score=0,
            reasoning=[
                ReasoningItem(
                    statement="Unsupported reasoning statement.",
                    source_refs=[SourceRef("transactions", "missing")],
                )
            ],
            claims=[
                Claim(
                    statement="Supported transaction claim.",
                    source_refs=[SourceRef("transactions", "1")],
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
        self.assertEqual(validation.findings[0].kind, "reasoning")
        self.assertIn("transactions:missing", validation.findings[0].issue)


if __name__ == "__main__":
    unittest.main()
