"""
Banking Compliance System — Database Seeder
Connects directly to PostgreSQL and inserts all sample data.

Usage:
    pip install faker psycopg2-binary
    python seed_database.py

Configure your DB connection in the CONFIG block below.
"""

import psycopg2
from psycopg2.extras import execute_batch
from faker import Faker
import random
from datetime import date, datetime, timedelta

# ── CONFIG ──────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     "localhost",
    "port":     5432,
    "dbname":   "aml_platform",
    "user":     "postgres",
    "password": "postgres",
}

# ── SETUP ────────────────────────────────────────────────────────────────────
fake = Faker()
random.seed(42)
Faker.seed(42)


def connect():
    return psycopg2.connect(**DB_CONFIG)


def truncate_all(conn):
    """Wipe all tables in correct reverse-FK order so we can re-seed cleanly."""
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
    # Disable FK checks temporarily for clean wipe
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
    fn(cur)
    conn.commit()
    cur.close()
    print("done")


def fix_sequences(conn):
    """Realign every serial/identity sequence to MAX(id).

    Rows are inserted with explicit primary-key values, which does NOT advance
    the owning sequence. Without this, the first post-seed INSERT collides with
    an existing id and raises UniqueViolation. Run once after all seeding.
    """
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


# ── SEEDERS ──────────────────────────────────────────────────────────────────

def seed_countries(cur):
    data = [
        ("US","United States",    "whitelist", 0.5,  False),
        ("GB","United Kingdom",   "whitelist", 0.8,  False),
        ("KR","South Korea",      "whitelist", 1.0,  False),
        ("DE","Germany",          "whitelist", 0.6,  False),
        ("SG","Singapore",        "whitelist", 0.7,  False),
        ("JP","Japan",            "whitelist", 0.5,  False),
        ("FR","France",           "whitelist", 0.9,  False),
        ("UZ","Uzbekistan",       "greylist",  4.5,  False),
        ("AE","UAE",              "greylist",  5.2,  False),
        ("TR","Turkey",           "greylist",  4.8,  False),
        ("CN","China",            "greylist",  5.0,  False),
        ("RU","Russia",           "blacklist", 8.5,  True),
        ("IR","Iran",             "blacklist", 9.8,  True),
        ("KP","North Korea",      "blacklist",10.0,  True),
        ("MM","Myanmar",          "blacklist", 8.2,  True),
        ("NG","Nigeria",          "greylist",  6.1,  False),
        ("PK","Pakistan",         "greylist",  5.8,  False),
        ("VN","Vietnam",          "greylist",  4.2,  False),
        ("CH","Switzerland",      "whitelist", 1.2,  False),
        ("AU","Australia",        "whitelist", 0.6,  False),
    ]
    execute_batch(cur, """
        INSERT INTO countries (country_code, country_name, fatf_status, risk_score, is_sanctioned, updated_at)
        VALUES (%s,%s,%s,%s,%s,NOW())
        ON CONFLICT DO NOTHING
    """, data)


def seed_officer_roles(cur):
    data = [
        (1,"junior_analyst",     True, False,False,False,False,"Read-only analyst"),
        (2,"senior_analyst",     True, True, False,False,False,"Can manage cases"),
        (3,"compliance_officer", True, True, True, False,False,"Can file SARs"),
        (4,"compliance_manager", True, True, True, True, True, "Full compliance access"),
        (5,"db_admin",           True, True, True, True, True, "System administrator"),
    ]
    execute_batch(cur, """
        INSERT INTO officer_roles
            (role_id,role_name,can_view_alerts,can_manage_cases,can_file_sar,can_manage_rules,can_manage_users,description)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, data)


def seed_currency_rates(cur):
    data = [
        ("USD","US Dollar",       1.0),
        ("EUR","Euro",            1.08),
        ("GBP","British Pound",   1.27),
        ("KRW","Korean Won",      0.00075),
        ("JPY","Japanese Yen",    0.0067),
        ("CNY","Chinese Yuan",    0.138),
        ("AED","UAE Dirham",      0.272),
        ("TRY","Turkish Lira",    0.031),
        ("RUB","Russian Ruble",   0.011),
        ("CHF","Swiss Franc",     1.13),
        ("AUD","Australian Dollar",0.65),
        ("SGD","Singapore Dollar",0.74),
        ("UZS","Uzbek Som",       0.000079),
    ]
    rows = [(code, name, rate, date.today()) for code, name, rate in data]
    execute_batch(cur, """
        INSERT INTO currency_rates (currency_code, currency_name, rate_to_usd, rate_date)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (currency_code, rate_date) DO NOTHING
    """, rows)


def seed_branches(cur):
    data = [
        (1,"Seoul HQ Branch",    "Seoul",     "KR"),
        (2,"Gangnam Branch",     "Seoul",     "KR"),
        (3,"Busan Branch",       "Busan",     "KR"),
        (4,"London City Branch", "London",    "GB"),
        (5,"New York Branch",    "New York",  "US"),
        (6,"Singapore Branch",   "Singapore", "SG"),
        (7,"Frankfurt Branch",   "Frankfurt", "DE"),
        (8,"Sydney Branch",      "Sydney",    "AU"),
    ]
    rows = [
        (bid, name, city, cc,
         fake.street_address(),
         fake.phone_number()[:20],
         True,
         fake.date_between(start_date='-10y', end_date='-2y'))
        for bid, name, city, cc in data
    ]
    execute_batch(cur, """
        INSERT INTO branches
            (branch_id,branch_name,city,country_code,address,phone,is_active,opened_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


def seed_officers(cur):
    rows = []
    for oid in range(1, 21):
        rows.append((
            oid,
            random.choice([1,1,1,2,2,3,3,4]),
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

    # Assign managers
    cur.execute("SELECT officer_id, role_id FROM compliance_officers")
    all_officers = cur.fetchall()
    senior = [o[0] for o in all_officers if o[1] >= 3]
    for bid in range(1, 9):
        mgr = random.choice(senior)
        cur.execute("UPDATE branches SET manager_id=%s WHERE branch_id=%s", (mgr, bid))


def seed_customers(cur):
    nationalities = ["US","GB","KR","DE","SG","JP","FR","UZ","AE","TR",
                     "CN","NG","PK","VN","CH","AU"]
    risk_pool     = ["low"]*60 + ["medium"]*25 + ["high"]*12 + ["critical"]*3
    kyc_pool      = ["verified"]*75 + ["pending"]*15 + ["expired"]*7 + ["rejected"]*3
    occupations   = ["Engineer","Merchant","Consultant","Executive","Trader",
                     "Doctor","Lawyer","Entrepreneur","Professor","Analyst"]
    rows = []
    for cid in range(1, 101):
        created = fake.date_time_between(start_date='-5y', end_date='-1m')
        rows.append((
            cid,
            fake.name()[:150],
            fake.unique.email()[:150],
            fake.phone_number()[:20],
            random.choice(nationalities),
            fake.date_of_birth(minimum_age=22, maximum_age=75),
            random.choice(occupations),
            random.choice(risk_pool),
            random.choice(kyc_pool),
            True,
            created,
            created,
        ))
    execute_batch(cur, """
        INSERT INTO customers
            (customer_id,full_name,email,phone,nationality,date_of_birth,occupation,
             risk_level,kyc_status,is_active,created_at,updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


def seed_accounts(cur):
    acct_types = ["checking","savings","business","investment"]
    currencies = ["USD","EUR","GBP","KRW","JPY","SGD","AUD","CHF"]
    rows = []
    for aid in range(1, 151):
        opened = fake.date_time_between(start_date='-5y', end_date='-3m')
        rows.append((
            aid,
            random.randint(1, 100),
            random.randint(1, 8),
            f"ACC{str(aid).zfill(8)}",
            random.choice(acct_types),
            random.choice(currencies),
            round(random.uniform(500, 500000), 2),
            random.choices(["active","frozen","suspended"], weights=[88,8,4])[0],
            opened,
        ))
    execute_batch(cur, """
        INSERT INTO accounts
            (account_id,customer_id,branch_id,account_number,account_type,
             currency_code,balance,status,opened_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


def seed_transactions(cur):
    rate_map = {
        "USD":1.0,"EUR":1.08,"GBP":1.27,"KRW":0.00075,"JPY":0.0067,
        "CNY":0.138,"AED":0.272,"SGD":0.74,"CHF":1.13,"AUD":0.65,"UZS":0.000079
    }
    tx_types      = ["deposit","withdrawal","transfer_domestic",
                     "transfer_international","wire","cash"]
    intl_countries= ["US","GB","DE","SG","JP","FR","UZ","AE","TR",
                     "CN","NG","RU","IR","CH","AU"]
    currencies    = ["USD","EUR","GBP","KRW","JPY","SGD","AUD","CHF"]

    # Fetch accounts
    cur.execute("SELECT account_id, currency_code FROM accounts")
    accounts = cur.fetchall()

    rows = []
    for tid in range(1, 401):
        aid, curr = random.choice(accounts)
        tx_type   = random.choices(tx_types, weights=[20,15,30,15,10,10])[0]

        if random.random() < 0.08:
            amount = round(random.uniform(9500, 9999), 2)
        elif random.random() < 0.05:
            amount = round(random.uniform(10000, 80000), 2)
        else:
            amount = round(random.uniform(50, 5000), 2)

        amount_usd    = round(amount * rate_map.get(curr, 1.0), 2)
        dest_country  = None
        counterparty  = None

        if tx_type in ("transfer_international","wire"):
            dest_country = random.choice(intl_countries)

        if tx_type in ("transfer_domestic","transfer_international","wire"):
            other = random.choice([a for a in accounts if a[0] != aid])
            counterparty = other[0]

        rows.append((
            tid, aid, counterparty, tx_type,
            amount, amount_usd, curr,
            dest_country,
            fake.sentence(nb_words=6)[:200],
            f"TXN{str(tid).zfill(8)}",
            random.choices(["completed","pending","failed"], weights=[90,7,3])[0],
            False,
            fake.date_time_between(start_date='-2y', end_date='now'),
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
        (1,"Large Cash Transaction",    "threshold",  10000.00,None,None,"cash",         "high"),
        (2,"Large Wire Transfer",       "threshold",  50000.00,None,None,"all",          "high"),
        (3,"Frequent International",    "frequency",  None,    5,   7,   "international","medium"),
        (4,"High Risk Country Transfer","geography",  None,    None,None,"international","critical"),
        (5,"Rapid Succession Transfers","velocity",   None,    10,  1,   "all",          "high"),
        (6,"Structuring Detection",     "structuring",9000.00, 3,   1,   "all",          "critical"),
        (7,"Sanctions Match",           "sanctions",  None,    None,None,"all",          "critical"),
    ]
    execute_batch(cur, """
        INSERT INTO compliance_rules
            (rule_id,rule_name,rule_type,threshold_amount,max_frequency,
             time_window_days,applies_to,severity,is_active,created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,TRUE,NOW())
        ON CONFLICT DO NOTHING
    """, data)


def seed_alerts(cur):
    blacklist = {"RU","IR","KP","MM"}
    cur.execute("""
        SELECT transaction_id, amount_usd, transaction_type, destination_country
        FROM transactions
    """)
    transactions = cur.fetchall()
    cur.execute("SELECT officer_id FROM compliance_officers")
    officer_ids = [r[0] for r in cur.fetchall()]

    statuses = ["open","under_review","escalated","dismissed","resolved"]
    rows = []
    aid  = 1

    for txid, amt_usd, tx_type, dest_country in transactions:
        triggered = []
        if amt_usd and amt_usd >= 10000 and tx_type == "cash":
            triggered.append((1,"high"))
        if amt_usd and amt_usd >= 50000:
            triggered.append((2,"high"))
        if dest_country and dest_country in blacklist:
            triggered.append((4,"critical"))
        if amt_usd and 9000 <= amt_usd <= 9999:
            triggered.append((6,"critical"))
        if random.random() < 0.04:
            triggered.append((3,"medium"))

        for rule_id, sev in triggered:
            status   = random.choices(statuses, weights=[30,25,15,15,15])[0]
            created  = fake.date_time_between(start_date='-1y', end_date='now')
            resolved = None
            if status in ("dismissed","resolved"):
                resolved = created + timedelta(days=random.randint(1,30))
            rows.append((
                aid, txid, rule_id,
                random.choice(officer_ids),
                sev, status,
                status == "escalated",
                created, resolved,
                fake.sentence(),
            ))
            aid += 1

    execute_batch(cur, """
        INSERT INTO alerts
            (alert_id,transaction_id,rule_id,assigned_to,severity,status,
             is_escalated,created_at,resolved_at,notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)
    return [r[0] for r in rows]


def seed_alert_comments(cur, alert_ids):
    cur.execute("SELECT officer_id FROM compliance_officers")
    officer_ids = [r[0] for r in cur.fetchall()]
    rows = []
    cid  = 1
    for alid in alert_ids[:60]:
        for _ in range(random.randint(1, 3)):
            rows.append((
                cid,
                alid,
                random.choice(officer_ids),
                fake.paragraph(nb_sentences=2)[:500],
                fake.date_time_between(start_date='-6m', end_date='now'),
            ))
            cid += 1
    execute_batch(cur, """
        INSERT INTO alert_comments (comment_id,alert_id,officer_id,comment,created_at)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


def seed_cases(cur):
    cur.execute("SELECT officer_id FROM compliance_officers")
    officer_ids = [r[0] for r in cur.fetchall()]
    case_types  = ["AML","fraud","KYC","sanctions","structuring"]
    statuses    = ["open","under_review","escalated","closed_clean","closed_sar"]
    priorities  = ["low","medium","high","critical"]
    rows = []

    for cid in range(1, 41):
        status  = random.choices(statuses, weights=[25,25,15,20,15])[0]
        opened  = fake.date_time_between(start_date='-1y', end_date='-1m')
        closed  = None
        if status in ("closed_clean","closed_sar"):
            closed = opened + timedelta(days=random.randint(7,90))
        rows.append((
            cid,
            random.randint(1, 100),
            random.choice(officer_ids),
            random.choice(case_types),
            status,
            random.choice(priorities),
            opened, closed,
            fake.paragraph(nb_sentences=3),
            fake.paragraph(nb_sentences=2) if closed else None,
        ))

    execute_batch(cur, """
        INSERT INTO cases
            (case_id,customer_id,officer_id,case_type,status,priority,
             opened_at,closed_at,summary,resolution)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


def seed_case_alerts(cur, alert_ids):
    cur.execute("SELECT officer_id FROM compliance_officers")
    officer_ids = [r[0] for r in cur.fetchall()]
    used = set()
    rows = []
    for case_id in range(1, 41):
        sample = random.sample(alert_ids[:min(len(alert_ids), 50)],
                               min(random.randint(1,4), len(alert_ids)))
        for alid in sample:
            if (case_id, alid) not in used:
                used.add((case_id, alid))
                rows.append((
                    case_id, alid,
                    fake.date_time_between(start_date='-6m', end_date='now'),
                    random.choice(officer_ids),
                ))
    execute_batch(cur, """
        INSERT INTO case_alerts (case_id,alert_id,added_at,added_by)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


def seed_risk_scores(cur):
    cur.execute("SELECT customer_id, risk_level FROM customers")
    customers = cur.fetchall()
    base_map  = {"low":10,"medium":35,"high":65,"critical":85}
    rows = []
    sid  = 1
    for cid, risk in customers:
        base = base_map.get(risk, 20)
        for _ in range(random.randint(1, 3)):
            score = round(min(100, max(0, base + random.uniform(-10,10))), 2)
            level = ("low" if score < 25 else
                     "medium" if score < 50 else
                     "high" if score < 75 else "critical")
            rows.append((
                sid, cid, score, level,
                random.choice(["system","agent","officer"]),
                fake.date_time_between(start_date='-1y', end_date='now'),
                fake.paragraph(nb_sentences=2),
            ))
            sid += 1
    execute_batch(cur, """
        INSERT INTO risk_scores
            (score_id,customer_id,score,score_level,computed_by,computed_at,reasoning)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


def seed_regulatory_reports(cur):
    cur.execute("SELECT case_id FROM cases WHERE status='closed_sar'")
    sar_cases   = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT officer_id FROM compliance_officers")
    officer_ids = [r[0] for r in cur.fetchall()]
    regulators  = ["FinCEN (US)","FCA (UK)","FSS (Korea)",
                   "MAS (Singapore)","BaFin (Germany)"]
    rows = []
    for i, cid in enumerate(sar_cases, 1):
        submitted = fake.date_time_between(start_date='-6m', end_date='now')
        rows.append((
            i, cid,
            random.choice(officer_ids),
            random.choice(["SAR","CTR","STR"]),
            random.choice(regulators),
            random.choice(["submitted","acknowledged"]),
            submitted,
            submitted + timedelta(days=30),
            f"REF-{fake.bothify('??####').upper()}",
            submitted,
        ))
    execute_batch(cur, """
        INSERT INTO regulatory_reports
            (report_id,case_id,officer_id,report_type,regulator,status,
             submitted_at,deadline,reference_number,created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


def seed_sanctions_list(cur):
    high_risk = ["RU","IR","KP","MM","NG"]
    listed_by = ["US Treasury OFAC","UN Security Council",
                 "European Commission","FATF"]
    rows = []
    for i in range(1, 31):
        rows.append((
            i,
            fake.name(),
            random.choice(["individual","organization","vessel"]),
            random.choice(high_risk),
            random.choice(["OFAC SDN","UN Security Council","EU Sanctions"]),
            random.choice(listed_by),
            fake.date_between(start_date='-10y', end_date='-1y'),
            True,
            fake.sentence(),
        ))
    execute_batch(cur, """
        INSERT INTO sanctions_list
            (sanction_id,full_name,entity_type,country_code,sanction_type,
             listed_by,listed_at,is_active,notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


def seed_pep_list(cur):
    positions   = ["Minister of Finance","President","Prime Minister",
                   "Central Bank Governor","Member of Parliament",
                   "Ambassador","Defense Minister"]
    pep_countries = ["RU","CN","TR","UZ","NG","AE","KP","IR","PK","VN"]
    rows = []
    for i in range(1, 21):
        rows.append((
            i,
            fake.name(),
            random.choice(positions),
            random.choice(pep_countries),
            random.choice(["domestic","foreign","international"]),
            True,
            fake.date_between(start_date='-15y', end_date='-1y'),
            fake.sentence(),
        ))
    execute_batch(cur, """
        INSERT INTO pep_list
            (pep_id,full_name,position,country_code,pep_level,is_active,since_date,notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


def seed_transaction_patterns(cur):
    cur.execute("SELECT customer_id FROM customers")
    cids = [r[0] for r in cur.fetchall()]
    rows = []
    for i, cid in enumerate(cids, 1):
        avg_tx  = round(random.uniform(200, 15000), 2)
        rows.append((
            i, cid,
            avg_tx,
            round(avg_tx * random.uniform(2, 10), 2),
            round(avg_tx * random.randint(3, 20), 2),
            ",".join(random.sample(["US","GB","KR","SG","DE","JP","FR","AE"],
                                   random.randint(1,4))),
            round(random.uniform(0, 60), 2),
            round(random.uniform(0, 30), 2),
            fake.date_time_between(start_date='-30d', end_date='now'),
        ))
    execute_batch(cur, """
        INSERT INTO transaction_patterns
            (pattern_id,customer_id,avg_transaction,max_transaction,monthly_volume,
             typical_countries,international_pct,cash_pct,computed_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


def seed_monthly_reports(cur):
    rows = []
    rid  = 1
    for bid in range(1, 9):
        for months_ago in range(12, 0, -1):
            month = (date.today().replace(day=1) -
                     timedelta(days=months_ago*30)).replace(day=1)
            rows.append((
                rid, bid, month,
                random.randint(200, 2000),
                round(random.uniform(500000, 50000000), 2),
                random.randint(5, 80),
                random.randint(0, 15),
                random.randint(0, 3),
            ))
            rid += 1
    execute_batch(cur, """
        INSERT INTO monthly_reports
            (report_id,branch_id,report_month,total_transactions,total_volume_usd,
             total_alerts,total_cases,sars_filed,generated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        ON CONFLICT (branch_id, report_month) DO NOTHING
    """, rows)


def seed_audit_log(cur):
    cur.execute("SELECT officer_id FROM compliance_officers")
    officer_ids = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT case_id FROM cases")
    case_ids = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT alert_id FROM alerts LIMIT 20")
    alert_ids = [r[0] for r in cur.fetchall()]

    actions = ["status_change","alert_assigned","case_opened","case_closed",
               "sar_filed","risk_score_updated","officer_login","rule_modified"]
    rows = []
    for i in range(1, 101):
        rows.append((
            i,
            random.choice(officer_ids),
            random.choice(case_ids + [None]*3),
            random.choice(alert_ids + [None]*3) if alert_ids else None,
            random.choice(actions),
            random.choice(["case","alert","customer","rule"]),
            random.randint(1, 50),
            fake.paragraph(nb_sentences=1),
            fake.ipv4(),
            fake.date_time_between(start_date='-1y', end_date='now'),
        ))
    execute_batch(cur, """
        INSERT INTO audit_log
            (log_id,officer_id,case_id,alert_id,action,entity_type,
             entity_id,details,ip_address,action_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("\n Banking Compliance DB Seeder")
    print("=" * 40)

    try:
        conn = connect()
        print(f"  Connected to '{DB_CONFIG['dbname']}' on {DB_CONFIG['host']}\n")
        print("  Clearing existing data...")
        truncate_all(conn)
    except Exception as e:
        print(f"\n  Failed: {e}")
        print("  Check your DB_CONFIG settings at the top of this file.")
        return

    steps = [
        ("countries",             lambda c: seed_countries(c)),
        ("officer_roles",         lambda c: seed_officer_roles(c)),
        ("currency_rates",        lambda c: seed_currency_rates(c)),
        ("branches",              lambda c: seed_branches(c)),
        ("compliance_officers",   lambda c: seed_officers(c)),
        ("customers",             lambda c: seed_customers(c)),
        ("accounts",              lambda c: seed_accounts(c)),
        ("transactions",          lambda c: seed_transactions(c)),
        ("compliance_rules",      lambda c: seed_compliance_rules(c)),
    ]

    for label, fn in steps:
        run(label, fn, conn)

    # Alerts returns IDs for downstream seeders
    print(f"  Seeding alerts...", end=" ", flush=True)
    cur = conn.cursor()
    alert_ids = seed_alerts(cur)
    conn.commit()
    cur.close()
    print(f"done ({len(alert_ids)} alerts)")

    remaining = [
        ("alert_comments",        lambda c: seed_alert_comments(c, alert_ids)),
        ("cases",                 lambda c: seed_cases(c)),
        ("case_alerts",           lambda c: seed_case_alerts(c, alert_ids)),
        ("risk_scores",           lambda c: seed_risk_scores(c)),
        ("regulatory_reports",    lambda c: seed_regulatory_reports(c)),
        ("sanctions_list",        lambda c: seed_sanctions_list(c)),
        ("pep_list",              lambda c: seed_pep_list(c)),
        ("transaction_patterns",  lambda c: seed_transaction_patterns(c)),
        ("monthly_reports",       lambda c: seed_monthly_reports(c)),
        ("audit_log",             lambda c: seed_audit_log(c)),
    ]

    for label, fn in remaining:
        run(label, fn, conn)

    fix_sequences(conn)

    conn.close()

    print("\n" + "=" * 40)
    print("  All tables seeded successfully.")
    print("\n  Row counts (approximate):")
    print("    countries: 20       officer_roles: 5")
    print("    currency_rates: 13  branches: 8")
    print("    officers: 20        customers: 100")
    print("    accounts: 150       transactions: 400")
    print("    compliance_rules: 7 alerts: varies")
    print("    alert_comments: ~150  cases: 40")
    print("    risk_scores: ~213   sanctions_list: 30")
    print("    pep_list: 20        monthly_reports: 96")
    print("    audit_log: 100")
    print("=" * 40 + "\n")


if __name__ == "__main__":
    main()