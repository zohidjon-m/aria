from __future__ import annotations

from copy import deepcopy
from typing import Any

from .source import SourceRecordNotFound
from ..utils import parse_datetime


class FakeBankSourceRepository:
    """In-memory source adapter for tests and demos.

    It exposes the same read methods as a bank adapter and intentionally has no
    write methods.
    """

    def __init__(self) -> None:
        self._alert_contexts = {
            1001: self._high_risk_alert_context(),
            1002: self._ordinary_alert_context(),
            1003: self._high_cash_baseline_context(),
            1004: self._low_cash_baseline_context(),
            1005: self._insufficient_history_context(),
        }
        self._customer_contexts = {
            501: self._customer_context_from_alert(1001),
            502: self._customer_context_from_alert(1002),
            503: self._customer_context_from_alert(1003),
            504: self._customer_context_from_alert(1004),
            505: self._customer_context_from_alert(1005),
        }
        self._case_contexts = {
            9001: self._case_context(),
        }

    def get_alert_context(self, alert_id: int) -> dict[str, Any]:
        try:
            return deepcopy(self._alert_contexts[alert_id])
        except KeyError as exc:
            raise SourceRecordNotFound(f"alert_id={alert_id}") from exc

    def get_customer_context(self, customer_id: int) -> dict[str, Any]:
        try:
            return deepcopy(self._customer_contexts[customer_id])
        except KeyError as exc:
            raise SourceRecordNotFound(f"customer_id={customer_id}") from exc

    def get_case_context(self, case_id: int) -> dict[str, Any]:
        try:
            return deepcopy(self._case_contexts[case_id])
        except KeyError as exc:
            raise SourceRecordNotFound(f"case_id={case_id}") from exc

    def get_open_cases_for_customer(
        self,
        customer_id: int,
        max_rows: int = 100,
    ) -> list[dict[str, Any]]:
        cases = [
            deepcopy(context["case"])
            for context in self._case_contexts.values()
            if context["case"].get("customer_id") == customer_id
            and context["case"].get("status") in {"open", "under_review", "escalated"}
        ]
        return cases[:max_rows]

    def get_customer_transactions_for_baseline(
        self,
        customer_id: int,
        transaction_id: int,
        lookback_days: int,
        max_rows: int,
    ) -> list[dict[str, Any]]:
        context = self.get_customer_context(customer_id)
        transactions = list(context.get("recent_transactions") or [])
        current = next(
            (tx for tx in transactions if tx.get("transaction_id") == transaction_id),
            None,
        )
        current_dt = parse_datetime(current.get("created_at")) if current else None
        rows = []
        for tx in transactions:
            if tx.get("transaction_id") == transaction_id:
                continue
            if current_dt:
                tx_dt = parse_datetime(tx.get("created_at"))
                if tx_dt and abs((current_dt - tx_dt).days) > lookback_days:
                    continue
            rows.append(deepcopy(tx))
        return rows[: max(1, min(100, int(max_rows)))]

    def get_similar_alerts_for_customer(
        self,
        customer_id: int,
        transaction_type: str,
        amount_usd: float,
        amount_tolerance_pct: float,
        lookback_days: int,
        max_rows: int,
    ) -> list[dict[str, Any]]:
        context = self.get_customer_context(customer_id)
        transactions = {
            tx.get("transaction_id"): tx
            for tx in context.get("recent_transactions") or []
            if tx.get("transaction_id") is not None
        }
        lower = amount_usd * (1 - amount_tolerance_pct / 100)
        upper = amount_usd * (1 + amount_tolerance_pct / 100)
        rows = []
        for alert in context.get("prior_alerts") or []:
            tx = transactions.get(alert.get("transaction_id"), {})
            candidate_type = alert.get("transaction_type") or tx.get("transaction_type")
            candidate_amount = float(alert.get("amount_usd") or tx.get("amount_usd") or 0)
            if candidate_type != transaction_type:
                continue
            if not (lower <= candidate_amount <= upper):
                continue
            merged = deepcopy(alert)
            merged.setdefault("transaction_type", candidate_type)
            merged.setdefault("amount_usd", candidate_amount)
            rows.append(merged)
        return rows[: max(1, min(100, int(max_rows)))]

    def _high_risk_alert_context(self) -> dict[str, Any]:
        recent_transactions = [
            {
                "transaction_id": 7001,
                "account_id": 3001,
                "transaction_type": "cash",
                "amount_usd": 9750.0,
                "destination_country": None,
                "created_at": "2026-06-05T09:20:00+00:00",
                "status": "completed",
            },
            {
                "transaction_id": 7002,
                "account_id": 3001,
                "transaction_type": "cash",
                "amount_usd": 9650.0,
                "destination_country": None,
                "created_at": "2026-06-05T11:40:00+00:00",
                "status": "completed",
            },
            {
                "transaction_id": 7003,
                "account_id": 3001,
                "transaction_type": "cash",
                "amount_usd": 9700.0,
                "destination_country": None,
                "created_at": "2026-06-05T15:10:00+00:00",
                "status": "completed",
            },
            {
                "transaction_id": 7004,
                "account_id": 3001,
                "transaction_type": "wire",
                "amount_usd": 42000.0,
                "destination_country": "IR",
                "created_at": "2026-06-06T08:30:00+00:00",
                "status": "completed",
            },
        ]
        return {
            "alert": {
                "alert_id": 1001,
                "transaction_id": 7004,
                "rule_id": 4,
                "severity": "critical",
                "status": "open",
                "created_at": "2026-06-06T08:35:00+00:00",
            },
            "rule": {
                "rule_id": 4,
                "rule_name": "High Risk Country Transfer",
                "rule_type": "geography",
                "severity": "critical",
            },
            "transaction": recent_transactions[-1],
            "account": {
                "account_id": 3001,
                "customer_id": 501,
                "branch_id": 17,
                "account_number": "ACC00003001",
                "account_type": "business",
                "currency_code": "USD",
                "status": "active",
            },
            "customer": {
                "customer_id": 501,
                "full_name": "Ari Kim",
                "nationality": "KR",
                "occupation": "Importer",
                "risk_level": "high",
                "kyc_status": "verified",
                "is_active": True,
            },
            "destination_country": {
                "country_code": "IR",
                "country_name": "Iran",
                "fatf_status": "blacklist",
                "risk_score": 9.8,
                "is_sanctioned": True,
            },
            "pattern": {
                "pattern_id": 8101,
                "customer_id": 501,
                "avg_transaction": 1200.0,
                "max_transaction": 8500.0,
                "monthly_volume": 18000.0,
                "typical_countries": "KR,US,SG",
                "international_pct": 8.0,
                "cash_pct": 12.0,
            },
            "recent_transactions": recent_transactions,
            "prior_alerts": [
                {
                    "alert_id": 9101,
                    "transaction_id": 7001,
                    "severity": "critical",
                    "status": "resolved",
                    "created_at": "2026-06-05T09:25:00+00:00",
                },
                {
                    "alert_id": 9102,
                    "transaction_id": 7002,
                    "severity": "critical",
                    "status": "resolved",
                    "created_at": "2026-06-05T11:45:00+00:00",
                },
            ],
            "sanctions_matches": [],
            "pep_matches": [],
        }

    def _ordinary_alert_context(self) -> dict[str, Any]:
        return {
            "alert": {
                "alert_id": 1002,
                "transaction_id": 7010,
                "rule_id": 2,
                "severity": "high",
                "status": "open",
                "created_at": "2026-06-06T10:35:00+00:00",
            },
            "rule": {
                "rule_id": 2,
                "rule_name": "Large Wire Transfer",
                "rule_type": "threshold",
                "severity": "high",
            },
            "transaction": {
                "transaction_id": 7010,
                "account_id": 3002,
                "transaction_type": "wire",
                "amount_usd": 52000.0,
                "destination_country": "GB",
                "created_at": "2026-06-06T10:30:00+00:00",
                "status": "completed",
            },
            "account": {
                "account_id": 3002,
                "customer_id": 502,
                "branch_id": 17,
                "account_number": "ACC00003002",
                "account_type": "business",
                "currency_code": "USD",
                "status": "active",
            },
            "customer": {
                "customer_id": 502,
                "full_name": "Morgan Lee",
                "nationality": "GB",
                "occupation": "Exporter",
                "risk_level": "medium",
                "kyc_status": "verified",
                "is_active": True,
            },
            "destination_country": {
                "country_code": "GB",
                "country_name": "United Kingdom",
                "fatf_status": "whitelist",
                "risk_score": 0.8,
                "is_sanctioned": False,
            },
            "pattern": {
                "pattern_id": 8102,
                "customer_id": 502,
                "avg_transaction": 44000.0,
                "max_transaction": 90000.0,
                "monthly_volume": 820000.0,
                "typical_countries": "GB,US,DE",
                "international_pct": 45.0,
                "cash_pct": 1.0,
            },
            "recent_transactions": [
                {
                    "transaction_id": 7010,
                    "account_id": 3002,
                    "transaction_type": "wire",
                    "amount_usd": 52000.0,
                    "destination_country": "GB",
                    "created_at": "2026-06-06T10:30:00+00:00",
                    "status": "completed",
                }
            ],
            "prior_alerts": [],
            "sanctions_matches": [],
            "pep_matches": [],
        }

    def _high_cash_baseline_context(self) -> dict[str, Any]:
        historical = [
            (7031, 9100.0, "2026-06-01T09:00:00+00:00"),
            (7032, 9200.0, "2026-05-28T10:00:00+00:00"),
            (7033, 9300.0, "2026-05-24T11:00:00+00:00"),
            (7034, 9400.0, "2026-05-20T12:00:00+00:00"),
            (7035, 9500.0, "2026-05-16T13:00:00+00:00"),
            (7036, 9600.0, "2026-05-12T14:00:00+00:00"),
            (7037, 9700.0, "2026-05-08T15:00:00+00:00"),
            (7038, 9800.0, "2026-05-04T16:00:00+00:00"),
            (7039, 9000.0, "2026-04-30T17:00:00+00:00"),
            (7041, 9900.0, "2026-04-26T18:00:00+00:00"),
        ]
        recent_transactions = [
            {
                "transaction_id": 7030,
                "account_id": 3003,
                "transaction_type": "cash",
                "amount_usd": 9500.0,
                "destination_country": None,
                "counterparty_account_id": None,
                "created_at": "2026-06-06T09:00:00+00:00",
                "status": "completed",
            },
            *[
                {
                    "transaction_id": tid,
                    "account_id": 3003,
                    "transaction_type": "cash",
                    "amount_usd": amount,
                    "destination_country": None,
                    "counterparty_account_id": None,
                    "created_at": created,
                    "status": "completed",
                }
                for tid, amount, created in historical
            ],
        ]
        return {
            "alert": {
                "alert_id": 1003,
                "transaction_id": 7030,
                "rule_id": 6,
                "severity": "critical",
                "status": "open",
                "created_at": "2026-06-06T09:05:00+00:00",
            },
            "rule": {
                "rule_id": 6,
                "rule_name": "Structuring Detection",
                "rule_type": "structuring",
                "severity": "critical",
            },
            "transaction": recent_transactions[0],
            "account": {
                "account_id": 3003,
                "customer_id": 503,
                "branch_id": 17,
                "account_number": "ACC00003003",
                "account_type": "business",
                "currency_code": "USD",
                "status": "active",
            },
            "customer": {
                "customer_id": 503,
                "full_name": "Cash Retail LLC",
                "nationality": "US",
                "occupation": "Retail Merchant",
                "risk_level": "medium",
                "kyc_status": "verified",
                "is_active": True,
            },
            "destination_country": None,
            "pattern": {
                "pattern_id": 8103,
                "customer_id": 503,
                "avg_transaction": 9450.0,
                "max_transaction": 9900.0,
                "monthly_volume": 190000.0,
                "typical_countries": "US",
                "international_pct": 0.0,
                "cash_pct": 90.0,
            },
            "recent_transactions": recent_transactions,
            "prior_alerts": [
                {
                    "alert_id": 9301,
                    "transaction_id": 7035,
                    "severity": "medium",
                    "status": "dismissed",
                    "created_at": "2026-05-16T13:05:00+00:00",
                },
                {
                    "alert_id": 9302,
                    "transaction_id": 7036,
                    "severity": "medium",
                    "status": "dismissed",
                    "created_at": "2026-05-12T14:05:00+00:00",
                },
            ],
            "sanctions_matches": [],
            "pep_matches": [],
        }

    def _low_cash_baseline_context(self) -> dict[str, Any]:
        historical = [
            (7041, "transfer_domestic", 120.0, "2026-06-01T09:00:00+00:00", 4101),
            (7042, "transfer_domestic", 180.0, "2026-05-28T10:00:00+00:00", 4102),
            (7043, "wire", 250.0, "2026-05-24T11:00:00+00:00", 4103),
            (7044, "transfer_domestic", 300.0, "2026-05-20T12:00:00+00:00", 4104),
            (7045, "wire", 450.0, "2026-05-16T13:00:00+00:00", 4105),
            (7046, "transfer_domestic", 500.0, "2026-05-12T14:00:00+00:00", 4106),
            (7047, "transfer_domestic", 700.0, "2026-05-08T15:00:00+00:00", 4107),
            (7048, "wire", 900.0, "2026-05-04T16:00:00+00:00", 4108),
            (7049, "transfer_domestic", 1100.0, "2026-04-30T17:00:00+00:00", 4109),
            (7050, "wire", 1500.0, "2026-04-26T18:00:00+00:00", 4110),
        ]
        recent_transactions = [
            {
                "transaction_id": 7040,
                "account_id": 3004,
                "transaction_type": "cash",
                "amount_usd": 9500.0,
                "destination_country": None,
                "counterparty_account_id": None,
                "created_at": "2026-06-06T10:00:00+00:00",
                "status": "completed",
            },
            *[
                {
                    "transaction_id": tid,
                    "account_id": 3004,
                    "transaction_type": tx_type,
                    "amount_usd": amount,
                    "destination_country": None,
                    "counterparty_account_id": counterparty,
                    "created_at": created,
                    "status": "completed",
                }
                for tid, tx_type, amount, created, counterparty in historical
            ],
        ]
        return {
            "alert": {
                "alert_id": 1004,
                "transaction_id": 7040,
                "rule_id": 6,
                "severity": "critical",
                "status": "open",
                "created_at": "2026-06-06T10:05:00+00:00",
            },
            "rule": {
                "rule_id": 6,
                "rule_name": "Structuring Detection",
                "rule_type": "structuring",
                "severity": "critical",
            },
            "transaction": recent_transactions[0],
            "account": {
                "account_id": 3004,
                "customer_id": 504,
                "branch_id": 17,
                "account_number": "ACC00003004",
                "account_type": "checking",
                "currency_code": "USD",
                "status": "active",
            },
            "customer": {
                "customer_id": 504,
                "full_name": "Low Cash Customer",
                "nationality": "US",
                "occupation": "Engineer",
                "risk_level": "low",
                "kyc_status": "verified",
                "is_active": True,
            },
            "destination_country": None,
            "pattern": {
                "pattern_id": 8104,
                "customer_id": 504,
                "avg_transaction": 650.0,
                "max_transaction": 1500.0,
                "monthly_volume": 9000.0,
                "typical_countries": "US",
                "international_pct": 0.0,
                "cash_pct": 0.0,
            },
            "recent_transactions": recent_transactions,
            "prior_alerts": [
                {
                    "alert_id": 9401,
                    "transaction_id": 7040,
                    "transaction_type": "cash",
                    "amount_usd": 9600.0,
                    "severity": "critical",
                    "status": "escalated",
                    "created_at": "2026-05-01T10:05:00+00:00",
                }
            ],
            "sanctions_matches": [],
            "pep_matches": [],
        }

    def _insufficient_history_context(self) -> dict[str, Any]:
        recent_transactions = [
            {
                "transaction_id": 7051,
                "account_id": 3005,
                "transaction_type": "cash",
                "amount_usd": 9500.0,
                "destination_country": None,
                "counterparty_account_id": None,
                "created_at": "2026-06-06T11:00:00+00:00",
                "status": "completed",
            },
            {
                "transaction_id": 7052,
                "account_id": 3005,
                "transaction_type": "cash",
                "amount_usd": 500.0,
                "destination_country": None,
                "counterparty_account_id": None,
                "created_at": "2026-06-01T11:00:00+00:00",
                "status": "completed",
            },
            {
                "transaction_id": 7053,
                "account_id": 3005,
                "transaction_type": "cash",
                "amount_usd": 700.0,
                "destination_country": None,
                "counterparty_account_id": None,
                "created_at": "2026-05-28T11:00:00+00:00",
                "status": "completed",
            },
        ]
        return {
            "alert": {
                "alert_id": 1005,
                "transaction_id": 7051,
                "rule_id": 6,
                "severity": "critical",
                "status": "open",
                "created_at": "2026-06-06T11:05:00+00:00",
            },
            "rule": {
                "rule_id": 6,
                "rule_name": "Structuring Detection",
                "rule_type": "structuring",
                "severity": "critical",
            },
            "transaction": recent_transactions[0],
            "account": {
                "account_id": 3005,
                "customer_id": 505,
                "branch_id": 17,
                "account_number": "ACC00003005",
                "account_type": "checking",
                "currency_code": "USD",
                "status": "active",
            },
            "customer": {
                "customer_id": 505,
                "full_name": "New Cash Customer",
                "nationality": "US",
                "occupation": "Consultant",
                "risk_level": "medium",
                "kyc_status": "verified",
                "is_active": True,
            },
            "destination_country": None,
            "pattern": {
                "pattern_id": 8105,
                "customer_id": 505,
                "avg_transaction": 600.0,
                "max_transaction": 700.0,
                "monthly_volume": 1200.0,
                "typical_countries": "US",
                "international_pct": 0.0,
                "cash_pct": 100.0,
            },
            "recent_transactions": recent_transactions,
            "prior_alerts": [],
            "sanctions_matches": [],
            "pep_matches": [],
        }

    def _customer_context_from_alert(self, alert_id: int) -> dict[str, Any]:
        context = self._alert_contexts[alert_id]
        return {
            "customer": deepcopy(context["customer"]),
            "accounts": [deepcopy(context["account"])],
            "latest_pattern": deepcopy(context["pattern"]),
            "recent_transactions": deepcopy(context["recent_transactions"]),
            "open_alerts": [deepcopy(context["alert"])],
            "prior_alerts": deepcopy(context["prior_alerts"]),
            "sanctions_matches": deepcopy(context["sanctions_matches"]),
            "pep_matches": deepcopy(context["pep_matches"]),
        }

    def _case_context(self) -> dict[str, Any]:
        alert_context = self._high_risk_alert_context()
        return {
            "case": {
                "case_id": 9001,
                "customer_id": 501,
                "case_type": "AML",
                "status": "under_review",
                "priority": "critical",
                "opened_at": "2026-06-06T12:00:00+00:00",
                "summary": "Potential structuring followed by high-risk country transfer.",
            },
            "customer": deepcopy(alert_context["customer"]),
            "linked_alerts": [
                deepcopy(alert_context["alert"]),
                deepcopy(alert_context["prior_alerts"][0]),
                deepcopy(alert_context["prior_alerts"][1]),
            ],
            "transactions": deepcopy(alert_context["recent_transactions"]),
            "comments": [
                {
                    "comment_id": 4401,
                    "alert_id": 1001,
                    "officer_id": 72,
                    "comment": "Customer activity deviates from baseline.",
                    "created_at": "2026-06-06T12:30:00+00:00",
                }
            ],
        }
