from __future__ import annotations

import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
TESTS = os.path.dirname(__file__)
for path in (SRC, ROOT, TESTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from compliance_agent.agents.live_mcp_demo import (
    InProcessMCPToolClient,
    LiveMCPAgent,
    LiveMCPAgentConfig,
)
from compliance_agent.contracts.phase1 import (
    AgentRunRequest,
    RuntimeBounds,
    SubjectRef,
    ToolExecutionScope,
)
from mcp_server.service import ReferenceMCPTools
from test_phase1_mcp_server import FakeReferenceRepository


class MockLLMProvider:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = [json.dumps(item) for item in responses]
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
        return self.responses.pop(0)


class Phase1LiveMCPAgentTest(unittest.TestCase):
    def _agent(self, responses: list[dict]) -> LiveMCPAgent:
        return LiveMCPAgent(
            provider=MockLLMProvider(responses),
            tool_client=InProcessMCPToolClient(ReferenceMCPTools(FakeReferenceRepository())),
            config=LiveMCPAgentConfig(model_id="mock-live-model"),
        )

    def _request(self, *, alert_id: int, customer_id: int, account_id: int, transaction_id: int) -> AgentRunRequest:
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
            runtime_bounds=RuntimeBounds(max_steps=5, max_tool_calls=5),
        )

    def test_clean_alert_uses_two_tools_revises_hypothesis_and_proposes_false_positive(self) -> None:
        agent = self._agent(
            [
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
        )

        proposal = agent.run(
            self._request(alert_id=1003, customer_id=503, account_id=3003, transaction_id=7030)
        )

        self.assertEqual(proposal.recommendation, "likely_false_positive")
        self.assertEqual(proposal.validation_status.status, "passed")
        self.assertGreaterEqual(len(proposal.tool_calls), 2)
        self.assertGreaterEqual(len({step.hypothesis_after for step in proposal.trace if step.hypothesis_after}), 2)
        self.assertTrue(proposal.factual_claims)

    def test_graph_ambiguous_alert_requires_graph_trace_before_escalation(self) -> None:
        agent = self._agent(
            [
                {
                    "thought": "Get baseline first.",
                    "hypothesis": "Baseline alone may not resolve graph risk.",
                    "next_tool": "get_behavioral_baseline",
                    "tool_args": {},
                    "stop": False,
                },
                {
                    "thought": "Trace the counterparty graph because the wire has a counterparty.",
                    "hypothesis": "Graph evidence may reveal linked risk.",
                    "next_tool": "trace_counterparty_graph",
                    "tool_args": {"max_hops": 2},
                    "stop": False,
                },
                {
                    "thought": "Graph evidence has a hard red flag.",
                    "hypothesis": "High-risk graph endpoint requires escalation review.",
                    "next_tool": None,
                    "tool_args": {},
                    "stop": True,
                },
            ]
        )

        proposal = agent.run(
            self._request(alert_id=1006, customer_id=506, account_id=3006, transaction_id=7060)
        )

        self.assertEqual(proposal.recommendation, "escalate")
        self.assertIn("trace_counterparty_graph", [call.tool_name for call in proposal.tool_calls])
        self.assertEqual(proposal.validation_status.status, "passed")

    def test_forbidden_llm_entity_id_fails_safe_to_needs_investigation(self) -> None:
        agent = self._agent(
            [
                {
                    "thought": "Try to override scope.",
                    "hypothesis": "Bad planner action.",
                    "next_tool": "get_transaction_history",
                    "tool_args": {"customer_id": 999},
                    "stop": False,
                }
            ]
        )

        proposal = agent.run(
            self._request(alert_id=1003, customer_id=503, account_id=3003, transaction_id=7030)
        )

        self.assertEqual(proposal.recommendation, "needs_investigation")
        self.assertIn("failed_safe", {step.status for step in proposal.trace})


if __name__ == "__main__":
    unittest.main()
