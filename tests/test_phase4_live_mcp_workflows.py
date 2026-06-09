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
    InProcessMCPToolClient,
    LiveMCPAgent,
    LiveMCPAgentConfig,
)
from compliance_agent.agents.live_mcp_workflows import LiveMCPWorkflowAgent
from compliance_agent.agents.validation import ComplianceValidationAgent
from compliance_agent.contracts.phase1 import (
    AgentRunRequest,
    DataCompleteness,
    MCPResponseEnvelope,
    MCPSourceRef,
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


class ScriptedToolClient:
    def __init__(self, responses: dict[str, MCPResponseEnvelope]) -> None:
        self.responses = responses
        self.calls = []

    def list_tools(self) -> list[str]:
        return list(PHASE1_TOOL_NAMES)

    def call_tool(self, tool_name, request):
        self.calls.append({"tool_name": tool_name, "request": request})
        return self.responses[tool_name]


def _response(
    tool_name: str,
    facts: dict,
    refs: list[tuple[str, str, list[str]]],
) -> MCPResponseEnvelope:
    return MCPResponseEnvelope(
        status="ok",
        facts=facts,
        source_refs=[
            MCPSourceRef(
                entity_type=entity_type,
                entity_id=entity_id,
                field_names=fields,
                retrieved_at="2026-06-09T00:00:00+00:00",
            )
            for entity_type, entity_id, fields in refs
        ],
        data_completeness=DataCompleteness(complete=True, rows_returned=1, rows_requested=1),
        audit_id=f"audit-{tool_name}",
        policy_decisions=[
            PolicyDecision(
                decision="allow",
                policy="test_policy",
                reason="test allow",
            )
        ],
    )


class Phase4LiveMCPWorkflowTest(unittest.TestCase):
    def _workflow_agent(
        self,
        responses: list[dict | str | BaseException],
        *,
        tool_client=None,
    ) -> tuple[LiveMCPWorkflowAgent, RuntimeMockProvider]:
        provider = RuntimeMockProvider(responses)
        live_agent = LiveMCPAgent(
            provider=provider,
            tool_client=tool_client
            or InProcessMCPToolClient(ReferenceMCPTools(FakeReferenceRepository())),
            config=LiveMCPAgentConfig(
                model_id="mock-live-model",
                runtime_bounds=RuntimeBounds(max_steps=6, max_tool_calls=6),
            ),
        )
        return LiveMCPWorkflowAgent(live_agent), provider

    def _alert_request(
        self,
        *,
        alert_id: int = 1003,
        customer_id: int = 503,
        account_id: int = 3003,
        transaction_id: int = 7030,
        purpose: str = "triage",
    ) -> AgentRunRequest:
        return AgentRunRequest(
            tenant_id="demo-bank",
            officer_id="officer-123",
            purpose=purpose,
            subject=SubjectRef(alert_id=alert_id, customer_id=customer_id),
            scope=ToolExecutionScope(
                allowed_customer_ids=[customer_id],
                allowed_account_ids=[account_id],
                allowed_transaction_ids=[transaction_id],
                allowed_case_ids=[9001],
            ),
            runtime_bounds=RuntimeBounds(max_steps=6, max_tool_calls=6),
        )

    def test_triage_workflow_uses_live_planner_payload(self) -> None:
        workflow, provider = self._workflow_agent(
            [
                {
                    "thought": "Get rule context.",
                    "hypothesis": "Rule context is needed for triage.",
                    "next_tool": "get_compliance_rule",
                    "tool_args": {},
                    "stop": False,
                },
                {
                    "thought": "Compare baseline.",
                    "hypothesis": "Baseline consistency can support a low-noise proposal.",
                    "next_tool": "get_behavioral_baseline",
                    "tool_args": {"lookback_days": 180},
                    "stop": False,
                },
                {
                    "thought": "Stop with evidence.",
                    "hypothesis": "Evidence is sufficient.",
                    "next_tool": None,
                    "tool_args": {},
                    "stop": True,
                },
            ]
        )

        output = workflow.run_triage(self._alert_request())

        self.assertEqual(output.result.agent_name, "triage_agent")
        self.assertEqual(output.result.details["phase4_live_mcp"]["workflow"], "triage")
        self.assertEqual(len(provider.calls), 3)
        payload = json.loads(provider.calls[0]["messages"][1]["content"])
        self.assertEqual(payload["purpose"], "triage")
        self.assertTrue(output.result.details["material_output_requires_human_review"])

    def test_investigation_workflow_recommends_open_case_and_persists_trail(self) -> None:
        workflow, _provider = self._workflow_agent(
            [
                {
                    "thought": "Get rule context first.",
                    "hypothesis": "Rule type will identify initial typology.",
                    "next_tool": "get_compliance_rule",
                    "tool_args": {},
                    "stop": False,
                },
                {
                    "thought": "Trace graph risk.",
                    "hypothesis": "Graph evidence may reveal linked high-risk endpoints.",
                    "next_tool": "trace_counterparty_graph",
                    "tool_args": {"max_hops": 2},
                    "stop": False,
                },
            ]
        )
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        os.unlink(path)
        try:
            sidecar = SidecarStore(path)
            response = workflow.run_and_persist(
                "investigation",
                self._alert_request(
                    alert_id=1006,
                    customer_id=506,
                    account_id=3006,
                    transaction_id=7060,
                    purpose="investigation",
                ),
                sidecar,
            )
            stored = sidecar.get_run(response["run_id"])
        finally:
            if os.path.exists(path):
                os.remove(path)

        self.assertEqual(response["result"]["recommendation"], "open_case")
        self.assertEqual(response["validation"]["status"], "passed")
        self.assertTrue(response["result"]["details"]["human_required"])
        assert stored is not None
        self.assertTrue(stored["output"]["details"]["phase4_live_mcp"]["trace"])

    def test_risk_scoring_uses_llm_for_evidence_and_deterministic_score_policy(self) -> None:
        tool_client = ScriptedToolClient(
            {
                "get_customer_profile": _response(
                    "get_customer_profile",
                    {
                        "customer": {
                            "customer_id": 503,
                            "risk_level": "critical",
                            "kyc_status": "pending",
                        }
                    },
                    [("customer", "503", ["customer_id", "risk_level", "kyc_status"])],
                ),
                "get_prior_alerts": _response(
                    "get_prior_alerts",
                    {
                        "prior_alerts": [
                            {"alert_id": 1003, "severity": "critical"},
                        ]
                    },
                    [("alert", "1003", ["alert_id", "severity"])],
                ),
                "screen_sanctions_pep": _response(
                    "screen_sanctions_pep",
                    {
                        "sanctions_matches": [],
                        "pep_matches": [],
                    },
                    [("customer", "503", ["customer_id"])],
                ),
            }
        )
        workflow, provider = self._workflow_agent(
            [
                {
                    "thought": "Gather profile.",
                    "hypothesis": "Customer profile gives base risk.",
                    "next_tool": "get_customer_profile",
                    "tool_args": {},
                    "stop": False,
                },
                {
                    "thought": "Gather alert history.",
                    "hypothesis": "Prior alerts may increase risk.",
                    "next_tool": "get_prior_alerts",
                    "tool_args": {"max_rows": 10},
                    "stop": False,
                },
                {
                    "thought": "Gather screening evidence.",
                    "hypothesis": "Screening can add hard risk factors.",
                    "next_tool": "screen_sanctions_pep",
                    "tool_args": {},
                    "stop": False,
                },
                {
                    "thought": "Stop after evidence.",
                    "hypothesis": "Deterministic policy must compute the final score.",
                    "next_tool": None,
                    "tool_args": {},
                    "stop": True,
                },
            ],
            tool_client=tool_client,
        )

        output = workflow.run_risk_scoring(
            self._alert_request(purpose="risk_scoring")
        )
        validation = ComplianceValidationAgent().validate(output.result)

        self.assertEqual(validation.status, "passed")
        self.assertEqual(output.result.recommendation, "record_risk_score_for_human_review")
        self.assertEqual(output.result.details["score_source"], "deterministic_policy")
        self.assertEqual(output.result.details["policy_version"], "phase4_live_mcp_workflow_policy_v1")
        self.assertEqual(output.result.score, 98.0)
        self.assertTrue(output.result.details["human_required"])
        self.assertEqual(len(provider.calls), 4)

    def test_sar_draft_is_evidence_grounded_and_never_files(self) -> None:
        tool_client = ScriptedToolClient(
            {
                "get_customer_profile": _response(
                    "get_customer_profile",
                    {"customer": {"customer_id": 503, "full_name": "Cash Retail LLC"}},
                    [("customer", "503", ["customer_id", "full_name"])],
                ),
                "get_case_history": _response(
                    "get_case_history",
                    {
                        "cases": [{"case_id": 9001, "customer_id": 503, "status": "open"}],
                        "linked_alerts": [{"alert_id": 1003, "case_id": 9001}],
                    },
                    [
                        ("case", "9001", ["case_id", "customer_id", "status"]),
                        ("alert", "1003", ["alert_id", "case_id"]),
                    ],
                ),
                "get_transaction_history": _response(
                    "get_transaction_history",
                    {"transactions": [{"transaction_id": 7030, "amount_usd": 9500.0}]},
                    [("transaction", "7030", ["transaction_id", "amount_usd"])],
                ),
            }
        )
        workflow, _provider = self._workflow_agent(
            [
                {
                    "thought": "Gather customer facts.",
                    "hypothesis": "Customer identity is required for the draft.",
                    "next_tool": "get_customer_profile",
                    "tool_args": {},
                    "stop": False,
                },
                {
                    "thought": "Gather case facts.",
                    "hypothesis": "Case history anchors the draft.",
                    "next_tool": "get_case_history",
                    "tool_args": {"max_rows": 10},
                    "stop": False,
                },
                {
                    "thought": "Gather transaction facts.",
                    "hypothesis": "Transactions support factual narrative sentences.",
                    "next_tool": "get_transaction_history",
                    "tool_args": {"max_rows": 10},
                    "stop": False,
                },
                {
                    "thought": "Stop after evidence.",
                    "hypothesis": "Draft can be assembled from retrieved facts.",
                    "next_tool": None,
                    "tool_args": {},
                    "stop": True,
                },
            ],
            tool_client=tool_client,
        )
        request = AgentRunRequest(
            tenant_id="demo-bank",
            officer_id="officer-123",
            purpose="sar_drafting",
            subject=SubjectRef(case_id=9001, customer_id=503),
            scope=ToolExecutionScope(
                allowed_customer_ids=[503],
                allowed_account_ids=[],
                allowed_transaction_ids=[],
                allowed_case_ids=[9001],
            ),
            runtime_bounds=RuntimeBounds(max_steps=6, max_tool_calls=6),
        )

        output = workflow.draft_sar(
            request,
            officer_context="Officer noted repeated cash deposits near reporting thresholds.",
        )
        validation = ComplianceValidationAgent().validate(output.result)

        self.assertEqual(validation.status, "passed")
        self.assertEqual(output.result.recommendation, "draft_for_human_review")
        self.assertIn("HUMAN REVIEW REQUIRED", output.result.details["narrative"])
        self.assertTrue(output.result.details["sar_confidential"])
        self.assertTrue(output.result.details["never_file_autonomously"])
        self.assertTrue(output.result.details["sentence_evidence"])
        self.assertEqual(output.result.details["missing_required_fields"], [])


if __name__ == "__main__":
    unittest.main()
