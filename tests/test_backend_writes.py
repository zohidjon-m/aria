from __future__ import annotations

import os
import sys
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, call, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
for p in (ROOT, SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient

MANAGE_OFFICER = {
    "officer_id": 1, "full_name": "Test Manager", "email": "mgr@bank.com",
    "is_active": True, "branch_id": 1, "role_id": 3, "role_name": "compliance_officer",
    "can_view_alerts": True, "can_manage_cases": True,
    "can_file_sar": True, "can_manage_rules": False, "can_manage_users": False,
}

VIEW_OFFICER = {
    "officer_id": 2, "full_name": "View Only", "email": "view@bank.com",
    "is_active": True, "branch_id": 1, "role_id": 1, "role_name": "junior_analyst",
    "can_view_alerts": True, "can_manage_cases": False,
    "can_file_sar": False, "can_manage_rules": False, "can_manage_users": False,
}

HEADERS_MANAGE = {"X-Officer-Id": "1"}
HEADERS_VIEW = {"X-Officer-Id": "2"}


def make_mock_rw_conn():
    conn = MagicMock()
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn, cur


def make_client():
    from backend.main import app
    return TestClient(app, raise_server_exceptions=False)


class TestAddComment(unittest.TestCase):
    @patch("backend.routes.alerts.rw_conn")
    @patch("backend.rbac.ro_cursor")
    def test_add_comment_ok(self, mock_rbac_ro, mock_rw):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = VIEW_OFFICER
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        conn, cur = make_mock_rw_conn()
        alert_row = {"alert_id": 1}
        comment_row = {"comment_id": 10, "created_at": "2024-01-01"}
        call_count = [0]
        def fetchone_side():
            n = call_count[0]
            call_count[0] += 1
            if n == 0:
                return alert_row
            return comment_row
        cur.fetchone.side_effect = fetchone_side
        mock_rw.return_value = conn

        client = make_client()
        resp = client.post(
            "/api/alerts/1/comments",
            json={"comment": "Looks suspicious"},
            headers=HEADERS_VIEW,
        )
        self.assertEqual(resp.status_code, 201)
        # Verify audit INSERT was called
        execute_calls = [str(c) for c in cur.execute.call_args_list]
        audit_called = any("audit_log" in c for c in execute_calls)
        self.assertTrue(audit_called, "audit_log INSERT should have been called")
        # Verify commit was called

    @patch("backend.rbac.ro_cursor")
    def test_add_comment_requires_view_alerts(self, mock_rbac_ro):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = {**VIEW_OFFICER, "can_view_alerts": False}
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        client = make_client()
        resp = client.post(
            "/api/alerts/1/comments",
            json={"comment": "test"},
            headers={"X-Officer-Id": "99"},
        )
        self.assertEqual(resp.status_code, 403)


class TestSetDisposition(unittest.TestCase):
    @patch("backend.routes.alerts.rw_conn")
    @patch("backend.rbac.ro_cursor")
    def test_set_disposition_ok(self, mock_rbac_ro, mock_rw):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = MANAGE_OFFICER
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        conn, cur = make_mock_rw_conn()
        alert_row = {"alert_id": 1}
        updated_row = {"alert_id": 1, "status": "dismissed", "notes": "FP", "resolved_at": "2024-01-01"}
        call_count = [0]
        def fetchone_side():
            n = call_count[0]
            call_count[0] += 1
            if n == 0:
                return alert_row
            return updated_row
        cur.fetchone.side_effect = fetchone_side
        mock_rw.return_value = conn

        client = make_client()
        resp = client.post(
            "/api/alerts/1/disposition",
            json={"status": "dismissed", "notes": "False positive"},
            headers=HEADERS_MANAGE,
        )
        self.assertEqual(resp.status_code, 200)
        execute_calls = [str(c) for c in cur.execute.call_args_list]
        audit_called = any("audit_log" in c for c in execute_calls)
        self.assertTrue(audit_called)

    @patch("backend.rbac.ro_cursor")
    def test_set_disposition_invalid_status(self, mock_rbac_ro):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = MANAGE_OFFICER
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        client = make_client()
        resp = client.post(
            "/api/alerts/1/disposition",
            json={"status": "invalid_status", "notes": "test"},
            headers=HEADERS_MANAGE,
        )
        self.assertEqual(resp.status_code, 422)


class TestCreateCase(unittest.TestCase):
    @patch("backend.routes.cases.rw_conn")
    @patch("backend.rbac.ro_cursor")
    def test_create_case_ok(self, mock_rbac_ro, mock_rw):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = MANAGE_OFFICER
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        conn, cur = make_mock_rw_conn()
        call_count = [0]
        def fetchone_side():
            n = call_count[0]
            call_count[0] += 1
            if n == 0:
                return {"customer_id": 1}
            return {"case_id": 5, "status": "open", "opened_at": "2024-01-01"}
        cur.fetchone.side_effect = fetchone_side
        mock_rw.return_value = conn

        client = make_client()
        resp = client.post(
            "/api/cases",
            json={"customer_id": 1, "case_type": "AML", "priority": "high", "summary": "Test"},
            headers=HEADERS_MANAGE,
        )
        self.assertEqual(resp.status_code, 201)
        execute_calls = [str(c) for c in cur.execute.call_args_list]
        audit_called = any("audit_log" in c for c in execute_calls)
        self.assertTrue(audit_called)

    @patch("backend.rbac.ro_cursor")
    def test_create_case_invalid_type(self, mock_rbac_ro):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = MANAGE_OFFICER
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        client = make_client()
        resp = client.post(
            "/api/cases",
            json={"customer_id": 1, "case_type": "INVALID", "priority": "medium"},
            headers=HEADERS_MANAGE,
        )
        self.assertEqual(resp.status_code, 422)


class TestLinkAlert(unittest.TestCase):
    @patch("backend.routes.cases.rw_conn")
    @patch("backend.rbac.ro_cursor")
    def test_link_alert_ok(self, mock_rbac_ro, mock_rw):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = MANAGE_OFFICER
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        conn, cur = make_mock_rw_conn()
        call_count = [0]
        def fetchone_side():
            n = call_count[0]
            call_count[0] += 1
            if n == 0:
                return {"case_id": 1}
            return {"alert_id": 1}
        cur.fetchone.side_effect = fetchone_side
        mock_rw.return_value = conn

        client = make_client()
        resp = client.post(
            "/api/cases/1/link-alert",
            json={"alert_id": 1},
            headers=HEADERS_MANAGE,
        )
        self.assertEqual(resp.status_code, 200)
        execute_calls = [str(c) for c in cur.execute.call_args_list]
        audit_called = any("audit_log" in c for c in execute_calls)
        self.assertTrue(audit_called)


if __name__ == "__main__":
    unittest.main()
