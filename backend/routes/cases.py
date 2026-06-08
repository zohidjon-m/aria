from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from mcp_server.db import query

router = APIRouter()

@router.get("/cases")
def list_cases(
    page: int = Query(1, ge=1),
    limit: int = 20,
    status: Optional[str] = None,
    case_type: Optional[str] = None
):
    offset = (page - 1) * limit
    sql = """
        SELECT cs.*, c.full_name as customer_name, co.full_name as officer_name
        FROM cases cs
        JOIN customers c ON cs.customer_id = c.customer_id
        LEFT JOIN compliance_officers co ON cs.officer_id = co.officer_id
        WHERE 1=1
    """
    params: list = []
    if status:
        sql += " AND cs.status = %s"
        params.append(status)
    if case_type:
        sql += " AND cs.case_type = %s"
        params.append(case_type)
    sql += " ORDER BY cs.opened_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    return {"data": query(sql, tuple(params)), "page": page, "limit": limit}

@router.get("/cases/{case_id}")
def get_case(case_id: int):
    cs = query(
        """
        SELECT cs.*, c.full_name as customer_name, co.full_name as officer_name
        FROM cases cs
        JOIN customers c ON cs.customer_id = c.customer_id
        LEFT JOIN compliance_officers co ON cs.officer_id = co.officer_id
        WHERE cs.case_id = %s
        """,
        (case_id,),
    )
    if not cs:
        raise HTTPException(status_code=404, detail="Case not found")

    linked_alerts = query(
        """
        SELECT al.*, cr.rule_name
        FROM case_alerts ca
        JOIN alerts al ON ca.alert_id = al.alert_id
        JOIN compliance_rules cr ON al.rule_id = cr.rule_id
        WHERE ca.case_id = %s
        """,
        (case_id,),
    )

    return {
        "case": cs[0],
        "linked_alerts": linked_alerts,
    }
