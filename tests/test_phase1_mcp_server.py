from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
for path in (SRC, ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from compliance_agent.contracts.phase1 import (
    MCPRequestEnvelope,
    SubjectRef,
    ToolExecutionScope,
)
from mcp_server.service import ReferenceMCPTools


class FakeReferenceRepository:
    def get_alert_scope(self, alert_id: int):
        return {
            1003: {"alert_id": 1003, "customer_id": 503, "account_id": 3003, "transaction_id": 7030},
            1006: {"alert_id": 1006, "customer_id": 506, "account_id": 3006, "transaction_id": 7060},
        }.get(alert_id)

    def get_customer_profile(self, customer_id: int):
        return {
            "customer": {"customer_id": customer_id, "full_name": "Cash Retail LLC"},
            "accounts": [{"account_id": 3003, "customer_id": customer_id}],
            "latest_pattern": {"pattern_id": 8103, "customer_id": customer_id},
        }

    def get_transaction_history(self, customer_id: int, *, max_rows: int, lookback_days: int):
        return [
            {"transaction_id": 7030, "account_id": 3003, "amount_usd": 9500.0},
        ][:max_rows]

    def get_behavioral_baseline(self, customer_id: int, alert_id: int, *, max_rows: int, lookback_days: int):
        return {
            "current_transaction": {"transaction_id": 7030, "account_id": 3003, "amount_usd": 9500.0},
            "historical_transactions": [
                {"transaction_id": 7031, "account_id": 3003, "amount_usd": 9100.0}
            ],
            "latest_pattern": {"pattern_id": 8103, "customer_id": customer_id},
            "computed_features": {"baseline_assessment": "consistent"},
        }

    def get_prior_alerts(self, customer_id: int, alert_id: int | None, *, max_rows: int):
        return []

    def get_case_history(self, customer_id: int, *, max_rows: int):
        return {"cases": [], "linked_alerts": [], "comments": []}

    def trace_counterparty_graph(self, alert_id: int, *, max_hops: int, max_rows: int):
        return {
            "start_transaction": {"transaction_id": 7060, "account_id": 3006, "counterparty_account_id": 4500},
            "paths": [{"account_path": [3006, 4500], "transaction_ids": [7060], "hop_count": 1}],
            "edges": [{"transaction_id": 7060, "account_id": 3006, "counterparty_account_id": 4500}],
            "reached_accounts": [3006, 4500],
            "linked_alerts": [{"alert_id": 9901, "transaction_id": 7060}],
            "linked_cases": [{"case_id": 9902, "customer_id": 650, "status": "open"}],
            "computed_features": {
                "signals": {
                    "rapid_pass_through": False,
                    "cycle_detected": False,
                    "fan_out": False,
                    "many_to_one": False,
                    "high_risk_endpoint": True,
                    "linked_alert_count": 1,
                    "linked_open_case_count": 1,
                }
            },
        }

    def screen_sanctions_pep(self, customer_id: int):
        return {
            "customer": {"customer_id": customer_id},
            "sanctions_matches": [],
            "pep_matches": [],
        }

    def get_similar_alerts(self, customer_id: int, alert_id: int, *, max_rows: int):
        return []

    def get_compliance_rule(self, alert_id: int):
        return {"alert_id": alert_id, "transaction_id": 7030, "rule_id": 6, "rule_name": "Structuring Detection", "rule_type": "structuring"}


class Phase1ReferenceMCPServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tools = ReferenceMCPTools(FakeReferenceRepository())

    def _request(self, *, customer_id: int = 503, alert_id: int = 1003, tool_args=None):
        return MCPRequestEnvelope(
            tenant_id="demo-bank",
            officer_id="officer-123",
            agent_run_id="run-test",
            purpose="triage",
            subject=SubjectRef(alert_id=alert_id, customer_id=customer_id),
            scope=ToolExecutionScope(
                allowed_customer_ids=[customer_id],
                allowed_account_ids=[3003 if alert_id == 1003 else 3006],
                allowed_transaction_ids=[7030 if alert_id == 1003 else 7060],
                allowed_case_ids=[],
            ),
            tool_args=tool_args or {},
            idempotency_key="idem-test",
            correlation_id="corr-test",
        ).model_dump(mode="json")

    def test_customer_profile_returns_contract_response_with_refs_and_audit(self) -> None:
        response = self.tools.get_customer_profile(self._request())

        self.assertEqual(response["status"], "ok")
        self.assertTrue(response["audit_id"].startswith("audit-"))
        self.assertTrue(response["source_refs"])
        self.assertEqual(response["policy_decisions"][0]["decision"], "allow")

    def test_scope_violation_is_denied_and_auditable(self) -> None:
        request = self._request(customer_id=999, alert_id=1003)

        response = self.tools.get_customer_profile(request)

        self.assertEqual(response["status"], "denied")
        self.assertEqual(response["policy_decisions"][0]["decision"], "deny")
        self.assertTrue(response["limitations"])

    def test_forbidden_entity_args_are_denied(self) -> None:
        response = self.tools.get_transaction_history(
            self._request(tool_args={"customer_id": 999})
        )

        self.assertEqual(response["status"], "denied")
        self.assertIn("Tool arguments cannot include", response["limitations"][0])

    def test_graph_trace_returns_source_grounded_graph_facts(self) -> None:
        response = self.tools.trace_counterparty_graph(
            self._request(customer_id=506, alert_id=1006, tool_args={"max_hops": 2})
        )

        self.assertEqual(response["status"], "ok")
        self.assertTrue(response["facts"]["computed_features"]["signals"]["high_risk_endpoint"])
        self.assertIn("transaction", {ref["entity_type"] for ref in response["source_refs"]})


if __name__ == "__main__":
    unittest.main()
