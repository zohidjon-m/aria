from __future__ import annotations

import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
for path in (SRC, ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from compliance_agent.contracts.phase3 import (
    Phase3AuditEvent,
    Phase3MCPRequestEnvelope,
    Phase3MCPResponseEnvelope,
    Phase3PolicyDecision,
    Phase3ScopeExpansionPolicy,
    Phase3ToolMetadata,
)
from compliance_agent.contracts.tool_catalog import PHASE1_TOOL_NAMES
from compliance_agent.contracts.tool_catalog_phase3 import (
    PHASE3_TOOL_CATALOG,
    PHASE3_TOOL_NAMES,
    PHASE3_TOOL_REGISTRY_VERSION,
)


EXPECTED_PHASE3_TOOL_NAMES = {
    "get_customer_profile",
    "get_transaction_history",
    "get_behavioral_baseline",
    "get_prior_alerts",
    "get_case_history",
    "trace_counterparty_graph",
    "screen_sanctions_pep",
    "get_similar_alerts",
    "get_compliance_rule",
    "get_officer_permissions",
    "add_alert_comment",
    "open_case",
    "link_alert_to_case",
    "export_human_decision",
    "record_agent_trace",
    "propose_alert_disposition",
    "store_agent_risk_score",
    "draft_regulatory_report",
    "record_evaluation_result",
}

BANK_WRITE_TOOLS = {
    "add_alert_comment",
    "open_case",
    "link_alert_to_case",
    "export_human_decision",
}

SIDECAR_WRITE_OR_PROPOSAL_TOOLS = {
    "record_agent_trace",
    "propose_alert_disposition",
    "store_agent_risk_score",
    "draft_regulatory_report",
    "record_evaluation_result",
}


class Phase3MCPContractsTest(unittest.TestCase):
    def test_phase3_catalog_contains_exact_v2_tool_set(self) -> None:
        self.assertEqual(set(PHASE3_TOOL_NAMES), EXPECTED_PHASE3_TOOL_NAMES)
        self.assertEqual(len(PHASE3_TOOL_CATALOG), 19)
        self.assertEqual(PHASE3_TOOL_REGISTRY_VERSION, "phase3_bank_mcp_contract_v1")

    def test_every_tool_has_required_metadata_schema_and_example(self) -> None:
        for tool in PHASE3_TOOL_CATALOG:
            with self.subTest(tool=tool.name):
                self.assertTrue(tool.description)
                self.assertTrue(tool.category)
                self.assertTrue(tool.purpose)
                self.assertTrue(tool.side_effect_type)
                self.assertTrue(tool.execution_owner)
                self.assertIsInstance(tool.required_permissions, list)
                self.assertTrue(tool.deterministic_policy_required)
                self.assertTrue(tool.idempotency_required)
                self.assertTrue(tool.args_schema)
                self.assertTrue(tool.response_schema)
                self.assertTrue(tool.audit_outcomes)
                self.assertTrue(tool.examples)

    def test_bank_writes_and_sidecar_tools_are_separate_and_policy_gated(self) -> None:
        by_name = {tool.name: tool for tool in PHASE3_TOOL_CATALOG}

        self.assertEqual(
            {name for name, tool in by_name.items() if tool.category == "bank_write"},
            BANK_WRITE_TOOLS,
        )
        self.assertEqual(
            {
                name
                for name, tool in by_name.items()
                if tool.category in {"sidecar_write", "sidecar_proposal"}
            },
            SIDECAR_WRITE_OR_PROPOSAL_TOOLS,
        )

        for name in BANK_WRITE_TOOLS | SIDECAR_WRITE_OR_PROPOSAL_TOOLS:
            with self.subTest(tool=name):
                tool = by_name[name]
                self.assertTrue(tool.deterministic_policy_required)
                self.assertTrue(tool.human_review_required or tool.execution_owner == "sidecar")
                self.assertNotEqual(tool.side_effect_type, "none")

    def test_rbac_permissions_and_sar_draft_safety_are_encoded(self) -> None:
        by_name = {tool.name: tool for tool in PHASE3_TOOL_CATALOG}

        self.assertEqual(by_name["add_alert_comment"].required_permissions, ["can_view_alerts"])
        self.assertEqual(by_name["open_case"].required_permissions, ["can_manage_cases"])
        self.assertEqual(by_name["link_alert_to_case"].required_permissions, ["can_manage_cases"])
        self.assertIn("service_identity", by_name["record_agent_trace"].required_permissions)
        self.assertEqual(
            by_name["draft_regulatory_report"].side_effect_type,
            "draft_only",
        )
        self.assertIn("can_file_sar", by_name["draft_regulatory_report"].required_permissions)
        self.assertTrue(
            any("SAR filing is never an agent action" in note for note in by_name["draft_regulatory_report"].notes)
        )

    def test_graph_scope_expansion_policy_is_present_and_bounded(self) -> None:
        graph_tool = next(tool for tool in PHASE3_TOOL_CATALOG if tool.name == "trace_counterparty_graph")
        policy = graph_tool.scope_expansion_policy

        self.assertIsNotNone(policy)
        assert policy is not None
        self.assertEqual(policy.mode, "bounded_graph_traversal")
        self.assertEqual(policy.max_hops, 4)
        self.assertEqual(policy.max_rows, 100)
        self.assertTrue(policy.requires_policy_decision)
        self.assertIn("account_id", policy.forbidden_tool_arg_fields)

    def test_generated_phase3_schema_files_exist_and_match_models(self) -> None:
        expected = {
            "phase3_mcp_request_envelope.schema.json": Phase3MCPRequestEnvelope,
            "phase3_mcp_response_envelope.schema.json": Phase3MCPResponseEnvelope,
            "phase3_tool_metadata.schema.json": Phase3ToolMetadata,
            "phase3_policy_decision.schema.json": Phase3PolicyDecision,
            "phase3_audit_event.schema.json": Phase3AuditEvent,
            "phase3_scope_expansion_policy.schema.json": Phase3ScopeExpansionPolicy,
        }
        for filename, model in expected.items():
            with self.subTest(filename=filename):
                path = os.path.join(ROOT, "contracts", filename)
                self.assertTrue(os.path.exists(path))
                with open(path, encoding="utf-8") as handle:
                    schema = json.load(handle)
                self.assertEqual(schema["title"], model.model_json_schema()["title"])

    def test_generated_catalog_represents_denial_audit_and_scope_rules(self) -> None:
        path = os.path.join(ROOT, "contracts", "phase3_tool_catalog.json")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as handle:
            catalog = json.load(handle)

        self.assertEqual(catalog["tool_registry_version"], PHASE3_TOOL_REGISTRY_VERSION)
        self.assertEqual({item["name"] for item in catalog["tools"]}, EXPECTED_PHASE3_TOOL_NAMES)

        for item in catalog["tools"]:
            with self.subTest(tool=item["name"]):
                self.assertIn("denial", item["audit_outcomes"])
                self.assertIn("error", item["audit_outcomes"])
                self.assertTrue(item["examples"])

        graph_tool = next(item for item in catalog["tools"] if item["name"] == "trace_counterparty_graph")
        self.assertEqual(graph_tool["scope_expansion_policy"]["mode"], "bounded_graph_traversal")

    def test_phase1_runtime_catalog_remains_read_only_and_unchanged(self) -> None:
        self.assertNotIn("get_officer_permissions", PHASE1_TOOL_NAMES)
        self.assertFalse(BANK_WRITE_TOOLS.intersection(PHASE1_TOOL_NAMES))
        self.assertEqual(len(PHASE1_TOOL_NAMES), 9)


if __name__ == "__main__":
    unittest.main()
