from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
DEPS = os.path.join(ROOT, ".codex_deps")
for path in (SRC, DEPS):
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

from compliance_agent.adapters.fake_source import FakeBankSourceRepository
from compliance_agent.agents.phase1_tools import build_phase1_tool_registry, build_scope_for_alert
from compliance_agent.agents.react_runtime import CRITICAL_SIGNAL_FOUND, ReActRuntime
from compliance_agent.agents.tooling import ToolExecutionContext, ToolObservation


class Phase8GraphTracingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = FakeBankSourceRepository()
        self.registry = build_phase1_tool_registry()

    def _context(self, alert_id: int) -> ToolExecutionContext:
        return ToolExecutionContext(
            source=self.source,
            scope=build_scope_for_alert(self.source, alert_id),
        )

    def _install_graph_fixture(
        self,
        *,
        high_risk_endpoint: bool = False,
        linked_case: bool = False,
    ) -> None:
        context = self.source._alert_contexts[1002]
        context["transaction"]["counterparty_account_id"] = 4500
        context["transaction"]["is_flagged"] = False
        context["recent_transactions"][0]["counterparty_account_id"] = 4500
        context["recent_transactions"][0]["is_flagged"] = False

        self.source._graph_accounts.update(
            {
                4500: {
                    "account_id": 4500,
                    "customer_id": 650,
                    "branch_id": 17,
                    "account_number": "GRAPH04500",
                    "account_type": "business",
                    "currency_code": "USD",
                    "status": "active",
                },
                4600: {
                    "account_id": 4600,
                    "customer_id": 651,
                    "branch_id": 17,
                    "account_number": "GRAPH04600",
                    "account_type": "business",
                    "currency_code": "USD",
                    "status": "active",
                },
                4601: {
                    "account_id": 4601,
                    "customer_id": 652,
                    "branch_id": 17,
                    "account_number": "GRAPH04601",
                    "account_type": "checking",
                    "currency_code": "USD",
                    "status": "active",
                },
                4602: {
                    "account_id": 4602,
                    "customer_id": 653,
                    "branch_id": 17,
                    "account_number": "GRAPH04602",
                    "account_type": "checking",
                    "currency_code": "USD",
                    "status": "active",
                },
                4700: {
                    "account_id": 4700,
                    "customer_id": 654,
                    "branch_id": 17,
                    "account_number": "GRAPH04700",
                    "account_type": "checking",
                    "currency_code": "USD",
                    "status": "active",
                },
                4800: {
                    "account_id": 4800,
                    "customer_id": 655,
                    "branch_id": 17,
                    "account_number": "GRAPH04800",
                    "account_type": "checking",
                    "currency_code": "USD",
                    "status": "active",
                },
            }
        )
        self.source._graph_customers.update(
            {
                650: {
                    "customer_id": 650,
                    "full_name": "Pass Through LLC",
                    "risk_level": "high" if high_risk_endpoint else "medium",
                    "kyc_status": "verified",
                    "is_active": True,
                },
                651: {
                    "customer_id": 651,
                    "full_name": "Endpoint LLC",
                    "risk_level": "high" if high_risk_endpoint else "medium",
                    "kyc_status": "verified",
                    "is_active": True,
                },
                652: {
                    "customer_id": 652,
                    "full_name": "Fanout A",
                    "risk_level": "medium",
                    "kyc_status": "verified",
                    "is_active": True,
                },
                653: {
                    "customer_id": 653,
                    "full_name": "Fanout B",
                    "risk_level": "medium",
                    "kyc_status": "verified",
                    "is_active": True,
                },
                654: {
                    "customer_id": 654,
                    "full_name": "Aggregator A",
                    "risk_level": "medium",
                    "kyc_status": "verified",
                    "is_active": True,
                },
                655: {
                    "customer_id": 655,
                    "full_name": "Aggregator B",
                    "risk_level": "medium",
                    "kyc_status": "verified",
                    "is_active": True,
                },
            }
        )
        self.source._graph_transactions = [
            {
                "transaction_id": 8001,
                "account_id": 4500,
                "counterparty_account_id": 4600,
                "transaction_type": "wire",
                "amount_usd": 50000.0,
                "destination_country": None,
                "created_at": "2026-06-06T11:00:00+00:00",
                "status": "completed",
                "is_flagged": False,
            },
            {
                "transaction_id": 8002,
                "account_id": 4500,
                "counterparty_account_id": 4601,
                "transaction_type": "wire",
                "amount_usd": 12000.0,
                "destination_country": None,
                "created_at": "2026-06-06T11:10:00+00:00",
                "status": "completed",
                "is_flagged": False,
            },
            {
                "transaction_id": 8003,
                "account_id": 4500,
                "counterparty_account_id": 4602,
                "transaction_type": "wire",
                "amount_usd": 11000.0,
                "destination_country": None,
                "created_at": "2026-06-06T11:20:00+00:00",
                "status": "completed",
                "is_flagged": False,
            },
            {
                "transaction_id": 8004,
                "account_id": 4500,
                "counterparty_account_id": 3002,
                "transaction_type": "wire",
                "amount_usd": 1000.0,
                "destination_country": None,
                "created_at": "2026-06-06T11:30:00+00:00",
                "status": "completed",
                "is_flagged": False,
            },
            {
                "transaction_id": 8005,
                "account_id": 4700,
                "counterparty_account_id": 4500,
                "transaction_type": "wire",
                "amount_usd": 7000.0,
                "destination_country": None,
                "created_at": "2026-06-06T10:00:00+00:00",
                "status": "completed",
                "is_flagged": False,
            },
            {
                "transaction_id": 8006,
                "account_id": 4800,
                "counterparty_account_id": 4500,
                "transaction_type": "wire",
                "amount_usd": 8000.0,
                "destination_country": None,
                "created_at": "2026-06-06T10:15:00+00:00",
                "status": "completed",
                "is_flagged": False,
            },
        ]
        self.source._graph_alerts = [
            {
                "alert_id": 9901,
                "transaction_id": 8001,
                "rule_id": 2,
                "severity": "high",
                "status": "open",
                "created_at": "2026-06-06T11:05:00+00:00",
            }
        ]
        self.source._graph_cases = []
        if linked_case:
            self.source._graph_cases = [
                {
                    "case_id": 9902,
                    "customer_id": 650,
                    "case_type": "AML",
                    "status": "open",
                    "priority": "high",
                    "opened_at": "2026-06-06T11:10:00+00:00",
                    "summary": "Open graph endpoint case.",
                }
            ]

    def test_no_counterparty_returns_empty_paths_and_no_scope_expansion(self) -> None:
        observation, updated_context = self.registry.execute_with_context(
            "trace_money_flow",
            self._context(1003),
            {},
        )

        self.assertEqual(observation.facts["paths"], [])
        self.assertEqual(observation.facts["edges"], [])
        self.assertEqual(observation.computed_features["trusted_graph_edges"], [])
        self.assertEqual(updated_context.scope.allowed_account_ids, {3003})

    def test_immediate_edge_behavior_remains_compatible(self) -> None:
        self.source._alert_contexts[1001]["transaction"]["counterparty_account_id"] = 4001
        self.source._alert_contexts[1001]["recent_transactions"][-1][
            "counterparty_account_id"
        ] = 4001

        observation, updated_context = self.registry.execute_with_context(
            "trace_money_flow",
            self._context(1001),
            {},
        )

        self.assertTrue(observation.computed_features["has_immediate_counterparty"])
        self.assertEqual(observation.facts["paths"][0]["account_path"], [3001, 4001])
        self.assertEqual(len(updated_context.scope.trusted_graph_edges), 1)
        self.assertIn(4001, updated_context.scope.allowed_account_ids)

    def test_multi_hop_tracing_follows_observed_edges_only(self) -> None:
        self._install_graph_fixture()

        observation = self.registry.execute(
            "trace_money_flow",
            self._context(1002),
            {"max_hops": 2, "max_rows": 20},
        )

        paths = observation.facts["paths"]
        self.assertIn([3002, 4500, 4600], [path["account_path"] for path in paths])
        self.assertIn(4600, observation.facts["reached_accounts"])
        self.assertIn(8001, [edge["transaction_id"] for edge in observation.facts["edges"]])

    def test_max_hops_truncates_traversal(self) -> None:
        self._install_graph_fixture()

        observation = self.registry.execute(
            "trace_money_flow",
            self._context(1002),
            {"max_hops": 1, "max_rows": 20},
        )

        self.assertNotIn(4600, observation.facts["reached_accounts"])
        self.assertEqual({path["hop_count"] for path in observation.facts["paths"]}, {1})

    def test_max_rows_truncates_results_and_marks_incomplete(self) -> None:
        self._install_graph_fixture()

        observation = self.registry.execute(
            "trace_money_flow",
            self._context(1002),
            {"max_hops": 4, "max_rows": 1},
        )

        self.assertEqual(len(observation.facts["edges"]), 1)
        self.assertFalse(observation.data_completeness.complete)
        self.assertIn("graph_row_limit_reached", {item.code for item in observation.limitations})

    def test_graph_red_flag_signals_are_detected(self) -> None:
        self._install_graph_fixture(high_risk_endpoint=True, linked_case=True)

        observation = self.registry.execute(
            "trace_money_flow",
            self._context(1002),
            {"max_hops": 2, "max_rows": 20},
        )
        signals = observation.computed_features["signals"]

        self.assertTrue(signals["rapid_pass_through"])
        self.assertTrue(signals["cycle_detected"])
        self.assertTrue(signals["fan_out"])
        self.assertTrue(signals["many_to_one"])
        self.assertTrue(signals["high_risk_endpoint"])
        self.assertEqual(signals["linked_alert_count"], 2)
        self.assertEqual(signals["linked_open_case_count"], 1)

    def test_runtime_escalates_on_graph_critical_signal(self) -> None:
        self._install_graph_fixture(high_risk_endpoint=True, linked_case=True)

        result = ReActRuntime().run_triage(self.source, 1002)

        self.assertEqual(result.recommendation, "escalate")
        self.assertEqual(result.details["react_runtime"]["stop_reason"], CRITICAL_SIGNAL_FOUND)

    def test_graph_red_flags_prevent_false_positive_recommendation(self) -> None:
        observation = ToolObservation(
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
        )
        baseline = ToolObservation(
            computed_features={"baseline_assessment": "consistent"}
        )

        recommendation = ReActRuntime()._completed_recommendation(
            {
                "compute_behavioral_baseline": baseline,
                "trace_money_flow": observation,
            }
        )

        self.assertEqual(recommendation, "investigate")


if __name__ == "__main__":
    unittest.main()
