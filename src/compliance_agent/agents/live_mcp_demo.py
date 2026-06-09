from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..adapters.sidecar_store import SidecarStore
from ..agents.llm_planner import OpenAICompatibleChatProvider
from ..agents.validation import ComplianceValidationAgent
from ..contracts.phase1 import (
    AgentObservation,
    AgentProposal,
    AgentRunRequest,
    AgentToolCall,
    AgentTraceStep,
    DataCompleteness,
    FactualClaim,
    MCPRequestEnvelope,
    MCPResponseEnvelope,
    MCPSourceRef,
    RuntimeEvent,
    RuntimeBounds,
    RuntimeState,
    ValidationStatus,
)
from ..contracts.tool_catalog import (
    PHASE1_TOOL_CATALOG,
    PHASE1_TOOL_NAMES,
    TOOL_REGISTRY_VERSION,
)
from ..domain import AgentResult, Claim, EvidenceItem, ReasoningItem, SourceRef
from ..utils import new_id, stable_hash, to_plain


PROMPT_VERSION = "phase1_live_mcp_agent_v1"
POLICY_VERSION = "phase1_reference_mcp_policy_v1"

FAILED_SAFE = "failed_safe"
COMPLETED = "completed"
TOOL_DENIED = "tool_denied"
TOOL_ERROR = "tool_error"
SCHEMA_ERROR = "schema_error"
NO_PROGRESS = "no_progress"
BUDGET_EXHAUSTED = "budget_exhausted"
CRITICAL_SIGNAL_FOUND = "critical_signal_found"
INSUFFICIENT_EVIDENCE = "insufficient_evidence"
TIMEOUT = "timeout"

FAIL_SAFE_STOP_REASONS = {
    INSUFFICIENT_EVIDENCE,
    TOOL_DENIED,
    TOOL_ERROR,
    SCHEMA_ERROR,
    NO_PROGRESS,
    BUDGET_EXHAUSTED,
    TIMEOUT,
}

ALLOWED_RUNTIME_TRANSITIONS: dict[RuntimeState, set[RuntimeState]] = {
    "created": {"context_loaded", "validating", "failed_safe"},
    "context_loaded": {"planning", "validating", "failed_safe"},
    "planning": {"tool_requested", "validating", "failed_safe"},
    "tool_requested": {"tool_executed", "validating", "failed_safe"},
    "tool_executed": {"observing", "validating", "failed_safe"},
    "observing": {"revising", "validating", "failed_safe"},
    "revising": {"planning", "validating", "failed_safe"},
    "validating": {"proposed", "failed_safe"},
    "proposed": set(),
    "failed_safe": set(),
}

ENTITY_TABLES = {
    "account": "accounts",
    "alert": "alerts",
    "alert_comment": "alert_comments",
    "behavioral_baseline": "transaction_patterns",
    "case": "cases",
    "compliance_rule": "compliance_rules",
    "customer": "customers",
    "pep_match": "pep_list",
    "sanctions_match": "sanctions_list",
    "transaction": "transactions",
}


class LLMProvider(Protocol):
    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        response_schema: dict[str, Any],
        timeout_seconds: float,
    ) -> str:
        ...


class MCPToolClient(Protocol):
    def list_tools(self) -> list[str]:
        ...

    def call_tool(self, tool_name: str, request: MCPRequestEnvelope) -> MCPResponseEnvelope:
        ...


class Phase1PlannerAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thought: str = Field(min_length=1, max_length=2000)
    hypothesis: str = Field(min_length=1, max_length=2000)
    next_tool: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    stop: bool = False

    @model_validator(mode="after")
    def validate_action_shape(self) -> "Phase1PlannerAction":
        if self.stop:
            if self.next_tool is not None:
                raise ValueError("stop actions must not include next_tool")
            if self.tool_args:
                raise ValueError("stop actions must not include tool_args")
        elif not self.next_tool:
            raise ValueError("non-stop actions must include next_tool")
        return self


@dataclass(frozen=True)
class LiveMCPAgentConfig:
    model_id: str
    runtime_bounds: RuntimeBounds = field(default_factory=RuntimeBounds)
    timeout_seconds: float = 30.0
    prompt_version: str = PROMPT_VERSION
    tool_registry_version: str = TOOL_REGISTRY_VERSION
    policy_version: str = POLICY_VERSION


@dataclass
class _RuntimeStateMachine:
    """Small state machine and append-only event ledger for the live MCP POC."""

    run_id: str
    state: RuntimeState = "created"
    events: list[RuntimeEvent] = field(default_factory=list)

    def emit(
        self,
        state: RuntimeState,
        event_type: str,
        *,
        step_number: int | None = None,
        tool_name: str | None = None,
        tool_args: dict[str, Any] | None = None,
        status: str | None = None,
        stop_reason: str | None = None,
        hypothesis_before: str | None = None,
        hypothesis_after: str | None = None,
        audit_id: str | None = None,
        policy_decisions: list[Any] | None = None,
        data_completeness: DataCompleteness | None = None,
        error: str | None = None,
    ) -> RuntimeEvent:
        if state != self.state:
            allowed = ALLOWED_RUNTIME_TRANSITIONS[self.state]
            if state not in allowed:
                raise RuntimeError(
                    f"Invalid runtime transition {self.state!r} -> {state!r}"
                )
        event = RuntimeEvent(
            event_id=new_id("evt"),
            sequence_number=len(self.events) + 1,
            state=state,
            event_type=event_type,
            step_number=step_number,
            tool_name=tool_name,
            tool_args=tool_args or {},
            status=status,
            stop_reason=stop_reason,
            hypothesis_before=hypothesis_before,
            hypothesis_after=hypothesis_after,
            audit_id=audit_id,
            policy_decisions=policy_decisions or [],
            data_completeness=data_completeness,
            error=error,
            created_at=_utc_now(),
        )
        self.state = state
        self.events.append(event)
        return event


class InProcessMCPToolClient:
    """CI-safe client that calls ReferenceMCPTools directly."""

    def __init__(self, tools: Any) -> None:
        self.tools = tools

    def list_tools(self) -> list[str]:
        return list(PHASE1_TOOL_NAMES)

    def call_tool(self, tool_name: str, request: MCPRequestEnvelope) -> MCPResponseEnvelope:
        handler = getattr(self.tools, tool_name)
        raw = handler(request.model_dump(mode="json"))
        return MCPResponseEnvelope.model_validate(raw)


class StdioMCPToolClient:
    """MCP stdio client for the manual live demo."""

    def __init__(
        self,
        *,
        server_script: str | None = None,
        python_executable: str | None = None,
    ) -> None:
        root = Path(__file__).resolve().parents[3]
        self.server_script = server_script or str(root / "mcp_server" / "server.py")
        self.python_executable = python_executable or sys.executable

    def list_tools(self) -> list[str]:
        return list(PHASE1_TOOL_NAMES)

    def call_tool(self, tool_name: str, request: MCPRequestEnvelope) -> MCPResponseEnvelope:
        return asyncio.run(self._call_tool(tool_name, request))

    async def _call_tool(self, tool_name: str, request: MCPRequestEnvelope) -> MCPResponseEnvelope:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:
            raise RuntimeError("Install the 'mcp' package to run the live MCP demo.") from exc

        params = StdioServerParameters(
            command=self.python_executable,
            args=[self.server_script],
            env=_stdio_env(),
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    tool_name,
                    arguments={"request": request.model_dump(mode="json")},
                )
                raw = getattr(result, "structuredContent", None)
                if not raw:
                    raw = _parse_tool_text_result(result)
                if isinstance(raw, dict) and "result" in raw and isinstance(raw["result"], dict):
                    raw = raw["result"]
                return MCPResponseEnvelope.model_validate(raw)


class LiveMCPAgent:
    """Live/model planner over a governed reference MCP boundary."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        tool_client: MCPToolClient,
        config: LiveMCPAgentConfig,
    ) -> None:
        self.provider = provider
        self.tool_client = tool_client
        self.config = config

    def run(self, request: AgentRunRequest) -> AgentProposal:
        run_id = new_id("run")
        bounds = request.runtime_bounds or self.config.runtime_bounds
        allowed_tools = set(self.tool_client.list_tools())
        deadline = time.monotonic() + bounds.timeout_seconds
        state_machine = _RuntimeStateMachine(run_id)
        observations: list[AgentObservation] = []
        tool_calls: list[AgentToolCall] = []
        trace: list[AgentTraceStep] = []
        seen_calls: set[str] = set()
        hypothesis = "Initial hypothesis requires scoped MCP evidence."
        stop_reason = BUDGET_EXHAUSTED
        metered_cost_usd = 0.0

        state_machine.emit(
            "created",
            "runtime_created",
            status="started",
            tool_args={
                "allowed_tools": sorted(allowed_tools),
                "runtime_bounds": bounds.model_dump(mode="json"),
                "cost_budget": {
                    "max_cost_usd": bounds.max_cost_usd,
                    "metered_cost_usd": metered_cost_usd,
                    "enforcement": "no_provider_usage_metadata",
                },
            },
        )
        state_machine.emit(
            "context_loaded",
            "context_loaded",
            status="accepted",
            tool_args={
                "subject": request.subject.model_dump(mode="json"),
                "scope": request.scope.model_dump(mode="json"),
            },
            hypothesis_after=hypothesis,
        )

        for step_number in range(1, bounds.max_steps + 1):
            if _deadline_expired(deadline):
                stop_reason = TIMEOUT
                trace.append(
                    AgentTraceStep(
                        step_number=step_number,
                        status="failed_safe",
                        hypothesis_before=hypothesis,
                        hypothesis_after=hypothesis,
                        stop_reason=stop_reason,
                        error="Runtime timeout elapsed before planner action.",
                    )
                )
                state_machine.emit(
                    state_machine.state,
                    "runtime_timeout",
                    step_number=step_number,
                    status="failed_safe",
                    stop_reason=stop_reason,
                    hypothesis_before=hypothesis,
                    hypothesis_after=hypothesis,
                    error="Runtime timeout elapsed before planner action.",
                )
                break
            if len(tool_calls) >= bounds.max_tool_calls:
                stop_reason = BUDGET_EXHAUSTED
                trace.append(
                    AgentTraceStep(
                        step_number=step_number,
                        status="failed_safe",
                        hypothesis_before=hypothesis,
                        hypothesis_after=hypothesis,
                        stop_reason=stop_reason,
                    )
                )
                state_machine.emit(
                    state_machine.state,
                    "tool_budget_exhausted",
                    step_number=step_number,
                    status="failed_safe",
                    stop_reason=stop_reason,
                    hypothesis_before=hypothesis,
                    hypothesis_after=hypothesis,
                    error="Tool-call budget exhausted before planner action.",
                )
                break

            state_machine.emit(
                "planning",
                "planner_requested",
                step_number=step_number,
                status="started",
                hypothesis_before=hypothesis,
                hypothesis_after=hypothesis,
            )
            try:
                action = self._next_action(
                    request=request,
                    run_id=run_id,
                    step_number=step_number,
                    hypothesis=hypothesis,
                    observations=observations,
                    allowed_tools=allowed_tools,
                    timeout_seconds=_remaining_seconds(
                        deadline,
                        default=self.config.timeout_seconds,
                    ),
                )
            except TimeoutError as exc:
                stop_reason = TIMEOUT
                trace.append(
                    AgentTraceStep(
                        step_number=step_number,
                        status="failed_safe",
                        hypothesis_before=hypothesis,
                        hypothesis_after=hypothesis,
                        stop_reason=stop_reason,
                        error=str(exc) or "Planner timed out.",
                    )
                )
                state_machine.emit(
                    "planning",
                    "planner_timeout",
                    step_number=step_number,
                    status="failed_safe",
                    stop_reason=stop_reason,
                    hypothesis_before=hypothesis,
                    hypothesis_after=hypothesis,
                    error=str(exc) or "Planner timed out.",
                )
                break
            except Exception as exc:
                stop_reason = SCHEMA_ERROR
                trace.append(
                    AgentTraceStep(
                        step_number=step_number,
                        status="failed_safe",
                        hypothesis_before=hypothesis,
                        hypothesis_after=hypothesis,
                        stop_reason=stop_reason,
                        error=str(exc),
                    )
                )
                state_machine.emit(
                    "planning",
                    "planner_schema_error",
                    step_number=step_number,
                    status="failed_safe",
                    stop_reason=stop_reason,
                    hypothesis_before=hypothesis,
                    hypothesis_after=hypothesis,
                    error=str(exc),
                )
                break

            if _deadline_expired(deadline):
                stop_reason = TIMEOUT
                trace.append(
                    AgentTraceStep(
                        step_number=step_number,
                        status="failed_safe",
                        thought=action.thought,
                        hypothesis_before=hypothesis,
                        hypothesis_after=action.hypothesis,
                        stop_reason=stop_reason,
                        error="Runtime timeout elapsed after planner action.",
                    )
                )
                state_machine.emit(
                    "planning",
                    "runtime_timeout",
                    step_number=step_number,
                    status="failed_safe",
                    stop_reason=stop_reason,
                    hypothesis_before=hypothesis,
                    hypothesis_after=action.hypothesis,
                    error="Runtime timeout elapsed after planner action.",
                )
                break

            if action.stop:
                stop_reason = _terminal_stop_reason(observations)
                trace_status = (
                    "failed_safe"
                    if _is_fail_safe_stop_reason(stop_reason)
                    else "proposed"
                )
                trace.append(
                    AgentTraceStep(
                        step_number=step_number,
                        status=trace_status,
                        thought=action.thought,
                        hypothesis_before=hypothesis,
                        hypothesis_after=action.hypothesis,
                        stop_reason=stop_reason,
                    )
                )
                state_machine.emit(
                    "planning",
                    "planner_stop_selected",
                    step_number=step_number,
                    status=trace_status,
                    stop_reason=stop_reason,
                    hypothesis_before=hypothesis,
                    hypothesis_after=action.hypothesis,
                )
                hypothesis = action.hypothesis
                break

            assert action.next_tool is not None
            if action.next_tool not in allowed_tools:
                stop_reason = SCHEMA_ERROR
                trace.append(
                    AgentTraceStep(
                        step_number=step_number,
                        status="failed_safe",
                        thought=action.thought,
                        hypothesis_before=hypothesis,
                        hypothesis_after=action.hypothesis,
                        tool_name=action.next_tool,
                        tool_args=dict(action.tool_args),
                        stop_reason=stop_reason,
                        error="Planner selected a tool outside the phase 1 catalog.",
                    )
                )
                state_machine.emit(
                    "planning",
                    "tool_request_rejected",
                    step_number=step_number,
                    tool_name=action.next_tool,
                    tool_args=dict(action.tool_args),
                    status="failed_safe",
                    stop_reason=stop_reason,
                    hypothesis_before=hypothesis,
                    hypothesis_after=action.hypothesis,
                    error="Planner selected a tool outside the phase 1 catalog.",
                )
                break
            if _find_forbidden_entity_args(action.tool_args):
                stop_reason = SCHEMA_ERROR
                trace.append(
                    AgentTraceStep(
                        step_number=step_number,
                        status="failed_safe",
                        thought=action.thought,
                        hypothesis_before=hypothesis,
                        hypothesis_after=action.hypothesis,
                        tool_name=action.next_tool,
                        tool_args=dict(action.tool_args),
                        stop_reason=stop_reason,
                        error="Planner supplied forbidden scoped entity IDs.",
                    )
                )
                state_machine.emit(
                    "planning",
                    "tool_request_rejected",
                    step_number=step_number,
                    tool_name=action.next_tool,
                    tool_args=dict(action.tool_args),
                    status="failed_safe",
                    stop_reason=stop_reason,
                    hypothesis_before=hypothesis,
                    hypothesis_after=action.hypothesis,
                    error="Planner supplied forbidden scoped entity IDs.",
                )
                break

            call_hash = stable_hash({"tool": action.next_tool, "args": action.tool_args})
            if call_hash in seen_calls:
                stop_reason = NO_PROGRESS
                trace.append(
                    AgentTraceStep(
                        step_number=step_number,
                        status="failed_safe",
                        thought=action.thought,
                        hypothesis_before=hypothesis,
                        hypothesis_after=action.hypothesis,
                        tool_name=action.next_tool,
                        tool_args=dict(action.tool_args),
                        stop_reason=stop_reason,
                        error="Planner repeated an already executed tool call.",
                    )
                )
                state_machine.emit(
                    "planning",
                    "tool_request_rejected",
                    step_number=step_number,
                    tool_name=action.next_tool,
                    tool_args=dict(action.tool_args),
                    status="failed_safe",
                    stop_reason=stop_reason,
                    hypothesis_before=hypothesis,
                    hypothesis_after=action.hypothesis,
                    error="Planner repeated an already executed tool call.",
                )
                break
            seen_calls.add(call_hash)

            state_machine.emit(
                "tool_requested",
                "tool_requested",
                step_number=step_number,
                tool_name=action.next_tool,
                tool_args=dict(action.tool_args),
                status="accepted",
                hypothesis_before=hypothesis,
                hypothesis_after=action.hypothesis,
            )

            envelope = MCPRequestEnvelope(
                tenant_id=request.tenant_id,
                officer_id=request.officer_id,
                agent_run_id=run_id,
                purpose=request.purpose,
                subject=request.subject,
                scope=request.scope,
                tool_args=dict(action.tool_args),
                idempotency_key=stable_hash(
                    {
                        "run_id": run_id,
                        "step_number": step_number,
                        "tool": action.next_tool,
                        "args": action.tool_args,
                    }
                ),
                correlation_id=run_id,
            )

            if _deadline_expired(deadline):
                stop_reason = TIMEOUT
                trace.append(
                    AgentTraceStep(
                        step_number=step_number,
                        status="failed_safe",
                        thought=action.thought,
                        hypothesis_before=hypothesis,
                        hypothesis_after=action.hypothesis,
                        tool_name=action.next_tool,
                        tool_args=dict(action.tool_args),
                        stop_reason=stop_reason,
                        error="Runtime timeout elapsed before tool execution.",
                    )
                )
                state_machine.emit(
                    "tool_requested",
                    "runtime_timeout",
                    step_number=step_number,
                    tool_name=action.next_tool,
                    tool_args=dict(action.tool_args),
                    status="failed_safe",
                    stop_reason=stop_reason,
                    hypothesis_before=hypothesis,
                    hypothesis_after=action.hypothesis,
                    error="Runtime timeout elapsed before tool execution.",
                )
                break

            try:
                response = self.tool_client.call_tool(action.next_tool, envelope)
            except TimeoutError as exc:
                stop_reason = TIMEOUT
                trace.append(
                    AgentTraceStep(
                        step_number=step_number,
                        status="failed_safe",
                        thought=action.thought,
                        hypothesis_before=hypothesis,
                        hypothesis_after=action.hypothesis,
                        tool_name=action.next_tool,
                        tool_args=dict(action.tool_args),
                        stop_reason=stop_reason,
                        error=str(exc) or "Tool call timed out.",
                    )
                )
                state_machine.emit(
                    "tool_requested",
                    "tool_timeout",
                    step_number=step_number,
                    tool_name=action.next_tool,
                    tool_args=dict(action.tool_args),
                    status="failed_safe",
                    stop_reason=stop_reason,
                    hypothesis_before=hypothesis,
                    hypothesis_after=action.hypothesis,
                    error=str(exc) or "Tool call timed out.",
                )
                break
            except Exception as exc:
                stop_reason = TOOL_ERROR
                trace.append(
                    AgentTraceStep(
                        step_number=step_number,
                        status="failed_safe",
                        thought=action.thought,
                        hypothesis_before=hypothesis,
                        hypothesis_after=action.hypothesis,
                        tool_name=action.next_tool,
                        tool_args=dict(action.tool_args),
                        stop_reason=stop_reason,
                        error=str(exc),
                    )
                )
                state_machine.emit(
                    "tool_requested",
                    "tool_error",
                    step_number=step_number,
                    tool_name=action.next_tool,
                    tool_args=dict(action.tool_args),
                    status="failed_safe",
                    stop_reason=stop_reason,
                    hypothesis_before=hypothesis,
                    hypothesis_after=action.hypothesis,
                    error=str(exc),
                )
                break

            timed_out_after_tool = _deadline_expired(deadline)

            tool_calls.append(
                AgentToolCall(
                    step_number=step_number,
                    tool_name=action.next_tool,
                    tool_args=dict(action.tool_args),
                    status=response.status,
                    audit_id=response.audit_id,
                )
            )
            observations.append(
                AgentObservation(
                    step_number=step_number,
                    tool_name=action.next_tool,
                    facts=response.facts,
                    source_refs=response.source_refs,
                    data_completeness=response.data_completeness,
                    limitations=response.limitations,
                )
            )
            state_machine.emit(
                "tool_executed",
                "tool_response_received",
                step_number=step_number,
                tool_name=action.next_tool,
                tool_args=dict(action.tool_args),
                status=response.status,
                audit_id=response.audit_id,
                policy_decisions=response.policy_decisions,
                data_completeness=response.data_completeness,
                hypothesis_before=hypothesis,
                hypothesis_after=action.hypothesis,
            )
            state_machine.emit(
                "observing",
                "observation_recorded",
                step_number=step_number,
                tool_name=action.next_tool,
                tool_args=dict(action.tool_args),
                status=response.status,
                audit_id=response.audit_id,
                policy_decisions=response.policy_decisions,
                data_completeness=response.data_completeness,
                hypothesis_before=hypothesis,
                hypothesis_after=action.hypothesis,
            )
            trace.append(
                AgentTraceStep(
                    step_number=step_number,
                    status="tool_executed",
                    thought=action.thought,
                    hypothesis_before=hypothesis,
                    hypothesis_after=action.hypothesis,
                    tool_name=action.next_tool,
                    tool_args=dict(action.tool_args),
                    stop_reason=response.status if response.status != "ok" else None,
                )
            )
            previous_hypothesis = hypothesis
            hypothesis = action.hypothesis
            state_machine.emit(
                "revising",
                "hypothesis_revised",
                step_number=step_number,
                tool_name=action.next_tool,
                tool_args=dict(action.tool_args),
                status=response.status,
                audit_id=response.audit_id,
                hypothesis_before=previous_hypothesis,
                hypothesis_after=hypothesis,
            )

            if response.status == "denied":
                stop_reason = TOOL_DENIED
                trace[-1].stop_reason = stop_reason
                break
            if response.status == "error":
                stop_reason = TOOL_ERROR
                trace[-1].stop_reason = stop_reason
                break
            if timed_out_after_tool:
                stop_reason = TIMEOUT
                trace[-1].stop_reason = stop_reason
                trace[-1].error = "Runtime timeout elapsed after tool execution."
                break
            if _critical_signal(observations):
                stop_reason = CRITICAL_SIGNAL_FOUND
                trace[-1].stop_reason = stop_reason
                break
        else:
            stop_reason = BUDGET_EXHAUSTED
            trace.append(
                AgentTraceStep(
                    step_number=bounds.max_steps,
                    status="failed_safe",
                    hypothesis_before=hypothesis,
                    hypothesis_after=hypothesis,
                    stop_reason=stop_reason,
                    error="Step budget exhausted before terminal planner action.",
                )
            )
            state_machine.emit(
                state_machine.state,
                "step_budget_exhausted",
                step_number=bounds.max_steps,
                status="failed_safe",
                stop_reason=stop_reason,
                hypothesis_before=hypothesis,
                hypothesis_after=hypothesis,
                error="Step budget exhausted before terminal planner action.",
            )

        terminal_state = _terminal_state_for_stop_reason(stop_reason)
        state_machine.emit(
            "validating",
            "proposal_validation_started",
            status="started",
            stop_reason=stop_reason,
            hypothesis_before=hypothesis,
            hypothesis_after=hypothesis,
        )
        state_machine.emit(
            terminal_state,
            "proposal_terminal",
            status=terminal_state,
            stop_reason=stop_reason,
            hypothesis_before=hypothesis,
            hypothesis_after=hypothesis,
        )

        return self._build_proposal(
            run_id=run_id,
            request=request,
            observations=observations,
            tool_calls=tool_calls,
            trace=trace,
            stop_reason=stop_reason,
            terminal_state=terminal_state,
            runtime_events=list(state_machine.events),
        )

    def run_and_persist(
        self,
        request: AgentRunRequest,
        sidecar: SidecarStore,
    ) -> dict[str, Any]:
        proposal = self.run(request)
        result = proposal_to_agent_result(proposal)
        validation = ComplianceValidationAgent().validate(result)
        if validation.status != "passed":
            result.details["validation_blocked"] = True
        sidecar.save_result(proposal.run_id, request.model_dump(mode="json"), result, validation)
        return {
            "run_id": proposal.run_id,
            "proposal": proposal.model_dump(mode="json"),
            "result": to_plain(result),
            "validation": to_plain(validation),
        }

    def _next_action(
        self,
        *,
        request: AgentRunRequest,
        run_id: str,
        step_number: int,
        hypothesis: str,
        observations: list[AgentObservation],
        allowed_tools: set[str],
        timeout_seconds: float,
    ) -> Phase1PlannerAction:
        raw = self.provider.complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a bounded AML investigation planner. Return one strict JSON object only. "
                        "You may choose only a listed MCP tool, provide bounded tool_args, update the current "
                        "hypothesis, or stop. Do not include alert_id, customer_id, account_id, transaction_id, "
                        "or case_id in tool_args. Do not request SQL. Do not decide SAR filing, final dismissal, "
                        "officer permissions, or final numeric risk scores. For risk scoring, gather and explain "
                        "evidence only; deterministic policy computes the score. For SAR drafting, gather case "
                        "facts for a draft narrative only."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "prompt_version": self.config.prompt_version,
                            "required_json_schema": Phase1PlannerAction.model_json_schema(),
                            "run_id": run_id,
                            "step_number": step_number,
                            "purpose": request.purpose,
                            "subject": request.subject.model_dump(mode="json"),
                            "current_hypothesis": hypothesis,
                            "allowed_tools": sorted(allowed_tools),
                            "tool_catalog": [
                                item.model_dump(mode="json")
                                for item in PHASE1_TOOL_CATALOG
                                if item.name in allowed_tools
                            ],
                            "observations": [
                                _observation_summary(item) for item in observations
                            ],
                        },
                        sort_keys=True,
                        default=str,
                    ),
                },
            ],
            model=self.config.model_id,
            response_schema=Phase1PlannerAction.model_json_schema(),
            timeout_seconds=timeout_seconds,
        )
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("Planner output was not JSON.") from exc
        try:
            return Phase1PlannerAction.model_validate(decoded)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

    def _build_proposal(
        self,
        *,
        run_id: str,
        request: AgentRunRequest,
        observations: list[AgentObservation],
        tool_calls: list[AgentToolCall],
        trace: list[AgentTraceStep],
        stop_reason: str,
        terminal_state: RuntimeState,
        runtime_events: list[RuntimeEvent],
    ) -> AgentProposal:
        evidence_refs = _dedupe_source_refs(
            [ref for observation in observations for ref in observation.source_refs]
        )
        recommendation = _recommendation(observations, stop_reason)
        claims = _claims(request, observations)
        validation = _validate_claims(claims, evidence_refs)
        completeness = _combined_completeness(observations)
        limitations = [
            limitation
            for observation in observations
            for limitation in observation.limitations
        ]
        if stop_reason != COMPLETED:
            limitations.append(f"Runtime stopped because {stop_reason}.")

        return AgentProposal(
            run_id=run_id,
            tenant_id=request.tenant_id,
            subject=request.subject,
            recommendation=recommendation,
            confidence=_confidence(recommendation, validation.status, stop_reason),
            score=_score(recommendation),
            structured_reasoning=_reasoning(recommendation, observations, stop_reason),
            factual_claims=claims,
            evidence_refs=evidence_refs,
            limitations=limitations,
            data_completeness=completeness,
            required_human_action=_human_action(recommendation),
            model_version=self.config.model_id,
            prompt_version=self.config.prompt_version,
            tool_registry_version=self.config.tool_registry_version,
            policy_version=self.config.policy_version,
            runtime_bounds=request.runtime_bounds,
            validation_status=validation,
            terminal_state=terminal_state,
            stop_reason=stop_reason,
            runtime_events=runtime_events,
            trace=trace,
            tool_calls=tool_calls,
            observations=observations,
        )


def build_live_provider_from_env() -> OpenAICompatibleChatProvider:
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("LLM_API_KEY or OPENAI_API_KEY is required for the live MCP demo.")
    return OpenAICompatibleChatProvider(
        api_key=api_key,
        endpoint=os.getenv("LLM_ENDPOINT", "https://api.openai.com/v1/chat/completions"),
    )


def proposal_to_agent_result(proposal: AgentProposal) -> AgentResult:
    evidence = [
        EvidenceItem(
            evidence_id=f"{_table_for_entity(ref.entity_type)}:{ref.entity_id}",
            source_ref=SourceRef(
                _table_for_entity(ref.entity_type),
                ref.entity_id,
                tuple(ref.field_names),
            ),
            payload=ref.model_dump(mode="json"),
            retrieved_at=ref.retrieved_at,
        )
        for ref in proposal.evidence_refs
    ]
    fallback_ref = evidence[0].source_ref if evidence else SourceRef("alerts", str(proposal.subject.alert_id or "unknown"))
    claims = [
        Claim(
            statement=claim.statement,
            source_refs=[
                SourceRef(_table_for_entity(ref.entity_type), ref.entity_id, tuple(ref.field_names))
                for ref in claim.evidence_refs
            ],
        )
        for claim in proposal.factual_claims
    ]
    reasoning = [
        ReasoningItem(statement=statement, source_refs=[fallback_ref])
        for statement in proposal.structured_reasoning
    ]
    return AgentResult(
        agent_name="triage_agent",
        subject_type="alert",
        subject_id=proposal.subject.alert_id or proposal.subject.customer_id or "unknown",
        recommendation=proposal.recommendation,
        confidence=proposal.confidence,
        score=proposal.score,
        reasoning=reasoning,
        claims=claims,
        evidence=evidence,
        details={
            "recommendation_id": new_id("rec"),
            "customer_id": proposal.subject.customer_id,
            "human_required": True,
            "required_human_action": proposal.required_human_action,
            "runtime_version": {
                "planner_type": "live_mcp_llm",
                "model_id": proposal.model_version,
                "prompt_version": proposal.prompt_version,
                "tool_registry_version": proposal.tool_registry_version,
                "runtime_bounds": proposal.runtime_bounds.model_dump(mode="json"),
            },
            "react_runtime": _sidecar_react_runtime(proposal),
            "phase1_proposal": proposal.model_dump(mode="json"),
        },
    )


def _sidecar_react_runtime(proposal: AgentProposal) -> dict[str, Any]:
    tool_observations = {}
    for observation in proposal.observations:
        tool_observations[observation.tool_name] = {
            "facts": observation.facts,
            "computed_features": observation.facts.get("computed_features", {}),
            "source_refs": [
                {
                    "table": _table_for_entity(ref.entity_type),
                    "key": ref.entity_id,
                    "columns": list(ref.field_names),
                }
                for ref in observation.source_refs
            ],
            "data_completeness": observation.data_completeness.model_dump(mode="json"),
            "limitations": [
                {"code": "phase1_mcp_limitation", "message": item, "severity": "info"}
                for item in observation.limitations
            ],
        }
    return {
        "planner": "live_mcp_llm",
        "planner_metadata": {
            "model_id": proposal.model_version,
            "prompt_version": proposal.prompt_version,
        },
        "stop_reason": _proposal_stop_reason(proposal),
        "max_steps": proposal.runtime_bounds.max_steps,
        "max_tool_calls": proposal.runtime_bounds.max_tool_calls,
        "tool_call_count": len(proposal.tool_calls),
        "events": [event.model_dump(mode="json") for event in proposal.runtime_events],
        "steps": [
            {
                "step_number": step.step_number,
                "status": "observed" if step.status == "tool_executed" else step.status,
                "thought": step.thought,
                "hypothesis": step.hypothesis_after or step.hypothesis_before,
                "tool_name": step.tool_name,
                "tool_args": step.tool_args,
                "stop_reason": step.stop_reason,
                "error": step.error,
                "observation": tool_observations.get(step.tool_name or ""),
            }
            for step in proposal.trace
        ],
        "tool_observations": tool_observations,
    }


def _proposal_stop_reason(proposal: AgentProposal) -> str:
    if proposal.stop_reason:
        return proposal.stop_reason
    for step in reversed(proposal.trace):
        if step.stop_reason:
            return step.stop_reason
    return COMPLETED


def _recommendation(observations: list[AgentObservation], stop_reason: str) -> str:
    if stop_reason == CRITICAL_SIGNAL_FOUND:
        return "escalate"
    if stop_reason in FAIL_SAFE_STOP_REASONS:
        return "needs_investigation"
    if _critical_signal(observations):
        return "escalate"
    baseline = _baseline_assessment(observations)
    if baseline == "consistent" and not _graph_red_flag(observations):
        return "likely_false_positive"
    return "needs_investigation"


def _critical_signal(observations: list[AgentObservation]) -> bool:
    for observation in observations:
        facts = observation.facts
        if observation.tool_name == "get_compliance_rule":
            rule = facts.get("compliance_rule") or {}
            if str(rule.get("rule_type") or "").lower() == "geography":
                return True
        if observation.tool_name == "screen_sanctions_pep":
            if facts.get("sanctions_matches") or facts.get("pep_matches"):
                return True
        if observation.tool_name == "get_transaction_history":
            for tx in facts.get("transactions") or []:
                fatf = str(tx.get("destination_fatf_status") or "").lower()
                if bool(tx.get("destination_is_sanctioned")) or fatf == "blacklist":
                    return True
        if observation.tool_name == "trace_counterparty_graph":
            signals = _graph_signals_from_observation(observation)
            if signals.get("high_risk_endpoint") or int(signals.get("linked_open_case_count") or 0) > 0:
                return True
    return False


def _graph_red_flag(observations: list[AgentObservation]) -> bool:
    for observation in observations:
        if observation.tool_name != "trace_counterparty_graph":
            continue
        signals = _graph_signals_from_observation(observation)
        for key in ("rapid_pass_through", "cycle_detected", "fan_out", "many_to_one", "high_risk_endpoint"):
            if signals.get(key):
                return True
        if int(signals.get("linked_alert_count") or 0) > 0:
            return True
    return False


def _graph_signals_from_observation(observation: AgentObservation) -> dict[str, Any]:
    computed = observation.facts.get("computed_features") or {}
    return computed.get("signals") or {}


def _baseline_assessment(observations: list[AgentObservation]) -> str | None:
    for observation in observations:
        if observation.tool_name != "get_behavioral_baseline":
            continue
        computed = observation.facts.get("computed_features") or {}
        return computed.get("baseline_assessment")
    return None


def _terminal_stop_reason(observations: list[AgentObservation]) -> str:
    if _critical_signal(observations):
        return CRITICAL_SIGNAL_FOUND
    if not observations:
        return INSUFFICIENT_EVIDENCE
    if not _combined_completeness(observations).complete:
        return INSUFFICIENT_EVIDENCE
    return COMPLETED


def _terminal_state_for_stop_reason(stop_reason: str) -> RuntimeState:
    if _is_fail_safe_stop_reason(stop_reason):
        return "failed_safe"
    return "proposed"


def _is_fail_safe_stop_reason(stop_reason: str) -> bool:
    return stop_reason in FAIL_SAFE_STOP_REASONS


def _claims(request: AgentRunRequest, observations: list[AgentObservation]) -> list[FactualClaim]:
    claims: list[FactualClaim] = []
    for observation in observations:
        if observation.tool_name == "get_compliance_rule":
            rule = observation.facts.get("compliance_rule") or {}
            if rule and request.subject.alert_id is not None:
                refs = _refs_for_entities(observation, {"alert", "compliance_rule"})
                claims.append(
                    FactualClaim(
                        statement=(
                            f"Alert {request.subject.alert_id} was generated by "
                            f"{rule.get('rule_name', 'a compliance rule')}."
                        ),
                        evidence_refs=refs,
                    )
                )
        if observation.tool_name == "get_behavioral_baseline":
            assessment = (observation.facts.get("computed_features") or {}).get("baseline_assessment")
            if assessment:
                claims.append(
                    FactualClaim(
                        statement=f"Behavioral baseline assessment is {assessment}.",
                        evidence_refs=observation.source_refs[:5],
                    )
                )
        if observation.tool_name == "trace_counterparty_graph":
            signals = _graph_signals_from_observation(observation)
            if signals:
                claims.append(
                    FactualClaim(
                        statement=(
                            "Counterparty graph signals include "
                            f"{json.dumps(signals, sort_keys=True)}."
                        ),
                        evidence_refs=observation.source_refs[:8],
                    )
                )
        if observation.tool_name == "screen_sanctions_pep":
            sanctions = len(observation.facts.get("sanctions_matches") or [])
            peps = len(observation.facts.get("pep_matches") or [])
            claims.append(
                FactualClaim(
                    statement=f"Screening returned {sanctions} sanctions matches and {peps} PEP matches.",
                    evidence_refs=observation.source_refs[:5],
                )
            )
    return [claim for claim in claims if claim.evidence_refs]


def _refs_for_entities(observation: AgentObservation, entity_types: set[str]) -> list[MCPSourceRef]:
    return [ref for ref in observation.source_refs if ref.entity_type in entity_types]


def _validate_claims(
    claims: list[FactualClaim],
    evidence_refs: list[MCPSourceRef],
) -> ValidationStatus:
    available = {
        (ref.source_system, ref.entity_type, ref.entity_id)
        for ref in evidence_refs
    }
    findings = []
    for claim in claims:
        if not claim.evidence_refs:
            findings.append(f"Claim has no evidence refs: {claim.statement}")
            continue
        for ref in claim.evidence_refs:
            key = (ref.source_system, ref.entity_type, ref.entity_id)
            if key not in available:
                findings.append(f"Missing evidence ref {key} for claim: {claim.statement}")
    return ValidationStatus(
        status="passed" if not findings else "failed",
        unsupported_claim_count=len(findings),
        findings=findings,
    )


def _combined_completeness(observations: list[AgentObservation]) -> DataCompleteness:
    missing = []
    complete = True
    rows_returned = 0
    rows_requested = 0
    for observation in observations:
        completeness = observation.data_completeness
        complete = complete and completeness.complete
        missing.extend(completeness.missing_segments)
        rows_returned += completeness.rows_returned or 0
        rows_requested += completeness.rows_requested or 0
    return DataCompleteness(
        complete=complete,
        rows_returned=rows_returned,
        rows_requested=rows_requested,
        missing_segments=sorted(set(missing)),
    )


def _confidence(recommendation: str, validation_status: str, stop_reason: str) -> float:
    if validation_status != "passed":
        return 0.35
    if stop_reason in FAIL_SAFE_STOP_REASONS:
        return 0.45
    if recommendation == "escalate":
        return 0.86
    if recommendation == "likely_false_positive":
        return 0.78
    return 0.62


def _score(recommendation: str) -> float:
    return {
        "escalate": 90.0,
        "likely_false_positive": 25.0,
        "needs_investigation": 55.0,
    }[recommendation]


def _human_action(recommendation: str) -> str:
    return {
        "escalate": "review_escalation_proposal",
        "likely_false_positive": "review_false_positive_proposal",
        "needs_investigation": "continue_human_investigation",
    }[recommendation]


def _reasoning(
    recommendation: str,
    observations: list[AgentObservation],
    stop_reason: str,
) -> list[str]:
    observed_tools = ", ".join(observation.tool_name for observation in observations) or "none"
    return [
        f"Phase 1 live MCP runtime observed tools: {observed_tools}.",
        f"Runtime stop reason: {stop_reason}.",
        f"Recommendation is {recommendation} and requires human review.",
    ]


def _dedupe_source_refs(refs: list[MCPSourceRef]) -> list[MCPSourceRef]:
    deduped: list[MCPSourceRef] = []
    seen = set()
    for ref in refs:
        key = (ref.source_system, ref.entity_type, ref.entity_id)
        if key in seen:
            continue
        deduped.append(ref)
        seen.add(key)
    return deduped


def _observation_summary(observation: AgentObservation) -> dict[str, Any]:
    return {
        "step_number": observation.step_number,
        "tool_name": observation.tool_name,
        "fact_keys": sorted(observation.facts),
        "source_refs": [ref.model_dump(mode="json") for ref in observation.source_refs[:12]],
        "data_completeness": observation.data_completeness.model_dump(mode="json"),
        "limitations": observation.limitations,
    }


def _find_forbidden_entity_args(value: Any, path: str = "$") -> list[str]:
    forbidden = {"alert_id", "customer_id", "account_id", "transaction_id", "case_id"}
    found: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            child_path = f"{path}.{key}"
            if key in forbidden:
                found.append(child_path)
            found.extend(_find_forbidden_entity_args(nested, child_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_find_forbidden_entity_args(item, f"{path}[{index}]"))
    return found


def _remaining_seconds(deadline: float, *, default: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return 0.001
    return max(0.001, min(default, remaining))


def _deadline_expired(deadline: float) -> bool:
    return time.monotonic() >= deadline


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_for_entity(entity_type: str) -> str:
    return ENTITY_TABLES.get(entity_type, entity_type)


def _stdio_env() -> dict[str, str]:
    root = Path(__file__).resolve().parents[3]
    src = root / "src"
    deps = root / ".codex_deps"
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    parts = [str(src), str(root)]
    if deps.exists():
        parts.append(str(deps))
    if existing:
        parts.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def _parse_tool_text_result(result: Any) -> dict[str, Any]:
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            return json.loads(text)
    raise ValueError("MCP tool result did not contain structured content or JSON text.")
