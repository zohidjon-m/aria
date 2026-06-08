from __future__ import annotations

from typing import Any

import psycopg2
import psycopg2.extras

from .source import SourceRecordNotFound


class PostgresBankSourceRepository:
    """Read-only PostgreSQL adapter for the bank source system.

    This adapter never accepts arbitrary SQL. Every query is an allowlisted,
    parameterized statement owned by this codebase.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _connect(self):
        conn = psycopg2.connect(self._dsn)
        conn.set_session(readonly=True, autocommit=True)
        return conn

    def _one(self, sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                return dict(row) if row else None

    def _many(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(row) for row in cur.fetchall()]

    def get_alert_context(self, alert_id: int) -> dict[str, Any]:
        alert = self._one("SELECT * FROM alerts WHERE alert_id = %s", (alert_id,))
        if not alert:
            raise SourceRecordNotFound(f"alert_id={alert_id}")

        transaction = self._one(
            "SELECT * FROM transactions WHERE transaction_id = %s",
            (alert["transaction_id"],),
        )
        if not transaction:
            raise SourceRecordNotFound(f"transaction_id={alert['transaction_id']}")

        account = self._one(
            "SELECT * FROM accounts WHERE account_id = %s",
            (transaction["account_id"],),
        )
        if not account:
            raise SourceRecordNotFound(f"account_id={transaction['account_id']}")

        customer = self._one(
            "SELECT * FROM customers WHERE customer_id = %s",
            (account["customer_id"],),
        )
        if not customer:
            raise SourceRecordNotFound(f"customer_id={account['customer_id']}")

        rule = self._one(
            "SELECT * FROM compliance_rules WHERE rule_id = %s",
            (alert["rule_id"],),
        )
        destination_country = None
        if transaction.get("destination_country"):
            destination_country = self._one(
                "SELECT * FROM countries WHERE country_code = %s",
                (transaction["destination_country"],),
            )

        pattern = self._one(
            """
            SELECT *
            FROM transaction_patterns
            WHERE customer_id = %s
            ORDER BY computed_at DESC
            LIMIT 1
            """,
            (customer["customer_id"],),
        )
        recent_transactions = self._many(
            """
            SELECT t.*
            FROM transactions t
            JOIN accounts a ON a.account_id = t.account_id
            WHERE a.customer_id = %s
            ORDER BY t.created_at DESC
            LIMIT 100
            """,
            (customer["customer_id"],),
        )
        prior_alerts = self._many(
            """
            SELECT al.*
            FROM alerts al
            JOIN transactions t ON t.transaction_id = al.transaction_id
            JOIN accounts a ON a.account_id = t.account_id
            WHERE a.customer_id = %s
              AND al.alert_id <> %s
            ORDER BY al.created_at DESC
            LIMIT 50
            """,
            (customer["customer_id"], alert_id),
        )
        sanctions_matches = self._screen_sanctions(customer["full_name"])
        pep_matches = self._screen_pep(customer["full_name"])

        return {
            "alert": alert,
            "rule": rule,
            "transaction": transaction,
            "account": account,
            "customer": customer,
            "destination_country": destination_country,
            "pattern": pattern,
            "recent_transactions": recent_transactions,
            "prior_alerts": prior_alerts,
            "sanctions_matches": sanctions_matches,
            "pep_matches": pep_matches,
        }

    def get_customer_context(self, customer_id: int) -> dict[str, Any]:
        customer = self._one("SELECT * FROM customers WHERE customer_id = %s", (customer_id,))
        if not customer:
            raise SourceRecordNotFound(f"customer_id={customer_id}")

        accounts = self._many(
            "SELECT * FROM accounts WHERE customer_id = %s ORDER BY opened_at DESC",
            (customer_id,),
        )
        latest_pattern = self._one(
            """
            SELECT *
            FROM transaction_patterns
            WHERE customer_id = %s
            ORDER BY computed_at DESC
            LIMIT 1
            """,
            (customer_id,),
        )
        recent_transactions = self._many(
            """
            SELECT t.*
            FROM transactions t
            JOIN accounts a ON a.account_id = t.account_id
            WHERE a.customer_id = %s
            ORDER BY t.created_at DESC
            LIMIT 100
            """,
            (customer_id,),
        )
        open_alerts = self._many(
            """
            SELECT al.*
            FROM alerts al
            JOIN transactions t ON t.transaction_id = al.transaction_id
            JOIN accounts a ON a.account_id = t.account_id
            WHERE a.customer_id = %s
              AND al.status IN ('open', 'under_review', 'escalated')
            ORDER BY al.created_at DESC
            LIMIT 50
            """,
            (customer_id,),
        )
        prior_alerts = self._many(
            """
            SELECT al.*
            FROM alerts al
            JOIN transactions t ON t.transaction_id = al.transaction_id
            JOIN accounts a ON a.account_id = t.account_id
            WHERE a.customer_id = %s
            ORDER BY al.created_at DESC
            LIMIT 100
            """,
            (customer_id,),
        )

        return {
            "customer": customer,
            "accounts": accounts,
            "latest_pattern": latest_pattern,
            "recent_transactions": recent_transactions,
            "open_alerts": open_alerts,
            "prior_alerts": prior_alerts,
            "sanctions_matches": self._screen_sanctions(customer["full_name"]),
            "pep_matches": self._screen_pep(customer["full_name"]),
        }

    def get_case_context(self, case_id: int) -> dict[str, Any]:
        case = self._one("SELECT * FROM cases WHERE case_id = %s", (case_id,))
        if not case:
            raise SourceRecordNotFound(f"case_id={case_id}")

        customer = self._one(
            "SELECT * FROM customers WHERE customer_id = %s",
            (case["customer_id"],),
        )
        linked_alerts = self._many(
            """
            SELECT al.*
            FROM case_alerts ca
            JOIN alerts al ON al.alert_id = ca.alert_id
            WHERE ca.case_id = %s
            ORDER BY al.created_at
            """,
            (case_id,),
        )
        transactions = self._many(
            """
            SELECT t.*
            FROM case_alerts ca
            JOIN alerts al ON al.alert_id = ca.alert_id
            JOIN transactions t ON t.transaction_id = al.transaction_id
            WHERE ca.case_id = %s
            ORDER BY t.created_at
            """,
            (case_id,),
        )
        comments = self._many(
            """
            SELECT ac.*
            FROM alert_comments ac
            JOIN case_alerts ca ON ca.alert_id = ac.alert_id
            WHERE ca.case_id = %s
            ORDER BY ac.created_at
            """,
            (case_id,),
        )
        return {
            "case": case,
            "customer": customer,
            "linked_alerts": linked_alerts,
            "transactions": transactions,
            "comments": comments,
        }

    def get_open_cases_for_customer(
        self,
        customer_id: int,
        max_rows: int = 100,
    ) -> list[dict[str, Any]]:
        bounded_max_rows = max(1, min(100, int(max_rows)))
        return self._many(
            """
            SELECT *
            FROM cases
            WHERE customer_id = %s
              AND status IN ('open', 'under_review', 'escalated')
            ORDER BY opened_at DESC
            LIMIT %s
            """,
            (customer_id, bounded_max_rows),
        )

    def get_customer_transactions_for_baseline(
        self,
        customer_id: int,
        transaction_id: int,
        lookback_days: int,
        max_rows: int,
    ) -> list[dict[str, Any]]:
        bounded_lookback_days = max(1, min(365, int(lookback_days)))
        bounded_max_rows = max(1, min(100, int(max_rows)))
        return self._many(
            """
            SELECT t.*
            FROM transactions t
            JOIN accounts a ON a.account_id = t.account_id
            JOIN transactions anchor ON anchor.transaction_id = %s
            WHERE a.customer_id = %s
              AND t.transaction_id <> %s
              AND t.created_at >= anchor.created_at - (%s * INTERVAL '1 day')
              AND t.created_at <= anchor.created_at
            ORDER BY t.created_at DESC
            LIMIT %s
            """,
            (
                transaction_id,
                customer_id,
                transaction_id,
                bounded_lookback_days,
                bounded_max_rows,
            ),
        )

    def get_similar_alerts_for_customer(
        self,
        customer_id: int,
        transaction_type: str,
        amount_usd: float,
        amount_tolerance_pct: float,
        lookback_days: int,
        max_rows: int,
    ) -> list[dict[str, Any]]:
        bounded_lookback_days = max(1, min(365, int(lookback_days)))
        bounded_max_rows = max(1, min(100, int(max_rows)))
        bounded_tolerance_pct = max(1.0, min(50.0, float(amount_tolerance_pct)))
        tolerance_amount = float(amount_usd) * (bounded_tolerance_pct / 100)
        return self._many(
            """
            SELECT
                al.*,
                t.transaction_type,
                t.amount_usd,
                t.destination_country,
                t.counterparty_account_id
            FROM alerts al
            JOIN transactions t ON t.transaction_id = al.transaction_id
            JOIN accounts a ON a.account_id = t.account_id
            WHERE a.customer_id = %s
              AND t.transaction_type = %s
              AND ABS(t.amount_usd - %s) <= %s
              AND al.created_at >= NOW() - (%s * INTERVAL '1 day')
            ORDER BY al.created_at DESC
            LIMIT %s
            """,
            (
                customer_id,
                transaction_type,
                float(amount_usd),
                tolerance_amount,
                bounded_lookback_days,
                bounded_max_rows,
            ),
        )

    def _screen_sanctions(self, full_name: str) -> list[dict[str, Any]]:
        return self._many(
            """
            SELECT *
            FROM sanctions_list
            WHERE is_active = TRUE
              AND lower(full_name) = lower(%s)
            LIMIT 20
            """,
            (full_name,),
        )

    def _screen_pep(self, full_name: str) -> list[dict[str, Any]]:
        return self._many(
            """
            SELECT *
            FROM pep_list
            WHERE is_active = TRUE
              AND lower(full_name) = lower(%s)
            LIMIT 20
            """,
            (full_name,),
        )
