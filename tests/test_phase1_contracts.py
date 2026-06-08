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

from compliance_agent.contracts.phase1 import (
    AgentProposal,
    AgentRunRequest,
    MCPRequestEnvelope,
    MCPResponseEnvelope,
)
from compliance_agent.contracts.tool_catalog import PHASE1_TOOL_CATALOG, PHASE1_TOOL_NAMES


class Phase1ContractsTest(unittest.TestCase):
    def test_required_schema_files_exist_and_match_models(self) -> None:
        expected = {
            "agent_proposal.schema.json": AgentProposal,
            "agent_run_request.schema.json": AgentRunRequest,
            "mcp_request_envelope.schema.json": MCPRequestEnvelope,
            "mcp_response_envelope.schema.json": MCPResponseEnvelope,
        }
        for filename, model in expected.items():
            with self.subTest(filename=filename):
                path = os.path.join(ROOT, "contracts", filename)
                self.assertTrue(os.path.exists(path))
                with open(path, encoding="utf-8") as handle:
                    schema = json.load(handle)
                self.assertEqual(schema["title"], model.model_json_schema()["title"])

    def test_phase1_tool_catalog_contains_required_tool_names(self) -> None:
        self.assertEqual(
            set(PHASE1_TOOL_NAMES),
            {
                "get_customer_profile",
                "get_transaction_history",
                "get_behavioral_baseline",
                "get_prior_alerts",
                "get_case_history",
                "trace_counterparty_graph",
                "screen_sanctions_pep",
                "get_similar_alerts",
                "get_compliance_rule",
            },
        )
        self.assertEqual(len(PHASE1_TOOL_CATALOG), 9)
        self.assertTrue(all(item.read_only for item in PHASE1_TOOL_CATALOG))

    def test_tool_catalog_json_is_generated_for_frontend_backend_consumers(self) -> None:
        path = os.path.join(ROOT, "contracts", "phase1_tool_catalog.json")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as handle:
            catalog = json.load(handle)
        self.assertIn("tool_registry_version", catalog)
        self.assertEqual(
            {item["name"] for item in catalog["tools"]},
            set(PHASE1_TOOL_NAMES),
        )


if __name__ == "__main__":
    unittest.main()
