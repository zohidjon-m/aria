import os
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
from mcp_server import db

load_dotenv()

mcp = FastMCP("AML_Compliance_Database")

@mcp.tool()
def query_database(sql: str) -> dict:
    """Execute a read-only SQL SELECT query against the compliance database."""
    if "LIMIT " not in sql.upper():
        sql += " LIMIT 100"
    data = db.query(sql)
    return {"row_count": len(data), "data": data}

@mcp.tool()
def analyze_customer(customer_id: int) -> dict:
    """Get complete risk profile for a customer including accounts, transactions, alerts, cases, and risk scores."""
    
    customer = db.query(f"""
        SELECT c.*, co.country_name, co.fatf_status, co.risk_score as country_risk
        FROM customers c
        LEFT JOIN countries co ON c.nationality = co.country_code
        WHERE c.customer_id = {customer_id}
    """)
    accounts = db.query(f"""
        SELECT a.*, b.branch_name, b.city
        FROM accounts a
        JOIN branches b ON a.branch_id = b.branch_id
        WHERE a.customer_id = {customer_id}
    """)
    recent_transactions = db.query(f"""
        SELECT t.*, dest.country_name as dest_country_name,
               dest.fatf_status as dest_fatf_status
        FROM transactions t
        JOIN accounts a ON t.account_id = a.account_id
        LEFT JOIN countries dest ON t.destination_country = dest.country_code
        WHERE a.customer_id = {customer_id}
          AND t.created_at >= NOW() - INTERVAL '90 days'
        ORDER BY t.created_at DESC
    """)
    open_alerts = db.query(f"""
        SELECT al.*, cr.rule_name, cr.rule_type
        FROM alerts al
        JOIN transactions t ON al.transaction_id = t.transaction_id
        JOIN accounts a ON t.account_id = a.account_id
        JOIN compliance_rules cr ON al.rule_id = cr.rule_id
        WHERE a.customer_id = {customer_id}
          AND al.status NOT IN ('dismissed', 'resolved')
        ORDER BY al.created_at DESC
    """)
    cases = db.query(f"""
        SELECT cs.*, co.full_name as officer_name
        FROM cases cs
        JOIN compliance_officers co ON cs.officer_id = co.officer_id
        WHERE cs.customer_id = {customer_id}
        ORDER BY cs.opened_at DESC
    """)
    latest_risk_score = db.query(f"""
        SELECT * FROM risk_scores
        WHERE customer_id = {customer_id}
        ORDER BY computed_at DESC
        LIMIT 1
    """)
    transaction_patterns = db.query(f"""
        SELECT * FROM transaction_patterns
        WHERE customer_id = {customer_id}
        ORDER BY computed_at DESC
        LIMIT 1
    """)

    return {
        "customer": customer[0] if customer else None,
        "accounts": accounts,
        "recent_transactions": recent_transactions,
        "open_alerts": open_alerts,
        "cases": cases,
        "latest_risk_score": latest_risk_score[0] if latest_risk_score else None,
        "transaction_patterns": transaction_patterns[0] if transaction_patterns else None
    }

@mcp.tool()
def triage_alert(alert_id: int) -> dict:
    """Get full context for an alert to assess whether it is a true positive or false positive."""
    alert = db.query(f"""
        SELECT al.*, cr.rule_name, cr.rule_type, cr.threshold_amount,
               cr.max_frequency, cr.time_window_days
        FROM alerts al
        JOIN compliance_rules cr ON al.rule_id = cr.rule_id
        WHERE al.alert_id = {alert_id}
    """)
    triggering_tx = db.query(f"""
        SELECT t.*, a.account_number, a.account_type,
               c.full_name as customer_name, c.customer_id,
               c.risk_level, c.kyc_status, c.nationality,
               dest.country_name as dest_country_name,
               dest.fatf_status as dest_fatf_status,
               dest.risk_score as dest_country_risk
        FROM transactions t
        JOIN alerts al ON al.transaction_id = t.transaction_id
        JOIN accounts a ON t.account_id = a.account_id
        JOIN customers c ON a.customer_id = c.customer_id
        LEFT JOIN countries dest ON t.destination_country = dest.country_code
        WHERE al.alert_id = {alert_id}
    """)
    prior_alerts = db.query(f"""
        SELECT al2.alert_id, al2.severity, al2.status,
               cr.rule_name, al2.created_at
        FROM alerts al2
        JOIN compliance_rules cr ON al2.rule_id = cr.rule_id
        JOIN transactions t2 ON al2.transaction_id = t2.transaction_id
        JOIN accounts a2 ON t2.account_id = a2.account_id
        JOIN transactions t ON t.transaction_id = (
            SELECT transaction_id FROM alerts WHERE alert_id = {alert_id}
        )
        JOIN accounts a ON t.account_id = a.account_id
        WHERE a2.customer_id = a.customer_id
          AND al2.alert_id != {alert_id}
        ORDER BY al2.created_at DESC
        LIMIT 10
    """)
    return {
        "alert": alert[0] if alert else None,
        "triggering_transaction": triggering_tx[0] if triggering_tx else None,
        "prior_alerts": prior_alerts
    }

@mcp.tool()
def draft_case_narrative(case_id: int) -> dict:
    """Get all data needed to draft an investigation narrative for a case."""
    case_details = db.query(f"""
        SELECT cs.*, c.full_name as customer_name, c.risk_level,
               c.kyc_status, c.nationality,
               co.full_name as officer_name, co.email as officer_email
        FROM cases cs
        JOIN customers c ON cs.customer_id = c.customer_id
        JOIN compliance_officers co ON cs.officer_id = co.officer_id
        WHERE cs.case_id = {case_id}
    """)
    linked_alerts = db.query(f"""
        SELECT al.*, cr.rule_name, cr.rule_type,
               t.amount_usd, t.transaction_type,
               t.destination_country, t.created_at as tx_date
        FROM case_alerts ca
        JOIN alerts al ON ca.alert_id = al.alert_id
        JOIN compliance_rules cr ON al.rule_id = cr.rule_id
        JOIN transactions t ON al.transaction_id = t.transaction_id
        WHERE ca.case_id = {case_id}
        ORDER BY al.created_at
    """)
    all_transactions = db.query(f"""
        SELECT t.*, a.account_number,
               dest.country_name as dest_country_name,
               dest.fatf_status
        FROM transactions t
        JOIN accounts a ON t.account_id = a.account_id
        JOIN cases cs ON cs.customer_id = a.customer_id
        LEFT JOIN countries dest ON t.destination_country = dest.country_code
        WHERE cs.case_id = {case_id}
          AND t.created_at BETWEEN cs.opened_at - INTERVAL '30 days'
                               AND COALESCE(cs.closed_at, NOW())
        ORDER BY t.created_at
    """)
    alert_comments = db.query(f"""
        SELECT ac.*, co.full_name as author
        FROM alert_comments ac
        JOIN compliance_officers co ON ac.officer_id = co.officer_id
        JOIN alerts al ON ac.alert_id = al.alert_id
        JOIN case_alerts ca ON al.alert_id = ca.alert_id
        WHERE ca.case_id = {case_id}
        ORDER BY ac.created_at
    """)
    return {
        "case_details": case_details[0] if case_details else None,
        "linked_alerts": linked_alerts,
        "all_transactions": all_transactions,
        "alert_comments": alert_comments
    }

@mcp.tool()
def draft_sar_report(case_id: int) -> dict:
    """Get all data needed to draft a Suspicious Activity Report for a case."""
    base_narrative = draft_case_narrative(case_id)
    
    regulatory_reports = db.query(f"""
        SELECT * FROM regulatory_reports
        WHERE case_id = {case_id}
    """)
    kyc_data = db.query(f"""
        SELECT c.*, co.country_name, co.fatf_status
        FROM customers c
        JOIN cases cs ON cs.customer_id = c.customer_id
        LEFT JOIN countries co ON c.nationality = co.country_code
        WHERE cs.case_id = {case_id}
    """)
    totals = db.query(f"""
        SELECT
          COUNT(*) as total_transactions,
          SUM(t.amount_usd) as total_amount_usd,
          MIN(t.created_at) as first_activity,
          MAX(t.created_at) as last_activity,
          COUNT(DISTINCT t.destination_country) as countries_involved
        FROM transactions t
        JOIN accounts a ON t.account_id = a.account_id
        JOIN case_alerts ca ON ca.case_id = {case_id}
        JOIN alerts al ON ca.alert_id = al.alert_id
        WHERE al.transaction_id = t.transaction_id
    """)
    
    return {
        "case_details": base_narrative.get("case_details"),
        "linked_alerts": base_narrative.get("linked_alerts"),
        "all_transactions": base_narrative.get("all_transactions"),
        "alert_comments": base_narrative.get("alert_comments"),
        "regulatory_reports": regulatory_reports,
        "kyc_data": kyc_data[0] if kyc_data else None,
        "totals": totals[0] if totals else None
    }

if __name__ == "__main__":
    host = os.getenv("MCP_SERVER_HOST", "localhost")
    port = int(os.getenv("MCP_SERVER_PORT", "8001"))
    
    # Enable SSE transport
    mcp.settings.host = host
    mcp.settings.port = port
    mcp.run(transport='sse')
