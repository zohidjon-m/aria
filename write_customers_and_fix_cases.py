import pathlib

ROUTES = pathlib.Path("D:/sejong_major/projects/compliance-agent/backend/routes")

# Fix cases.py - use RealDictCursor in rw_conn contexts so fetchone() returns dicts
CASES_CONTENT = '''from __future__ import annotations

import logging

import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..audit import insert_audit
from ..db import ro_cursor, rw_conn
from ..rbac import require_view, require_manage

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_CASE_TYPES = {"AML", "fraud", "sanctions", "pep", "other"}
ALLOWED_PRIORITIES = {"low", "medium", "high", "critical"}
ALLOWED_CASE_STATUS = {"open", "under_review", "closed_clean", "closed_sar", "escalated"}


@router.get("/cases/{case_id}")
def get_case(case_id: int, officer: dict = Depends(require_view)) -> dict:
    with ro_cursor() as cur:
        cur.execute(
            """
            SELECT cs.case_id, cs.customer_id, cs.officer_id, cs.case_type, cs.status,
                   cs.priority, cs.summary, cs.resolution, cs.opened_at, cs.closed_at,
                   c.full_name AS customer_name, c.risk_level AS customer_risk_level,
                   c.kyc_status AS customer_kyc_status,
                   co.full_name AS officer_name
            FROM cases cs
            LEFT JOIN customers c ON c.customer_id = cs.customer_id
            LEFT JOIN compliance_officers co ON co.officer_id = cs.officer_id
            WHERE cs.case_id = %s
            """,
            (case_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
        case = dict(row)

        cur.execute(
            """
            SELECT al.alert_id, al.severity, al.status, al.created_at,
                   cr.rule_name, t.amount_usd
            FROM case_alerts ca
            JOIN alerts al ON al.alert_id = ca.alert_id
            JOIN compliance_rules cr ON cr.rule_id = al.rule_id
            JOIN transactions t ON t.transaction_id = al.transaction_id
            WHERE ca.case_id = %s ORDER BY al.created_at DESC
            """,
            (case_id,),
        )
        case["alerts"] = [dict(r) for r in cur.fetchall()]
    return case


class CreateCaseBody(BaseModel):
    customer_id: int
    case_type: str
    priority: str = "medium"
    summary: str = ""


@router.post("/cases", status_code=201)
def create_case(body: CreateCaseBody, officer: dict = Depends(require_manage)) -> dict:
    if body.case_type not in ALLOWED_CASE_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid case_type")
    if body.priority not in ALLOWED_PRIORITIES:
        raise HTTPException(status_code=422, detail=f"Invalid priority")
    with rw_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT customer_id FROM customers WHERE customer_id = %s", (body.customer_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"Customer {body.customer_id} not found")
            cur.execute(
                "INSERT INTO cases (customer_id, officer_id, case_type, priority, summary, status) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING case_id",
                (body.customer_id, officer["officer_id"], body.case_type, body.priority, body.summary, "open"),
            )
            row = cur.fetchone()
            case_id = row["case_id"] if isinstance(row, dict) else row[0]
            insert_audit(cur, officer_id=officer["officer_id"], action="create_case",
                         entity_type="case", entity_id=case_id, case_id=case_id,
                         details={"case_type": body.case_type, "priority": body.priority})
    return {"case_id": case_id, "ok": True}


class LinkAlertBody(BaseModel):
    alert_id: int


@router.post("/cases/{case_id}/link-alert")
def link_alert(case_id: int, body: LinkAlertBody, officer: dict = Depends(require_manage)) -> dict:
    with rw_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT case_id FROM cases WHERE case_id = %s", (case_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
            cur.execute("SELECT alert_id FROM alerts WHERE alert_id = %s", (body.alert_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"Alert {body.alert_id} not found")
            cur.execute(
                "INSERT INTO case_alerts (case_id, alert_id, added_by) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (case_id, body.alert_id, officer["officer_id"]),
            )
            insert_audit(cur, officer_id=officer["officer_id"], action="link_alert",
                         entity_type="case", entity_id=case_id, case_id=case_id,
                         alert_id=body.alert_id)
    return {"ok": True}


class CaseDispositionBody(BaseModel):
    status: str
    resolution: str = ""


@router.post("/cases/{case_id}/disposition")
def case_disposition(case_id: int, body: CaseDispositionBody, officer: dict = Depends(require_manage)) -> dict:
    if body.status not in ALLOWED_CASE_STATUS:
        raise HTTPException(status_code=422, detail=f"Invalid case status")
    with rw_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT case_id FROM cases WHERE case_id = %s", (case_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
            cur.execute(
                "UPDATE cases SET status = %s, resolution = %s WHERE case_id = %s",
                (body.status, body.resolution, case_id),
            )
            insert_audit(cur, officer_id=officer["officer_id"], action="case_disposition",
                         entity_type="case", entity_id=case_id, case_id=case_id,
                         details={"status": body.status})
    return {"ok": True, "status": body.status}
'''

CUSTOMERS_CONTENT = '''from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..db import ro_cursor
from ..rbac import require_view

router = APIRouter()


@router.get("/customers/{customer_id}")
def get_customer(customer_id: int, officer: dict = Depends(require_view)) -> dict:
    with ro_cursor() as cur:
        cur.execute(
            "SELECT c.*, cnt.country_name AS nationality_name, cnt.fatf_status AS nationality_fatf_status "
            "FROM customers c LEFT JOIN countries cnt ON cnt.country_code = c.nationality "
            "WHERE c.customer_id = %s",
            (customer_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
        customer = dict(row)
        cur.execute(
            "SELECT ac.*, b.branch_name FROM accounts ac LEFT JOIN branches b ON b.branch_id = ac.branch_id "
            "WHERE ac.customer_id = %s ORDER BY ac.opened_at DESC",
            (customer_id,),
        )
        customer["accounts"] = [dict(r) for r in cur.fetchall()]
        cur.execute(
            "SELECT score, score_level, computed_by, computed_at, reasoning FROM risk_scores "
            "WHERE customer_id = %s ORDER BY computed_at DESC LIMIT 1",
            (customer_id,),
        )
        rs = cur.fetchone()
        customer["latest_risk_score"] = dict(rs) if rs else None
        cur.execute(
            "SELECT avg_transaction, max_transaction, monthly_volume, typical_countries, "
            "international_pct, cash_pct, computed_at FROM transaction_patterns "
            "WHERE customer_id = %s ORDER BY computed_at DESC LIMIT 1",
            (customer_id,),
        )
        bp = cur.fetchone()
        customer["baseline"] = dict(bp) if bp else None
        cur.execute(
            "SELECT sl.full_name AS matched_name, sl.entity_type, sl.sanction_type, sl.listed_by "
            "FROM sanctions_list sl WHERE sl.is_active = TRUE AND sl.full_name ILIKE %s LIMIT 10",
            (f"%{customer['full_name']}%",),
        )
        customer["sanctions_matches"] = [dict(r) for r in cur.fetchall()]
        cur.execute(
            "SELECT pl.full_name AS matched_name, pl.position, pl.pep_level, pl.country_code, pl.since_date "
            "FROM pep_list pl WHERE pl.is_active = TRUE AND pl.full_name ILIKE %s LIMIT 10",
            (f"%{customer['full_name']}%",),
        )
        customer["pep_matches"] = [dict(r) for r in cur.fetchall()]
    return customer


@router.get("/customers/{customer_id}/transactions")
def get_customer_transactions(
    customer_id: int,
    officer: dict = Depends(require_view),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    is_flagged: bool | None = Query(None),
) -> dict:
    with ro_cursor() as cur:
        cur.execute("SELECT customer_id FROM customers WHERE customer_id = %s", (customer_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
        conditions = ["ac.customer_id = %s"]
        params = [customer_id]
        if is_flagged is not None:
            conditions.append("t.is_flagged = %s")
            params.append(is_flagged)
        where = "WHERE " + " AND ".join(conditions)
        offset = (page - 1) * limit
        cur.execute(f"SELECT COUNT(*) AS total FROM transactions t JOIN accounts ac ON ac.account_id = t.account_id {where}", params)
        total = cur.fetchone()["total"]
        cur.execute(
            f"SELECT t.transaction_id, t.amount, t.currency_code, t.amount_usd, t.transaction_type, "
            f"t.destination_country, ct.country_name AS destination_country_name, ct.fatf_status AS destination_fatf_status, "
            f"t.description, t.reference_number, t.status, t.is_flagged, t.created_at, "
            f"ac.account_number, ac.account_type "
            f"FROM transactions t JOIN accounts ac ON ac.account_id = t.account_id "
            f"LEFT JOIN countries ct ON ct.country_code = t.destination_country "
            f"{where} ORDER BY t.created_at DESC LIMIT %s OFFSET %s",
            params + [limit, offset],
        )
        items = [dict(r) for r in cur.fetchall()]
    return {"total": total, "page": page, "limit": limit, "items": items}


@router.get("/customers/{customer_id}/cases")
def get_customer_cases(customer_id: int, officer: dict = Depends(require_view)) -> list:
    with ro_cursor() as cur:
        cur.execute("SELECT customer_id FROM customers WHERE customer_id = %s", (customer_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
        cur.execute(
            "SELECT cs.case_id, cs.case_type, cs.status, cs.priority, cs.opened_at, cs.closed_at, cs.summary, "
            "co.full_name AS officer_name, COUNT(ca.alert_id) AS linked_alert_count "
            "FROM cases cs LEFT JOIN compliance_officers co ON co.officer_id = cs.officer_id "
            "LEFT JOIN case_alerts ca ON ca.case_id = cs.case_id "
            "WHERE cs.customer_id = %s GROUP BY cs.case_id, co.full_name ORDER BY cs.opened_at DESC",
            (customer_id,),
        )
        return [dict(r) for r in cur.fetchall()]
'''

(ROUTES / "cases.py").write_text(CASES_CONTENT, encoding="utf-8")
(ROUTES / "customers.py").write_text(CUSTOMERS_CONTENT, encoding="utf-8")
print("cases.py and customers.py written.")
