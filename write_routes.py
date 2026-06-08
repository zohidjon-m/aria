import pathlib

ROUTES = pathlib.Path("D:/sejong_major/projects/compliance-agent/backend/routes")

ALERTS_CONTENT = '''from __future__ import annotations

import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..audit import insert_audit
from ..db import ro_cursor, rw_conn
from ..rbac import require_view, require_manage

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_SORT = {"created_at", "amount", "severity"}
ALLOWED_STATUS = {"open", "under_review", "escalated", "dismissed", "resolved", "closed_clean", "closed_sar"}


def _latest_agent_run(sidecar_db_path, alert_id):
    if not sidecar_db_path:
        return None
    try:
        conn = sqlite3.connect(sidecar_db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT run_id, created_at, status FROM agent_runs "
            "WHERE subject_type=\'alert\' AND subject_id=? ORDER BY created_at DESC LIMIT 1",
            (str(alert_id),),
        )
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None


@router.get("/alerts")
def list_alerts(
    officer: dict = Depends(require_view),
    status: str | None = Query(None),
    severity: str | None = Query(None),
    assigned_to: int | None = Query(None),
    sort_by: str = Query("created_at"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
) -> dict:
    if sort_by not in ALLOWED_SORT:
        sort_by = "created_at"

    conditions = []
    params = []

    if status:
        conditions.append("al.status = %s")
        params.append(status)
    if severity:
        conditions.append("al.severity = %s")
        params.append(severity)
    if assigned_to is not None:
        conditions.append("al.assigned_to = %s")
        params.append(assigned_to)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sort_col = {"created_at": "al.created_at", "amount": "t.amount_usd", "severity": "al.severity"}[sort_by]
    offset = (page - 1) * limit

    with ro_cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS total FROM alerts al {where}", params)
        total = cur.fetchone()["total"]
        cur.execute(
            f"""
            SELECT
                al.alert_id, al.severity, al.status, al.created_at, al.assigned_to,
                cr.rule_name, cr.rule_type,
                t.amount, t.currency_code, t.amount_usd, t.transaction_type,
                c.customer_id, c.full_name AS customer_name, c.risk_level,
                co.full_name AS officer_name,
                EXISTS(
                    SELECT 1 FROM case_alerts ca WHERE ca.alert_id = al.alert_id
                ) AS has_case,
                EXISTS(
                    SELECT 1 FROM sanctions_list sl
                    WHERE sl.is_active = TRUE AND sl.full_name ILIKE \'%\' || c.full_name || \'%\'
                ) AS has_sanctions_hit,
                EXISTS(
                    SELECT 1 FROM pep_list pl
                    WHERE pl.is_active = TRUE AND pl.full_name ILIKE \'%\' || c.full_name || \'%\'
                ) AS has_pep_hit
            FROM alerts al
            JOIN compliance_rules cr ON cr.rule_id = al.rule_id
            JOIN transactions t ON t.transaction_id = al.transaction_id
            JOIN accounts ac ON ac.account_id = t.account_id
            JOIN customers c ON c.customer_id = ac.customer_id
            LEFT JOIN compliance_officers co ON co.officer_id = al.assigned_to
            {where}
            ORDER BY {sort_col} DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        items = [dict(r) for r in cur.fetchall()]
    return {"total": total, "page": page, "limit": limit, "items": items}


@router.get("/alerts/{alert_id}")
def get_alert(alert_id: int, officer: dict = Depends(require_view)) -> dict:
    with ro_cursor() as cur:
        cur.execute(
            """
            SELECT
                al.alert_id, al.severity, al.status, al.created_at, al.assigned_to,
                al.notes,
                cr.rule_name, cr.rule_type, cr.threshold_amount,
                t.amount, t.currency_code, t.amount_usd, t.transaction_type,
                t.created_at AS transaction_date, t.reference_number,
                cnt.country_name AS destination_country_name,
                cnt.fatf_status AS destination_fatf_status,
                t.destination_country,
                c.customer_id, c.full_name AS customer_name, c.risk_level,
                c.kyc_status, c.nationality,
                nat.country_name AS nationality_name,
                co.full_name AS officer_name,
                EXISTS(
                    SELECT 1 FROM sanctions_list sl
                    WHERE sl.is_active = TRUE AND sl.full_name ILIKE \'%\' || c.full_name || \'%\'
                ) AS has_sanctions_hit,
                EXISTS(
                    SELECT 1 FROM pep_list pl
                    WHERE pl.is_active = TRUE AND pl.full_name ILIKE \'%\' || c.full_name || \'%\'
                ) AS has_pep_hit
            FROM alerts al
            JOIN compliance_rules cr ON cr.rule_id = al.rule_id
            JOIN transactions t ON t.transaction_id = al.transaction_id
            JOIN accounts ac ON ac.account_id = t.account_id
            JOIN customers c ON c.customer_id = ac.customer_id
            LEFT JOIN countries cnt ON cnt.country_code = t.destination_country
            LEFT JOIN countries nat ON nat.country_code = c.nationality
            LEFT JOIN compliance_officers co ON co.officer_id = al.assigned_to
            WHERE al.alert_id = %s
            """,
            (alert_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
        alert = dict(row)

        cur.execute(
            """
            SELECT ac.comment_id, ac.comment, ac.created_at, co.full_name AS officer_name
            FROM alert_comments ac
            LEFT JOIN compliance_officers co ON co.officer_id = ac.officer_id
            WHERE ac.alert_id = %s ORDER BY ac.created_at ASC
            """,
            (alert_id,),
        )
        alert["comments"] = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT t2.transaction_id, t2.amount, t2.currency_code, t2.amount_usd,
                   t2.transaction_type, t2.destination_country, t2.is_flagged, t2.created_at
            FROM transactions t2
            JOIN accounts ac2 ON ac2.account_id = t2.account_id
            WHERE ac2.customer_id = %s ORDER BY t2.created_at DESC LIMIT 10
            """,
            (alert["customer_id"],),
        )
        alert["recent_transactions"] = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT al2.alert_id, al2.severity, al2.status, al2.created_at, cr2.rule_name
            FROM alerts al2 JOIN compliance_rules cr2 ON cr2.rule_id = al2.rule_id
            JOIN transactions t3 ON t3.transaction_id = al2.transaction_id
            JOIN accounts ac3 ON ac3.account_id = t3.account_id
            WHERE ac3.customer_id = %s AND al2.alert_id != %s
            ORDER BY al2.created_at DESC LIMIT 5
            """,
            (alert["customer_id"], alert_id),
        )
        alert["prior_alerts"] = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT cs.case_id, cs.case_type, cs.status, cs.priority, cs.opened_at, cs.summary
            FROM cases cs WHERE cs.customer_id = %s ORDER BY cs.opened_at DESC LIMIT 5
            """,
            (alert["customer_id"],),
        )
        alert["prior_cases"] = [dict(r) for r in cur.fetchall()]

    try:
        from compliance_agent.config import Settings
        settings = Settings.from_env()
        latest = _latest_agent_run(settings.sidecar_db_path, alert_id)
        alert["latest_run_id"] = latest["run_id"] if latest else None
    except Exception:
        alert["latest_run_id"] = None

    return alert


class AddCommentBody(BaseModel):
    comment: str


@router.post("/alerts/{alert_id}/comments", status_code=201)
def add_comment(
    alert_id: int,
    body: AddCommentBody,
    officer: dict = Depends(require_view),
) -> dict:
    if not body.comment.strip():
        raise HTTPException(status_code=422, detail="comment must not be empty")
    with rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT alert_id FROM alerts WHERE alert_id = %s", (alert_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
            cur.execute(
                "INSERT INTO alert_comments (alert_id, officer_id, comment) VALUES (%s, %s, %s)",
                (alert_id, officer["officer_id"], body.comment.strip()),
            )
            insert_audit(cur, officer_id=officer["officer_id"], action="add_comment",
                         entity_type="alert", entity_id=alert_id, alert_id=alert_id)
    return {"ok": True}


class DispositionBody(BaseModel):
    status: str
    notes: str


@router.post("/alerts/{alert_id}/disposition")
def set_disposition(
    alert_id: int,
    body: DispositionBody,
    officer: dict = Depends(require_manage),
) -> dict:
    if body.status not in ALLOWED_STATUS:
        raise HTTPException(status_code=422, detail=f"Invalid status \'{body.status}\'")
    with rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT alert_id FROM alerts WHERE alert_id = %s", (alert_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
            cur.execute(
                "UPDATE alerts SET status = %s, notes = %s WHERE alert_id = %s",
                (body.status, body.notes, alert_id),
            )
            insert_audit(cur, officer_id=officer["officer_id"], action="set_disposition",
                         entity_type="alert", entity_id=alert_id, alert_id=alert_id,
                         details={"status": body.status, "notes": body.notes})
    return {"ok": True, "status": body.status}
'''

CASES_CONTENT = '''from __future__ import annotations

import logging

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
        raise HTTPException(status_code=422, detail=f"Invalid case_type \'{body.case_type}\'")
    if body.priority not in ALLOWED_PRIORITIES:
        raise HTTPException(status_code=422, detail=f"Invalid priority \'{body.priority}\'")
    with rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT customer_id FROM customers WHERE customer_id = %s", (body.customer_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"Customer {body.customer_id} not found")
            cur.execute(
                "INSERT INTO cases (customer_id, officer_id, case_type, priority, summary, status) "
                "VALUES (%s, %s, %s, %s, %s, \'open\') RETURNING case_id",
                (body.customer_id, officer["officer_id"], body.case_type, body.priority, body.summary),
            )
            case_id = cur.fetchone()[0]
            insert_audit(cur, officer_id=officer["officer_id"], action="create_case",
                         entity_type="case", entity_id=case_id, case_id=case_id,
                         details={"case_type": body.case_type, "priority": body.priority})
    return {"case_id": case_id, "ok": True}


class LinkAlertBody(BaseModel):
    alert_id: int


@router.post("/cases/{case_id}/link-alert")
def link_alert(case_id: int, body: LinkAlertBody, officer: dict = Depends(require_manage)) -> dict:
    with rw_conn() as conn:
        with conn.cursor() as cur:
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
        raise HTTPException(status_code=422, detail=f"Invalid case status \'{body.status}\'")
    with rw_conn() as conn:
        with conn.cursor() as cur:
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

(ROUTES / "alerts.py").write_text(ALERTS_CONTENT, encoding="utf-8")
(ROUTES / "cases.py").write_text(CASES_CONTENT, encoding="utf-8")
print("alerts.py and cases.py written.")
