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

VIEW_ONLY_OFFICER = {
    "officer_id": 2, "full_name": "View Officer", "email": "view@bank.com",
    "is_active": True, "branch_id": 1, "role_id": 1, "role_name": "junior_analyst",
    "can_view_alerts": True, "can_manage_cases": False,
    "can_file_sar": False, "can_manage_rules": False, "can_manage_users": False,
}

NO_VIEW_OFFICER = {
    "officer_id": 3, "full_name": "Admin Officer", "email": "admin@bank.com",
    "is_active": True, "branch_id": 1, "role_id": 5, "role_name": "db_admin",
    "can_view_alerts": False, "can_manage_cases": False,
    "can_file_sar": False, "can_manage_rules": False, "can_manage_users": True,
}

MANAGE_OFFICER = {
    "officer_id": 4, "full_name": "Manager", "email": "mgr@bank.com",
    "is_active": True, "branch_id": 1, "role_id": 3, "role_name": "compliance_officer",
    "can_view_alerts": True, "can_manage_cases": True,
    "can_file_sar": True, "can_manage_rules": False, "can_manage_users": False,
}


def make_client():
    from backend.main import app
    return TestClient(app, raise_server_exceptions=False)


class TestRBACMissingHeader(unittest.TestCase):
    def test_missing_officer_id_on_alerts(self):
        client = make_client()
        resp = client.get("/api/alerts")
        self.assertIn(resp.status_code, [422, 403])

    def test_missing_officer_id_on_customers(self):
        client = make_client()
        resp = client.get("/api/customers/1")
        self.assertIn(resp.status_code, [422, 403])

    def test_missing_officer_id_on_cases(self):
        client = make_client()
        resp = client.get("/api/cases/1")
        self.assertIn(resp.status_code, [422, 403])


class TestRBACNoViewAlerts(unittest.TestCase):
    @patch("backend.rbac.ro_cursor")
    def _get_client_with_no_view(self, mock_ro):
        cur = MagicMock()
        cur.fetchone.return_value = NO_VIEW_OFFICER
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        mock_ro.return_value = cur
        return make_client()

    @patch("backend.rbac.ro_cursor")
    def test_no_view_on_alerts_list(self, mock_ro):
        cur = MagicMock()
        cur.fetchone.return_value = NO_VIEW_OFFICER
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        mock_ro.return_value = cur
        client = make_client()
        resp = client.get("/api/alerts", headers={"X-Officer-Id": "3"})
        self.assertEqual(resp.status_code, 403)

    @patch("backend.rbac.ro_cursor")
    def test_no_view_on_audit_log(self, mock_ro):
        cur = MagicMock()
        cur.fetchone.return_value = NO_VIEW_OFFICER
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        mock_ro.return_value = cur
        client = make_client()
        resp = client.get("/api/audit-log", headers={"X-Officer-Id": "3"})
        self.assertEqual(resp.status_code, 403)


class TestRBACNoManageCases(unittest.TestCase):
    @patch("backend.routes.alerts.ro_cursor")
    @patch("backend.rbac.ro_cursor")
    def test_view_only_cannot_set_disposition(self, mock_rbac_ro, mock_alerts_ro):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = VIEW_ONLY_OFFICER
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        client = make_client()
        resp = client.post(
            "/api/alerts/1/disposition",
            json={"status": "dismissed", "notes": "test"},
            headers={"X-Officer-Id": "2"},
        )
        self.assertEqual(resp.status_code, 403)

    @patch("backend.rbac.ro_cursor")
    def test_view_only_cannot_create_case(self, mock_rbac_ro):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = VIEW_ONLY_OFFICER
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        client = make_client()
        resp = client.post(
            "/api/cases",
            json={"customer_id": 1, "case_type": "AML", "priority": "medium"},
            headers={"X-Officer-Id": "2"},
        )
        self.assertEqual(resp.status_code, 403)

    @patch("backend.rbac.ro_cursor")
    def test_view_only_cannot_link_alert(self, mock_rbac_ro):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = VIEW_ONLY_OFFICER
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        client = make_client()
        resp = client.post(
            "/api/cases/1/link-alert",
            json={"alert_id": 1},
            headers={"X-Officer-Id": "2"},
        )
        self.assertEqual(resp.status_code, 403)


class TestRBACInactiveOfficer(unittest.TestCase):
    @patch("backend.rbac.ro_cursor")
    def test_inactive_officer_is_rejected(self, mock_ro):
        cur = MagicMock()
        cur.fetchone.return_value = {**MANAGE_OFFICER, "is_active": False}
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        mock_ro.return_value = cur
        client = make_client()
        resp = client.get("/api/alerts", headers={"X-Officer-Id": "4"})
        self.assertEqual(resp.status_code, 403)


class TestRBACNonExistentOfficer(unittest.TestCase):
    @patch("backend.rbac.ro_cursor")
    def test_nonexistent_officer_is_rejected(self, mock_ro):
        cur = MagicMock()
        cur.fetchone.return_value = None
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        mock_ro.return_value = cur
        client = make_client()
        resp = client.get("/api/alerts", headers={"X-Officer-Id": "9999"})
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
