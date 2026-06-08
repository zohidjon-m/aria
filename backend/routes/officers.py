from __future__ import annotations

from fastapi import APIRouter

from ..db import ro_cursor

router = APIRouter()


@router.get("/officers")
def list_officers() -> list[dict]:
    with ro_cursor() as cur:
        cur.execute(
            """
            SELECT
                co.officer_id,
                co.full_name,
                co.email,
                co.is_active,
                co.branch_id,
                r.role_name,
                r.can_view_alerts,
                r.can_manage_cases,
                r.can_file_sar
            FROM compliance_officers co
            JOIN officer_roles r ON r.role_id = co.role_id
            WHERE co.is_active = TRUE
            ORDER BY co.full_name
            """
        )
        return [dict(row) for row in cur.fetchall()]
