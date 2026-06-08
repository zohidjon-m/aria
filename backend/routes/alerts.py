from fastapi import APIRouter, Query, Body, HTTPException
from typing import Optional
from mcp_server.db import query

router = APIRouter()

ALLOWED_STATUSES = {"open", "dismissed", "resolved"}

@router.get("/alerts")
def list_alerts(
    page: int = Query(1, ge=1),
    limit: int = 20,
    status: Optional[str] = None,
    severity: Optional[str] = None
):
    offset = (page - 1) * limit
    sql = """
        SELECT al.*, cr.rule_name, c.full_name as customer_name, c.customer_id
        FROM alerts al
        JOIN compliance_rules cr ON al.rule_id = cr.rule_id
        JOIN transactions t ON al.transaction_id = t.transaction_id
        JOIN accounts a ON t.account_id = a.account_id
        JOIN customers c ON a.customer_id = c.customer_id
        WHERE 1=1
    """
    params: list = []
    if status:
        sql += " AND al.status = %s"
        params.append(status)
    if severity:
        sql += " AND al.severity = %s"
        params.append(severity)

    sql += """
        ORDER BY
            CASE al.severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
            al.created_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    return {"data": query(sql, tuple(params)), "page": page, "limit": limit}

@router.get("/alerts/{alert_id}")
def get_alert(alert_id: int):
    al = query("SELECT * FROM alerts WHERE alert_id = %s", (alert_id,))
    if not al:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"alert": al[0]}

@router.patch("/alerts/{alert_id}/status")
def update_alert_status(alert_id: int, status: str = Body(..., embed=True)):
    if status not in ALLOWED_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{status}'. Must be one of: {sorted(ALLOWED_STATUSES)}",
        )
    import mcp_server.db as db
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute("UPDATE alerts SET status = %s WHERE alert_id = %s", (status, alert_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "success", "new_status": status}
