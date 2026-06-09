from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
TESTS = os.path.dirname(__file__)
for path in (SRC, ROOT, TESTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from compliance_agent.adapters.sidecar_store import SidecarStore
from compliance_agent.agents.live_mcp_demo import (
    BUDGET_EXHAUSTED,
    COMPLETED,
    CRITICAL_SIGNAL_FOUND,
    InProcessMCPToolClient,
    INSUFFICIENT_EVIDENCE,
    LiveMCPAgent,
    LiveMCPAgentConfig,
    NO_PROGRESS,
    SCHEMA_ERROR,
    TIMEOUT,
    TOOL_DENIED,
    TOOL_ERROR,
)
from compliance_agent.contracts.phase1 import (
    AgentRunRequest,
    DataCompleteness,
    MCPResponseEnvelope,
    PolicyDecision,
    RuntimeBounds,
    SubjectRef,
    ToolExecutionScope,
)
from compliance_agent.contracts.tool_catalog import PHASE1_TOOL_NAMES
from mcp_server.service import ReferenceMCPTools
from test_phase1_mcp_server import FakeReferenceRepository


class RuntimeMockProvider:
    def __init__(self, responses: list[dict | str | BaseException]) -> None:
        self.responses = list(responses)
        self.calls = []

    def complete(self, *, messages, model, response_schema, timeout_seconds) -> str:
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "response_schema": response_schema,
                "timeout_seconds": timeout_seconds,
            }
        )
        if not self.responses:
            raise AssertionError("No mock LLM response queued")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if isinstance(response, str):
            return response
        return json.dumps(response)


class StaticResponseToolClient:
    def __init__(self, response: MCPResponseEnvelope) -> None:
        self.response = response
        self.calls = []

    def list_tools(self) -> list[str]:
        return list(PHASE1_TOOL_NAMES)

    def call_tool(self, tool_name, request):
        self.calls.append({"tool_name": tool_name, "request": request})
        return self.response


class RaisingToolClient:
    def list_tools(self) -> list[str]:
        return list(PHASE1_TOOL_NAMES)

    def call_tool(self, tool_name, request):
        raise RuntimeError("reference MCP tool failed")


class Phase2LiveMCPRuntimeTest(unittest.TestCase):
    def _agent(
        self,
        responses: list[dict | str | BaseException],
        *,
        tool_client=None,
        bounds: RuntimeBounds | None = None,
    ) -> LiveMCPAgent:
        return LiveMCPAgent(
            provider=RuntimeMockProvider(responses),
            tool_client=tool_client
            or InProcessMCPToolClient(ReferenceMCPTools(FakeReferenceRepository())),
            config=LiveMCPAgentConfig(
                model_id="mock-live-model",
                runtime_bounds=bounds or RuntimeBounds(),
            ),
        )

    def _request(
        self,
        *,
        alert_id: int = 1003,
        customer_id: int = 503,
        account_id: int = 3003,
        transaction_id: int = 7030,
        bounds: RuntimeBounds | None = None,
    ) -> AgentRunRequest:
        return AgentRunRequest(
            tenant_id="demo-bank",
            officer_id="officer-123",
            purpose="triage",
            subject=SubjectRef(alert_id=alert_id, customer_id=customer_id),
            scope=ToolExecutionScope(
                allowed_customer_ids=[customer_id],
                allowed_account_ids=[account_id],
                allowed_transaction_ids=[transaction_id],
                allowed_case_ids=[],
            ),
            runtime_bounds=bounds or RuntimeBounds(max_steps=5, max_tool_calls=5),
        )

    def _clean_success_responses(self) -> list[dict]:
        return [
            {
                "thought": "Get the rule before baseline comparison.",
                "hypothesis": "Rule context is needed.",
                "next_tool": "get_compliance_rule",
                "tool_args": {},
                "stop": False,
            },
            {
                "thought": "Compare the transaction to customer behavior.",
                "hypothesis": "If baseline is consistent this may be a false positive.",
                "next_tool": "get_behavioral_baseline",
                "tool_args": {"lookback_days": 180},
                "stop": False,
            },
            {
                "thought": "Evidence is sufficient for a human-review proposal.",
                "hypothesis": "Baseline is consistent and no hard red flag is observed.",
                "next_tool": None,
                "tool_args": {},
                "stop": True,
            },
        ]

    def _assert_terminal_fields(self, proposal, *, state: str, reason: str) -> None:
        self.assertEqual(proposal.terminal_state, state)
        self.assertEqual(proposal.stop_reason, reason)
        self.assertTrue(proposal.runtime_events)
        self.assertEqual(proposal.runtime_events[-1].state, state)
        self.assertEqual(proposal.runtime_events[-1].stop_reason, reason)

    def test_successful_run_emits_ordered_runtime_events_to_proposed(self) -> None:
        proposal = self._agent(self._clean_success_responses()).run(self._request())

        states = [event.state for event in proposal.runtime_events]
        sequence_numbers = [event.sequence_number for event in proposal.runtime_events]

        self.assertEqual(states[0], "created")
        self.assertIn("context_loaded", states)
        self.assertIn("planning", states)
        self.assertIn("tool_requested", states)
        self.assertIn("tool_executed", states)
        self.assertIn("observing", states)
        self.assertIn("revising", states)
        self.assertEqual(states[-2], "validating")
        self.assertEqual(states[-1], "proposed")
        self.assertEqual(sequence_numbers, list(range(1, len(sequence_numbers) + 1)))
        self._assert_terminal_fields(proposal, state="proposed", reason=COMPLETED)

    def test_persisted_proposal_contains_replayable_runtime_events(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        os.unlink(path)
        try:
            sidecar = SidecarStore(path)
            result = self._agent(self._clean_success_responses()).run_and_persist(
                self._request(),
                sidecar,
            )
            stored = sidecar.get_run(result["run_id"])
            trace = sidecar.get_trace(result["run_id"])
        finally:
            if os.path.exists(path):
                os.remove(path)

        proposal = result["proposal"]
        self.assertTrue(proposal["runtime_events"])
        self.assertEqual(proposal["runtime_events"][-1]["state"], "proposed")
        assert stored is not None
        output = stored["output"]
        self.assertTrue(output["details"]["phase1_proposal"]["runtime_events"])
        self.assertTrue(output["details"]["react_runtime"]["events"])
        assert trace is not None
        self.assertTrue(trace["runtime_events"])
        self.assertEqual(trace["terminal_state"], "proposed")
        self.assertEqual(trace["stop_reason"], COMPLETED)

    def test_malformed_planner_json_fails_safe_with_schema_error(self) -> None:
        proposal = self._agent(["not json"]).run(self._request())

        self.assertEqual(proposal.recommendation, "needs_investigation")
        self._assert_terminal_fields(proposal, state="failed_safe", reason=SCHEMA_ERROR)

    def test_repeated_tool_call_produces_no_progress_and_never_false_positive(self) -> None:
        repeated_tool = {
            "thought": "Get the rule again.",
            "hypothesis": "Repeating the same call should be blocked.",
            "next_tool": "get_compliance_rule",
            "tool_args": {},
            "stop": False,
        }
        proposal = self._agent(
            [
                {
                    "thought": "Get the rule.",
                    "hypothesis": "Rule context is needed.",
                    "next_tool": "get_compliance_rule",
                    "tool_args": {},
                    "stop": False,
                },
                repeated_tool,
            ]
        ).run(self._request())

        self.assertEqual(proposal.recommendation, "needs_investigation")
        self.assertNotEqual(proposal.recommendation, "likely_false_positive")
        self._assert_terminal_fields(proposal, state="failed_safe", reason=NO_PROGRESS)

    def test_tool_denial_fails_safe_to_needs_investigation(self) -> None:
        denied = MCPResponseEnvelope(
            status="denied",
            facts={},
            source_refs=[],
            data_completeness=DataCompleteness(complete=False, missing_segments=["denied"]),
            limitations=["denied for test"],
            audit_id="audit-denied",
            policy_decisions=[
                PolicyDecision(
                    decision="deny",
                    policy="test_policy",
                    reason="test denial",
                )
            ],
        )
        proposal = self._agent(
            [
                {
                    "thought": "Request a tool.",
                    "hypothesis": "Tool may be denied.",
                    "next_tool": "get_customer_profile",
                    "tool_args": {},
                    "stop": False,
                }
            ],
            tool_client=StaticResponseToolClient(denied),
        ).run(self._request())

        self.assertEqual(proposal.recommendation, "needs_investigation")
        self._assert_terminal_fields(proposal, state="failed_safe", reason=TOOL_DENIED)

    def test_tool_error_fails_safe_to_needs_investigation(self) -> None:
        proposal = self._agent(
            [
                {
                    "thought": "Request a tool.",
                    "hypothesis": "Tool may fail.",
                    "next_tool": "get_customer_profile",
                    "tool_args": {},
                    "stop": False,
                }
            ],
            tool_client=RaisingToolClient(),
        ).run(self._request())

        self.assertEqual(proposal.recommendation, "needs_investigation")
        self._assert_terminal_fields(proposal, state="failed_safe", reason=TOOL_ERROR)

    def test_tool_call_budget_exhaustion_fails_safe(self) -> None:
        bounds = RuntimeBounds(max_steps=5, max_tool_calls=1)
        proposal = self._agent(
            self._clean_success_responses(),
            bounds=bounds,
        ).run(self._request(bounds=bounds))

        self.assertEqual(proposal.recommendation, "needs_investigation")
        self._assert_terminal_fields(
            proposal,
            state="failed_safe",
            reason=BUDGET_EXHAUSTED,
        )

    def test_step_budget_exhaustion_fails_safe(self) -> None:
        bounds = RuntimeBounds(max_steps=1, max_tool_calls=5)
        proposal = self._agent(
            self._clean_success_responses(),
            bounds=bounds,
        ).run(self._request(bounds=bounds))

        self.assertEqual(proposal.recommendation, "needs_investigation")
        self._assert_terminal_fields(
            proposal,
            state="failed_safe",
            reason=BUDGET_EXHAUSTED,
        )

    def test_timeout_fails_safe_to_needs_investigation(self) -> None:
        proposal = self._agent([TimeoutError("planner timeout")]).run(self._request())

        self.assertEqual(proposal.recommendation, "needs_investigation")
        self._assert_terminal_fields(proposal, state="failed_safe", reason=TIMEOUT)

    def test_critical_graph_signal_maps_to_escalation(self) -> None:
        proposal = self._agent(
            [
                {
                    "thought": "Get baseline first.",
                    "hypothesis": "Baseline alone may not resolve graph risk.",
                    "next_tool": "get_behavioral_baseline",
                    "tool_args": {},
                    "stop": False,
                },
                {
                    "thought": "Trace the counterparty graph.",
                    "hypothesis": "Graph evidence may reveal linked risk.",
                    "next_tool": "trace_counterparty_graph",
                    "tool_args": {"max_hops": 2},
                    "stop": False,
                },
            ]
        ).run(
            self._request(
                alert_id=1006,
                customer_id=506,
                account_id=3006,
                transaction_id=7060,
            )
        )

        self.assertEqual(proposal.recommendation, "escalate")
        self._assert_terminal_fields(
            proposal,
            state="proposed",
            reason=CRITICAL_SIGNAL_FOUND,
        )

    def test_stop_without_evidence_records_insufficient_evidence(self) -> None:
        proposal = self._agent(
            [
                {
                    "thought": "Stop too early.",
                    "hypothesis": "No evidence was gathered.",
                    "next_tool": None,
                    "tool_args": {},
                    "stop": True,
                }
            ]
        ).run(self._request())

        self.assertEqual(proposal.recommendation, "needs_investigation")
        self._assert_terminal_fields(
            proposal,
            state="failed_safe",
            reason=INSUFFICIENT_EVIDENCE,
        )


if __name__ == "__main__":
    unittest.main()
