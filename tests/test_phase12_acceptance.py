"""Phase 12 acceptance tests.

Each test maps directly to one acceptance criterion from docs/agent-intelligence-plan.md
§ Phase 12.  All tests are deterministic and no live LLM calls are made.
"""

from __future__ import annotations

import json
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
from compliance_agent.agents.llm_planner import LLMPlanner
from compliance_agent.agents.phase1_tools import build_phase1_tool_registry, build_scope_for_alert
from compliance_agent.agents.pre_screen import PreScreenGate
from compliance_agent.agents.react_runtime import (
    MAX_STEPS_EXHAUSTED,
    NO_PROGRESS,
    SCHEMA_ERROR,
    PlannerAction,
    ReActRuntime,
    ReActRuntimeConfig,
)
from compliance_agent.agents.typology_router import TypologyRouter
from compliance_agent.agents.validation import ComplianceValidationAgent
from compliance_agent.domain import (
    AgentResult,
    Claim,
    EvidenceItem,
    ReasoningItem,
    SourceRef,
)
from compliance_agent.orchestrator import ComplianceOrchestrator
from compliance_agent.agents.tooling import (
    ScopeViolationError,
    ToolArgumentError,
    ToolExecutionContext,
    UnknownToolError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class MockLLMProvider:
    """Records calls and returns queued responses without any HTTP activity."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, *, messages, model, response_schema, timeout_seconds) -> str:
        self.calls.append({"messages": messages, "model": model})
        if not self.responses:
            raise AssertionError("MockLLMProvider ran out of queued responses")
        return self.responses.pop(0)


class UnknownToolPlanner:
    """Always requests a tool that does not exist in the registry."""

    planner_type = "unknown_tool_test"

    def next_action(self, state):
        return PlannerAction(
            thought="Deliberately request a tool that is not registered.",
            next_tool="nonexistent_tool_xyz",
            tool_args={},
        )


class RepeatingPlanner:
    """Always requests the same tool to trigger the no-progress guard."""

    planner_type = "repeating_test"

    def next_action(self, state):
        return PlannerAction(
            thought="Repeat the same call intentionally.",
            next_tool="get_alert_context",
            tool_args={},
        )


def _minimal_passing_result(
    *,
    reasoning: list,
    claims: list[Claim] | None = None,
    evidence: list[EvidenceItem] | None = None,
) -> AgentResult:
    default_evidence = [
        EvidenceItem(
            evidence_id="alerts:1001",
            source_ref=SourceRef("alerts", "1001"),
            payload={"alert_id": 1001},
        )
    ]
    default_claims = [
        Claim(
            statement="Alert 1001 is the subject.",
            source_refs=[SourceRef("alerts", "1001")],
        )
    ]
    return AgentResult(
        agent_name="test_agent",
        subject_type="alert",
        subject_id=1001,
        recommendation="investigate",
        confidence=0.6,
        score=50.0,
        reasoning=reasoning,
        claims=claims if claims is not None else default_claims,
        evidence=evidence if evidence is not None else default_evidence,
    )


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------

class Phase12AcceptanceTest(unittest.TestCase):

    def setUp(self) -> None:
        self.source = FakeBankSourceRepository()
        self.registry = build_phase1_tool_registry()
        self.gate = PreScreenGate()

    # -----------------------------------------------------------------------
    # 1. tool schemas reject unbounded args
    # -----------------------------------------------------------------------

    def test_tool_schemas_reject_unbounded_lookback_days(self) -> None:
        """lookback_days above 365 must raise ToolArgumentError."""
        context = ToolExecutionContext(
            source=self.source,
            scope=build_scope_for_alert(self.source, 1003),
        )
        with self.assertRaises(ToolArgumentError):
            self.registry.execute("get_recent_transactions", context, {"lookback_days": 366})
        with self.assertRaises(ToolArgumentError):
            self.registry.execute("compute_behavioral_baseline", context, {"lookback_days": 366})

    def test_tool_schemas_reject_unbounded_max_rows(self) -> None:
        """max_rows above 100 must raise ToolArgumentError."""
        context = ToolExecutionContext(
            source=self.source,
            scope=build_scope_for_alert(self.source, 1003),
        )
        with self.assertRaises(ToolArgumentError):
            self.registry.execute("get_recent_transactions", context, {"max_rows": 101})
        with self.assertRaises(ToolArgumentError):
            self.registry.execute("get_prior_alerts", context, {"max_rows": 200})
        with self.assertRaises(ToolArgumentError):
            self.registry.execute("compute_behavioral_baseline", context, {"max_rows": 101})

    def test_tool_schemas_reject_unbounded_max_hops(self) -> None:
        """max_hops above 4 must raise ToolArgumentError for trace_money_flow."""
        context = ToolExecutionContext(
            source=self.source,
            scope=build_scope_for_alert(self.source, 1003),
        )
        with self.assertRaises(ToolArgumentError):
            self.registry.execute("trace_money_flow", context, {"max_hops": 5})
        with self.assertRaises(ToolArgumentError):
            self.registry.execute("trace_money_flow", context, {"max_hops": 100})

    def test_tool_schemas_accept_exact_upper_bounds(self) -> None:
        """Exact upper-boundary values must not raise ToolArgumentError."""
        context = ToolExecutionContext(
            source=self.source,
            scope=build_scope_for_alert(self.source, 1003),
        )
        obs = self.registry.execute("get_recent_transactions", context, {"lookback_days": 365, "max_rows": 100})
        self.assertIsNotNone(obs)
        obs2 = self.registry.execute("trace_money_flow", context, {"max_hops": 4, "max_rows": 100})
        self.assertIsNotNone(obs2)

    # -----------------------------------------------------------------------
    # 2. planner cannot call unknown tools
    # -----------------------------------------------------------------------

    def test_unknown_tool_raises_controlled_error_from_registry(self) -> None:
        """Direct registry call with an unknown tool name raises UnknownToolError."""
        context = ToolExecutionContext(
            source=self.source,
            scope=build_scope_for_alert(self.source, 1003),
        )
        with self.assertRaises(UnknownToolError):
            self.registry.execute("run_arbitrary_sql", context, {})
        with self.assertRaises(UnknownToolError):
            self.registry.execute("", context, {})

    def test_planner_selecting_unknown_tool_stops_runtime_as_schema_error(self) -> None:
        """ReAct runtime maps a planner-selected unknown tool to SCHEMA_ERROR → investigate."""
        result = ReActRuntime(
            planner=UnknownToolPlanner(),
        ).run_triage(self.source, 1005)

        self.assertEqual(result.recommendation, "investigate")
        self.assertEqual(result.details["react_runtime"]["stop_reason"], SCHEMA_ERROR)

    # -----------------------------------------------------------------------
    # 3. planner cannot read unrelated customer IDs
    # -----------------------------------------------------------------------

    def test_all_forbidden_entity_fields_are_rejected(self) -> None:
        """Every forbidden entity field raises ScopeViolationError at the registry."""
        context = ToolExecutionContext(
            source=self.source,
            scope=build_scope_for_alert(self.source, 1003),
        )
        forbidden = {
            "customer_id": 999999,
            "account_id": 999999,
            "transaction_id": 999999,
            "alert_id": 999999,
            "case_id": 999999,
        }
        for field, value in forbidden.items():
            with self.subTest(field=field):
                with self.assertRaises(ScopeViolationError):
                    self.registry.execute("get_recent_transactions", context, {field: value})

    def test_scope_is_locked_to_alert_customer_id(self) -> None:
        """The execution scope carries only the alert-linked customer, account, and transaction."""
        scope = build_scope_for_alert(self.source, 1003)

        self.assertEqual(scope.customer_id, 503)
        self.assertEqual(scope.account_id, 3003)
        self.assertEqual(scope.transaction_id, 7030)
        self.assertNotIn(999999, scope.allowed_customer_ids)
        self.assertNotIn(999999, scope.allowed_account_ids)

    def test_llm_planner_supplying_entity_id_stops_as_schema_error(self) -> None:
        """LLMPlanner output containing a forbidden entity field must produce SCHEMA_ERROR."""
        provider = MockLLMProvider(
            [
                json.dumps({
                    "thought": "Attempt to read an unrelated customer.",
                    "next_tool": "get_recent_transactions",
                    "tool_args": {"customer_id": 999999},
                    "stop": False,
                })
            ]
        )
        result = ReActRuntime(
            planner=LLMPlanner(provider=provider, model_id="mock-model"),
        ).run_triage(self.source, 1005)

        self.assertEqual(result.details["react_runtime"]["stop_reason"], SCHEMA_ERROR)
        self.assertEqual(result.recommendation, "investigate")

    # -----------------------------------------------------------------------
    # 4. repeated tool call is blocked
    # -----------------------------------------------------------------------

    def test_repeated_tool_call_stops_runtime_as_no_progress(self) -> None:
        """A planner that repeats an identical call must trigger NO_PROGRESS → investigate."""
        result = ReActRuntime(
            config=ReActRuntimeConfig(max_steps=4, max_tool_calls=4),
            planner=RepeatingPlanner(),
        ).run_triage(self.source, 1002)

        self.assertEqual(result.recommendation, "investigate")
        self.assertEqual(result.details["react_runtime"]["stop_reason"], NO_PROGRESS)

    def test_repeated_call_never_produces_false_positive(self) -> None:
        """No-progress stop must not produce likely_false_positive."""
        result = ReActRuntime(
            config=ReActRuntimeConfig(max_steps=6, max_tool_calls=6),
            planner=RepeatingPlanner(),
        ).run_triage(self.source, 1003)

        self.assertNotEqual(result.recommendation, "likely_false_positive")

    # -----------------------------------------------------------------------
    # 5. max steps maps to `investigate`
    # -----------------------------------------------------------------------

    def test_max_steps_exhausted_maps_to_investigate(self) -> None:
        """A loop that exhausts max_steps must recommend investigate, not likely_false_positive."""
        result = ReActRuntime(
            config=ReActRuntimeConfig(max_steps=1, max_tool_calls=5),
        ).run_triage(self.source, 1003)

        self.assertEqual(result.details["react_runtime"]["stop_reason"], MAX_STEPS_EXHAUSTED)
        self.assertEqual(result.recommendation, "investigate")
        self.assertNotEqual(result.recommendation, "likely_false_positive")

    def test_max_tool_calls_exhausted_maps_to_investigate(self) -> None:
        """A loop that exhausts max_tool_calls also maps to investigate."""
        result = ReActRuntime(
            config=ReActRuntimeConfig(max_steps=10, max_tool_calls=1),
        ).run_triage(self.source, 1003)

        self.assertEqual(result.recommendation, "investigate")
        self.assertNotEqual(result.recommendation, "likely_false_positive")

    # -----------------------------------------------------------------------
    # 6. reasoning without source refs fails validation
    # -----------------------------------------------------------------------

    def test_reasoning_item_with_empty_source_refs_fails_validation(self) -> None:
        """A ReasoningItem with no source_refs must produce a validation failure."""
        result = _minimal_passing_result(
            reasoning=[
                ReasoningItem(
                    statement="This statement has no source references at all.",
                    source_refs=[],
                )
            ]
        )
        report = ComplianceValidationAgent().validate(result)

        self.assertEqual(report.status, "failed")
        finding = report.findings[0]
        self.assertEqual(finding.kind, "reasoning")
        self.assertIn("no source references", finding.issue)

    def test_free_text_reasoning_not_structured_fails_validation(self) -> None:
        """Plain-string reasoning (not a ReasoningItem) must fail validation."""
        result = _minimal_passing_result(
            reasoning=["This is legacy free text, not a ReasoningItem."]  # type: ignore[list-item]
        )
        report = ComplianceValidationAgent().validate(result)

        self.assertEqual(report.status, "failed")
        self.assertEqual(report.findings[0].kind, "reasoning")
        self.assertIn("not structured", report.findings[0].issue)

    def test_reasoning_pointing_to_missing_evidence_fails_validation(self) -> None:
        """A ReasoningItem whose source ref is not in evidence must fail validation."""
        result = _minimal_passing_result(
            reasoning=[
                ReasoningItem(
                    statement="This points to a record that was never retrieved.",
                    source_refs=[SourceRef("transactions", "missing-tx-id")],
                )
            ]
        )
        report = ComplianceValidationAgent().validate(result)

        self.assertEqual(report.status, "failed")
        self.assertIn("transactions:missing-tx-id", report.findings[0].issue)

    def test_reasoning_with_valid_source_refs_passes_validation(self) -> None:
        """A ReasoningItem backed by evidence must pass validation."""
        result = _minimal_passing_result(
            reasoning=[
                ReasoningItem(
                    statement="Alert 1001 is the subject of this investigation.",
                    source_refs=[SourceRef("alerts", "1001")],
                )
            ]
        )
        report = ComplianceValidationAgent().validate(result)

        self.assertEqual(report.status, "passed")
        self.assertEqual(report.findings, [])

    # -----------------------------------------------------------------------
    # 7. 9,500 USD high-cash baseline recommends dismiss
    # -----------------------------------------------------------------------

    def test_high_cash_9500_baseline_is_consistent(self) -> None:
        """Alert 1003 (9500 USD cash, 100% cash history) baseline must be consistent."""
        context = ToolExecutionContext(
            source=self.source,
            scope=build_scope_for_alert(self.source, 1003),
        )
        obs = self.registry.execute("compute_behavioral_baseline", context, {})
        features = obs.computed_features

        self.assertEqual(features["baseline_assessment"], "consistent")
        self.assertEqual(features["deviation_points"], 0)
        self.assertGreaterEqual(features["observed_cash_pct"], 90.0)

    def test_high_cash_9500_gate_is_obvious_clear(self) -> None:
        """Alert 1003 pre-screen gate must classify obvious_clear."""
        gate_result = self.gate.run(self.source, 1003)

        self.assertEqual(gate_result.gate_decision, "obvious_clear")
        self.assertEqual(gate_result.recommended_disposition, "likely_false_positive")

    def test_high_cash_9500_end_to_end_recommends_likely_false_positive(self) -> None:
        """End-to-end orchestrator triage of alert 1003 must produce likely_false_positive."""
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        os.remove(path)
        try:
            orchestrator = ComplianceOrchestrator(
                source=self.source,
                sidecar=SidecarStore(path),
            )
            response = orchestrator.triage_alert(1003)

            self.assertEqual(response["result"]["recommendation"], "likely_false_positive")
            self.assertEqual(response["validation"]["status"], "passed")
            self.assertEqual(
                response["result"]["details"]["pre_screen_gate"]["gate_decision"],
                "obvious_clear",
            )
        finally:
            if os.path.exists(path):
                os.remove(path)

    # -----------------------------------------------------------------------
    # 8. 9,500 USD low-cash baseline routes to structuring
    # -----------------------------------------------------------------------

    def test_low_cash_9500_baseline_is_strong_deviation(self) -> None:
        """Alert 1004 (9500 USD cash, 0% cash history) baseline must be strong_deviation."""
        context = ToolExecutionContext(
            source=self.source,
            scope=build_scope_for_alert(self.source, 1004),
        )
        obs = self.registry.execute("compute_behavioral_baseline", context, {})
        features = obs.computed_features

        self.assertEqual(features["baseline_assessment"], "strong_deviation")
        self.assertIn("transaction_type_unseen", features["assessment_factors"])
        self.assertEqual(features["observed_cash_pct"], 0.0)

    def test_low_cash_9500_router_activates_structuring(self) -> None:
        """Alert 1004 typology router must activate the structuring typology."""
        alert_context = self.source.get_alert_context(1004)
        gate_result = self.gate.run(self.source, 1004)
        baseline = gate_result.tool_observations["compute_behavioral_baseline"].computed_features
        route = TypologyRouter().route(
            alert_context,
            baseline_features=baseline,
            pre_screen_signals=gate_result.selected_typology_signals,
        )

        self.assertIn("structuring", route.activated)
        self.assertIn("run_structuring_check", route.registry.names)

    def test_low_cash_9500_end_to_end_escalates(self) -> None:
        """End-to-end orchestrator triage of alert 1004 must escalate."""
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        os.remove(path)
        try:
            orchestrator = ComplianceOrchestrator(
                source=self.source,
                sidecar=SidecarStore(path),
            )
            response = orchestrator.triage_alert(1004)

            self.assertEqual(response["result"]["recommendation"], "escalate")
            self.assertNotEqual(response["result"]["recommendation"], "likely_false_positive")
        finally:
            if os.path.exists(path):
                os.remove(path)

    # -----------------------------------------------------------------------
    # 9. router narrows available tools
    # -----------------------------------------------------------------------

    def test_router_removes_skipped_typology_tools_from_registry(self) -> None:
        """A skipped typology tool must be absent from the routed registry."""
        alert_context = self.source.get_alert_context(1003)
        gate_result = self.gate.run(self.source, 1003)
        baseline = gate_result.tool_observations["compute_behavioral_baseline"].computed_features
        route = TypologyRouter().route(
            alert_context,
            baseline_features=baseline,
            pre_screen_signals=gate_result.selected_typology_signals,
        )

        self.assertIn("geography", route.skipped)
        self.assertNotIn("run_geography_check", route.registry.names)
        self.assertNotIn("run_geography_check", route.allowed_tools)

    def test_executing_skipped_tool_via_routed_registry_raises_error(self) -> None:
        """Calling a skipped tool through the routed registry must raise UnknownToolError."""
        alert_context = self.source.get_alert_context(1003)
        gate_result = self.gate.run(self.source, 1003)
        baseline = gate_result.tool_observations["compute_behavioral_baseline"].computed_features
        route = TypologyRouter().route(
            alert_context,
            baseline_features=baseline,
            pre_screen_signals=gate_result.selected_typology_signals,
        )
        context = ToolExecutionContext(
            source=self.source,
            scope=build_scope_for_alert(self.source, 1003),
        )

        with self.assertRaises(UnknownToolError):
            route.registry.execute("run_geography_check", context, {})

    def test_router_keeps_core_tools_always_available(self) -> None:
        """Core tools must always be present in the routed registry regardless of typology."""
        from compliance_agent.agents.typology_router import CORE_TOOL_NAMES

        alert_context = self.source.get_alert_context(1003)
        gate_result = self.gate.run(self.source, 1003)
        baseline = gate_result.tool_observations["compute_behavioral_baseline"].computed_features
        route = TypologyRouter().route(
            alert_context,
            baseline_features=baseline,
            pre_screen_signals=gate_result.selected_typology_signals,
        )

        for name in CORE_TOOL_NAMES:
            self.assertIn(name, route.registry.names, f"Core tool {name!r} missing from routed registry")

    def test_runtime_only_executes_routed_tools(self) -> None:
        """ReAct runtime steps must not contain any tool that was skipped by the router."""
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        os.remove(path)
        try:
            orchestrator = ComplianceOrchestrator(
                source=self.source,
                sidecar=SidecarStore(path),
            )
            response = orchestrator.triage_alert(1005)
            route = response["result"]["details"]["typology_route"]
            executed = {
                step["tool_name"]
                for step in response["result"]["details"]["react_runtime"]["steps"]
                if step.get("tool_name")
            }
            skipped_tools = {
                tool
                for typology in route["skipped"]
                for tool in (
                    {"structuring": ["run_structuring_check"],
                     "velocity": ["run_velocity_check"],
                     "geography": ["run_geography_check"],
                     "sanctions": ["screen_sanctions_pep"],
                     "graph": ["trace_money_flow"]}.get(typology, [])
                )
            }

            for tool_name in skipped_tools:
                self.assertNotIn(tool_name, executed, f"Skipped tool {tool_name!r} was executed")
        finally:
            if os.path.exists(path):
                os.remove(path)

    # -----------------------------------------------------------------------
    # 10. graph tracing follows allowed edges only
    # -----------------------------------------------------------------------

    def test_graph_tracing_only_expands_scope_via_fetched_transaction_edges(self) -> None:
        """Scope expansion during graph tracing must only use counterparty IDs
        found in fetched transaction records, recorded as trusted_graph_edges."""
        self.source._alert_contexts[1002]["transaction"]["counterparty_account_id"] = 4500
        self.source._graph_accounts[4500] = {
            "account_id": 4500,
            "customer_id": 650,
            "branch_id": 17,
            "account_number": "GRAPH04500",
            "account_type": "business",
            "currency_code": "USD",
            "status": "active",
        }
        self.source._graph_customers[650] = {
            "customer_id": 650,
            "full_name": "Counterparty LLC",
            "risk_level": "medium",
            "kyc_status": "verified",
            "is_active": True,
        }
        self.source._graph_transactions = [
            {
                "transaction_id": 8001,
                "account_id": 3002,
                "counterparty_account_id": 4500,
                "transaction_type": "wire",
                "amount_usd": 10000.0,
                "destination_country": None,
                "created_at": "2026-06-06T10:00:00+00:00",
                "status": "completed",
                "is_flagged": False,
            }
        ]

        scope = build_scope_for_alert(self.source, 1002)
        context = ToolExecutionContext(source=self.source, scope=scope)
        observation, updated_context = self.registry.execute_with_context(
            "trace_money_flow", context, {"max_hops": 2, "max_rows": 20}
        )
        trusted_edges = updated_context.scope.trusted_graph_edges
        trusted_counterparty_ids = {edge.counterparty_account_id for edge in trusted_edges}

        self.assertTrue(observation.computed_features["has_immediate_counterparty"])
        self.assertEqual(trusted_counterparty_ids, {4500})
        self.assertIn(4500, updated_context.scope.allowed_account_ids)
        self.assertNotIn(99999, updated_context.scope.allowed_account_ids)

    def test_graph_tracing_without_counterparty_adds_no_trusted_edges(self) -> None:
        """An alert with no counterparty must not expand scope at all."""
        scope = build_scope_for_alert(self.source, 1003)
        context = ToolExecutionContext(source=self.source, scope=scope)
        observation, updated_context = self.registry.execute_with_context(
            "trace_money_flow", context, {}
        )

        self.assertEqual(observation.facts["paths"], [])
        self.assertEqual(updated_context.scope.trusted_graph_edges, [])
        self.assertEqual(updated_context.scope.allowed_account_ids, {3003})

    # -----------------------------------------------------------------------
    # 11. graph tracing respects max hops
    # -----------------------------------------------------------------------

    def test_graph_tracing_max_hops_1_does_not_reach_second_hop_accounts(self) -> None:
        """With max_hops=1, the traversal must not reach depth-2 accounts."""
        self.source._alert_contexts[1002]["transaction"]["counterparty_account_id"] = 4500
        self.source._graph_accounts.update({
            4500: {
                "account_id": 4500, "customer_id": 650, "branch_id": 1,
                "account_number": "GFWD4500", "account_type": "business",
                "currency_code": "USD", "status": "active",
            },
            4600: {
                "account_id": 4600, "customer_id": 651, "branch_id": 1,
                "account_number": "GFWD4600", "account_type": "business",
                "currency_code": "USD", "status": "active",
            },
        })
        self.source._graph_customers.update({
            650: {"customer_id": 650, "full_name": "Hop1 LLC", "risk_level": "medium",
                  "kyc_status": "verified", "is_active": True},
            651: {"customer_id": 651, "full_name": "Hop2 LLC", "risk_level": "medium",
                  "kyc_status": "verified", "is_active": True},
        })
        self.source._graph_transactions = [
            {
                "transaction_id": 8001,
                "account_id": 3002,
                "counterparty_account_id": 4500,
                "transaction_type": "wire",
                "amount_usd": 10000.0,
                "destination_country": None,
                "created_at": "2026-06-06T10:00:00+00:00",
                "status": "completed",
                "is_flagged": False,
            },
            {
                "transaction_id": 8002,
                "account_id": 4500,
                "counterparty_account_id": 4600,
                "transaction_type": "wire",
                "amount_usd": 9000.0,
                "destination_country": None,
                "created_at": "2026-06-06T11:00:00+00:00",
                "status": "completed",
                "is_flagged": False,
            },
        ]

        context = ToolExecutionContext(
            source=self.source,
            scope=build_scope_for_alert(self.source, 1002),
        )
        obs_1hop = self.registry.execute("trace_money_flow", context, {"max_hops": 1, "max_rows": 20})

        hop_counts = {path["hop_count"] for path in obs_1hop.facts["paths"]}
        self.assertEqual(hop_counts, {1}, "All paths must be at hop depth 1")
        self.assertNotIn(4600, obs_1hop.facts["reached_accounts"])

    def test_graph_tracing_max_hops_2_reaches_second_hop(self) -> None:
        """With max_hops=2, the same fixture must reach the second-hop account."""
        self.source._alert_contexts[1002]["transaction"]["counterparty_account_id"] = 4500
        self.source._graph_accounts.update({
            4500: {
                "account_id": 4500, "customer_id": 650, "branch_id": 1,
                "account_number": "GFWD4500B", "account_type": "business",
                "currency_code": "USD", "status": "active",
            },
            4600: {
                "account_id": 4600, "customer_id": 651, "branch_id": 1,
                "account_number": "GFWD4600B", "account_type": "business",
                "currency_code": "USD", "status": "active",
            },
        })
        self.source._graph_customers.update({
            650: {"customer_id": 650, "full_name": "Hop1 LLC B", "risk_level": "medium",
                  "kyc_status": "verified", "is_active": True},
            651: {"customer_id": 651, "full_name": "Hop2 LLC B", "risk_level": "medium",
                  "kyc_status": "verified", "is_active": True},
        })
        self.source._graph_transactions = [
            {
                "transaction_id": 8001,
                "account_id": 3002,
                "counterparty_account_id": 4500,
                "transaction_type": "wire",
                "amount_usd": 10000.0,
                "destination_country": None,
                "created_at": "2026-06-06T10:00:00+00:00",
                "status": "completed",
                "is_flagged": False,
            },
            {
                "transaction_id": 8002,
                "account_id": 4500,
                "counterparty_account_id": 4600,
                "transaction_type": "wire",
                "amount_usd": 9000.0,
                "destination_country": None,
                "created_at": "2026-06-06T11:00:00+00:00",
                "status": "completed",
                "is_flagged": False,
            },
        ]

        context = ToolExecutionContext(
            source=self.source,
            scope=build_scope_for_alert(self.source, 1002),
        )
        obs_2hop = self.registry.execute("trace_money_flow", context, {"max_hops": 2, "max_rows": 20})

        self.assertIn(4600, obs_2hop.facts["reached_accounts"])
        hop_counts = {path["hop_count"] for path in obs_2hop.facts["paths"]}
        self.assertIn(2, hop_counts)

    def test_graph_row_limit_marks_data_incomplete(self) -> None:
        """When max_rows is hit the observation must be marked incomplete with a limitation."""
        self.source._alert_contexts[1002]["transaction"]["counterparty_account_id"] = 4500
        self.source._graph_accounts[4500] = {
            "account_id": 4500, "customer_id": 650, "branch_id": 1,
            "account_number": "GLIM4500", "account_type": "business",
            "currency_code": "USD", "status": "active",
        }
        self.source._graph_customers[650] = {
            "customer_id": 650, "full_name": "Limit Test LLC", "risk_level": "low",
            "kyc_status": "verified", "is_active": True,
        }
        self.source._graph_transactions = [
            {
                "transaction_id": 8001 + i,
                "account_id": 3002,
                "counterparty_account_id": 4500,
                "transaction_type": "wire",
                "amount_usd": float(1000 + i),
                "destination_country": None,
                "created_at": f"2026-06-06T10:{i:02d}:00+00:00",
                "status": "completed",
                "is_flagged": False,
            }
            for i in range(5)
        ]

        context = ToolExecutionContext(
            source=self.source,
            scope=build_scope_for_alert(self.source, 1002),
        )
        obs = self.registry.execute("trace_money_flow", context, {"max_hops": 2, "max_rows": 2})

        self.assertFalse(obs.data_completeness.complete)
        limitation_codes = {lim.code for lim in obs.limitations}
        self.assertIn("graph_row_limit_reached", limitation_codes)

    # -----------------------------------------------------------------------
    # 12. heuristic planner works with no LLM
    # -----------------------------------------------------------------------

    def test_heuristic_planner_completes_triage_with_no_llm(self) -> None:
        """Full triage via HeuristicPlanner must complete and return a valid AgentResult
        without any LLM configuration or HTTP calls."""
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        os.remove(path)
        try:
            orchestrator = ComplianceOrchestrator(
                source=self.source,
                sidecar=SidecarStore(path),
            )
            # Alert 1005 is ambiguous → enters ReAct runtime with HeuristicPlanner
            response = orchestrator.triage_alert(1005)
            result = response["result"]
            runtime = result["details"]["react_runtime"]

            self.assertEqual(runtime["planner"], "heuristic")
            self.assertIn(result["recommendation"], {"investigate", "escalate", "likely_false_positive"})
            self.assertEqual(response["validation"]["status"], "passed")
            self.assertTrue(runtime["steps"])
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_heuristic_planner_type_attribute_is_heuristic(self) -> None:
        """HeuristicPlanner must have planner_type == 'heuristic'."""
        from compliance_agent.agents.react_runtime import HeuristicPlanner

        planner = HeuristicPlanner()
        self.assertEqual(planner.planner_type, "heuristic")

    def test_heuristic_planner_covers_all_routed_tools_in_order(self) -> None:
        """HeuristicPlanner must request each tool that appears in the routed registry
        exactly once (until the loop completes)."""
        from compliance_agent.agents.react_runtime import HeuristicPlanner, ReActState

        source = FakeBankSourceRepository()
        alert_context = source.get_alert_context(1001)
        route = TypologyRouter().route(alert_context)
        planner = HeuristicPlanner()
        observed_tools: list[str] = []

        observations: dict = {}
        for _ in range(20):
            state = ReActState(
                alert_context=alert_context,
                route=route,
                observations=observations,
                tool_call_count=len(observed_tools),
                step_number=len(observed_tools) + 1,
            )
            action = planner.next_action(state)
            if action.stop:
                break
            assert action.next_tool is not None
            self.assertIn(action.next_tool, route.registry.names)
            self.assertNotIn(action.next_tool, observed_tools)
            observations[action.next_tool] = object()
            observed_tools.append(action.next_tool)

    # -----------------------------------------------------------------------
    # 13. LLM planner contract is tested with mocked responses only
    # -----------------------------------------------------------------------

    def test_llm_planner_uses_mocked_provider_no_live_http(self) -> None:
        """LLMPlanner must call the injected provider, not make live HTTP requests."""
        provider = MockLLMProvider(
            [
                json.dumps({
                    "thought": "Fetch baseline facts first.",
                    "next_tool": "compute_behavioral_baseline",
                    "tool_args": {"lookback_days": 180},
                    "stop": False,
                }),
                json.dumps({
                    "thought": "Insufficient evidence; stop safely.",
                    "next_tool": None,
                    "tool_args": {},
                    "stop": True,
                }),
            ]
        )
        runtime = ReActRuntime(
            planner=LLMPlanner(provider=provider, model_id="test-mock-model"),
        )

        result = runtime.run_triage(self.source, 1005)

        self.assertGreaterEqual(len(provider.calls), 1)
        self.assertEqual(result.details["react_runtime"]["planner"], "llm")
        self.assertEqual(
            result.details["react_runtime"]["planner_metadata"]["model_id"],
            "test-mock-model",
        )
        self.assertIn(result.recommendation, {"investigate", "escalate", "likely_false_positive"})

    def test_llm_planner_malformed_json_maps_to_schema_error(self) -> None:
        """Non-JSON output from the LLM provider must produce SCHEMA_ERROR → investigate."""
        result = ReActRuntime(
            planner=LLMPlanner(
                provider=MockLLMProvider(["this is not json"]),
                model_id="test-mock-model",
            ),
        ).run_triage(self.source, 1005)

        self.assertEqual(result.details["react_runtime"]["stop_reason"], SCHEMA_ERROR)
        self.assertEqual(result.recommendation, "investigate")

    def test_llm_planner_extra_confidence_field_rejected_as_schema_error(self) -> None:
        """LLM output containing a confidence field (self-certification) must fail."""
        from compliance_agent.agents.react_runtime import ReActState
        from compliance_agent.agents.llm_planner import LLMPlanner
        from compliance_agent.agents.react_runtime import PlannerOutputError

        provider = MockLLMProvider(
            [
                json.dumps({
                    "thought": "Self-certify confidence.",
                    "next_tool": "compute_behavioral_baseline",
                    "tool_args": {},
                    "stop": False,
                    "confidence": 0.99,
                })
            ]
        )
        planner = LLMPlanner(provider=provider, model_id="test-mock-model")
        alert_context = self.source.get_alert_context(1005)
        route = TypologyRouter().route(alert_context)
        state = ReActState(
            alert_context=alert_context,
            route=route,
            observations={},
            tool_call_count=0,
            step_number=1,
        )

        with self.assertRaises(PlannerOutputError):
            planner.next_action(state)

    def test_llm_planner_stop_action_requires_no_tool(self) -> None:
        """A stop=True action must not include next_tool and must not try to call anything."""
        provider = MockLLMProvider(
            [
                json.dumps({
                    "thought": "Stopping immediately.",
                    "next_tool": None,
                    "tool_args": {},
                    "stop": True,
                })
            ]
        )
        result = ReActRuntime(
            planner=LLMPlanner(provider=provider, model_id="test-mock-model"),
        ).run_triage(self.source, 1005)

        self.assertEqual(result.details["react_runtime"]["tool_call_count"], 0)
        self.assertIn(result.recommendation, {"investigate", "escalate"})

    def test_llm_planner_cannot_select_tool_outside_routed_registry(self) -> None:
        """LLM selecting a tool not in the routed registry must produce SCHEMA_ERROR."""
        provider = MockLLMProvider(
            [
                json.dumps({
                    "thought": "Try a tool skipped by the router.",
                    "next_tool": "run_geography_check",
                    "tool_args": {},
                    "stop": False,
                })
            ]
        )
        # Alert 1003 has geography skipped (no destination country)
        result = ReActRuntime(
            planner=LLMPlanner(provider=provider, model_id="test-mock-model"),
        ).run_triage(self.source, 1003)

        self.assertEqual(result.details["react_runtime"]["stop_reason"], SCHEMA_ERROR)
        self.assertNotEqual(result.recommendation, "likely_false_positive")


if __name__ == "__main__":
    unittest.main()
