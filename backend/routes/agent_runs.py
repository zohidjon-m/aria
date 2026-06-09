from __future__ import annotations

import logging
import os
import sys
from typing import Any, Literal

import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from compliance_agent.api import build_orchestrator
from compliance_agent.adapters.sidecar_store import SidecarStore
from compliance_agent.adapters.source import SourceRecordNotFound
from compliance_agent.agents.live_mcp_demo import (
    InProcessMCPToolClient,
    LiveMCPAgent,
    LiveMCPAgentConfig,
)
from compliance_agent.agents.live_mcp_workflows import LiveMCPWorkflowAgent, WorkflowName
from compliance_agent.agents.llm_planner import OpenAICompatibleChatProvider
from compliance_agent.config import Settings
from compliance_agent.contracts.phase1 import (
    AgentRunRequest,
    RuntimeBounds,
    SubjectRef,
    ToolExecutionScope,
)
from mcp_server.repository import PostgresReferenceRepository
from mcp_server.service import ReferenceMCPTools

from ..audit import insert_audit
from ..db import ro_cursor, rw_conn
from ..rbac import require_view

logger = logging.getLogger(__name__)
router = APIRouter()


class TriageRunBody(BaseModel):
    alert_id: int


class LiveMcpTriageRunBody(BaseModel):
    alert_id: int
    max_steps: int | None = Field(default=None, ge=1, le=20)
    max_tool_calls: int | None = Field(default=None, ge=1, le=20)
    max_rows: int | None = Field(default=None, ge=1, le=500)
    max_graph_hops: int | None = Field(default=None, ge=1, le=8)
    timeout_seconds: float | None = Field(default=None, ge=1.0, le=600.0)
    max_cost_usd: float | None = Field(default=None, ge=0.0, le=100.0)


class LiveMcpWorkflowRunBody(BaseModel):
    workflow: WorkflowName
    alert_id: int | None = None
    customer_id: int | None = None
    case_id: int | None = None
    officer_context: str = Field(default="", max_length=4000)
    max_steps: int | None = Field(default=None, ge=1, le=20)
    max_tool_calls: int | None = Field(default=None, ge=1, le=20)
    max_rows: int | None = Field(default=None, ge=1, le=500)
    max_graph_hops: int | None = Field(default=None, ge=1, le=8)
    timeout_seconds: float | None = Field(default=None, ge=1.0, le=600.0)
    max_cost_usd: float | None = Field(default=None, ge=0.0, le=100.0)


class HumanDecisionBody(BaseModel):
    decision: str = Field(min_length=1, max_length=80)
    rationale: str | None = Field(default=None, max_length=4000)


class BankExportBody(BaseModel):
    decision_id: str | None = None
    export_type: Literal["human_decision", "sar_draft_review", "risk_score_review"] = "human_decision"
    destination: str = Field(default="bank_system_of_record", min_length=1, max_length=120)


def _runtime_bounds_from_body(
    settings: Settings,
    body: LiveMcpWorkflowRunBody | LiveMcpTriageRunBody,
) -> RuntimeBounds:
    defaults = settings.default_runtime_bounds() if hasattr(settings, "default_runtime_bounds") else RuntimeBounds()
    values = defaults.model_dump(mode="json")
    for key in (
        "max_steps",
        "max_tool_calls",
        "max_rows",
        "max_graph_hops",
        "timeout_seconds",
        "max_cost_usd",
    ):
        override = getattr(body, key, None)
        if override is not None:
            values[key] = override
    return RuntimeBounds(**values)


def _require_live_llm_config(settings: Settings) -> tuple[str, str]:
    api_key = settings.llm_api_key or os.getenv("OPENAI_API_KEY")
    model_id = settings.llm_model or os.getenv("OPENAI_MODEL")
    if not api_key:
        raise HTTPException(status_code=503, detail="LLM_API_KEY is required for live MCP workflows")
    if not model_id:
        raise HTTPException(status_code=503, detail="LLM_MODEL is required for live MCP workflows")
    return api_key, model_id


def _build_live_workflow_agent(
    *,
    settings: Settings,
    repository: PostgresReferenceRepository,
    bounds: RuntimeBounds,
    api_key: str,
    model_id: str,
) -> LiveMCPWorkflowAgent:
    live_agent = LiveMCPAgent(
        provider=OpenAICompatibleChatProvider(
            api_key=api_key,
            endpoint=settings.llm_endpoint,
        ),
        tool_client=InProcessMCPToolClient(ReferenceMCPTools(repository)),
        config=LiveMCPAgentConfig(
            model_id=model_id,
            runtime_bounds=bounds,
            timeout_seconds=settings.llm_timeout_seconds,
            prompt_version=getattr(settings, "llm_prompt_version", "phase1_live_mcp_agent_v1"),
            tool_registry_version=getattr(settings, "mcp_tool_registry_version", "phase1_reference_mcp_v1"),
            policy_version=getattr(settings, "agent_policy_version", "phase1_reference_mcp_policy_v1"),
        ),
    )
    return LiveMCPWorkflowAgent(live_agent)


def _workflow_request(
    *,
    body: LiveMcpWorkflowRunBody,
    officer: dict,
    settings: Settings,
    repository: PostgresReferenceRepository,
    bounds: RuntimeBounds,
) -> AgentRunRequest:
    if body.workflow in {"triage", "investigation"}:
        if body.alert_id is None:
            raise HTTPException(status_code=422, detail="alert_id is required for alert workflows")
        scope = repository.get_alert_scope(body.alert_id)
        if not scope:
            raise HTTPException(status_code=404, detail=f"Alert {body.alert_id} not found")
        subject = SubjectRef(
            alert_id=int(scope["alert_id"]),
            customer_id=int(scope["customer_id"]),
        )
        execution_scope = ToolExecutionScope(
            allowed_customer_ids=[int(scope["customer_id"])],
            allowed_account_ids=[int(scope["account_id"])],
            allowed_transaction_ids=[int(scope["transaction_id"])],
            allowed_case_ids=[],
        )
    elif body.workflow == "risk_scoring":
        if body.customer_id is None:
            raise HTTPException(status_code=422, detail="customer_id is required for risk_scoring")
        scope = repository.get_customer_scope(body.customer_id)
        if not scope:
            raise HTTPException(status_code=404, detail=f"Customer {body.customer_id} not found")
        subject = SubjectRef(customer_id=int(scope["customer_id"]))
        execution_scope = ToolExecutionScope(
            allowed_customer_ids=[int(scope["customer_id"])],
            allowed_account_ids=[int(value) for value in scope.get("account_ids", [])],
            allowed_transaction_ids=[int(value) for value in scope.get("transaction_ids", [])],
            allowed_case_ids=[int(value) for value in scope.get("case_ids", [])],
        )
    elif body.workflow == "sar_drafting":
        if body.case_id is None:
            raise HTTPException(status_code=422, detail="case_id is required for sar_drafting")
        scope = repository.get_case_scope(body.case_id)
        if not scope:
            raise HTTPException(status_code=404, detail=f"Case {body.case_id} not found")
        subject = SubjectRef(
            case_id=int(scope["case_id"]),
            customer_id=int(scope["customer_id"]),
            alert_id=scope.get("primary_alert_id"),
        )
        execution_scope = ToolExecutionScope(
            allowed_customer_ids=[int(scope["customer_id"])],
            allowed_account_ids=[int(value) for value in scope.get("account_ids", [])],
            allowed_transaction_ids=[int(value) for value in scope.get("transaction_ids", [])],
            allowed_case_ids=[int(value) for value in scope.get("case_ids", [])],
        )
    else:
        raise HTTPException(status_code=422, detail=f"Unsupported workflow: {body.workflow}")

    return AgentRunRequest(
        tenant_id=getattr(settings, "tenant_id", os.getenv("TENANT_ID", "demo-bank")),
        officer_id=str(officer["officer_id"]),
        purpose=body.workflow,
        subject=subject,
        scope=execution_scope,
        runtime_bounds=bounds,
    )


def _run_live_workflow(
    *,
    body: LiveMcpWorkflowRunBody,
    officer: dict,
    settings: Settings,
) -> dict:
    api_key, model_id = _require_live_llm_config(settings)
    try:
        repository = PostgresReferenceRepository(settings.bank_source_dsn)
        bounds = _runtime_bounds_from_body(settings, body)
        request = _workflow_request(
            body=body,
            officer=officer,
            settings=settings,
            repository=repository,
            bounds=bounds,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Live MCP scope lookup failed for workflow %s", body.workflow)
        raise HTTPException(status_code=503, detail=f"Live MCP scope lookup failed: {type(exc).__name__}: {exc}") from exc

    agent = _build_live_workflow_agent(
        settings=settings,
        repository=repository,
        bounds=bounds,
        api_key=api_key,
        model_id=model_id,
    )
    try:
        return agent.run_and_persist(
            body.workflow,
            request,
            SidecarStore(settings.sidecar_db_path),
            officer_context=body.officer_context,
        )
    except Exception as exc:
        logger.exception("Live MCP workflow %s failed", body.workflow)
        raise HTTPException(status_code=503, detail=f"Live MCP workflow failed: {type(exc).__name__}: {exc}") from exc


def _entity_for_workflow(body: LiveMcpWorkflowRunBody) -> tuple[str, int | str, int | None, int | None]:
    if body.workflow in {"triage", "investigation"} and body.alert_id is not None:
        return "alert", body.alert_id, body.alert_id, None
    if body.workflow == "risk_scoring" and body.customer_id is not None:
        return "customer", body.customer_id, None, None
    if body.workflow == "sar_drafting" and body.case_id is not None:
        return "case", body.case_id, None, body.case_id
    return "agent_run", body.workflow, None, None


def _audit_agent_action(
    *,
    officer: dict,
    action: str,
    body: LiveMcpWorkflowRunBody,
    run_id: str | None,
) -> None:
    try:
        entity_type, entity_id, alert_id, case_id = _entity_for_workflow(body)
        with rw_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                insert_audit(
                    cur,
                    officer_id=officer["officer_id"],
                    action=action,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    alert_id=alert_id,
                    case_id=case_id,
                    details={"run_id": run_id, "workflow": body.workflow},
                )
    except Exception:
        logger.exception("Audit log insert failed for %s workflow %s", action, body.workflow)


def _stored_output(record: dict[str, Any]) -> dict[str, Any]:
    output = record.get("output")
    return output if isinstance(output, dict) else {}


def _is_sar_run(record: dict[str, Any]) -> bool:
    run = record.get("run") or {}
    output = _stored_output(record)
    details = output.get("details") if isinstance(output.get("details"), dict) else {}
    return (
        run.get("agent_name") == "sar_drafting_agent"
        or output.get("agent_name") == "sar_drafting_agent"
        or output.get("subject_type") == "case"
        or bool(details.get("sar_confidential"))
    )


def _assert_human_action_permission(officer: dict, record: dict[str, Any]) -> None:
    if _is_sar_run(record):
        if not officer.get("can_file_sar"):
            raise HTTPException(status_code=403, detail="Requires can_file_sar permission")
        return
    if not officer.get("can_manage_cases"):
        raise HTTPException(status_code=403, detail="Requires can_manage_cases permission")


def _parse_json_field(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        import json

        return json.loads(value)
    except Exception:
        return value


def _collect_audit_ids(value: Any) -> list[str]:
    ids: list[str] = []
    if isinstance(value, dict):
        audit_id = value.get("audit_id")
        if audit_id:
            ids.append(str(audit_id))
        for item in value.values():
            ids.extend(_collect_audit_ids(item))
    elif isinstance(value, list):
        for item in value:
            ids.extend(_collect_audit_ids(item))
    deduped = []
    seen = set()
    for audit_id in ids:
        if audit_id in seen:
            continue
        seen.add(audit_id)
        deduped.append(audit_id)
    return deduped


def _source_ref_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "source": value.get("table") or value.get("source_table") or value.get("entity_type"),
        "record_key": value.get("key") or value.get("source_key") or value.get("entity_id"),
        "fields": value.get("columns") or value.get("field_names") or [],
    }


def _payload_preview(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, dict):
        parts = []
        for key, value in list(payload.items())[:4]:
            if isinstance(value, (dict, list)):
                rendered = f"{len(value)} item(s)" if isinstance(value, list) else "object"
            else:
                rendered = str(value)
            parts.append(f"{key}: {rendered}")
        return "; ".join(parts)
    if isinstance(payload, list):
        return f"{len(payload)} item(s)"
    return str(payload)


def _normalize_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_items = []
    for item in items:
        normalized = dict(item)
        if "payload_json" in normalized:
            normalized["payload"] = _parse_json_field(normalized.pop("payload_json"))
        source_ref = normalized.get("source_ref")
        source = (
            normalized.get("source_table")
            or normalized.get("source")
            or _source_ref_dict(source_ref).get("source")
        )
        record_key = (
            normalized.get("source_key")
            or normalized.get("record_key")
            or _source_ref_dict(source_ref).get("record_key")
        )
        fields = (
            normalized.get("fields")
            or normalized.get("columns")
            or _source_ref_dict(source_ref).get("fields")
            or []
        )
        normalized["source"] = source
        normalized["record_key"] = str(record_key) if record_key is not None else None
        normalized["fields"] = fields
        normalized["payload_preview"] = _payload_preview(normalized.get("payload"))
        normalized_items.append(normalized)
    return normalized_items


def _validation_findings(validation: Any) -> list[dict[str, Any]]:
    if not isinstance(validation, dict):
        return []
    report = validation.get("report")
    if report is None and validation.get("report_json"):
        report = _parse_json_field(validation["report_json"])
    if isinstance(report, dict):
        findings = report.get("findings") or []
        return findings if isinstance(findings, list) else []
    return []


def _timeline_label(item: dict[str, Any], fallback: str) -> str:
    event_type = str(item.get("event_type") or item.get("status") or fallback)
    return event_type.replace("_", " ")


def _workflow_timeline(trace: dict[str, Any]) -> list[dict[str, Any]]:
    timeline = []
    for index, event in enumerate(trace.get("runtime_events") or [], start=1):
        if not isinstance(event, dict):
            continue
        timeline.append(
            {
                "order": float(event.get("sequence_number") or index),
                "phase": event.get("state") or "runtime",
                "label": _timeline_label(event, "runtime_event"),
                "description": event.get("hypothesis_after") or event.get("hypothesis_before"),
                "tool_name": event.get("tool_name"),
                "status": event.get("status"),
                "audit_id": event.get("audit_id"),
                "policy_decisions": event.get("policy_decisions") or [],
                "data_completeness": event.get("data_completeness"),
                "error": event.get("error"),
                "raw": event,
            }
        )
    for index, row in enumerate(trace.get("agent_steps") or [], start=1):
        if not isinstance(row, dict):
            continue
        step = row.get("step") if isinstance(row.get("step"), dict) else row
        timeline.append(
            {
                "order": float(step.get("step_number") or row.get("step_number") or index) + 0.1,
                "phase": "planning",
                "label": _timeline_label(step, "agent_step"),
                "description": step.get("thought") or step.get("hypothesis") or step.get("hypothesis_after"),
                "tool_name": step.get("tool_name"),
                "status": step.get("status") or row.get("status"),
                "error": step.get("error"),
                "raw": row,
            }
        )
    for index, call in enumerate(trace.get("tool_calls") or [], start=1):
        if not isinstance(call, dict):
            continue
        timeline.append(
            {
                "order": float(call.get("step_number") or index) + 0.2,
                "phase": "tool",
                "label": f"Tool call: {call.get('tool_name') or 'unknown'}",
                "description": call.get("stop_reason"),
                "tool_name": call.get("tool_name"),
                "status": call.get("status"),
                "audit_id": call.get("audit_id"),
                "policy_decisions": call.get("policy_decisions") or [],
                "data_completeness": call.get("data_completeness"),
                "error": call.get("error"),
                "raw": call,
            }
        )
    for index, observation in enumerate(trace.get("observations") or [], start=1):
        if not isinstance(observation, dict):
            continue
        completeness = observation.get("data_completeness") or {}
        rows = completeness.get("rows_returned") if isinstance(completeness, dict) else None
        timeline.append(
            {
                "order": float(observation.get("step_number") or index) + 0.3,
                "phase": "observation",
                "label": f"Observed: {observation.get('tool_name') or 'tool response'}",
                "description": f"{rows} row(s) returned" if rows is not None else None,
                "tool_name": observation.get("tool_name"),
                "status": "complete" if isinstance(completeness, dict) and completeness.get("complete") else None,
                "audit_id": observation.get("audit_id"),
                "policy_decisions": observation.get("policy_decisions") or [],
                "data_completeness": completeness,
                "error": observation.get("error"),
                "raw": observation,
            }
        )
    return [
        {key: value for key, value in item.items() if key != "order"}
        for item in sorted(timeline, key=lambda item: item["order"])
    ]


def _review_from_record(store: SidecarStore, run_id: str, record: dict[str, Any]) -> dict[str, Any]:
    output = _stored_output(record)
    details = output.get("details") if isinstance(output.get("details"), dict) else {}
    trace = store.get_trace(run_id) or {}
    run = record.get("run") or {}
    evidence = _normalize_evidence(record.get("evidence") or [])

    reasoning = output.get("reasoning") or output.get("structured_reasoning") or []
    limitations = list(output.get("limitations") or [])
    phase4 = details.get("phase4_live_mcp") if isinstance(details.get("phase4_live_mcp"), dict) else {}
    for observation in phase4.get("observations") or []:
        for limitation in observation.get("limitations") or []:
            if limitation not in limitations:
                limitations.append(limitation)

    missing_data = []
    for key in ("missing_required_fields", "missing_data"):
        values = details.get(key)
        if isinstance(values, list):
            missing_data.extend(str(item) for item in values)
    validation = record.get("validation")
    if isinstance(validation, dict) and validation.get("report_json"):
        validation = {**validation, "report": _parse_json_field(validation["report_json"])}
    decisions = store.list_human_decisions(run_id)
    exports = store.list_bank_exports(run_id)
    phase4_workflow = trace.get("phase4_workflow") if isinstance(trace.get("phase4_workflow"), dict) else {}
    workflow = phase4.get("workflow") or phase4_workflow.get("workflow") or output.get("purpose")

    review = {
        "run_id": run_id,
        "run": record.get("run"),
        "workflow": workflow,
        "agent_name": run.get("agent_name") or output.get("agent_name"),
        "subject": {
            "type": run.get("subject_type") or output.get("subject_type"),
            "id": run.get("subject_id") or output.get("subject_id"),
        },
        "created_at": run.get("created_at"),
        "status": run.get("status"),
        "recommendation": output.get("recommendation") or output.get("action"),
        "confidence": output.get("confidence_score", output.get("confidence")),
        "score": output.get("score"),
        "evidence": evidence,
        "claims": output.get("claims") or output.get("factual_claims") or [],
        "reasoning": reasoning,
        "limitations": limitations,
        "missing_data": sorted(set(missing_data)),
        "stop_reason": trace.get("stop_reason") or phase4.get("stop_reason"),
        "required_human_action": details.get("required_human_action") or (
            "Authorized human SAR review required." if _is_sar_run(record) else "Review proposal and record a human decision."
        ),
        "audit_ids": _collect_audit_ids({"output": output, "trace": trace}),
        "validation": validation,
        "validation_findings": _validation_findings(validation),
        "human_decisions": decisions,
        "exports": exports,
        "latest_human_decision": decisions[-1] if decisions else None,
        "latest_export": exports[-1] if exports else None,
        "workflow_timeline": _workflow_timeline(trace),
        "trace_summary": {
            "terminal_state": trace.get("terminal_state"),
            "runtime_event_count": len(trace.get("runtime_events") or []),
            "tool_call_count": len(trace.get("tool_calls") or []),
            "observation_count": len(trace.get("observations") or []),
        },
    }
    return review


@router.post("/agent-runs/triage")
def run_triage(body: TriageRunBody, officer: dict = Depends(require_view)) -> dict:
    with ro_cursor() as cur:
        cur.execute("SELECT alert_id FROM alerts WHERE alert_id = %s", (body.alert_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail=f"Alert {body.alert_id} not found")

    settings = Settings.from_env()
    try:
        orchestrator = build_orchestrator(settings)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=f"Agent configuration error: {exc}") from exc

    try:
        result = orchestrator.triage_alert(body.alert_id)
    except SourceRecordNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Agent triage failed for alert %s", body.alert_id)
        raise HTTPException(status_code=503, detail=f"Agent run failed: {type(exc).__name__}: {exc}") from exc

    try:
        with rw_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                insert_audit(cur, officer_id=officer["officer_id"], action="agent_triage",
                             entity_type="alert", entity_id=body.alert_id, alert_id=body.alert_id,
                             details={"run_id": result.get("run_id")})
    except Exception:
        logger.exception("Audit log insert failed for agent_triage on alert %s", body.alert_id)

    return result


@router.post("/agent-runs/live-mcp-triage")
def run_live_mcp_triage(
    body: LiveMcpTriageRunBody,
    officer: dict = Depends(require_view),
) -> dict:
    settings = Settings.from_env()
    workflow_body = LiveMcpWorkflowRunBody(
        workflow="triage",
        alert_id=body.alert_id,
        max_steps=body.max_steps,
        max_tool_calls=body.max_tool_calls,
        max_rows=body.max_rows,
        max_graph_hops=body.max_graph_hops,
        timeout_seconds=body.timeout_seconds,
        max_cost_usd=body.max_cost_usd,
    )
    result = _run_live_workflow(body=workflow_body, officer=officer, settings=settings)
    _audit_agent_action(
        officer=officer,
        action="agent_live_mcp_triage",
        body=workflow_body,
        run_id=result.get("run_id"),
    )
    return result


@router.post("/agent-runs/live-mcp")
def run_live_mcp_workflow(
    body: LiveMcpWorkflowRunBody,
    officer: dict = Depends(require_view),
) -> dict:
    settings = Settings.from_env()
    result = _run_live_workflow(body=body, officer=officer, settings=settings)
    _audit_agent_action(
        officer=officer,
        action="agent_live_mcp_workflow",
        body=body,
        run_id=result.get("run_id"),
    )
    return result


@router.get("/agent-runs/live-mcp-config")
def get_live_mcp_config(officer: dict = Depends(require_view)) -> dict:
    settings = Settings.from_env()
    bounds = settings.default_runtime_bounds() if hasattr(settings, "default_runtime_bounds") else RuntimeBounds()
    return {
        "provider_endpoint": settings.llm_endpoint,
        "model": settings.llm_model,
        "llm_configured": bool(settings.llm_api_key or os.getenv("OPENAI_API_KEY"))
        and bool(settings.llm_model or os.getenv("OPENAI_MODEL")),
        "prompt_version": getattr(settings, "llm_prompt_version", "phase1_live_mcp_agent_v1"),
        "tool_registry_version": getattr(settings, "mcp_tool_registry_version", "phase1_reference_mcp_v1"),
        "policy_version": getattr(settings, "agent_policy_version", "phase1_reference_mcp_policy_v1"),
        "runtime_bounds": bounds.model_dump(mode="json"),
        "supported_workflows": ["triage", "investigation", "risk_scoring", "sar_drafting"],
    }


@router.get("/agent-runs/{run_id}/review")
def get_agent_review(run_id: str, officer: dict = Depends(require_view)) -> dict:
    settings = Settings.from_env()
    store = SidecarStore(settings.sidecar_db_path)
    record = store.get_run(run_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Agent run not found: {run_id}")
    return _review_from_record(store, run_id, record)


@router.post("/agent-runs/{run_id}/human-decisions", status_code=201)
def record_human_decision(
    run_id: str,
    body: HumanDecisionBody,
    officer: dict = Depends(require_view),
) -> dict:
    settings = Settings.from_env()
    store = SidecarStore(settings.sidecar_db_path)
    record = store.get_run(run_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Agent run not found: {run_id}")
    _assert_human_action_permission(officer, record)
    try:
        decision = store.record_human_decision(
            run_id,
            officer_id=str(officer["officer_id"]),
            decision=body.decision,
            rationale=body.rationale,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        with rw_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                insert_audit(
                    cur,
                    officer_id=officer["officer_id"],
                    action="record_human_decision",
                    entity_type="agent_run",
                    entity_id=run_id,
                    details={"decision_id": decision["decision_id"], "decision": body.decision},
                )
    except Exception:
        logger.exception("Audit log insert failed for human decision on run %s", run_id)
    return decision


@router.post("/agent-runs/{run_id}/exports", status_code=201)
def record_bank_export(
    run_id: str,
    body: BankExportBody,
    officer: dict = Depends(require_view),
) -> dict:
    settings = Settings.from_env()
    store = SidecarStore(settings.sidecar_db_path)
    record = store.get_run(run_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Agent run not found: {run_id}")
    _assert_human_action_permission(officer, record)
    decisions = store.list_human_decisions(run_id)
    if not decisions:
        raise HTTPException(status_code=409, detail="A human decision is required before export")
    decision = None
    if body.decision_id:
        decision = next((item for item in decisions if item["decision_id"] == body.decision_id), None)
        if decision is None:
            raise HTTPException(status_code=404, detail=f"Human decision not found: {body.decision_id}")
    else:
        decision = decisions[-1]

    review = _review_from_record(store, run_id, record)
    payload = {
        "run_id": run_id,
        "decision": decision,
        "recommendation": review["recommendation"],
        "confidence": review["confidence"],
        "validation": review["validation"],
        "audit_ids": review["audit_ids"],
        "export_note": "Explicit POC export record only; no autonomous bank source mutation.",
    }
    try:
        export = store.record_bank_export(
            run_id,
            decision_id=decision["decision_id"],
            officer_id=str(officer["officer_id"]),
            export_type=body.export_type,
            destination=body.destination,
            payload=payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        with rw_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                insert_audit(
                    cur,
                    officer_id=officer["officer_id"],
                    action="export_human_decision",
                    entity_type="agent_run",
                    entity_id=run_id,
                    details={
                        "export_id": export["export_id"],
                        "decision_id": decision["decision_id"],
                        "destination": body.destination,
                        "export_type": body.export_type,
                    },
                )
    except Exception:
        logger.exception("Audit log insert failed for export on run %s", run_id)
    return export


@router.get("/agent-runs/{run_id}")
def get_agent_run(run_id: str, officer: dict = Depends(require_view)) -> dict:
    settings = Settings.from_env()
    store = SidecarStore(settings.sidecar_db_path)
    record = store.get_run(run_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Agent run not found: {run_id}")
    return record


@router.get("/agent-runs/{run_id}/trace")
def get_agent_trace(run_id: str, officer: dict = Depends(require_view)) -> dict:
    settings = Settings.from_env()
    store = SidecarStore(settings.sidecar_db_path)
    trace = store.get_trace(run_id)
    if not trace:
        raise HTTPException(status_code=404, detail=f"Agent run not found: {run_id}")
    return trace
