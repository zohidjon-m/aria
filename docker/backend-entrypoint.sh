#!/usr/bin/env bash
# Backend container entrypoint: wait for Postgres, prepare the schema for the
# deterministic seeder, seed once if empty, then start the API.
set -euo pipefail

echo "[entrypoint] Waiting for Postgres..."
python - <<'PY'
import os, time, psycopg2
dsn = os.environ["BANK_SOURCE_DSN"]
for attempt in range(60):
    try:
        psycopg2.connect(dsn).close()
        print("[entrypoint] Postgres is ready.")
        break
    except Exception as exc:
        print(f"[entrypoint]   ...waiting ({exc})")
        time.sleep(2)
else:
    raise SystemExit("[entrypoint] Postgres never became reachable")
PY

echo "[entrypoint] Preparing schema and seeding (first run only)..."
python - <<'PY'
import os, subprocess, psycopg2
dsn = os.environ["BANK_SOURCE_DSN"]
conn = psycopg2.connect(dsn)
conn.autocommit = True
cur = conn.cursor()

# The reference schema ships an AFTER-INSERT trigger that auto-creates alerts and
# an audit trigger on case updates. The seeder generates its own deterministic,
# linked alerts and the API writes its own audit rows, so drop both to avoid
# duplicate / conflicting data. (No-ops if they were never created.)
cur.execute("DROP TRIGGER IF EXISTS trg_compliance_check ON transactions")
cur.execute("DROP TRIGGER IF EXISTS trg_audit_case ON cases")

cur.execute("SELECT count(*) FROM customers")
count = cur.fetchone()[0]
conn.close()

if count == 0:
    print("[entrypoint] Empty database -> running seed_database.py")
    subprocess.check_call(["python", "seed_database.py"])
else:
    print(f"[entrypoint] Database already has {count} customers -> skipping seed")
PY

echo "[entrypoint] Starting API on 0.0.0.0:8000"
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
