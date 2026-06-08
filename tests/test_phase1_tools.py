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
from compliance_agent.agents.phase1_tools import (
    PHASE1_TOOL_NAMES,
    build_phase1_tool_registry,
    build_scope_for_alert,
)
from compliance_agent.agents.tooling import (
    InvestigationScope,
    ScopeViolationError,
    ToolArgumentError,
    ToolExecutionContext,
    ToolObservation,
    UnknownToolError,
)


class Phase1ToolingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = FakeBankSourceRepository()
        self.registry = build_phase1_tool_registry()
        self.alert_context = self.source.get_alert_context(1001)
        self.scope = build_scope_for_alert(self.source, 1001)
        self.execution_context = ToolExecutionContext(
            source=self.source,
            scope=self.scope,
        )

    def test_registry_contains_phase1_tools(self) -> None:
        self.assertEqual(self.registry.names, PHASE1_TOOL_NAMES)

    def test_unknown_tool_raises_controlled_error(self) -> None:
        with self.assertRaises(UnknownToolError):
            self.registry.execute("not_a_tool", self.execution_context, {})

    def test_tool_schemas_reject_unbounded_args(self) -> None:
        with self.assertRaises(ToolArgumentError):
            self.registry.execute(
                "get_recent_transactions",
                self.execution_context,
                {"lookback_days": 366},
            )
        with self.assertRaises(ToolArgumentError):
            self.registry.execute(
                "get_recent_transactions",
                self.execution_context,
                {"max_rows": 101},
            )
        with self.assertRaises(ToolArgumentError):
            self.registry.execute(
                "trace_money_flow",
                self.execution_context,
                {"max_hops": 5},
            )

    def test_scoped_tools_reject_planner_supplied_entity_ids(self) -> None:
        for tool_name in ("get_alert_context", "get_recent_transactions", "trace_money_flow"):
            with self.subTest(tool_name=tool_name):
                with self.assertRaises(ScopeViolationError):
                    self.registry.execute(
                        tool_name,
                        self.execution_context,
                        {"customer_id": 999999},
                    )

    def test_investigation_scope_is_built_from_alert_context(self) -> None:
        scope = InvestigationScope.from_alert_context(self.alert_context)

        self.assertEqual(scope.alert_id, 1001)
        self.assertEqual(scope.customer_id, 501)
        self.assertEqual(scope.account_id, 3001)
        self.assertEqual(scope.transaction_id, 7004)

    def test_get_alert_context_returns_facts_refs_and_no_narrative(self) -> None:
        observation = self.registry.execute("get_alert_context", self.execution_context, {})

        self.assertIsInstance(observation, ToolObservation)
        self.assertIn("alert", observation.facts)
        self.assertIn("customer", observation.facts)
        self.assertGreaterEqual(len(observation.source_refs), 5)
        self.assertNotIn("narrative", observation.model_dump())
        self.assertNotIn("reasoning", observation.model_dump())

    def test_get_recent_transactions_respects_max_rows(self) -> None:
        observation = self.registry.execute(
            "get_recent_transactions",
            self.execution_context,
            {"max_rows": 2},
        )

        self.assertEqual(len(observation.facts["recent_transactions"]), 2)
        self.assertEqual(observation.data_completeness.rows_requested, 2)
        self.assertEqual(observation.data_completeness.rows_returned, 2)

    def test_get_open_cases_uses_scoped_customer_only(self) -> None:
        observation = self.registry.execute(
            "get_open_cases",
            self.execution_context,
            {"max_rows": 10},
        )

        self.assertEqual(observation.computed_features["open_case_count"], 1)
        self.assertEqual(observation.facts["open_cases"][0]["customer_id"], 501)

    def test_screen_sanctions_pep_returns_structured_observation(self) -> None:
        observation = self.registry.execute("screen_sanctions_pep", self.execution_context, {})

        self.assertIn("sanctions_matches", observation.facts)
        self.assertIn("pep_matches", observation.facts)
        self.assertIn("sanctions_match_count", observation.computed_features)
        self.assertIsNotNone(observation.data_completeness)
        self.assertGreaterEqual(len(observation.limitations), 1)

    def test_minimal_baseline_typology_and_graph_tools_return_observations(self) -> None:
        for tool_name in (
            "compute_behavioral_baseline",
            "run_structuring_check",
            "run_velocity_check",
            "run_geography_check",
            "trace_money_flow",
        ):
            with self.subTest(tool_name=tool_name):
                observation = self.registry.execute(tool_name, self.execution_context, {})
                self.assertIsInstance(observation, ToolObservation)
                self.assertIsInstance(observation.facts, dict)
                self.assertIsInstance(observation.computed_features, dict)
                self.assertIsNotNone(observation.data_completeness)


if __name__ == "__main__":
    unittest.main()
