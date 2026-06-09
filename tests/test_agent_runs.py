from __future__ import annotations

import os
import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
