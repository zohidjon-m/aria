"""
Banking Compliance System — Database Seeder
Connects directly to PostgreSQL and inserts a large, internally-consistent
sample dataset.

Design goals (consistency / linkage):
  * Sanctions & PEP list entries reuse REAL customer names, so screening hits
    (full_name ILIKE) actually fire and tie to risk_level.
  * Transaction behaviour is correlated with customer risk_level (high-risk
    customers transact larger, more international, more cash, more structuring).
  * amount_usd is the driver; the local `amount` is back-computed from the FX
    rate, so threshold rules are meaningful regardless of currency.
  * Alerts are derived deterministically from the rulebook + sanctions linkage.
  * case_alerts only link alerts that belong to the SAME customer as the case.
  * transaction_patterns / monthly_reports are AGGREGATED from real rows.
  * risk_scores trend to a latest level that matches customers.risk_level.

Usage:
    pip install faker psycopg2-binary
    python seed_database.py
"""

import os
import psycopg2
from psycopg2.extras import execute_batch
from faker import Faker
import random
from collections import defaultdict
from datetime import date, datetime, timedelta

# ── CONFIG ──────────────────────────────────────────────────────────────────
# Honours standard libpq env vars (PGHOST/PGPORT/...) so the same script runs
# locally (defaults to localhost) and inside Docker (PGHOST=db).
DB_CONFIG = {
    "host":     os.getenv("PGHOST", "localhost"),
    "port":     int(os.getenv("PGPORT", "5432")),
    "dbname":   os.getenv("PGDATABASE", "aml_platform"),
    "user":     os.getenv("PGUSER", "postgres"),
    "password": os.getenv("PGPASSWORD", "postgres"),
}

N_OFFICERS       = 30
N_CUSTOMERS      = 250
N_TRANSACTIONS   = 2500
N_CASES          = 90
N_AUDIT          = 300
N_SANCTIONED     = 12     # customers placed on the sanctions list
N_PEP            = 16     # customers placed on the PEP list
ACCOUNTS_PER_CUST = (1, 3)

# FX rates to USD (must cover every currency used by accounts)
RATE = {
    "USD": 1.0, "EUR": 1.08, "GBP": 1.27, "KRW": 0.00075, "JPY": 0.0067,
    "CNY": 0.138, "AED": 0.272, "TRY": 0.031, "RUB": 0.011, "CHF": 1.13,
    "AUD": 0.65, "SGD": 0.74, "UZS": 0.000079,
}

WHITELIST = ["US", "GB", "KR", "DE", "SG", "JP", "FR", "CH", "AU"]
GREYLIST  = ["UZ", "AE", "TR", "CN", "NG", "PK", "VN"]
BLACKLIST = ["RU", "IR", "KP", "MM"]
HIGH_RISK_NATIONS = GREYLIST + BLACKLIST

# nationality -> preferred branch ids
NAT_BRANCH = {"KR": [1, 2, 3], "GB": [4], "US": [5], "SG": [6], "DE": [7], "AU": [8]}
# branch id -> local currency
BRANCH_CCY = {1: "KRW", 2: "KRW", 3: "KRW", 4: "GBP", 5: "USD", 6: "SGD", 7: "EUR", 8: "AUD"}

RISK_WEIGHT = {"low": 1, "medium": 2, "high": 4, "critical": 7}

# ── SETUP ────────────────────────────────────────────────────────────────────
fake = Faker()
random.seed(42)
Faker.seed(42)

# cross-seeder state
STATE = {
    "sanctioned": [],      # list of (name, country)
    "pep": [],             # list of (name, position, country)
    "sanctioned_ids": set(),
    "pep_ids": set(),
}


def connect():
    return psycopg2.connect(**DB_CONFIG)


def truncate_all(conn):
    tables = [
        "audit_log", "monthly_reports", "transaction_patterns",
        "pep_list", "sanctions_list", "regulatory_reports",
        "risk_scores", "case_alerts", "cases",
        "alert_comments", "alerts", "compliance_rules",
        "transactions", "accounts", "customers",
        "compliance_officers", "branches",
        "currency_rates", "officer_roles", "countries",
    ]
    cur = conn.cursor()
    cur.execute("SET session_replication_role = replica;")
    for t in tables:
        cur.execute(f"TRUNCATE TABLE {t} RESTART IDENTITY CASCADE;")
    cur.execute("SET session_replication_role = DEFAULT;")
    conn.commit()
    cur.close()
    print("  All tables cleared.\n")


def run(label, fn, conn):
    print(f"  Seeding {label}...", end=" ", flush=True)
    cur = conn.cursor()
    result = fn(cur)
    conn.commit()
    cur.close()
    print("done")
    return result


def fix_sequences(conn):
    """Realign every serial sequence to MAX(id) (rows inserted with explicit ids
    do not advance the owning sequence)."""
    print("  Realigning sequences...", end=" ", flush=True)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT c.relname AS table_name, a.attname AS column_name
        FROM pg_class c
        JOIN pg_attribute a ON a.attrelid = c.oid
        WHERE c.relkind = 'r'
          AND c.relnamespace = 'public'::regnamespace
          AND pg_get_serial_sequence(c.relname, a.attname) IS NOT NULL
        """
    )
    targets = cur.fetchall()
    for table_name, column_name in targets:
        cur.execute(
            f"SELECT setval(pg_get_serial_sequence(%s, %s), "
            f"COALESCE((SELECT MAX({column_name}) FROM {table_name}), 1))",
            (table_name, column_name),
        )
    conn.commit()
    cur.close()
    print(f"done ({len(targets)} sequences)")


# ── REFERENCE DATA ────────────────────────────────────────────────────────────

def seed_countries(cur):
    data = [
        ("US", "United States", "whitelist", 0.5, False),
        ("GB", "United Kingdom", "whitelist", 0.8, False),
        ("KR", "South Korea", "whitelist", 1.0, False),
        ("DE", "Germany", "whitelist", 0.6, False),
        ("SG", "Singapore", "whitelist", 0.7, False),
        ("JP", "Japan", "whitelist", 0.5, False),
        ("FR", "France", "whitelist", 0.9, False),
        ("UZ", "Uzbekistan", "greylist", 4.5, False),
        ("AE", "UAE", "greylist", 5.2, False),
        ("TR", "Turkey", "greylist", 4.8, False),
        ("CN", "China", "greylist", 5.0, False),
        ("RU", "Russia", "blacklist", 8.5, True),
        ("IR", "Iran", "blacklist", 9.8, True),
        ("KP", "North Korea", "blacklist", 10.0, True),
        ("MM", "Myanmar", "blacklist", 8.2, True),
        ("NG", "Nigeria", "greylist", 6.1, False),
        ("PK", "Pakistan", "greylist", 5.8, False),
        ("VN", "Vietnam", "greylist", 4.2, False),
        ("CH", "Switzerland", "whitelist", 1.2, False),
        ("AU", "Australia", "whitelist", 0.6, False),
    ]
    execute_batch(cur, """
        INSERT INTO countries (country_code, country_name, fatf_status, risk_score, is_sanctioned, updated_at)
        VALUES (%s,%s,%s,%s,%s,NOW())
        ON CONFLICT DO NOTHING
    """, data)


def seed_officer_roles(cur):
    data = [
        (1, "junior_analyst", True, False, False, False, False, "Read-only analyst"),
        (2, "senior_analyst", True, True, False, False, False, "Can manage cases"),
        (3, "compliance_officer", True, True, True, False, False, "Can file SARs"),
        (4, "compliance_manager", True, True, True, True, True, "Full compliance access"),
        (5, "db_admin", True, True, True, True, True, "System administrator"),
    ]
    execute_batch(cur, """
        INSERT INTO officer_roles
            (role_id,role_name,can_view_alerts,can_manage_cases,can_file_sar,can_manage_rules,can_manage_users,description)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, data)


def seed_currency_rates(cur):
    names = {
        "USD": "US Dollar", "EUR": "Euro", "GBP": "British Pound", "KRW": "Korean Won",
        "JPY": "Japanese Yen", "CNY": "Chinese Yuan", "AED": "UAE Dirham", "TRY": "Turkish Lira",
        "RUB": "Russian Ruble", "CHF": "Swiss Franc", "AUD": "Australian Dollar",
        "SGD": "Singapore Dollar", "UZS": "Uzbek Som",
    }
    rows = [(code, names[code], rate, date.today()) for code, rate in RATE.items()]
    execute_batch(cur, """
        INSERT INTO currency_rates (currency_code, currency_name, rate_to_usd, rate_date)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (currency_code, rate_date) DO NOTHING
    """, rows)


def seed_branches(cur):
    data = [
        (1, "Seoul HQ Branch", "Seoul", "KR"),
        (2, "Gangnam Branch", "Seoul", "KR"),
        (3, "Busan Branch", "Busan", "KR"),
        (4, "London City Branch", "London", "GB"),
        (5, "New York Branch", "New York", "US"),
        (6, "Singapore Branch", "Singapore", "SG"),
        (7, "Frankfurt Branch", "Frankfurt", "DE"),
        (8, "Sydney Branch", "Sydney", "AU"),
    ]
    rows = [
        (bid, name, city, cc, fake.street_address(), fake.phone_number()[:20],
         True, fake.date_between(start_date='-10y', end_date='-2y'))
        for bid, name, city, cc in data
    ]
    execute_batch(cur, """
        INSERT INTO branches (branch_id,branch_name,city,country_code,address,phone,is_active,opened_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


def seed_officers(cur):
    rows = []
    for oid in range(1, N_OFFICERS + 1):
        rows.append((
            oid,
            random.choice([1, 1, 1, 2, 2, 3, 3, 4]),
            random.randint(1, 8),
            fake.name()[:100],
            fake.unique.email()[:150],
            fake.phone_number()[:20],
            True,
            fake.date_between(start_date='-8y', end_date='-6m'),
        ))
    execute_batch(cur, """
        INSERT INTO compliance_officers
            (officer_id,role_id,branch_id,full_name,email,phone,is_active,hired_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)

    cur.execute("SELECT officer_id, role_id FROM compliance_officers")
    seniors = [o[0] for o in cur.fetchall() if o[1] >= 3]
    for bid in range(1, 9):
        cur.execute("UPDATE branches SET manager_id=%s WHERE branch_id=%s",
                    (random.choice(seniors), bid))


# ── CUSTOMERS (with sanctions / PEP linkage) ──────────────────────────────────

def seed_customers(cur):
    occupations = ["Engineer", "Merchant", "Consultant", "Executive", "Trader",
                   "Doctor", "Lawyer", "Entrepreneur", "Professor", "Analyst",
                   "Import/Export", "Real Estate", "Crypto Trader", "Shipping Agent"]
    pep_positions = ["Minister of Finance", "Deputy Minister", "Central Bank Governor",
                     "Member of Parliament", "Ambassador", "Defense Official",
                     "State Enterprise Director", "Provincial Governor"]
    risk_pool = ["low"] * 55 + ["medium"] * 28 + ["high"] * 13 + ["critical"] * 4

    ids = list(range(1, N_CUSTOMERS + 1))
    sanctioned_ids = set(random.sample(ids, N_SANCTIONED))
    pep_ids = set(random.sample([i for i in ids if i not in sanctioned_ids], N_PEP))
    STATE["sanctioned_ids"] = sanctioned_ids
    STATE["pep_ids"] = pep_ids

    rows = []
    for cid in ids:
        created = fake.date_time_between(start_date='-6y', end_date='-1m')
        name = fake.name()[:150]

        if cid in sanctioned_ids:
            risk = "critical"
            nat = random.choice(BLACKLIST + GREYLIST)
            kyc = random.choice(["verified", "pending", "rejected"])
            STATE["sanctioned"].append((name, nat))
        elif cid in pep_ids:
            risk = random.choice(["high", "critical"])
            nat = random.choice(GREYLIST + ["RU"])
            kyc = random.choice(["verified", "verified", "pending"])
            STATE["pep"].append((name, random.choice(pep_positions), nat))
        else:
            risk = random.choice(risk_pool)
            if risk in ("high", "critical"):
                nat = random.choice(GREYLIST + WHITELIST)
            else:
                nat = random.choice(WHITELIST + WHITELIST + GREYLIST)
            kyc = random.choices(["verified", "pending", "expired", "rejected"],
                                 weights=[78, 13, 6, 3])[0]

        rows.append((
            cid, name, fake.unique.email()[:150], fake.phone_number()[:20],
            nat, fake.date_of_birth(minimum_age=22, maximum_age=78),
            random.choice(occupations), risk, kyc, True, created, created,
        ))
    execute_batch(cur, """
        INSERT INTO customers
            (customer_id,full_name,email,phone,nationality,date_of_birth,occupation,
             risk_level,kyc_status,is_active,created_at,updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


def seed_accounts(cur):
    acct_types = ["checking", "savings", "business", "investment"]
    cur.execute("SELECT customer_id, risk_level, nationality FROM customers ORDER BY customer_id")
    customers = cur.fetchall()

    rows = []
    aid = 1
    for cid, risk, nat in customers:
        n_acc = random.randint(*ACCOUNTS_PER_CUST)
        # critical-risk customers tend to spread across more accounts (layering)
        if risk == "critical":
            n_acc = max(n_acc, 2)
        for _ in range(n_acc):
            branch = random.choice(NAT_BRANCH.get(nat, list(range(1, 9))))
            # 55% USD, else the branch local currency
            ccy = "USD" if random.random() < 0.55 else BRANCH_CCY.get(branch, "USD")
            atype = random.choices(acct_types, weights=[45, 25, 20, 10])[0]
            base = random.uniform(2000, 60000)
            if atype in ("business", "investment"):
                base *= random.uniform(2, 6)
            if risk in ("high", "critical"):
                base *= random.uniform(1.5, 4)
            status = "active"
            if risk == "critical" and random.random() < 0.20:
                status = random.choice(["frozen", "suspended"])
            elif random.random() < 0.04:
                status = random.choice(["frozen", "suspended"])
            opened = fake.date_time_between(start_date='-6y', end_date='-3m')
            rows.append((aid, cid, branch, f"ACC{str(aid).zfill(8)}", atype, ccy,
                         round(base, 2), status, opened))
            aid += 1
    execute_batch(cur, """
        INSERT INTO accounts
            (account_id,customer_id,branch_id,account_number,account_type,
             currency_code,balance,status,opened_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


def _gen_amount_usd(risk):
    r = random.random()
    if risk in ("high", "critical"):
        if r < 0.14:
            return round(random.uniform(9000, 9999), 2)        # structuring
        if r < 0.34:
            return round(random.uniform(50000, 220000), 2)     # large wire
        if r < 0.50:
            return round(random.uniform(10000, 49999), 2)      # large
        return round(random.uniform(200, 9000), 2)
    if risk == "medium":
        if r < 0.05:
            return round(random.uniform(9000, 9999), 2)
        if r < 0.13:
            return round(random.uniform(50000, 120000), 2)
        if r < 0.22:
            return round(random.uniform(10000, 49999), 2)
        return round(random.uniform(100, 8000), 2)
    # low
    if r < 0.02:
        return round(random.uniform(10000, 28000), 2)
    return round(random.uniform(50, 6000), 2)


def seed_transactions(cur):
    cur.execute("""
        SELECT a.account_id, a.customer_id, a.currency_code, c.risk_level
        FROM accounts a JOIN customers c ON c.customer_id = a.customer_id
    """)
    accounts = cur.fetchall()
    acct_ids = [a[0] for a in accounts]
    weights = [RISK_WEIGHT.get(a[3], 1) for a in accounts]
    # pre-pick weighted accounts in one shot
    chosen = random.choices(range(len(accounts)), weights=weights, k=N_TRANSACTIONS)

    rows = []
    for tid, idx in enumerate(chosen, start=1):
        aid, cid, ccy, risk = accounts[idx]
        amount_usd = _gen_amount_usd(risk)

        # transaction type biased by risk
        if risk in ("high", "critical"):
            tx_type = random.choices(
                ["cash", "wire", "transfer_international", "transfer_domestic", "withdrawal", "deposit"],
                weights=[22, 22, 24, 14, 9, 9])[0]
        else:
            tx_type = random.choices(
                ["deposit", "withdrawal", "transfer_domestic", "transfer_international", "wire", "cash"],
                weights=[26, 20, 30, 9, 6, 9])[0]

        dest = None
        if tx_type in ("transfer_international", "wire"):
            if risk in ("high", "critical"):
                dest = random.choices(HIGH_RISK_NATIONS + WHITELIST, weights=[3] * len(HIGH_RISK_NATIONS) + [1] * len(WHITELIST))[0]
            else:
                dest = random.choices(WHITELIST + GREYLIST, weights=[4] * len(WHITELIST) + [1] * len(GREYLIST))[0]

        counterparty = None
        if tx_type in ("transfer_domestic", "transfer_international", "wire") and random.random() < 0.7:
            counterparty = random.choice([x for x in acct_ids if x != aid])

        amount_local = round(amount_usd / RATE.get(ccy, 1.0), 2)
        created = fake.date_time_between(start_date='-18M', end_date='now')
        rows.append((
            tid, aid, counterparty, tx_type, amount_local, amount_usd, ccy, dest,
            fake.sentence(nb_words=6)[:200], f"TXN{str(tid).zfill(8)}",
            random.choices(["completed", "pending", "failed", "reversed"], weights=[90, 6, 3, 1])[0],
            False, created,
        ))
    execute_batch(cur, """
        INSERT INTO transactions
            (transaction_id,account_id,counterparty_account_id,transaction_type,
             amount,amount_usd,currency_code,destination_country,description,
             reference_number,status,is_flagged,created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


def seed_compliance_rules(cur):
    data = [
        (1, "Large Cash Transaction", "threshold", 10000.00, None, None, "cash", "high"),
        (2, "Large Wire Transfer", "threshold", 50000.00, None, None, "all", "high"),
        (3, "Frequent International", "frequency", None, 5, 7, "international", "medium"),
        (4, "High Risk Country Transfer", "geography", None, None, None, "international", "critical"),
        (5, "Rapid Succession Transfers", "velocity", None, 10, 1, "all", "high"),
        (6, "Structuring Detection", "structuring", 9000.00, 3, 1, "all", "critical"),
        (7, "Sanctions Match", "sanctions", None, None, None, "all", "critical"),
    ]
    execute_batch(cur, """
        INSERT INTO compliance_rules
            (rule_id,rule_name,rule_type,threshold_amount,max_frequency,
             time_window_days,applies_to,severity,is_active,created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,TRUE,NOW())
        ON CONFLICT DO NOTHING
    """, data)


# ── ALERTS (derived from rulebook + sanctions linkage) ────────────────────────

def seed_alerts(cur):
    cur.execute("SELECT officer_id, branch_id FROM compliance_officers")
    officers = cur.fetchall()
    by_branch = defaultdict(list)
    for oid, bid in officers:
        by_branch[bid].append(oid)
    all_officers = [o[0] for o in officers]

    sanctioned_ids = STATE["sanctioned_ids"]

    cur.execute("""
        SELECT t.transaction_id, t.amount_usd, t.transaction_type,
               t.destination_country, t.created_at, a.customer_id, a.branch_id
        FROM transactions t
        JOIN accounts a ON a.account_id = t.account_id
        WHERE t.status <> 'failed'
        ORDER BY t.transaction_id
    """)
    txns = cur.fetchall()

    statuses = ["open", "under_review", "escalated", "dismissed", "resolved"]
    rows = []
    aid = 1
    for txid, amt, tx_type, dest, created, cid, branch in txns:
        amt = float(amt or 0)
        triggered = []  # (rule_id, severity)

        if amt >= 10000 and tx_type == "cash":
            triggered.append((1, "high"))
        if amt >= 50000:
            triggered.append((2, "high"))
        if dest in BLACKLIST:
            triggered.append((4, "critical"))
        elif dest in GREYLIST:
            triggered.append((4, "high"))
        if 9000 <= amt <= 9999:
            triggered.append((6, "critical"))
        if cid in sanctioned_ids and tx_type in ("wire", "transfer_international", "cash"):
            triggered.append((7, "critical"))
        # occasional frequency/velocity flavour on busy high-value tx
        if amt >= 20000 and random.random() < 0.06:
            triggered.append((3, "medium"))

        for rule_id, sev in triggered:
            status = random.choices(statuses, weights=[34, 24, 16, 13, 13])[0]
            a_created = created + timedelta(hours=random.randint(1, 72))
            resolved = None
            if status in ("dismissed", "resolved"):
                resolved = a_created + timedelta(days=random.randint(1, 25))
            assigned = random.choice(by_branch.get(branch) or all_officers)
            note = f"Auto-generated on rule #{rule_id}. " + fake.sentence()
            rows.append((aid, txid, rule_id, assigned, sev, status,
                         status == "escalated", a_created, resolved, note))
            aid += 1

    execute_batch(cur, """
        INSERT INTO alerts
            (alert_id,transaction_id,rule_id,assigned_to,severity,status,
             is_escalated,created_at,resolved_at,notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)

    # mark the underlying transactions as flagged
    cur.execute("""
        UPDATE transactions SET is_flagged = TRUE
        WHERE transaction_id IN (SELECT DISTINCT transaction_id FROM alerts)
    """)
    return len(rows)


def seed_alert_comments(cur):
    cur.execute("SELECT officer_id FROM compliance_officers")
    officer_ids = [r[0] for r in cur.fetchall()]
    # comment on alerts that are actively being worked
    cur.execute("""
        SELECT alert_id FROM alerts
        WHERE status IN ('under_review','escalated','resolved')
        ORDER BY created_at DESC LIMIT 120
    """)
    alert_ids = [r[0] for r in cur.fetchall()]
    rows = []
    cid = 1
    for alid in alert_ids:
        for _ in range(random.randint(1, 3)):
            rows.append((cid, alid, random.choice(officer_ids),
                         fake.paragraph(nb_sentences=2)[:500],
                         fake.date_time_between(start_date='-5m', end_date='now')))
            cid += 1
    execute_batch(cur, """
        INSERT INTO alert_comments (comment_id,alert_id,officer_id,comment,created_at)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


# ── CASES (opened on customers that actually have alerts) ─────────────────────

def seed_cases(cur):
    cur.execute("SELECT officer_id FROM compliance_officers")
    officer_ids = [r[0] for r in cur.fetchall()]

    # customers that have alerts, with their risk
    cur.execute("""
        SELECT DISTINCT a.customer_id, c.risk_level
        FROM alerts al
        JOIN transactions t ON t.transaction_id = al.transaction_id
        JOIN accounts a ON a.account_id = t.account_id
        JOIN customers c ON c.customer_id = a.customer_id
    """)
    alerted = {cid: risk for cid, risk in cur.fetchall()}

    # customers with a structuring alert
    cur.execute("""
        SELECT DISTINCT a.customer_id FROM alerts al
        JOIN transactions t ON t.transaction_id = al.transaction_id
        JOIN accounts a ON a.account_id = t.account_id
        WHERE al.rule_id = 6
    """)
    structuring = {r[0] for r in cur.fetchall()}
    sanctioned = STATE["sanctioned_ids"]

    priorities_by_risk = {
        "critical": ["critical", "critical", "high"],
        "high": ["high", "high", "medium"],
        "medium": ["medium", "medium", "low"],
        "low": ["low", "medium"],
    }
    statuses = ["open", "under_review", "escalated", "closed_clean", "closed_sar"]

    # guarantee a case for every alerted sanctioned customer first
    targets = []
    for cid in sorted(sanctioned & set(alerted)):
        targets.append((cid, "sanctions"))
    pool = list(alerted.keys())
    while len(targets) < N_CASES:
        cid = random.choice(pool)
        if cid in sanctioned:
            ctype = "sanctions"
        elif cid in structuring:
            ctype = "structuring"
        else:
            ctype = random.choices(["AML", "fraud", "KYC"], weights=[55, 30, 15])[0]
        targets.append((cid, ctype))

    rows = []
    for case_id, (cid, ctype) in enumerate(targets[:N_CASES], start=1):
        risk = alerted.get(cid, "medium")
        status = random.choices(statuses, weights=[24, 26, 16, 19, 15])[0]
        opened = fake.date_time_between(start_date='-14M', end_date='-1m')
        closed = None
        resolution = None
        if status in ("closed_clean", "closed_sar"):
            closed = opened + timedelta(days=random.randint(7, 90))
            resolution = fake.paragraph(nb_sentences=2)
        priority = random.choice(priorities_by_risk.get(risk, ["medium"]))
        summary = f"{ctype} investigation for customer #{cid}. " + fake.paragraph(nb_sentences=2)
        rows.append((case_id, cid, random.choice(officer_ids), ctype, status,
                     priority, opened, closed, summary, resolution))
    execute_batch(cur, """
        INSERT INTO cases
            (case_id,customer_id,officer_id,case_type,status,priority,
             opened_at,closed_at,summary,resolution)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


def seed_case_alerts(cur):
    # link each case ONLY to alerts belonging to that case's customer
    cur.execute("SELECT case_id, customer_id, officer_id, opened_at FROM cases ORDER BY case_id")
    cases = cur.fetchall()

    cust_alerts = defaultdict(list)
    cur.execute("""
        SELECT a.customer_id, al.alert_id
        FROM alerts al
        JOIN transactions t ON t.transaction_id = al.transaction_id
        JOIN accounts a ON a.account_id = t.account_id
    """)
    for cid, alid in cur.fetchall():
        cust_alerts[cid].append(alid)

    rows = []
    seen = set()
    for case_id, cust_id, officer_id, opened in cases:
        candidates = cust_alerts.get(cust_id, [])
        if not candidates:
            continue
        k = min(len(candidates), random.randint(1, 5))
        for alid in random.sample(candidates, k):
            if (case_id, alid) in seen:
                continue
            seen.add((case_id, alid))
            rows.append((case_id, alid, opened + timedelta(days=random.randint(0, 5)), officer_id))
    execute_batch(cur, """
        INSERT INTO case_alerts (case_id,alert_id,added_at,added_by)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


def seed_risk_scores(cur):
    base_map = {"low": 12, "medium": 38, "high": 66, "critical": 86}
    # actual alert counts per customer (for grounded reasoning)
    cur.execute("""
        SELECT a.customer_id, COUNT(*) AS n
        FROM alerts al
        JOIN transactions t ON t.transaction_id = al.transaction_id
        JOIN accounts a ON a.account_id = t.account_id
        GROUP BY a.customer_id
    """)
    alert_count = {cid: n for cid, n in cur.fetchall()}

    cur.execute("SELECT customer_id, risk_level FROM customers ORDER BY customer_id")
    customers = cur.fetchall()

    rows = []
    sid = 1
    for cid, risk in customers:
        base = base_map.get(risk, 20)
        n_hist = random.randint(1, 3)
        # ascending timestamps so the LAST score is the most recent
        times = sorted(fake.date_time_between(start_date='-1y', end_date='now') for _ in range(n_hist))
        for i, ts in enumerate(times):
            is_latest = (i == len(times) - 1)
            if is_latest:
                score = round(min(100, max(0, base + random.uniform(-4, 4))), 2)
                level = risk  # latest score agrees with the customer's risk_level
            else:
                score = round(min(100, max(0, base + random.uniform(-18, 6))), 2)
                level = ("low" if score < 25 else "medium" if score < 50
                         else "high" if score < 75 else "critical")
            n = alert_count.get(cid, 0)
            reasoning = (f"Risk {level}. {n} alert(s) linked to customer activity; "
                         f"base profile '{risk}'. " + fake.sentence())
            rows.append((sid, cid, score, level,
                         random.choice(["system", "system", "agent", "officer"]),
                         ts, reasoning[:480]))
            sid += 1
    execute_batch(cur, """
        INSERT INTO risk_scores
            (score_id,customer_id,score,score_level,computed_by,computed_at,reasoning)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


def seed_regulatory_reports(cur):
    cur.execute("SELECT case_id, opened_at FROM cases WHERE status='closed_sar' ORDER BY case_id")
    sar_cases = cur.fetchall()
    cur.execute("""
        SELECT o.officer_id FROM compliance_officers o
        JOIN officer_roles r ON r.role_id = o.role_id
        WHERE r.can_file_sar = TRUE
    """)
    filers = [r[0] for r in cur.fetchall()] or [1]
    regulators = ["FinCEN (US)", "FCA (UK)", "FSS (Korea)", "MAS (Singapore)", "BaFin (Germany)"]
    rows = []
    for i, (cid, opened) in enumerate(sar_cases, 1):
        submitted = opened + timedelta(days=random.randint(20, 80))
        rows.append((i, cid, random.choice(filers), random.choice(["SAR", "SAR", "STR", "CTR"]),
                     random.choice(regulators),
                     random.choice(["submitted", "acknowledged"]),
                     submitted, submitted + timedelta(days=30),
                     f"REF-{fake.bothify('??####').upper()}", submitted))
    execute_batch(cur, """
        INSERT INTO regulatory_reports
            (report_id,case_id,officer_id,report_type,regulator,status,
             submitted_at,deadline,reference_number,created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


# ── SCREENING LISTS (linked to real customers + padding) ──────────────────────

def seed_sanctions_list(cur):
    listed_by = ["US Treasury OFAC", "UN Security Council", "European Commission", "FATF"]
    stypes = ["OFAC SDN", "UN Security Council", "EU Sanctions", "Asset Freeze"]
    rows = []
    i = 1
    # real customers first -> screening actually hits
    for name, country in STATE["sanctioned"]:
        rows.append((i, name, "individual", country, random.choice(stypes),
                     random.choice(listed_by), fake.date_between(start_date='-8y', end_date='-6m'),
                     True, "Name match against onboarded customer."))
        i += 1
    # padding (non-customer) entries
    for _ in range(18):
        rows.append((i, fake.name(), random.choice(["individual", "organization", "vessel"]),
                     random.choice(BLACKLIST + GREYLIST), random.choice(stypes),
                     random.choice(listed_by), fake.date_between(start_date='-10y', end_date='-1y'),
                     True, fake.sentence()))
        i += 1
    execute_batch(cur, """
        INSERT INTO sanctions_list
            (sanction_id,full_name,entity_type,country_code,sanction_type,
             listed_by,listed_at,is_active,notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


def seed_pep_list(cur):
    rows = []
    i = 1
    for name, position, country in STATE["pep"]:
        rows.append((i, name, position, country,
                     random.choice(["domestic", "foreign", "international"]),
                     True, fake.date_between(start_date='-15y', end_date='-1y'),
                     "PEP match against onboarded customer."))
        i += 1
    positions = ["Minister", "Senator", "Governor", "Ambassador", "Judge", "Mayor"]
    for _ in range(16):
        rows.append((i, fake.name(), random.choice(positions),
                     random.choice(GREYLIST + BLACKLIST + ["US", "GB"]),
                     random.choice(["domestic", "foreign", "international"]),
                     True, fake.date_between(start_date='-15y', end_date='-1y'), fake.sentence()))
        i += 1
    execute_batch(cur, """
        INSERT INTO pep_list
            (pep_id,full_name,position,country_code,pep_level,is_active,since_date,notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


# ── ANALYTICS (aggregated from real rows) ─────────────────────────────────────

def seed_transaction_patterns(cur):
    # baseline computed from each customer's ACTUAL transactions
    cur.execute("""
        INSERT INTO transaction_patterns
            (customer_id, avg_transaction, max_transaction, monthly_volume,
             typical_countries, international_pct, cash_pct, computed_at)
        SELECT
            a.customer_id,
            ROUND(AVG(t.amount_usd), 2),
            ROUND(MAX(t.amount_usd), 2),
            ROUND(SUM(t.amount_usd) / GREATEST(COUNT(DISTINCT DATE_TRUNC('month', t.created_at)), 1), 2),
            COALESCE(string_agg(DISTINCT t.destination_country, ',')
                     FILTER (WHERE t.destination_country IS NOT NULL), ''),
            ROUND(100.0 * SUM(CASE WHEN t.transaction_type IN ('transfer_international','wire') THEN 1 ELSE 0 END) / COUNT(*), 2),
            ROUND(100.0 * SUM(CASE WHEN t.transaction_type = 'cash' THEN 1 ELSE 0 END) / COUNT(*), 2),
            NOW()
        FROM transactions t
        JOIN accounts a ON a.account_id = t.account_id
        GROUP BY a.customer_id
    """)


def seed_monthly_reports(cur):
    # transaction volume + alerts aggregated per branch / month
    cur.execute("""
        INSERT INTO monthly_reports
            (branch_id, report_month, total_transactions, total_volume_usd,
             total_alerts, total_cases, sars_filed, generated_at)
        SELECT
            a.branch_id,
            DATE_TRUNC('month', t.created_at)::date AS rmonth,
            COUNT(DISTINCT t.transaction_id),
            ROUND(COALESCE(SUM(t.amount_usd), 0), 2),
            COUNT(DISTINCT al.alert_id),
            0, 0, NOW()
        FROM accounts a
        JOIN transactions t ON t.account_id = a.account_id
        LEFT JOIN alerts al ON al.transaction_id = t.transaction_id
        GROUP BY a.branch_id, DATE_TRUNC('month', t.created_at)
    """)
    # backfill cases / SARs handled by each branch's officers that month
    cur.execute("""
        UPDATE monthly_reports m SET
            total_cases = COALESCE((
                SELECT COUNT(*) FROM cases cs
                JOIN compliance_officers o ON o.officer_id = cs.officer_id
                WHERE o.branch_id = m.branch_id
                  AND DATE_TRUNC('month', cs.opened_at)::date = m.report_month), 0),
            sars_filed = COALESCE((
                SELECT COUNT(*) FROM regulatory_reports rr
                JOIN cases cs ON cs.case_id = rr.case_id
                JOIN compliance_officers o ON o.officer_id = cs.officer_id
                WHERE o.branch_id = m.branch_id
                  AND rr.report_type = 'SAR'
                  AND DATE_TRUNC('month', rr.created_at)::date = m.report_month), 0)
    """)


def seed_audit_log(cur):
    cur.execute("SELECT officer_id FROM compliance_officers")
    officer_ids = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT case_id FROM cases")
    case_ids = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT alert_id FROM alerts ORDER BY created_at DESC LIMIT 200")
    alert_ids = [r[0] for r in cur.fetchall()]

    case_actions = ["case_opened", "case_closed", "status_change", "sar_filed", "case_note_added"]
    alert_actions = ["alert_assigned", "set_disposition", "add_comment", "agent_triage", "alert_escalated"]
    other_actions = ["officer_login", "risk_score_updated", "rule_modified"]

    rows = []
    for i in range(1, N_AUDIT + 1):
        officer = random.choice(officer_ids)
        roll = random.random()
        if roll < 0.45 and case_ids:
            cid = random.choice(case_ids)
            action = random.choice(case_actions)
            rows.append((i, officer, cid, None, action, "case", cid,
                         f"{action.replace('_', ' ')} on case #{cid}", fake.ipv4(),
                         fake.date_time_between(start_date='-1y', end_date='now')))
        elif roll < 0.85 and alert_ids:
            alid = random.choice(alert_ids)
            action = random.choice(alert_actions)
            rows.append((i, officer, None, alid, action, "alert", alid,
                         f"{action.replace('_', ' ')} on alert #{alid}", fake.ipv4(),
                         fake.date_time_between(start_date='-1y', end_date='now')))
        else:
            action = random.choice(other_actions)
            rows.append((i, officer, None, None, action, "system", officer,
                         f"{action.replace('_', ' ')}", fake.ipv4(),
                         fake.date_time_between(start_date='-1y', end_date='now')))
    execute_batch(cur, """
        INSERT INTO audit_log
            (log_id,officer_id,case_id,alert_id,action,entity_type,entity_id,details,ip_address,action_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("  AML Platform — Database Seeder")
    print("=" * 50 + "\n")

    conn = connect()
    truncate_all(conn)

    run("countries", seed_countries, conn)
    run("officer_roles", seed_officer_roles, conn)
    run("currency_rates", seed_currency_rates, conn)
    run("branches", seed_branches, conn)
    run("compliance_officers", seed_officers, conn)
    run("customers", seed_customers, conn)
    run("accounts", seed_accounts, conn)
    run("transactions", seed_transactions, conn)
    run("compliance_rules", seed_compliance_rules, conn)
    n_alerts = run("alerts", seed_alerts, conn)
    run("alert_comments", seed_alert_comments, conn)
    run("cases", seed_cases, conn)
    run("case_alerts", seed_case_alerts, conn)
    run("risk_scores", seed_risk_scores, conn)
    run("regulatory_reports", seed_regulatory_reports, conn)
    run("sanctions_list", seed_sanctions_list, conn)
    run("pep_list", seed_pep_list, conn)
    run("transaction_patterns", seed_transaction_patterns, conn)
    run("monthly_reports", seed_monthly_reports, conn)
    run("audit_log", seed_audit_log, conn)

    fix_sequences(conn)
    conn.close()

    print("\n" + "=" * 50)
    print("  Seeding complete.")
    print(f"    officers: {N_OFFICERS}    customers: {N_CUSTOMERS}")
    print(f"    transactions: {N_TRANSACTIONS}   alerts: {n_alerts}")
    print(f"    cases: {N_CASES}    sanctioned customers: {N_SANCTIONED}   PEP customers: {N_PEP}")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()
