from __future__ import annotations

import os
import sqlite3
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
from compliance_agent.orchestrator import ComplianceOrchestrator


PHASE11_TABLES = {
    "runtime_versions",
    "typology_routes",
    "agent_steps",
    "tool_calls",
    "observations",
    "hypotheses",
    "baseline_snapshots",
    "money_flow_paths",
}


class Phase11TracePersistenceTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        os.remove(path)
        self.db_path = path
        self.source = FakeBankSourceRepository()
        self.sidecar = SidecarStore(path)
        self.orchestrator = ComplianceOrchestrator(
            source=self.source,
            sidecar=self.sidecar,
        )

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_schema_creation_includes_phase11_tables(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        finally:
            conn.close()

        table_names = {row[0] for row in rows}
        self.assertTrue(PHASE11_TABLES.issubset(table_names))

    def test_obvious_pre_screen_triage_writes_queryable_trace(self) -> None:
        response = self.orchestrator.triage_alert(1003)
        trace = self.sidecar.get_trace(response["run_id"])

        self.assertIsNotNone(trace)
        assert trace is not None
        self.assertEqual(trace["runtime_version"]["planner_type"], "pre_screen_gate")
        self.assertEqual(
            trace["runtime_version"]["tool_registry_version"],
            "phase1_tools_v1",
        )
        self.assertEqual(trace["agent_steps"], [])
        self.assertIn(
            "compute_behavioral_baseline",
            {call["tool_name"] for call in trace["tool_calls"]},
        )
        self.assertIn(
            "compute_behavioral_baseline",
            {item["tool_name"] for item in trace["observations"]},
        )
        self.assertEqual(trace["baseline_snapshots"][0]["phase"], "pre_screen")
        self.assertEqual(
            trace["baseline_snapshots"][0]["baseline_assessment"],
            "consistent",
        )

    def test_ambiguous_react_triage_writes_runtime_spine(self) -> None:
        response = self.orchestrator.triage_alert(1005)
        trace = self.sidecar.get_trace(response["run_id"])

        self.assertIsNotNone(trace)
        assert trace is not None
        self.assertEqual(trace["runtime_version"]["planner_type"], "heuristic")
        self.assertTrue(trace["typology_routes"])
        self.assertTrue(trace["agent_steps"])
        self.assertTrue(trace["hypotheses"])
        self.assertIn(
            "react_runtime",
            {call["phase"] for call in trace["tool_calls"]},
        )
        self.assertIn(
            "react_runtime",
            {item["phase"] for item in trace["observations"]},
        )
        self.assertIn(
            "pre_screen",
            {item["phase"] for item in trace["baseline_snapshots"]},
        )

    def test_graph_trace_writes_money_flow_paths(self) -> None:
        self._install_minimal_graph_fixture()

        response = self.orchestrator.triage_alert(1002)
        trace = self.sidecar.get_trace(response["run_id"])

        self.assertIsNotNone(trace)
        assert trace is not None
        self.assertTrue(trace["money_flow_paths"])
        path = trace["money_flow_paths"][0]
        self.assertEqual(path["account_path"], [3002, 4500])
        self.assertEqual(path["phase"], "pre_screen")
        self.assertIn("rapid_pass_through", path["graph_signals"])

    def test_same_alert_reruns_share_idempotency_key_but_keep_distinct_runs(self) -> None:
        first = self.orchestrator.triage_alert(1003)
        second = self.orchestrator.triage_alert(1003)
        first_trace = self.sidecar.get_trace(first["run_id"])
        second_trace = self.sidecar.get_trace(second["run_id"])

        self.assertIsNotNone(first_trace)
        self.assertIsNotNone(second_trace)
        assert first_trace is not None
        assert second_trace is not None
        first_key = first_trace["runtime_version"]["idempotency_key"]
        second_key = second_trace["runtime_version"]["idempotency_key"]

        self.assertEqual(first_key, second_key)
        self.assertNotEqual(first["run_id"], second["run_id"])
        matching = self.sidecar.find_runs_by_idempotency_key(first_key)
        self.assertEqual({item["run_id"] for item in matching}, {first["run_id"], second["run_id"]})

    def test_get_trace_does_not_change_get_run_compatibility_shape(self) -> None:
        response = self.orchestrator.triage_alert(1005)
        stored = self.sidecar.get_run(response["run_id"])
        trace = self.sidecar.get_trace(response["run_id"])

        self.assertIsNotNone(stored)
        self.assertIsNotNone(trace)
        assert stored is not None
        self.assertIn("run", stored)
        self.assertIn("output", stored)
        self.assertIn("validation", stored)
        self.assertIn("evidence", stored)
        self.assertNotIn("agent_steps", stored)

    def _install_minimal_graph_fixture(self) -> None:
        context = self.source._alert_contexts[1002]
        context["transaction"]["counterparty_account_id"] = 4500
        context["transaction"]["is_flagged"] = False
        context["recent_transactions"][0]["counterparty_account_id"] = 4500
        context["recent_transactions"][0]["is_flagged"] = False
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
            "full_name": "Graph Counterparty LLC",
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
                "amount_usd": 52000.0,
                "destination_country": None,
                "created_at": "2026-06-06T10:30:00+00:00",
                "status": "completed",
                "is_flagged": False,
            }
        ]


if __name__ == "__main__":
    unittest.main()
