from __future__ import annotations

from typing import Any

from .phase3 import Phase3ScopeExpansionPolicy, Phase3ToolMetadata


PHASE3_TOOL_REGISTRY_VERSION = "phase3_bank_mcp_contract_v1"

_RESPONSE_SCHEMA_REF: dict[str, Any] = {"$ref": "phase3_mcp_response_envelope.schema.json"}
_NO_ARGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}
_BOUNDED_LOOKBACK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "lookback_days": {"type": "integer", "minimum": 1, "maximum": 365},
        "max_rows": {"type": "integer", "minimum": 1, "maximum": 100},
    },
    "additionalProperties": False,
}
_MAX_ROWS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"max_rows": {"type": "integer", "minimum": 1, "maximum": 100}},
    "additionalProperties": False,
}


def _example(tool_name: str, facts_key: str = "result") -> dict[str, Any]:
    return {
        "name": f"{tool_name}_contract_example",
        "request": {
            "tenant_id": "demo-bank",
            "officer_id": "officer-123",
            "agent_run_id": "run-phase3-example",
            "requested_by": "agent",
            "tool_name": tool_name,
            "tool_args": {},
            "idempotency_key": f"idem-{tool_name}",
            "correlation_id": "corr-phase3-example",
        },
        "response": {
            "status": "ok",
            "facts": {facts_key: {}},
            "audit_event": {
                "audit_id": f"audit-{tool_name}",
                "outcome": "success",
                "status": "ok",
                "tool_name": tool_name,
            },
        },
    }


def _tool(
    *,
    name: str,
    description: str,
    category: str,
    purpose: str,
    side_effect_type: str,
    execution_owner: str,
    required_permissions: list[str],
    args_schema: dict[str, Any],
    facts_key: str,
    human_review_required: bool = False,
    llm_may_request: bool = True,
    scope_expansion_policy: Phase3ScopeExpansionPolicy | None = None,
    notes: list[str] | None = None,
) -> Phase3ToolMetadata:
    return Phase3ToolMetadata(
        name=name,
        description=description,
        category=category,  # type: ignore[arg-type]
        purpose=purpose,  # type: ignore[arg-type]
        side_effect_type=side_effect_type,  # type: ignore[arg-type]
        execution_owner=execution_owner,  # type: ignore[arg-type]
        required_permissions=required_permissions,  # type: ignore[arg-type]
        deterministic_policy_required=True,
        human_review_required=human_review_required,
        idempotency_required=True,
        llm_may_request=llm_may_request,
        args_schema=args_schema,
        response_schema=_RESPONSE_SCHEMA_REF,
        scope_expansion_policy=scope_expansion_policy,
        audit_outcomes=["success", "denial", "partial_response", "error"],
        examples=[_example(name, facts_key)],
        notes=notes or [],
    )


_GRAPH_SCOPE_POLICY = Phase3ScopeExpansionPolicy(
    mode="bounded_graph_traversal",
    description=(
        "Counterparty graph traversal may expand from the active alert transaction "
        "only through bank-owned graph policy, bounded hops, bounded rows, and "
        "audited source references."
    ),
    max_hops=4,
    max_rows=100,
    expandable_entity_types=["account", "customer", "transaction", "alert", "case"],
    forbidden_tool_arg_fields=[
        "alert_id",
        "case_id",
        "customer_id",
        "account_id",
        "transaction_id",
    ],
)


PHASE3_TOOL_CATALOG: list[Phase3ToolMetadata] = [
    _tool(
        name="get_customer_profile",
        description="Return scoped customer, account, and latest profile facts.",
        category="read",
        purpose="triage",
        side_effect_type="none",
        execution_owner="bank_mcp",
        required_permissions=["can_view_alerts"],
        args_schema=_NO_ARGS_SCHEMA,
        facts_key="customer_profile",
    ),
    _tool(
        name="get_transaction_history",
        description="Return bounded transaction history for the scoped customer.",
        category="read",
        purpose="triage",
        side_effect_type="none",
        execution_owner="bank_mcp",
        required_permissions=["can_view_alerts"],
        args_schema=_BOUNDED_LOOKBACK_SCHEMA,
        facts_key="transactions",
    ),
    _tool(
        name="get_behavioral_baseline",
        description="Return customer-relative behavioral baseline features.",
        category="read",
        purpose="triage",
        side_effect_type="none",
        execution_owner="bank_mcp",
        required_permissions=["can_view_alerts"],
        args_schema=_BOUNDED_LOOKBACK_SCHEMA,
        facts_key="behavioral_baseline",
    ),
    _tool(
        name="get_prior_alerts",
        description="Return prior alerts for the scoped customer.",
        category="read",
        purpose="triage",
        side_effect_type="none",
        execution_owner="bank_mcp",
        required_permissions=["can_view_alerts"],
        args_schema=_MAX_ROWS_SCHEMA,
        facts_key="prior_alerts",
    ),
    _tool(
        name="get_case_history",
        description="Return case history and linked alert context for the scoped customer.",
        category="read",
        purpose="investigation",
        side_effect_type="none",
        execution_owner="bank_mcp",
        required_permissions=["can_view_alerts"],
        args_schema=_MAX_ROWS_SCHEMA,
        facts_key="case_history",
    ),
    _tool(
        name="trace_counterparty_graph",
        description="Trace bounded counterparty graph paths from the alert transaction.",
        category="read",
        purpose="investigation",
        side_effect_type="none",
        execution_owner="bank_mcp",
        required_permissions=["can_view_alerts"],
        args_schema={
            "type": "object",
            "properties": {
                "max_hops": {"type": "integer", "minimum": 1, "maximum": 4},
                "max_rows": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "additionalProperties": False,
        },
        facts_key="counterparty_graph",
        scope_expansion_policy=_GRAPH_SCOPE_POLICY,
    ),
    _tool(
        name="screen_sanctions_pep",
        description="Return sanctions and PEP screening facts for the scoped customer.",
        category="read",
        purpose="investigation",
        side_effect_type="none",
        execution_owner="bank_mcp",
        required_permissions=["can_view_alerts"],
        args_schema=_NO_ARGS_SCHEMA,
        facts_key="screening",
    ),
    _tool(
        name="get_similar_alerts",
        description="Return similar prior alerts for the scoped customer and alert rule.",
        category="read",
        purpose="triage",
        side_effect_type="none",
        execution_owner="bank_mcp",
        required_permissions=["can_view_alerts"],
        args_schema=_MAX_ROWS_SCHEMA,
        facts_key="similar_alerts",
    ),
    _tool(
        name="get_compliance_rule",
        description="Return the compliance rule that generated the scoped alert.",
        category="read",
        purpose="triage",
        side_effect_type="none",
        execution_owner="bank_mcp",
        required_permissions=["can_view_alerts"],
        args_schema=_NO_ARGS_SCHEMA,
        facts_key="compliance_rule",
    ),
    _tool(
        name="get_officer_permissions",
        description="Return bank-owned permission facts for the acting officer.",
        category="read",
        purpose="triage",
        side_effect_type="none",
        execution_owner="bank_mcp",
        required_permissions=["can_view_alerts"],
        args_schema=_NO_ARGS_SCHEMA,
        facts_key="officer_permissions",
        llm_may_request=False,
        notes=["The LLM may read permission facts supplied by the runtime but cannot grant or decide permissions."],
    ),
    _tool(
        name="add_alert_comment",
        description="Add an officer-visible comment to a scoped alert.",
        category="bank_write",
        purpose="investigation",
        side_effect_type="bank_system_write",
        execution_owner="bank_mcp",
        required_permissions=["can_view_alerts"],
        args_schema={
            "type": "object",
            "properties": {"comment": {"type": "string", "minLength": 1, "maxLength": 4000}},
            "required": ["comment"],
            "additionalProperties": False,
        },
        facts_key="alert_comment",
        human_review_required=True,
    ),
    _tool(
        name="open_case",
        description="Open a new AML case for the scoped customer.",
        category="bank_write",
        purpose="investigation",
        side_effect_type="bank_system_write",
        execution_owner="bank_mcp",
        required_permissions=["can_manage_cases"],
        args_schema={
            "type": "object",
            "properties": {
                "case_type": {"type": "string", "enum": ["AML", "fraud", "sanctions", "pep", "other"]},
                "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                "summary": {"type": "string", "maxLength": 8000},
            },
            "required": ["case_type", "priority"],
            "additionalProperties": False,
        },
        facts_key="case",
        human_review_required=True,
    ),
    _tool(
        name="link_alert_to_case",
        description="Link the scoped alert to an authorized existing case.",
        category="bank_write",
        purpose="investigation",
        side_effect_type="bank_system_write",
        execution_owner="bank_mcp",
        required_permissions=["can_manage_cases"],
        args_schema={
            "type": "object",
            "properties": {"relationship": {"type": "string", "enum": ["primary", "related"]}},
            "additionalProperties": False,
        },
        facts_key="case_alert_link",
        human_review_required=True,
    ),
    _tool(
        name="export_human_decision",
        description="Export a human officer decision to the bank system of record.",
        category="bank_write",
        purpose="triage",
        side_effect_type="bank_system_write",
        execution_owner="bank_mcp",
        required_permissions=["can_manage_cases"],
        args_schema={
            "type": "object",
            "properties": {
                "decision_type": {"type": "string", "enum": ["alert_disposition", "case_disposition", "sar_review"]},
                "decision": {"type": "string", "minLength": 1},
                "notes": {"type": "string", "maxLength": 8000},
            },
            "required": ["decision_type", "decision"],
            "additionalProperties": False,
        },
        facts_key="human_decision_export",
        human_review_required=True,
        notes=["SAR-related exports must also pass bank policy for can_file_sar."],
    ),
    _tool(
        name="record_agent_trace",
        description="Persist the agent trace in the sidecar audit store.",
        category="sidecar_write",
        purpose="triage",
        side_effect_type="sidecar_persistence",
        execution_owner="sidecar",
        required_permissions=["service_identity"],
        args_schema={
            "type": "object",
            "properties": {"trace": {"type": "object"}},
            "required": ["trace"],
            "additionalProperties": False,
        },
        facts_key="agent_trace",
    ),
    _tool(
        name="propose_alert_disposition",
        description="Store an agent disposition proposal for human review.",
        category="sidecar_proposal",
        purpose="triage",
        side_effect_type="proposal_only",
        execution_owner="sidecar",
        required_permissions=["service_identity"],
        args_schema={
            "type": "object",
            "properties": {
                "recommendation": {
                    "type": "string",
                    "enum": ["likely_false_positive", "needs_investigation", "escalate"],
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "evidence_refs": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["recommendation", "confidence"],
            "additionalProperties": False,
        },
        facts_key="alert_disposition_proposal",
        human_review_required=True,
    ),
    _tool(
        name="store_agent_risk_score",
        description="Store an agent-generated risk score proposal in the sidecar.",
        category="sidecar_write",
        purpose="risk_scoring",
        side_effect_type="sidecar_persistence",
        execution_owner="sidecar",
        required_permissions=["service_identity"],
        args_schema={
            "type": "object",
            "properties": {
                "score": {"type": "number", "minimum": 0, "maximum": 100},
                "factors": {"type": "array", "items": {"type": "object"}},
                "policy_version": {"type": "string", "minLength": 1},
            },
            "required": ["score", "policy_version"],
            "additionalProperties": False,
        },
        facts_key="agent_risk_score",
        human_review_required=True,
    ),
    _tool(
        name="draft_regulatory_report",
        description="Store a draft regulatory report narrative for authorized human review.",
        category="sidecar_proposal",
        purpose="sar_drafting",
        side_effect_type="draft_only",
        execution_owner="sidecar",
        required_permissions=["service_identity", "can_file_sar"],
        args_schema={
            "type": "object",
            "properties": {
                "report_type": {"type": "string", "enum": ["SAR", "CTR", "internal_memo"]},
                "narrative": {"type": "string", "minLength": 1},
                "evidence_refs": {"type": "array", "items": {"type": "object"}},
                "missing_fields": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["report_type", "narrative"],
            "additionalProperties": False,
        },
        facts_key="regulatory_report_draft",
        human_review_required=True,
        notes=["This tool creates drafts only. SAR filing is never an agent action."],
    ),
    _tool(
        name="record_evaluation_result",
        description="Persist evaluation replay results and metrics in the sidecar.",
        category="sidecar_write",
        purpose="evaluation",
        side_effect_type="sidecar_persistence",
        execution_owner="sidecar",
        required_permissions=["service_identity"],
        args_schema={
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string", "minLength": 1},
                "metrics": {"type": "object"},
                "run_refs": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["dataset_id", "metrics"],
            "additionalProperties": False,
        },
        facts_key="evaluation_result",
    ),
]

PHASE3_TOOL_NAMES = tuple(item.name for item in PHASE3_TOOL_CATALOG)
