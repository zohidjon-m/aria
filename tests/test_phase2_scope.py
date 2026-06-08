from __future__ import annotations

import os
import sys
import unittest
from typing import Any

from pydantic import BaseModel, ConfigDict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
DEPS = os.path.join(ROOT, ".codex_deps")
for path in (SRC, DEPS):
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

from compliance_agent.adapters.fake_source import FakeBankSourceRepository
from compliance_agent.agents.phase1_tools import build_phase1_tool_registry, build_scope_for_alert
from compliance_agent.agents.tooling import (
    InvestigationScope,
    ScopeViolationError,
    ToolDefinition,
    ToolExecutionContext,
    ToolObservation,
    ToolRegistry,
)


class UnsafeCustomerArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: int


def unsafe_handler(context: ToolExecutionContext, args: BaseModel) -> ToolObservation:
    return ToolObservation(facts={"unsafe_customer_id": args.model_dump()["customer_id"]})


class Phase2ScopeControlTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = FakeBankSourceRepository()
        self.registry = build_phase1_tool_registry()
        self.scope = build_scope_for_alert(self.source, 1001)
        self.execution_context = ToolExecutionContext(
            source=self.source,
            scope=self.scope,
        )

    def test_tool_definitions_expose_scope_policies(self) -> None:
        self.assertEqual(self.registry.get("get_alert_context").scope_policy.name, "root_alert")
        trace_policy = self.registry.get("trace_money_flow").scope_policy
        self.assertEqual(trace_policy.name, "graph_expandable")
        self.assertTrue(trace_policy.allow_graph_expansion)

    def test_registry_rejects_planner_supplied_entity_fields_generically(self) -> None:
        forbidden_fields: dict[str, Any] = {
            "customer_id": 999999,
            "account_id": 999999,
            "transaction_id": 999999,
            "alert_id": 999999,
            "case_id": 999999,
        }

        for field_name, value in forbidden_fields.items():
            with self.subTest(field_name=field_name):
                with self.assertRaises(ScopeViolationError):
                    self.registry.execute(
                        "get_recent_transactions",
                        self.execution_context,
                        {field_name: value},
                    )

    def test_unsafe_tool_schema_is_still_blocked_by_registry(self) -> None:
        unsafe_registry = ToolRegistry(
            [
                ToolDefinition(
                    name="unsafe_customer_lookup",
                    purpose="Deliberately unsafe test tool.",
                    args_model=UnsafeCustomerArgs,
                    handler=unsafe_handler,
                )
            ]
        )

        with self.assertRaises(ScopeViolationError):
            unsafe_registry.execute(
                "unsafe_customer_lookup",
                self.execution_context,
                {"customer_id": 999999},
            )

    def test_root_scoped_tools_execute_with_alert_linked_scope(self) -> None:
        observation = self.registry.execute("get_alert_context", self.execution_context, {})

        self.assertEqual(observation.facts["customer"]["customer_id"], 501)
        self.assertEqual(observation.facts["account"]["account_id"], 3001)
        self.assertEqual(observation.facts["transaction"]["transaction_id"], 7004)

    def test_scope_contains_only_root_ids_initially(self) -> None:
        self.assertEqual(self.scope.allowed_customer_ids, {501})
        self.assertEqual(self.scope.allowed_account_ids, {3001})
        self.assertEqual(self.scope.allowed_transaction_ids, {7004})
        self.assertEqual(self.scope.trusted_graph_edges, [])

    def test_mismatched_alert_context_raises_controlled_scope_error(self) -> None:
        mismatched_scope = InvestigationScope(
            alert_id=1001,
            customer_id=999999,
            account_id=3001,
            transaction_id=7004,
        )
        context = ToolExecutionContext(source=self.source, scope=mismatched_scope)

        with self.assertRaises(ScopeViolationError):
            self.registry.execute("get_alert_context", context, {})

    def test_trace_money_flow_records_immediate_trusted_graph_edge(self) -> None:
        self.source._alert_contexts[1001]["transaction"]["counterparty_account_id"] = 4001
        scoped_context = ToolExecutionContext(
            source=self.source,
            scope=build_scope_for_alert(self.source, 1001),
        )

        observation, updated_context = self.registry.execute_with_context(
            "trace_money_flow",
            scoped_context,
            {},
        )

        self.assertTrue(observation.computed_features["has_immediate_counterparty"])
        self.assertEqual(len(updated_context.scope.trusted_graph_edges), 1)
        edge = updated_context.scope.trusted_graph_edges[0]
        self.assertEqual(edge.source_transaction_id, 7004)
        self.assertEqual(edge.source_account_id, 3001)
        self.assertEqual(edge.counterparty_account_id, 4001)
        self.assertIn(4001, updated_context.scope.allowed_account_ids)

    def test_graph_expandable_tool_cannot_start_from_raw_account_id(self) -> None:
        with self.assertRaises(ScopeViolationError):
            self.registry.execute(
                "trace_money_flow",
                self.execution_context,
                {"account_id": 4001},
            )


if __name__ == "__main__":
    unittest.main()
