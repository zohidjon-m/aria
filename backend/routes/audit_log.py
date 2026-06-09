from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..db import ro_cursor
from ..rbac import require_view

router = APIRouter()


@router.get("/audit-log")
def get_audit_log(
    officer: dict = Depends(require_view),
    officer_id: int | None = Query(None),
    entity_type: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    conditions: list[str] = []
    params: list = []
    if officer_id is not None:
        conditions.append("al.officer_id = %s")
        params.append(officer_id)
    if entity_type:
        conditions.append("al.entity_type = %s")
        params.append(entity_type)
    if date_from:
        conditions.append("al.action_at >= %s")
        params.append(date_from)
    if date_to:
        conditions.append("al.action_at <= %s")
        params.append(date_to)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    offset = (page - 1) * limit

    with ro_cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS total FROM audit_log al {where}", params)
        total = cur.fetchone()["total"]
        cur.execute(
            f"""
            SELECT al.log_id, al.action, al.entity_type, al.entity_id,
                   al.case_id, al.alert_id, al.details, al.ip_address, al.action_at,
                   co.full_name AS officer_name, co.officer_id
            FROM audit_log al
            LEFT JOIN compliance_officers co ON co.officer_id = al.officer_id
            {where}
            ORDER BY al.action_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        items = [dict(r) for r in cur.fetchall()]
    return {"total": total, "page": page, "limit": limit, "items": items}
