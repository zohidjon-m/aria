from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from mcp_server.db import query

router = APIRouter()

@router.get("/customers")
def list_customers(
    page: int = Query(1, ge=1),
    limit: int = 20,
    risk_level: Optional[str] = None,
    kyc_status: Optional[str] = None
):
    offset = (page - 1) * limit
    sql = "SELECT * FROM customers WHERE 1=1"
    params: list = []
    if risk_level:
        sql += " AND risk_level = %s"
        params.append(risk_level)
    if kyc_status:
        sql += " AND kyc_status = %s"
        params.append(kyc_status)
    sql += " ORDER BY customer_id LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    data = query(sql, tuple(params))
    return {"data": data, "page": page, "limit": limit}

@router.get("/customers/{customer_id}")
def get_customer(customer_id: int):
    c = query("SELECT * FROM customers WHERE customer_id = %s", (customer_id,))
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    accs = query("SELECT * FROM accounts WHERE customer_id = %s", (customer_id,))
    risk = query(
        "SELECT * FROM risk_scores WHERE customer_id = %s ORDER BY computed_at DESC LIMIT 1",
        (customer_id,),
    )
    return {
        "customer": c[0],
        "accounts": accs,
        "latest_risk": risk[0] if risk else None,
    }

@router.get("/customers/{customer_id}/alerts")
def get_customer_alerts(customer_id: int):
    return query(
        """
        SELECT al.*, cr.rule_name
        FROM alerts al
        JOIN transactions t ON al.transaction_id = t.transaction_id
        JOIN accounts a ON t.account_id = a.account_id
        JOIN compliance_rules cr ON al.rule_id = cr.rule_id
        WHERE a.customer_id = %s
        ORDER BY al.created_at DESC
        """,
        (customer_id,),
    )

@router.get("/customers/{customer_id}/transactions")
def get_customer_transactions(customer_id: int):
    return query(
        """
        SELECT t.*
        FROM transactions t
        JOIN accounts a ON t.account_id = a.account_id
        WHERE a.customer_id = %s
        ORDER BY t.created_at DESC LIMIT 50
        """,
        (customer_id,),
    )
