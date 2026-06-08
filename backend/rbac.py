from __future__ import annotations

from fastapi import Depends, Header, HTTPException

from .db import ro_cursor


def get_officer(x_officer_id: str = Header(..., alias="X-Officer-Id")) -> dict:
    try:
        officer_id = int(x_officer_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=403, detail="Invalid X-Officer-Id header")

    with ro_cursor() as cur:
        cur.execute(
            """
            SELECT
                co.officer_id,
                co.full_name,
                co.email,
                co.is_active,
                co.branch_id,
                r.role_id,
                r.role_name,
                r.can_view_alerts,
                r.can_manage_cases,
                r.can_file_sar,
                r.can_manage_rules,
                r.can_manage_users
            FROM compliance_officers co
            JOIN officer_roles r ON r.role_id = co.role_id
            WHERE co.officer_id = %s
            """,
            (officer_id,),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=403, detail="Officer not found")
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="Officer account is inactive")
    return dict(row)


def require_view(officer: dict = Depends(get_officer)) -> dict:
    if not officer["can_view_alerts"]:
        raise HTTPException(status_code=403, detail="Requires can_view_alerts permission")
    return officer


def require_manage(officer: dict = Depends(get_officer)) -> dict:
    if not officer["can_manage_cases"]:
        raise HTTPException(status_code=403, detail="Requires can_manage_cases permission")
    return officer
