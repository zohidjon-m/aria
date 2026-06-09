from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


Purpose = Literal[
    "triage",
    "investigation",
    "risk_scoring",
    "sar_drafting",
    "evaluation",
]

MCPStatus = Literal["ok", "partial", "denied", "error"]
Recommendation = Literal["likely_false_positive", "needs_investigation", "escalate"]
ValidationStatusValue = Literal["passed", "failed", "not_run"]
RuntimeState = Literal[
    "created",
    "context_loaded",
    "planning",
    "tool_requested",
    "tool_executed",
    "observing",
    "revising",
    "validating",
    "proposed",
    "failed_safe",
]


class StrictContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SubjectRef(StrictContractModel):
    alert_id: int | None = None
    case_id: int | None = None
    customer_id: int | None = None


class ToolExecutionScope(StrictContractModel):
    allowed_customer_ids: list[int] = Field(default_factory=list)
    allowed_account_ids: list[int] = Field(default_factory=list)
    allowed_transaction_ids: list[int] = Field(default_factory=list)
    allowed_case_ids: list[int] = Field(default_factory=list)


class MCPRequestEnvelope(StrictContractModel):
    tenant_id: str = Field(min_length=1)
    officer_id: str = Field(min_length=1)
    agent_run_id: str = Field(min_length=1)
    purpose: Purpose
    subject: SubjectRef
    scope: ToolExecutionScope
    tool_args: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)


class MCPSourceRef(StrictContractModel):
    source_system: str = "bank_mcp"
    entity_type: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    field_names: list[str] = Field(default_factory=list)
    retrieved_at: str = Field(min_length=1)


class DataCompleteness(StrictContractModel):
    complete: bool = True
    rows_returned: int | None = Field(default=None, ge=0)
    rows_requested: int | None = Field(default=None, ge=0)
    missing_segments: list[str] = Field(default_factory=list)
    lookback_days_requested: int | None = Field(default=None, ge=1)
    lookback_days_available: int | None = Field(default=None, ge=0)


class PolicyDecision(StrictContractModel):
    decision: Literal["allow", "deny", "limit", "audit"]
    policy: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class MCPResponseEnvelope(StrictContractModel):
    status: MCPStatus
    facts: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[MCPSourceRef] = Field(default_factory=list)
    data_completeness: DataCompleteness = Field(default_factory=DataCompleteness)
    limitations: list[str] = Field(default_factory=list)
    audit_id: str = Field(min_length=1)
    policy_decisions: list[PolicyDecision] = Field(default_factory=list)


class ToolCatalogItem(StrictContractModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    purpose: Purpose
    read_only: bool = True
    args_schema: dict[str, Any] = Field(default_factory=dict)
    response_schema: dict[str, Any] = Field(default_factory=dict)


class RuntimeBounds(StrictContractModel):
    max_steps: int = Field(default=6, ge=1, le=20)
    max_tool_calls: int = Field(default=6, ge=1, le=20)
    max_rows: int = Field(default=100, ge=1, le=500)
    max_graph_hops: int = Field(default=4, ge=1, le=8)
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0)
    max_cost_usd: float = Field(default=1.0, ge=0.0, le=100.0)


class AgentRunRequest(StrictContractModel):
    tenant_id: str = Field(min_length=1)
    officer_id: str = Field(min_length=1)
    purpose: Purpose = "triage"
    subject: SubjectRef
    scope: ToolExecutionScope
    scenario: str | None = None
    runtime_bounds: RuntimeBounds = Field(default_factory=RuntimeBounds)


class AgentToolCall(StrictContractModel):
    step_number: int = Field(ge=1)
    tool_name: str = Field(min_length=1)
    tool_args: dict[str, Any] = Field(default_factory=dict)
    status: MCPStatus
    audit_id: str | None = None
    stop_reason: str | None = None


class AgentObservation(StrictContractModel):
    step_number: int = Field(ge=1)
    tool_name: str = Field(min_length=1)
    facts: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[MCPSourceRef] = Field(default_factory=list)
    data_completeness: DataCompleteness = Field(default_factory=DataCompleteness)
    limitations: list[str] = Field(default_factory=list)


class AgentTraceStep(StrictContractModel):
    step_number: int = Field(ge=1)
    status: Literal["planning", "tool_executed", "observing", "revising", "proposed", "failed_safe"]
    thought: str | None = None
    hypothesis_before: str | None = None
    hypothesis_after: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    stop_reason: str | None = None
    error: str | None = None


class RuntimeEvent(StrictContractModel):
    event_id: str = Field(min_length=1)
    sequence_number: int = Field(ge=1)
    state: RuntimeState
    event_type: str = Field(min_length=1)
    step_number: int | None = Field(default=None, ge=1)
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    status: str | None = None
    stop_reason: str | None = None
    hypothesis_before: str | None = None
    hypothesis_after: str | None = None
    audit_id: str | None = None
    policy_decisions: list[PolicyDecision] = Field(default_factory=list)
    data_completeness: DataCompleteness | None = None
    error: str | None = None
    created_at: str = Field(min_length=1)


class FactualClaim(StrictContractModel):
    statement: str = Field(min_length=1)
    evidence_refs: list[MCPSourceRef] = Field(default_factory=list)


class ValidationStatus(StrictContractModel):
    status: ValidationStatusValue
    unsupported_claim_count: int = Field(default=0, ge=0)
    findings: list[str] = Field(default_factory=list)


class AgentProposal(StrictContractModel):
    run_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    subject: SubjectRef
    recommendation: Recommendation
    confidence: float = Field(ge=0.0, le=1.0)
    score: float = Field(ge=0.0, le=100.0)
    structured_reasoning: list[str] = Field(default_factory=list)
    factual_claims: list[FactualClaim] = Field(default_factory=list)
    evidence_refs: list[MCPSourceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    data_completeness: DataCompleteness = Field(default_factory=DataCompleteness)
    required_human_action: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    tool_registry_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    runtime_bounds: RuntimeBounds
    validation_status: ValidationStatus
    terminal_state: RuntimeState
    stop_reason: str = Field(min_length=1)
    runtime_events: list[RuntimeEvent] = Field(default_factory=list)
    trace: list[AgentTraceStep] = Field(default_factory=list)
    tool_calls: list[AgentToolCall] = Field(default_factory=list)
    observations: list[AgentObservation] = Field(default_factory=list)
