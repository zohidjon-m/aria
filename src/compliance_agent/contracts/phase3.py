from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .phase1 import (
    DataCompleteness,
    MCPSourceRef,
    MCPStatus,
    Purpose,
    StrictContractModel,
    SubjectRef,
    ToolExecutionScope,
)


Phase3ToolCategory = Literal["read", "bank_write", "sidecar_write", "sidecar_proposal"]
Phase3SideEffectType = Literal[
    "none",
    "bank_system_write",
    "sidecar_persistence",
    "proposal_only",
    "draft_only",
]
Phase3Permission = Literal[
    "can_view_alerts",
    "can_manage_cases",
    "can_file_sar",
    "can_manage_rules",
    "can_manage_users",
    "service_identity",
]
Phase3PolicyDecisionValue = Literal["allow", "deny", "limit", "audit", "requires_human_review"]
Phase3DecisionSource = Literal["scope_policy", "rbac", "runtime_policy", "bank_mcp", "sidecar_policy"]
Phase3AuditOutcome = Literal["success", "denial", "partial_response", "error"]
Phase3RequestedBy = Literal["agent", "officer", "service"]
Phase3ExecutionOwner = Literal["bank_mcp", "sidecar"]
Phase3ScopeExpansionMode = Literal["none", "bounded_graph_traversal", "requires_policy_approval"]


class Phase3AuthContext(StrictContractModel):
    actor_type: Literal["officer", "service", "agent_runtime"]
    token_subject: str = Field(min_length=1)
    token_audience: str = Field(min_length=1)
    role_name: str | None = None
    granted_permissions: list[Phase3Permission] = Field(default_factory=list)


class Phase3PolicyDecision(StrictContractModel):
    decision: Phase3PolicyDecisionValue
    decision_source: Phase3DecisionSource
    policy: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    required_permissions: list[Phase3Permission] = Field(default_factory=list)
    granted_permissions: list[Phase3Permission] = Field(default_factory=list)
    missing_permissions: list[Phase3Permission] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class Phase3MCPRequestEnvelope(StrictContractModel):
    tenant_id: str = Field(min_length=1)
    officer_id: str = Field(min_length=1)
    agent_run_id: str = Field(min_length=1)
    purpose: Purpose
    requested_by: Phase3RequestedBy
    subject: SubjectRef
    scope: ToolExecutionScope
    tool_name: str = Field(min_length=1)
    tool_args: dict[str, Any] = Field(default_factory=dict)
    auth_context: Phase3AuthContext
    policy_version: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)


class Phase3AuditEvent(StrictContractModel):
    audit_id: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    officer_id: str = Field(min_length=1)
    agent_run_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    tool_category: Phase3ToolCategory
    outcome: Phase3AuditOutcome
    status: MCPStatus
    idempotency_key: str = Field(min_length=1)
    policy_decisions: list[Phase3PolicyDecision] = Field(default_factory=list)
    source_refs: list[MCPSourceRef] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(min_length=1)


class Phase3MCPResponseEnvelope(StrictContractModel):
    status: MCPStatus
    facts: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[MCPSourceRef] = Field(default_factory=list)
    data_completeness: DataCompleteness = Field(default_factory=DataCompleteness)
    limitations: list[str] = Field(default_factory=list)
    audit_event: Phase3AuditEvent
    policy_decisions: list[Phase3PolicyDecision] = Field(default_factory=list)


class Phase3ScopeExpansionPolicy(StrictContractModel):
    mode: Phase3ScopeExpansionMode
    description: str = Field(min_length=1)
    max_hops: int | None = Field(default=None, ge=1)
    max_rows: int | None = Field(default=None, ge=1)
    expandable_entity_types: list[str] = Field(default_factory=list)
    forbidden_tool_arg_fields: list[str] = Field(default_factory=list)
    requires_policy_decision: bool = True
    audit_required: bool = True


class Phase3ToolExample(StrictContractModel):
    name: str = Field(min_length=1)
    request: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] = Field(default_factory=dict)


class Phase3ToolMetadata(StrictContractModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    category: Phase3ToolCategory
    purpose: Purpose
    side_effect_type: Phase3SideEffectType
    execution_owner: Phase3ExecutionOwner
    required_permissions: list[Phase3Permission] = Field(default_factory=list)
    deterministic_policy_required: bool = True
    human_review_required: bool = False
    idempotency_required: bool = True
    llm_may_request: bool = True
    args_schema: dict[str, Any] = Field(default_factory=dict)
    response_schema: dict[str, Any] = Field(default_factory=dict)
    scope_expansion_policy: Phase3ScopeExpansionPolicy | None = None
    audit_outcomes: list[Phase3AuditOutcome] = Field(default_factory=list)
    examples: list[Phase3ToolExample] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
