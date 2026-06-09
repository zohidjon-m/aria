from __future__ import annotations

import os
import sys
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
BACKEND = ROOT
for p in (ROOT, SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient

OFFICER_FIXTURE = {
    "officer_id": 1,
    "full_name": "Test Officer",
    "email": "test@bank.com",
    "is_active": True,
    "branch_id": 1,
    "role_id": 2,
    "role_name": "senior_analyst",
    "can_view_alerts": True,
    "can_manage_cases": True,
    "can_file_sar": False,
    "can_manage_rules": False,
    "can_manage_users": False,
}

ALERT_FIXTURE = {
    "alert_id": 1,
    "severity": "high",
    "status": "open",
    "is_escalated": False,
    "created_at": "2024-01-01T00:00:00",
    "assigned_to": 1,
    "rule_id": 1,
    "transaction_id": 1,
    "notes": "",
    "resolved_at": None,
    "rule_name": "Large Cash Transaction",
    "rule_type": "threshold",
    "threshold_amount": 10000,
    "max_frequency": None,
    "time_window_days": None,
    "applies_to": "cash",
    "rule_severity": "high",
    "rule_is_active": True,
    "amount": 15000.0,
    "currency_code": "USD",
    "amount_usd": 15000.0,
    "transaction_type": "cash",
    "tx_description": None,
    "reference_number": "TXN001",
    "tx_status": "completed",
    "tx_created_at": "2024-01-01T00:00:00",
    "destination_country": None,
    "destination_country_name": None,
    "destination_fatf_status": None,
    "destination_is_sanctioned": None,
    "assigned_officer_name": "Test Officer",
}

CUSTOMER_FIXTURE = {
    "customer_id": 1,
    "full_name": "John Doe",
    "email": "john@example.com",
    "phone": "555-1234",
    "nationality": "US",
    "date_of_birth": "1980-01-01",
    "occupation": "Engineer",
    "risk_level": "low",
    "kyc_status": "verified",
    "is_active": True,
    "created_at": "2020-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00",
    "nationality_name": "United States",
    "nationality_fatf_status": "whitelist",
}

CASE_FIXTURE = {
    "case_id": 1,
    "customer_id": 1,
    "officer_id": 1,
    "case_type": "AML",
    "status": "open",
    "priority": "medium",
    "summary": "Test case",
    "resolution": None,
    "opened_at": "2024-01-01T00:00:00",
    "closed_at": None,
    "customer_name": "John Doe",
    "customer_risk_level": "low",
    "customer_kyc_status": "verified",
    "officer_name": "Test Officer",
}


@contextmanager
def mock_ro_cursor(rows_map: dict):
    mock_cur = MagicMock()
    def fetchone_side():
        key = mock_cur._last_key
        rows = rows_map.get(key, [])
        return rows[0] if rows else None
    def fetchall_side():
        key = mock_cur._last_key
        return rows_map.get(key, [])
    def execute_side(sql, params=None):
        mock_cur._last_key = sql.strip()[:60]
    mock_cur.execute.side_effect = execute_side
    mock_cur.fetchone.side_effect = fetchone_side
    mock_cur.fetchall.side_effect = fetchall_side
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_cur)
    mock_cm.__exit__ = MagicMock(return_value=False)
    yield mock_cm


def make_client():
    from backend.main import app
    return TestClient(app, raise_server_exceptions=False)


HEADERS = {"X-Officer-Id": "1"}


class TestHealthEndpoint(unittest.TestCase):
    @patch("backend.routes.health.ro_cursor")
    def test_health_ok(self, mock_ro):
        mock_cur = MagicMock()
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_ro.return_value = mock_cur

        client = make_client()
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "healthy")


class TestAlertListEndpoint(unittest.TestCase):
    def _mock_officer_cursor(self, mock_ro):
        mock_cur = MagicMock()
        call_count = [0]
        def fetchone_side():
            n = call_count[0]
            call_count[0] += 1
            if n == 0:
                return OFFICER_FIXTURE
            if n == 1:
                return {"total": 2}
            return None
        def fetchall_side():
            return [
                {"alert_id": 1, "severity": "high", "status": "open",
                 "is_escalated": False, "created_at": "2024-01-01",
                 "assigned_to": 1, "rule_name": "Large Cash", "rule_type": "threshold",
                 "customer_id": 1, "customer_name": "John Doe", "risk_level": "low",
                 "amount": 15000, "currency_code": "USD", "amount_usd": 15000,
                 "transaction_type": "cash", "officer_name": "Test Officer",
                 "has_case": False, "has_sanctions_hit": False, "has_pep_hit": False},
            ]
        mock_cur.fetchone.side_effect = fetchone_side
        mock_cur.fetchall.side_effect = fetchall_side
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_ro.return_value = mock_cur

    @patch("backend.routes.alerts.ro_cursor")
    @patch("backend.rbac.ro_cursor")
    def test_list_alerts_ok(self, mock_rbac_ro, mock_alerts_ro):
        # Mock officer lookup
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = OFFICER_FIXTURE
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        # Mock alerts list
        alerts_cur = MagicMock()
        count_called = [False]
        def fetchone_side():
            if not count_called[0]:
                count_called[0] = True
                return {"total": 1}
            return None
        def fetchall_side():
            return [{"alert_id": 1, "severity": "high", "status": "open",
                     "is_escalated": False, "created_at": "2024-01-01",
                     "assigned_to": 1, "rule_name": "Large Cash", "rule_type": "threshold",
                     "customer_id": 1, "customer_name": "John Doe", "risk_level": "low",
                     "amount": 15000, "currency_code": "USD", "amount_usd": 15000,
                     "transaction_type": "cash", "officer_name": "Test Officer",
                     "has_case": False, "has_sanctions_hit": False, "has_pep_hit": False}]
        alerts_cur.fetchone.side_effect = fetchone_side
        alerts_cur.fetchall.side_effect = fetchall_side
        alerts_cur.__enter__ = MagicMock(return_value=alerts_cur)
        alerts_cur.__exit__ = MagicMock(return_value=False)
        mock_alerts_ro.return_value = alerts_cur

        client = make_client()
        resp = client.get("/api/alerts", headers=HEADERS)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("items", body)
        self.assertIn("total", body)

    @patch("backend.routes.alerts.ro_cursor")
    @patch("backend.rbac.ro_cursor")
    def test_list_alerts_with_filters(self, mock_rbac_ro, mock_alerts_ro):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = OFFICER_FIXTURE
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        alerts_cur = MagicMock()
        count_called = [False]
        def fetchone_side():
            if not count_called[0]:
                count_called[0] = True
                return {"total": 0}
            return None
        alerts_cur.fetchone.side_effect = fetchone_side
        alerts_cur.fetchall.return_value = []
        alerts_cur.__enter__ = MagicMock(return_value=alerts_cur)
        alerts_cur.__exit__ = MagicMock(return_value=False)
        mock_alerts_ro.return_value = alerts_cur

        client = make_client()
        resp = client.get("/api/alerts?status=open&severity=high", headers=HEADERS)
        self.assertEqual(resp.status_code, 200)
        # Verify filter params were passed
        execute_calls = [str(c) for c in alerts_cur.execute.call_args_list]
        params_passed = any("open" in str(c) for c in execute_calls)
        self.assertTrue(params_passed)


class TestCustomerEndpoints(unittest.TestCase):
    @patch("backend.routes.customers.ro_cursor")
    @patch("backend.rbac.ro_cursor")
    def test_get_customer_ok(self, mock_rbac_ro, mock_cust_ro):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = OFFICER_FIXTURE
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        cust_cur = MagicMock()
        call_count = [0]
        def fetchone_side():
            n = call_count[0]
            call_count[0] += 1
            if n == 0:
                return CUSTOMER_FIXTURE
            return None
        cust_cur.fetchone.side_effect = fetchone_side
        cust_cur.fetchall.return_value = []
        cust_cur.__enter__ = MagicMock(return_value=cust_cur)
        cust_cur.__exit__ = MagicMock(return_value=False)
        mock_cust_ro.return_value = cust_cur

        client = make_client()
        resp = client.get("/api/customers/1", headers=HEADERS)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["customer_id"], 1)

    @patch("backend.routes.customers.ro_cursor")
    @patch("backend.rbac.ro_cursor")
    def test_get_customer_not_found(self, mock_rbac_ro, mock_cust_ro):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = OFFICER_FIXTURE
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        cust_cur = MagicMock()
        cust_cur.fetchone.return_value = None
        cust_cur.__enter__ = MagicMock(return_value=cust_cur)
        cust_cur.__exit__ = MagicMock(return_value=False)
        mock_cust_ro.return_value = cust_cur

        client = make_client()
        resp = client.get("/api/customers/999", headers=HEADERS)
        self.assertEqual(resp.status_code, 404)

    @patch("backend.routes.customers.ro_cursor")
    @patch("backend.rbac.ro_cursor")
    def test_get_customer_transactions_ok(self, mock_rbac_ro, mock_cust_ro):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = OFFICER_FIXTURE
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        cust_cur = MagicMock()
        call_count = [0]
        def fetchone_side():
            n = call_count[0]
            call_count[0] += 1
            if n == 0:
                return {"customer_id": 1}
            return {"total": 5}
        cust_cur.fetchone.side_effect = fetchone_side
        cust_cur.fetchall.return_value = [
            {"transaction_id": 1, "amount": 100, "currency_code": "USD", "amount_usd": 100,
             "transaction_type": "transfer_domestic", "destination_country": None,
             "destination_country_name": None, "destination_fatf_status": None,
             "description": None, "reference_number": "TXN001", "status": "completed",
             "is_flagged": False, "created_at": "2024-01-01", "account_number": "ACC001",
             "account_type": "checking"}
        ]
        cust_cur.__enter__ = MagicMock(return_value=cust_cur)
        cust_cur.__exit__ = MagicMock(return_value=False)
        mock_cust_ro.return_value = cust_cur

        client = make_client()
        resp = client.get("/api/customers/1/transactions", headers=HEADERS)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("items", body)
        self.assertIn("total", body)

    @patch("backend.routes.customers.ro_cursor")
    @patch("backend.rbac.ro_cursor")
    def test_get_customer_cases_ok(self, mock_rbac_ro, mock_cust_ro):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = OFFICER_FIXTURE
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        cust_cur = MagicMock()
        cust_cur.fetchone.return_value = {"customer_id": 1}
        cust_cur.fetchall.return_value = []
        cust_cur.__enter__ = MagicMock(return_value=cust_cur)
        cust_cur.__exit__ = MagicMock(return_value=False)
        mock_cust_ro.return_value = cust_cur

        client = make_client()
        resp = client.get("/api/customers/1/cases", headers=HEADERS)
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)


class TestCaseEndpoints(unittest.TestCase):
    @patch("backend.routes.cases.ro_cursor")
    @patch("backend.rbac.ro_cursor")
    def test_get_case_ok(self, mock_rbac_ro, mock_cases_ro):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = OFFICER_FIXTURE
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        cases_cur = MagicMock()
        cases_cur.fetchone.return_value = CASE_FIXTURE
        cases_cur.fetchall.return_value = []
        cases_cur.__enter__ = MagicMock(return_value=cases_cur)
        cases_cur.__exit__ = MagicMock(return_value=False)
        mock_cases_ro.return_value = cases_cur

        client = make_client()
        resp = client.get("/api/cases/1", headers=HEADERS)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["case_id"], 1)

    @patch("backend.routes.cases.ro_cursor")
    @patch("backend.rbac.ro_cursor")
    def test_get_case_not_found(self, mock_rbac_ro, mock_cases_ro):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = OFFICER_FIXTURE
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        cases_cur = MagicMock()
        cases_cur.fetchone.return_value = None
        cases_cur.__enter__ = MagicMock(return_value=cases_cur)
        cases_cur.__exit__ = MagicMock(return_value=False)
        mock_cases_ro.return_value = cases_cur

        client = make_client()
        resp = client.get("/api/cases/999", headers=HEADERS)
        self.assertEqual(resp.status_code, 404)


class TestAuditLogEndpoint(unittest.TestCase):
    @patch("backend.routes.audit_log.ro_cursor")
    @patch("backend.rbac.ro_cursor")
    def test_get_audit_log_ok(self, mock_rbac_ro, mock_audit_ro):
        rbac_cur = MagicMock()
        rbac_cur.fetchone.return_value = OFFICER_FIXTURE
        rbac_cur.__enter__ = MagicMock(return_value=rbac_cur)
        rbac_cur.__exit__ = MagicMock(return_value=False)
        mock_rbac_ro.return_value = rbac_cur

        audit_cur = MagicMock()
        audit_cur.fetchone.return_value = {"total": 0}
        audit_cur.fetchall.return_value = []
        audit_cur.__enter__ = MagicMock(return_value=audit_cur)
        audit_cur.__exit__ = MagicMock(return_value=False)
        mock_audit_ro.return_value = audit_cur

        client = make_client()
        resp = client.get("/api/audit-log", headers=HEADERS)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("items", body)
        self.assertIn("total", body)


if __name__ == "__main__":
    unittest.main()
