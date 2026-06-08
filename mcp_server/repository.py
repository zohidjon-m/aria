from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
import os
from typing import Any, Protocol

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv


class ReferenceRepository(Protocol):
    def get_alert_scope(self, alert_id: int) -> dict[str, Any] | None:
        ...

    def get_customer_profile(self, customer_id: int) -> dict[str, Any]:
        ...

    def get_transaction_history(
        self,
        customer_id: int,
        *,
        max_rows: int,
        lookback_days: int,
    ) -> list[dict[str, Any]]:
        ...

    def get_behavioral_baseline(
        self,
        customer_id: int,
        alert_id: int,
        *,
        max_rows: int,
        lookback_days: int,
    ) -> dict[str, Any]:
        ...

    def get_prior_alerts(
        self,
        customer_id: int,
        alert_id: int | None,
        *,
        max_rows: int,
    ) -> list[dict[str, Any]]:
        ...

    def get_case_history(self, customer_id: int, *, max_rows: int) -> dict[str, Any]:
        ...

    def trace_counterparty_graph(
        self,
        alert_id: int,
        *,
        max_hops: int,
        max_rows: int,
    ) -> dict[str, Any]:
        ...

    def screen_sanctions_pep(self, customer_id: int) -> dict[str, Any]:
        ...

    def get_similar_alerts(
        self,
        customer_id: int,
        alert_id: int,
        *,
        max_rows: int,
    ) -> list[dict[str, Any]]:
        ...

    def get_compliance_rule(self, alert_id: int) -> dict[str, Any] | None:
        ...


class PostgresReferenceRepository:
    """Schema-backed read repository for the reference MCP server."""

    def __init__(self, database_url: str | None = None) -> None:
        load_dotenv()
        self.database_url = (
            database_url
            or os.getenv("DEMO_DATABASE_URL")
            or os.getenv("DATABASE_URL")
            or os.getenv("BANK_SOURCE_DSN")
        )
        if not self.database_url:
            raise ValueError(
                "Set DEMO_DATABASE_URL, DATABASE_URL, or BANK_SOURCE_DSN for the reference MCP server."
            )

    def _connect(self):
        conn = psycopg2.connect(self.database_url)
        conn.autocommit = True
        return conn

    def _query(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, tuple(params or ()))
                if cur.description is None:
                    return []
                return [_json_safe(dict(row)) for row in cur.fetchall()]

    def get_alert_scope(self, alert_id: int) -> dict[str, Any] | None:
        rows = self._query(
            """
            SELECT
                al.alert_id,
                al.transaction_id,
                acc.account_id,
                acc.customer_id
            FROM alerts al
            JOIN transactions tx ON tx.transaction_id = al.transaction_id
            JOIN accounts acc ON acc.account_id = tx.account_id
            WHERE al.alert_id = %s
            """,
            (alert_id,),
        )
        return rows[0] if rows else None

    def get_customer_profile(self, customer_id: int) -> dict[str, Any]:
        customer = self._one(
            """
            SELECT c.*, country.country_name, country.fatf_status AS nationality_fatf_status
            FROM customers c
            LEFT JOIN countries country ON country.country_code = c.nationality
            WHERE c.customer_id = %s
            """,
            (customer_id,),
        )
        accounts = self._query(
            """
            SELECT * FROM accounts
            WHERE customer_id = %s
            ORDER BY opened_at DESC, account_id
            """,
            (customer_id,),
        )
        pattern = self._one(
            """
            SELECT * FROM transaction_patterns
            WHERE customer_id = %s
            ORDER BY computed_at DESC
            LIMIT 1
            """,
            (customer_id,),
        )
        return {"customer": customer, "accounts": accounts, "latest_pattern": pattern}

    def get_transaction_history(
        self,
        customer_id: int,
        *,
        max_rows: int,
        lookback_days: int,
    ) -> list[dict[str, Any]]:
        return self._query(
            """
            SELECT
                tx.*,
                acc.customer_id,
                country.country_name AS destination_country_name,
                country.fatf_status AS destination_fatf_status,
                country.risk_score AS destination_risk_score,
                country.is_sanctioned AS destination_is_sanctioned
            FROM transactions tx
            JOIN accounts acc ON acc.account_id = tx.account_id
            LEFT JOIN countries country ON country.country_code = tx.destination_country
            WHERE acc.customer_id = %s
              AND tx.created_at >= NOW() - (%s || ' days')::interval
            ORDER BY tx.created_at DESC, tx.transaction_id DESC
            LIMIT %s
            """,
            (customer_id, lookback_days, max_rows),
        )

    def get_behavioral_baseline(
        self,
        customer_id: int,
        alert_id: int,
        *,
        max_rows: int,
        lookback_days: int,
    ) -> dict[str, Any]:
        current = self._one(
            """
            SELECT tx.*
            FROM alerts al
            JOIN transactions tx ON tx.transaction_id = al.transaction_id
            WHERE al.alert_id = %s
            """,
            (alert_id,),
        )
        pattern = self._one(
            """
            SELECT * FROM transaction_patterns
            WHERE customer_id = %s
            ORDER BY computed_at DESC
            LIMIT 1
            """,
            (customer_id,),
        )
        historical = self._query(
            """
            SELECT tx.*
            FROM transactions tx
            JOIN accounts acc ON acc.account_id = tx.account_id
            WHERE acc.customer_id = %s
              AND tx.transaction_id <> %s
              AND tx.created_at >= COALESCE(%s::timestamptz, NOW()) - (%s || ' days')::interval
            ORDER BY tx.created_at DESC, tx.transaction_id DESC
            LIMIT %s
            """,
            (
                customer_id,
                (current or {}).get("transaction_id", -1),
                (current or {}).get("created_at"),
                lookback_days,
                max_rows,
            ),
        )
        features = _baseline_features(current or {}, historical, pattern or {})
        return {
            "current_transaction": current,
            "historical_transactions": historical,
            "latest_pattern": pattern,
            "computed_features": features,
        }

    def get_prior_alerts(
        self,
        customer_id: int,
        alert_id: int | None,
        *,
        max_rows: int,
    ) -> list[dict[str, Any]]:
        return self._query(
            """
            SELECT
                al.*,
                rule.rule_name,
                rule.rule_type,
                tx.amount_usd,
                tx.transaction_type
            FROM alerts al
            JOIN transactions tx ON tx.transaction_id = al.transaction_id
            JOIN accounts acc ON acc.account_id = tx.account_id
            JOIN compliance_rules rule ON rule.rule_id = al.rule_id
            WHERE acc.customer_id = %s
              AND (%s::int IS NULL OR al.alert_id <> %s)
            ORDER BY al.created_at DESC, al.alert_id DESC
            LIMIT %s
            """,
            (customer_id, alert_id, alert_id, max_rows),
        )

    def get_case_history(self, customer_id: int, *, max_rows: int) -> dict[str, Any]:
        cases = self._query(
            """
            SELECT * FROM cases
            WHERE customer_id = %s
            ORDER BY opened_at DESC, case_id DESC
            LIMIT %s
            """,
            (customer_id, max_rows),
        )
        case_ids = [case["case_id"] for case in cases]
        if not case_ids:
            return {"cases": [], "linked_alerts": [], "comments": []}
        linked_alerts = self._query(
            """
            SELECT ca.case_id, al.*, rule.rule_name, rule.rule_type
            FROM case_alerts ca
            JOIN alerts al ON al.alert_id = ca.alert_id
            JOIN compliance_rules rule ON rule.rule_id = al.rule_id
            WHERE ca.case_id = ANY(%s)
            ORDER BY ca.added_at DESC
            """,
            (case_ids,),
        )
        comments = self._query(
            """
            SELECT ac.*
            FROM alert_comments ac
            JOIN case_alerts ca ON ca.alert_id = ac.alert_id
            WHERE ca.case_id = ANY(%s)
            ORDER BY ac.created_at DESC
            """,
            (case_ids,),
        )
        return {"cases": cases, "linked_alerts": linked_alerts, "comments": comments}

    def trace_counterparty_graph(
        self,
        alert_id: int,
        *,
        max_hops: int,
        max_rows: int,
    ) -> dict[str, Any]:
        anchor = self._one(
            """
            SELECT tx.*
            FROM alerts al
            JOIN transactions tx ON tx.transaction_id = al.transaction_id
            WHERE al.alert_id = %s
            """,
            (alert_id,),
        )
        if not anchor:
            return _empty_graph()

        frontier = {int(anchor["account_id"])}
        reached = set(frontier)
        paths = []
        active_paths = [
            {
                "account_path": [int(anchor["account_id"])],
                "transaction_ids": [],
                "amount_usd_path": [],
            }
        ]
        edges: dict[int, dict[str, Any]] = {}

        for hop in range(1, max_hops + 1):
            if not frontier or len(edges) >= max_rows:
                break
            rows = self._query(
                """
                SELECT
                    tx.*,
                    source_acc.customer_id AS source_customer_id,
                    source_customer.risk_level AS source_customer_risk_level,
                    counter_acc.customer_id AS counterparty_customer_id,
                    counter_acc.status AS counterparty_account_status,
                    counter_customer.risk_level AS counterparty_customer_risk_level,
                    country.fatf_status AS country_fatf_status,
                    country.risk_score AS country_risk_score,
                    country.is_sanctioned AS country_is_sanctioned
                FROM transactions tx
                JOIN accounts source_acc ON source_acc.account_id = tx.account_id
                JOIN customers source_customer ON source_customer.customer_id = source_acc.customer_id
                LEFT JOIN accounts counter_acc ON counter_acc.account_id = tx.counterparty_account_id
                LEFT JOIN customers counter_customer ON counter_customer.customer_id = counter_acc.customer_id
                LEFT JOIN countries country ON country.country_code = tx.destination_country
                WHERE tx.counterparty_account_id IS NOT NULL
                  AND (tx.account_id = ANY(%s) OR tx.counterparty_account_id = ANY(%s))
                ORDER BY tx.created_at, tx.transaction_id
                LIMIT %s
                """,
                (list(frontier), list(frontier), max_rows - len(edges)),
            )
            next_frontier: set[int] = set()
            next_paths = []
            for row in rows:
                txid = int(row["transaction_id"])
                edges.setdefault(txid, row)
                source_account = int(row["account_id"])
                counterparty = row.get("counterparty_account_id")
                if counterparty is None:
                    continue
                counterparty = int(counterparty)
                for path in active_paths:
                    if source_account != int(path["account_path"][-1]):
                        continue
                    if txid in path["transaction_ids"]:
                        continue
                    extended = {
                        "account_path": [*path["account_path"], counterparty],
                        "transaction_ids": [*path["transaction_ids"], txid],
                        "amount_usd_path": [*path["amount_usd_path"], row.get("amount_usd")],
                        "hop_count": hop,
                    }
                    paths.append(extended)
                    next_paths.append(extended)
                    if counterparty not in reached:
                        next_frontier.add(counterparty)
                        reached.add(counterparty)
            active_paths = next_paths
            frontier = next_frontier

        edge_list = list(edges.values())[:max_rows]
        linked_alerts = self._linked_alerts([edge["transaction_id"] for edge in edge_list])
        linked_cases = self._linked_cases(edge_list)
        signals = _graph_signals(edge_list, paths, linked_alerts, linked_cases)
        return {
            "start_transaction": anchor,
            "paths": paths,
            "edges": edge_list,
            "reached_accounts": sorted(reached),
            "linked_alerts": linked_alerts,
            "linked_cases": linked_cases,
            "computed_features": {"signals": signals},
        }

    def screen_sanctions_pep(self, customer_id: int) -> dict[str, Any]:
        customer = self._one(
            "SELECT * FROM customers WHERE customer_id = %s",
            (customer_id,),
        )
        name = (customer or {}).get("full_name")
        if not name:
            return {"customer": customer, "sanctions_matches": [], "pep_matches": []}
        sanctions = self._query(
            """
            SELECT * FROM sanctions_list
            WHERE is_active = TRUE AND lower(full_name) = lower(%s)
            ORDER BY sanction_id
            """,
            (name,),
        )
        peps = self._query(
            """
            SELECT * FROM pep_list
            WHERE is_active = TRUE AND lower(full_name) = lower(%s)
            ORDER BY pep_id
            """,
            (name,),
        )
        return {"customer": customer, "sanctions_matches": sanctions, "pep_matches": peps}

    def get_similar_alerts(
        self,
        customer_id: int,
        alert_id: int,
        *,
        max_rows: int,
    ) -> list[dict[str, Any]]:
        anchor = self._one(
            """
            SELECT tx.transaction_type, tx.amount_usd, al.rule_id
            FROM alerts al
            JOIN transactions tx ON tx.transaction_id = al.transaction_id
            WHERE al.alert_id = %s
            """,
            (alert_id,),
        )
        if not anchor:
            return []
        return self._query(
            """
            SELECT al.*, tx.transaction_type, tx.amount_usd, rule.rule_name, rule.rule_type
            FROM alerts al
            JOIN transactions tx ON tx.transaction_id = al.transaction_id
            JOIN accounts acc ON acc.account_id = tx.account_id
            JOIN compliance_rules rule ON rule.rule_id = al.rule_id
            WHERE acc.customer_id = %s
              AND al.alert_id <> %s
              AND al.rule_id = %s
              AND tx.transaction_type = %s
              AND tx.amount_usd BETWEEN %s AND %s
            ORDER BY al.created_at DESC, al.alert_id DESC
            LIMIT %s
            """,
            (
                customer_id,
                alert_id,
                anchor["rule_id"],
                anchor["transaction_type"],
                float(anchor["amount_usd"]) * 0.85,
                float(anchor["amount_usd"]) * 1.15,
                max_rows,
            ),
        )

    def get_compliance_rule(self, alert_id: int) -> dict[str, Any] | None:
        return self._one(
            """
            SELECT rule.*, al.alert_id, al.transaction_id, al.severity AS alert_severity
            FROM alerts al
            JOIN compliance_rules rule ON rule.rule_id = al.rule_id
            WHERE al.alert_id = %s
            """,
            (alert_id,),
        )

    def _linked_alerts(self, transaction_ids: list[int]) -> list[dict[str, Any]]:
        if not transaction_ids:
            return []
        return self._query(
            "SELECT * FROM alerts WHERE transaction_id = ANY(%s) ORDER BY alert_id",
            (transaction_ids,),
        )

    def _linked_cases(self, edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
        customer_ids = {
            int(value)
            for edge in edges
            for value in (edge.get("source_customer_id"), edge.get("counterparty_customer_id"))
            if value is not None
        }
        if not customer_ids:
            return []
        return self._query(
            """
            SELECT * FROM cases
            WHERE customer_id = ANY(%s)
              AND status IN ('open', 'under_review', 'escalated')
            ORDER BY opened_at DESC, case_id DESC
            """,
            (list(customer_ids),),
        )

    def _one(self, sql: str, params: Sequence[Any]) -> dict[str, Any] | None:
        rows = self._query(sql, params)
        return rows[0] if rows else None


def _baseline_features(
    current: dict[str, Any],
    historical: list[dict[str, Any]],
    pattern: dict[str, Any],
) -> dict[str, Any]:
    amounts = [float(tx.get("amount_usd") or 0) for tx in historical]
    amount = float(current.get("amount_usd") or 0)
    tx_type = str(current.get("transaction_type") or "")
    type_counts: dict[str, int] = {}
    countries = set()
    counterparties = set()
    same_day_count = 1
    current_day = str(current.get("created_at") or "")[:10]
    for tx in historical:
        observed_type = str(tx.get("transaction_type") or "")
        type_counts[observed_type] = type_counts.get(observed_type, 0) + 1
        if tx.get("destination_country"):
            countries.add(str(tx["destination_country"]))
        if tx.get("counterparty_account_id") is not None:
            counterparties.add(int(tx["counterparty_account_id"]))
        if current_day and str(tx.get("created_at") or "")[:10] == current_day:
            same_day_count += 1

    historical_count = len(historical)
    amount_percentile = None
    if amounts:
        amount_percentile = round(
            sum(1 for candidate in amounts if candidate <= amount) / len(amounts) * 100,
            2,
        )
    transaction_type_count = type_counts.get(tx_type, 0)
    transaction_type_share = (
        round(transaction_type_count / historical_count * 100, 2)
        if historical_count
        else 0.0
    )
    new_country = bool(current.get("destination_country")) and str(current["destination_country"]) not in countries
    new_counterparty = (
        current.get("counterparty_account_id") is not None
        and int(current["counterparty_account_id"]) not in counterparties
    )
    deviation_points = 0
    factors: list[str] = []
    if historical_count < 5:
        assessment = "insufficient_data"
        factors.append("insufficient_history")
    else:
        if amount_percentile is not None and amount_percentile >= 95:
            deviation_points += 2
            factors.append("amount_percentile_extreme")
        if transaction_type_count == 0:
            deviation_points += 2
            factors.append("transaction_type_unseen")
        elif transaction_type_share < 10:
            deviation_points += 1
            factors.append("transaction_type_rare")
        if new_country:
            deviation_points += 1
            factors.append("new_destination_country")
        if new_counterparty:
            deviation_points += 1
            factors.append("new_counterparty")
        if same_day_count >= 10:
            deviation_points += 1
            factors.append("same_day_velocity")
        assessment = (
            "consistent"
            if deviation_points == 0
            else "mild_deviation"
            if deviation_points <= 2
            else "strong_deviation"
        )

    return {
        "historical_transaction_count": historical_count,
        "amount_usd": amount,
        "amount_percentile": amount_percentile,
        "average_transaction_amount": round(sum(amounts) / len(amounts), 2) if amounts else None,
        "max_transaction_amount": max(amounts) if amounts else None,
        "transaction_type_counts": type_counts,
        "transaction_type_share": transaction_type_share,
        "same_day_transaction_count": same_day_count,
        "new_destination_country": new_country,
        "new_counterparty": new_counterparty,
        "pattern_cash_pct": pattern.get("cash_pct"),
        "pattern_international_pct": pattern.get("international_pct"),
        "deviation_points": deviation_points,
        "assessment_factors": factors,
        "baseline_assessment": assessment,
    }


def _graph_signals(
    edges: list[dict[str, Any]],
    paths: list[dict[str, Any]],
    linked_alerts: list[dict[str, Any]],
    linked_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    fan_out: dict[int, set[int]] = {}
    many_to_one: dict[int, set[int]] = {}
    for edge in edges:
        source = edge.get("account_id")
        counterparty = edge.get("counterparty_account_id")
        if source is None or counterparty is None:
            continue
        fan_out.setdefault(int(source), set()).add(int(counterparty))
        many_to_one.setdefault(int(counterparty), set()).add(int(source))
    return {
        "rapid_pass_through": _rapid_pass_through(edges),
        "cycle_detected": any(
            len(path.get("account_path", [])) != len(set(path.get("account_path", [])))
            for path in paths
        ),
        "fan_out": any(len(values) >= 3 for values in fan_out.values()),
        "many_to_one": any(len(values) >= 3 for values in many_to_one.values()),
        "high_risk_endpoint": any(_high_risk_edge(edge) for edge in edges),
        "linked_alert_count": len({alert.get("alert_id") for alert in linked_alerts}),
        "linked_open_case_count": len({case.get("case_id") for case in linked_cases}),
    }


def _rapid_pass_through(edges: list[dict[str, Any]]) -> bool:
    for inbound in edges:
        intermediate = inbound.get("counterparty_account_id")
        if intermediate is None:
            continue
        inbound_dt = _parse_dt(inbound.get("created_at"))
        inbound_amount = float(inbound.get("amount_usd") or 0)
        for outbound in edges:
            if outbound.get("account_id") != intermediate:
                continue
            outbound_dt = _parse_dt(outbound.get("created_at"))
            if not inbound_dt or not outbound_dt:
                continue
            hours = (outbound_dt - inbound_dt).total_seconds() / 3600
            if 0 <= hours <= 24 and float(outbound.get("amount_usd") or 0) >= inbound_amount * 0.8:
                return True
    return False


def _high_risk_edge(edge: dict[str, Any]) -> bool:
    risk = str(edge.get("counterparty_customer_risk_level") or "").lower()
    status = str(edge.get("counterparty_account_status") or "").lower()
    fatf = str(edge.get("country_fatf_status") or "").lower()
    return (
        risk in {"high", "critical"}
        or status in {"frozen", "suspended"}
        or fatf in {"blacklist", "greylist"}
        or bool(edge.get("country_is_sanctioned"))
        or bool(edge.get("is_flagged"))
        or float(edge.get("country_risk_score") or 0) >= 4
    )


def _empty_graph() -> dict[str, Any]:
    return {
        "start_transaction": None,
        "paths": [],
        "edges": [],
        "reached_accounts": [],
        "linked_alerts": [],
        "linked_cases": [],
        "computed_features": {"signals": _graph_signals([], [], [], [])},
    }


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
