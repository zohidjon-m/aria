from __future__ import annotations

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
