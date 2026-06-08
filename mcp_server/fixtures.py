from __future__ import annotations

import os
from typing import Any

import psycopg2
from dotenv import load_dotenv


def load_phase1_fixtures(database_url: str | None = None) -> None:
    """Load deterministic phase 1 demo fixtures into a schema.sql database."""

    load_dotenv()
    dsn = (
        database_url
        or os.getenv("DEMO_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("BANK_SOURCE_DSN")
    )
    if not dsn:
        raise ValueError("Set DEMO_DATABASE_URL, DATABASE_URL, or BANK_SOURCE_DSN.")
    with psycopg2.connect(dsn) as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            _insert_fixtures(cur)
        conn.commit()


def _insert_fixtures(cur: Any) -> None:
    _sync_serial_sequences(cur)
    cur.executemany(
        """
        INSERT INTO countries (country_code, country_name, fatf_status, risk_score, is_sanctioned)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (country_code) DO UPDATE SET
            country_name = EXCLUDED.country_name,
            fatf_status = EXCLUDED.fatf_status,
            risk_score = EXCLUDED.risk_score,
            is_sanctioned = EXCLUDED.is_sanctioned
        """,
        [
            ("US", "United States", "whitelist", 0.5, False),
            ("GB", "United Kingdom", "whitelist", 0.8, False),
            ("KR", "South Korea", "whitelist", 1.0, False),
            ("IR", "Iran", "blacklist", 9.8, True),
        ],
    )
    cur.execute(
        """
        INSERT INTO officer_roles (
            role_id, role_name, can_view_alerts, can_manage_cases, can_file_sar,
            can_manage_rules, can_manage_users, description
        )
        VALUES (1, 'phase1_demo_officer', TRUE, TRUE, FALSE, FALSE, FALSE, 'Phase 1 demo officer')
        ON CONFLICT (role_id) DO UPDATE SET role_name = EXCLUDED.role_name
        """
    )
    cur.execute(
        """
        INSERT INTO branches (branch_id, branch_name, city, country_code, address, phone, is_active)
        VALUES (17, 'Phase 1 Demo Branch', 'Seoul', 'KR', 'Demo address', '000-0000', TRUE)
        ON CONFLICT (branch_id) DO UPDATE SET branch_name = EXCLUDED.branch_name
        """
    )
    cur.execute(
        """
        INSERT INTO compliance_officers (
            officer_id, role_id, branch_id, full_name, email, phone, is_active
        )
        VALUES (72, 1, 17, 'Phase One Officer', 'phase1-officer@example.invalid', '000-0000', TRUE)
        ON CONFLICT (officer_id) DO UPDATE SET full_name = EXCLUDED.full_name
        """
    )
    cur.executemany(
        """
        INSERT INTO compliance_rules (
            rule_id, rule_name, rule_type, threshold_amount, max_frequency,
            time_window_days, applies_to, severity, is_active
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)
        ON CONFLICT (rule_id) DO UPDATE SET
            rule_name = EXCLUDED.rule_name,
            rule_type = EXCLUDED.rule_type,
            threshold_amount = EXCLUDED.threshold_amount,
            severity = EXCLUDED.severity
        """,
        [
            (2, "Large Wire Transfer", "threshold", 50000.00, None, None, "all", "high"),
            (4, "High Risk Country Transfer", "geography", None, None, None, "international", "critical"),
            (6, "Structuring Detection", "structuring", 9000.00, 3, 1, "all", "critical"),
        ],
    )
    cur.executemany(
        """
        INSERT INTO customers (
            customer_id, full_name, email, phone, nationality, occupation,
            risk_level, kyc_status, is_active
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)
        ON CONFLICT (customer_id) DO UPDATE SET
            full_name = EXCLUDED.full_name,
            risk_level = EXCLUDED.risk_level,
            kyc_status = EXCLUDED.kyc_status
        """,
        [
            (501, "Ari Kim", "ari-kim@example.invalid", "000", "KR", "Importer", "high", "verified"),
            (503, "Cash Retail LLC", "cash-retail@example.invalid", "000", "US", "Retail Merchant", "medium", "verified"),
            (506, "Graph Ambiguous LLC", "graph-ambiguous@example.invalid", "000", "US", "Exporter", "medium", "verified"),
            (650, "Pass Through LLC", "pass-through@example.invalid", "000", "US", "Payment Processor", "high", "verified"),
        ],
    )
    cur.executemany(
        """
        INSERT INTO accounts (
            account_id, customer_id, branch_id, account_number, account_type,
            currency_code, balance, status
        )
        VALUES (%s, %s, 17, %s, %s, 'USD', %s, %s)
        ON CONFLICT (account_id) DO UPDATE SET
            customer_id = EXCLUDED.customer_id,
            account_number = EXCLUDED.account_number,
            status = EXCLUDED.status
        """,
        [
            (3001, 501, "PHASE10003001", "business", 100000.00, "active"),
            (3003, 503, "PHASE10003003", "business", 90000.00, "active"),
            (3006, 506, "PHASE10003006", "business", 120000.00, "active"),
            (4500, 650, "PHASE10004500", "business", 75000.00, "active"),
            (4600, 650, "PHASE10004600", "business", 50000.00, "active"),
        ],
    )
    cur.executemany(
        """
        INSERT INTO transactions (
            transaction_id, account_id, counterparty_account_id, transaction_type,
            amount, amount_usd, currency_code, destination_country, description,
            reference_number, status, is_flagged, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, 'USD', %s, %s, %s, 'completed', %s, %s)
        ON CONFLICT (transaction_id) DO UPDATE SET
            account_id = EXCLUDED.account_id,
            counterparty_account_id = EXCLUDED.counterparty_account_id,
            amount_usd = EXCLUDED.amount_usd,
            destination_country = EXCLUDED.destination_country,
            is_flagged = EXCLUDED.is_flagged
        """,
        [
            (7001, 3001, None, "cash", 9750, 9750, None, "Cash deposit", "PHASE1-TXN-7001", True, "2026-06-05T09:20:00+00:00"),
            (7002, 3001, None, "cash", 9650, 9650, None, "Cash deposit", "PHASE1-TXN-7002", True, "2026-06-05T11:40:00+00:00"),
            (7003, 3001, None, "cash", 9700, 9700, None, "Cash deposit", "PHASE1-TXN-7003", True, "2026-06-05T15:10:00+00:00"),
            (7004, 3001, None, "wire", 42000, 42000, "IR", "High risk destination wire", "PHASE1-TXN-7004", True, "2026-06-06T08:30:00+00:00"),
            (7030, 3003, None, "cash", 9500, 9500, None, "Routine cash retail activity", "PHASE1-TXN-7030", False, "2026-06-06T09:00:00+00:00"),
            (7031, 3003, None, "cash", 9100, 9100, None, "Routine cash retail activity", "PHASE1-TXN-7031", False, "2026-06-01T09:00:00+00:00"),
            (7032, 3003, None, "cash", 9200, 9200, None, "Routine cash retail activity", "PHASE1-TXN-7032", False, "2026-05-28T10:00:00+00:00"),
            (7033, 3003, None, "cash", 9300, 9300, None, "Routine cash retail activity", "PHASE1-TXN-7033", False, "2026-05-24T11:00:00+00:00"),
            (7034, 3003, None, "cash", 9400, 9400, None, "Routine cash retail activity", "PHASE1-TXN-7034", False, "2026-05-20T12:00:00+00:00"),
            (7035, 3003, None, "cash", 9500, 9500, None, "Routine cash retail activity", "PHASE1-TXN-7035", False, "2026-05-16T13:00:00+00:00"),
            (7036, 3003, None, "cash", 9600, 9600, None, "Routine cash retail activity", "PHASE1-TXN-7036", False, "2026-05-12T14:00:00+00:00"),
            (7037, 3003, None, "cash", 9700, 9700, None, "Routine cash retail activity", "PHASE1-TXN-7037", False, "2026-05-08T15:00:00+00:00"),
            (7038, 3003, None, "cash", 9800, 9800, None, "Routine cash retail activity", "PHASE1-TXN-7038", False, "2026-05-04T16:00:00+00:00"),
            (7060, 3006, 4500, "wire", 52000, 52000, "GB", "Ambiguous export payment", "PHASE1-TXN-7060", True, "2026-06-06T10:30:00+00:00"),
            (8061, 4500, 4600, "wire", 50000, 50000, None, "Rapid pass-through", "PHASE1-TXN-8061", True, "2026-06-06T13:00:00+00:00"),
        ],
    )
    cur.executemany(
        """
        INSERT INTO alerts (
            alert_id, transaction_id, rule_id, assigned_to, severity, status,
            is_escalated, created_at, notes
        )
        VALUES (%s, %s, %s, 72, %s, %s, %s, %s, %s)
        ON CONFLICT (alert_id) DO UPDATE SET
            transaction_id = EXCLUDED.transaction_id,
            rule_id = EXCLUDED.rule_id,
            severity = EXCLUDED.severity,
            status = EXCLUDED.status,
            is_escalated = EXCLUDED.is_escalated
        """,
        [
            (1001, 7004, 4, "critical", "open", False, "2026-06-06T08:35:00+00:00", "High risk country transfer."),
            (1003, 7030, 6, "critical", "open", False, "2026-06-06T09:05:00+00:00", "Cash-band alert for cash retailer."),
            (1006, 7060, 2, "high", "open", False, "2026-06-06T10:35:00+00:00", "Large wire with graph ambiguity."),
            (9301, 7035, 6, "medium", "dismissed", False, "2026-05-16T13:05:00+00:00", "Prior similar alert dismissed."),
            (9901, 8061, 2, "high", "open", False, "2026-06-06T13:05:00+00:00", "Linked graph alert."),
        ],
    )
    cur.executemany(
        """
        INSERT INTO transaction_patterns (
            pattern_id, customer_id, avg_transaction, max_transaction, monthly_volume,
            typical_countries, international_pct, cash_pct
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (pattern_id) DO UPDATE SET
            avg_transaction = EXCLUDED.avg_transaction,
            max_transaction = EXCLUDED.max_transaction,
            monthly_volume = EXCLUDED.monthly_volume,
            typical_countries = EXCLUDED.typical_countries,
            international_pct = EXCLUDED.international_pct,
            cash_pct = EXCLUDED.cash_pct
        """,
        [
            (8101, 501, 1200, 8500, 18000, "KR,US,SG", 8, 12),
            (8103, 503, 9450, 9900, 190000, "US", 0, 90),
            (8106, 506, 42000, 65000, 500000, "GB,US", 35, 0),
        ],
    )
    cur.execute(
        """
        INSERT INTO cases (
            case_id, customer_id, officer_id, case_type, status, priority,
            opened_at, summary
        )
        VALUES (9902, 650, 72, 'AML', 'open', 'high', '2026-06-06T13:10:00+00:00', 'Open graph endpoint case.')
        ON CONFLICT (case_id) DO UPDATE SET status = EXCLUDED.status
        """
    )
    cur.execute(
        """
        INSERT INTO case_alerts (case_id, alert_id, added_by)
        VALUES (9902, 9901, 72)
        ON CONFLICT (case_id, alert_id) DO NOTHING
        """
    )


def _sync_serial_sequences(cur: Any) -> None:
    """Keep trigger-generated IDs from colliding with explicitly seeded rows."""

    for table_name, column_name in (
        ("countries", "country_code"),
        ("officer_roles", "role_id"),
        ("branches", "branch_id"),
        ("compliance_officers", "officer_id"),
        ("compliance_rules", "rule_id"),
        ("customers", "customer_id"),
        ("accounts", "account_id"),
        ("transactions", "transaction_id"),
        ("alerts", "alert_id"),
        ("transaction_patterns", "pattern_id"),
        ("cases", "case_id"),
    ):
        cur.execute(
            """
            SELECT pg_get_serial_sequence(%s, %s)
            """,
            (table_name, column_name),
        )
        sequence = cur.fetchone()[0]
        if not sequence:
            continue
        cur.execute(
            f"""
            SELECT setval(%s, COALESCE((SELECT MAX({column_name}) FROM {table_name}), 1), TRUE)
            """,
            (sequence,),
        )
