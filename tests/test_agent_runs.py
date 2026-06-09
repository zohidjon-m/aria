from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
for p in (ROOT, SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient

OFFICER_FIXTURE = {
    "officer_id": 1, "full_name": "Test Officer", "email": "test@bank.com",
    "is_active": True, "branch_id": 1, "role_id": 2, "role_name": "senior_analyst",
    "can_view_alerts": True, "can_manage_cases": True,
    "can_file_sar": False, "can_manage_rules": False, "can_manage_users": False,
}

TRIAGE_RESULT = {
    "run_id": "run-abc123",
    "recommendation": "likely_false_positive",
    "confidence": 0.85,
    "score": 15.0,
    "validation_status": "passed",
}

HEADERS = {"X-Officer-Id": "1"}


def make_client():
    from backend.main import app
    return TestClient(app, raise_server_exceptions=False)


class TestTriageRunEndpoint(unittest.TestCase):
    @patch("backend.routes.agent_runs.rw_conn")
    @patch("backend.routes.agent_runs.build_orchestrator")
    @patch("backend.routes.agent_runs.ro_cursor")
    @patch("backend.rbac.ro_cursor")
    def test_triage_run_ok(self, mock_rbac_ro, mock_agent_ro, mock_build, mock_rw):
        # RBAC mock
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = OFFICER_FIXTURE
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        # Alert exists check
        agent_cur = MagicMock()
        agent_cur.fetchone.return_value = {"alert_id": 1}
        agent_cur.__enter__ = MagicMock(return_value=agent_cur)
        agent_cur.__exit__ = MagicMock(return_value=False)
        mock_agent_ro.return_value = agent_cur

        # Orchestrator mock
        mock_orchestrator = MagicMock()
        mock_orchestrator.triage_alert.return_value = TRIAGE_RESULT
        mock_build.return_value = mock_orchestrator

        # Audit rw mock
        conn = MagicMock()
        cur = MagicMock()
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        mock_rw.return_value = conn

        client = make_client()
        resp = client.post("/api/agent-runs/triage", json={"alert_id": 1}, headers=HEADERS)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["run_id"], "run-abc123")
        mock_orchestrator.triage_alert.assert_called_once_with(1)

    @patch("backend.routes.agent_runs.build_orchestrator")
    @patch("backend.routes.agent_runs.ro_cursor")
    @patch("backend.rbac.ro_cursor")
    def test_triage_run_503_on_value_error(self, mock_rbac_ro, mock_agent_ro, mock_build):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = OFFICER_FIXTURE
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        agent_cur = MagicMock()
        agent_cur.fetchone.return_value = {"alert_id": 1}
        agent_cur.__enter__ = MagicMock(return_value=agent_cur)
        agent_cur.__exit__ = MagicMock(return_value=False)
        mock_agent_ro.return_value = agent_cur

        mock_build.side_effect = ValueError("LLM_API_KEY is required")

        client = make_client()
        resp = client.post("/api/agent-runs/triage", json={"alert_id": 1}, headers=HEADERS)
        self.assertEqual(resp.status_code, 503)
        self.assertIn("configuration", resp.json()["detail"])

    @patch("backend.routes.agent_runs.build_orchestrator")
    @patch("backend.routes.agent_runs.ro_cursor")
    @patch("backend.rbac.ro_cursor")
    def test_triage_run_404_on_source_not_found(self, mock_rbac_ro, mock_agent_ro, mock_build):
        from compliance_agent.adapters.source import SourceRecordNotFound
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = OFFICER_FIXTURE
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        agent_cur = MagicMock()
        agent_cur.fetchone.return_value = {"alert_id": 1}
        agent_cur.__enter__ = MagicMock(return_value=agent_cur)
        agent_cur.__exit__ = MagicMock(return_value=False)
        mock_agent_ro.return_value = agent_cur

        mock_orchestrator = MagicMock()
        mock_orchestrator.triage_alert.side_effect = SourceRecordNotFound("alert 999 not found")
        mock_build.return_value = mock_orchestrator

        client = make_client()
        resp = client.post("/api/agent-runs/triage", json={"alert_id": 1}, headers=HEADERS)
        self.assertEqual(resp.status_code, 404)

    @patch("backend.routes.agent_runs.build_orchestrator")
    @patch("backend.routes.agent_runs.ro_cursor")
    @patch("backend.rbac.ro_cursor")
    def test_triage_run_503_on_generic_exception(self, mock_rbac_ro, mock_agent_ro, mock_build):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = OFFICER_FIXTURE
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        agent_cur = MagicMock()
        agent_cur.fetchone.return_value = {"alert_id": 1}
        agent_cur.__enter__ = MagicMock(return_value=agent_cur)
        agent_cur.__exit__ = MagicMock(return_value=False)
        mock_agent_ro.return_value = agent_cur

        mock_orchestrator = MagicMock()
        mock_orchestrator.triage_alert.side_effect = ConnectionError("LLM timeout")
        mock_build.return_value = mock_orchestrator

        client = make_client()
        resp = client.post("/api/agent-runs/triage", json={"alert_id": 1}, headers=HEADERS)
        self.assertEqual(resp.status_code, 503)


class TestLiveMcpTriageRunEndpoint(unittest.TestCase):
    def _settings(self, *, api_key="test-key", model="test-model"):
        return SimpleNamespace(
            bank_source_dsn="postgresql://example.invalid/db",
            sidecar_db_path="data/test-sidecar.sqlite3",
            llm_api_key=api_key,
            llm_model=model,
            llm_endpoint="https://example.invalid/v1/chat/completions",
            llm_timeout_seconds=30.0,
        )

    def _mock_rbac(self, mock_rbac_ro):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = OFFICER_FIXTURE
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

    def _mock_audit(self, mock_rw):
        conn = MagicMock()
        cur = MagicMock()
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        mock_rw.return_value = conn

    @patch("backend.routes.agent_runs.rw_conn")
    @patch("backend.routes.agent_runs.LiveMCPWorkflowAgent")
    @patch("backend.routes.agent_runs.PostgresReferenceRepository")
    @patch("backend.routes.agent_runs.Settings.from_env")
    @patch("backend.rbac.ro_cursor")
    def test_live_mcp_triage_run_ok(
        self,
        mock_rbac_ro,
        mock_settings,
        mock_repo_cls,
        mock_agent_cls,
        mock_rw,
    ):
        self._mock_rbac(mock_rbac_ro)
        self._mock_audit(mock_rw)
        mock_settings.return_value = self._settings()
        repo = MagicMock()
        repo.get_alert_scope.return_value = {
            "alert_id": 1,
            "customer_id": 10,
            "account_id": 20,
            "transaction_id": 30,
        }
        mock_repo_cls.return_value = repo
        agent = MagicMock()
        agent.run_and_persist.return_value = {
            "run_id": "run-live123",
            "proposal": {"recommendation": "needs_investigation"},
            "result": {"recommendation": "needs_investigation"},
            "validation": {"status": "passed"},
        }
        mock_agent_cls.return_value = agent

        client = make_client()
        resp = client.post("/api/agent-runs/live-mcp-triage", json={"alert_id": 1}, headers=HEADERS)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["run_id"], "run-live123")
        agent.run_and_persist.assert_called_once()
        self.assertEqual(agent.run_and_persist.call_args.args[0], "triage")

    @patch("backend.routes.agent_runs.PostgresReferenceRepository")
    @patch("backend.routes.agent_runs.Settings.from_env")
    @patch("backend.rbac.ro_cursor")
    def test_live_mcp_triage_404_on_missing_alert_scope(
        self,
        mock_rbac_ro,
        mock_settings,
        mock_repo_cls,
    ):
        self._mock_rbac(mock_rbac_ro)
        mock_settings.return_value = self._settings()
        repo = MagicMock()
        repo.get_alert_scope.return_value = None
        mock_repo_cls.return_value = repo

        client = make_client()
        resp = client.post("/api/agent-runs/live-mcp-triage", json={"alert_id": 999}, headers=HEADERS)

        self.assertEqual(resp.status_code, 404)

    @patch("backend.routes.agent_runs.os.getenv")
    @patch("backend.routes.agent_runs.Settings.from_env")
    @patch("backend.rbac.ro_cursor")
    def test_live_mcp_triage_503_on_missing_llm_config(
        self,
        mock_rbac_ro,
        mock_settings,
        mock_getenv,
    ):
        self._mock_rbac(mock_rbac_ro)
        mock_settings.return_value = self._settings(api_key=None, model=None)
        mock_getenv.return_value = None

        client = make_client()
        resp = client.post("/api/agent-runs/live-mcp-triage", json={"alert_id": 1}, headers=HEADERS)

        self.assertEqual(resp.status_code, 503)
        self.assertIn("LLM_API_KEY", resp.json()["detail"])

    @patch("backend.routes.agent_runs.LiveMCPWorkflowAgent")
    @patch("backend.routes.agent_runs.PostgresReferenceRepository")
    @patch("backend.routes.agent_runs.Settings.from_env")
    @patch("backend.rbac.ro_cursor")
    def test_live_mcp_triage_503_on_runtime_exception(
        self,
        mock_rbac_ro,
        mock_settings,
        mock_repo_cls,
        mock_agent_cls,
    ):
        self._mock_rbac(mock_rbac_ro)
        mock_settings.return_value = self._settings()
        repo = MagicMock()
        repo.get_alert_scope.return_value = {
            "alert_id": 1,
            "customer_id": 10,
            "account_id": 20,
            "transaction_id": 30,
        }
        mock_repo_cls.return_value = repo
        agent = MagicMock()
        agent.run_and_persist.side_effect = RuntimeError("planner failed")
        mock_agent_cls.return_value = agent

        client = make_client()
        resp = client.post("/api/agent-runs/live-mcp-triage", json={"alert_id": 1}, headers=HEADERS)

        self.assertEqual(resp.status_code, 503)
        self.assertIn("Live MCP workflow failed", resp.json()["detail"])


class TestGetAgentRun(unittest.TestCase):
    @patch("backend.routes.agent_runs.SidecarStore")
    @patch("backend.rbac.ro_cursor")
    def test_get_run_existing(self, mock_rbac_ro, mock_store_cls):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = OFFICER_FIXTURE
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        mock_store = MagicMock()
        mock_store.get_run.return_value = {
            "run": {"run_id": "run-abc123"},
            "output": TRIAGE_RESULT,
            "validation": {"status": "passed"},
            "evidence": [],
        }
        mock_store_cls.return_value = mock_store

        client = make_client()
        resp = client.get("/api/agent-runs/run-abc123", headers=HEADERS)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("output", body)

    @patch("backend.routes.agent_runs.SidecarStore")
    @patch("backend.rbac.ro_cursor")
    def test_get_run_not_found(self, mock_rbac_ro, mock_store_cls):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = OFFICER_FIXTURE
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        mock_store = MagicMock()
        mock_store.get_run.return_value = None
        mock_store_cls.return_value = mock_store

        client = make_client()
        resp = client.get("/api/agent-runs/no-such-run", headers=HEADERS)
        self.assertEqual(resp.status_code, 404)

    @patch("backend.routes.agent_runs.SidecarStore")
    @patch("backend.rbac.ro_cursor")
    def test_get_trace_ok(self, mock_rbac_ro, mock_store_cls):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = OFFICER_FIXTURE
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        mock_store = MagicMock()
        mock_store.get_trace.return_value = {
            "run_id": "run-abc123",
            "agent_steps": [],
            "tool_calls": [],
            "observations": [],
        }
        mock_store_cls.return_value = mock_store

        client = make_client()
        resp = client.get("/api/agent-runs/run-abc123/trace", headers=HEADERS)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("agent_steps", body)
        self.assertIn("tool_calls", body)

    @patch("backend.routes.agent_runs.SidecarStore")
    @patch("backend.rbac.ro_cursor")
    def test_get_trace_includes_phase2_runtime_events(self, mock_rbac_ro, mock_store_cls):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = OFFICER_FIXTURE
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        mock_store = MagicMock()
        mock_store.get_trace.return_value = {
            "run_id": "run-abc123",
            "runtime_events": [{"sequence_number": 1, "state": "created"}],
            "terminal_state": "proposed",
            "stop_reason": "completed",
            "agent_steps": [],
            "tool_calls": [],
            "observations": [],
        }
        mock_store_cls.return_value = mock_store

        client = make_client()
        resp = client.get("/api/agent-runs/run-abc123/trace", headers=HEADERS)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["runtime_events"][0]["state"], "created")
        self.assertEqual(body["terminal_state"], "proposed")


if __name__ == "__main__":
    unittest.main()
