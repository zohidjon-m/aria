from __future__ import annotations

from typing import Any, Protocol


class SourceRecordNotFound(KeyError):
    pass


class BankSourceRepository(Protocol):
    """Read-only access contract for the bank source system."""

    def get_alert_context(self, alert_id: int) -> dict[str, Any]:
        ...

    def get_customer_context(self, customer_id: int) -> dict[str, Any]:
        ...

    def get_case_context(self, case_id: int) -> dict[str, Any]:
        ...

    def get_open_cases_for_customer(
        self,
        customer_id: int,
        max_rows: int = 100,
    ) -> list[dict[str, Any]]:
        ...

    def get_customer_transactions_for_baseline(
        self,
        customer_id: int,
        transaction_id: int,
        lookback_days: int,
        max_rows: int,
    ) -> list[dict[str, Any]]:
        ...

    def get_similar_alerts_for_customer(
        self,
        customer_id: int,
        transaction_type: str,
        amount_usd: float,
        amount_tolerance_pct: float,
        lookback_days: int,
        max_rows: int,
    ) -> list[dict[str, Any]]:
        ...
