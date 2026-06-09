from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from ..adapters.sidecar_store import SidecarStore
from ..contracts.phase1 import (
    AgentObservation,
    AgentProposal,
    AgentRunRequest,
    MCPSourceRef,
    Purpose,
)
from ..domain import AgentResult, Claim, EvidenceItem, ReasoningItem, SourceRef, ValidationReport
from ..utils import clamp, new_id, to_plain
from .live_mcp_demo import (
    COMPLETED,
    CRITICAL_SIGNAL_FOUND,
    ENTITY_TABLES,
    LiveMCPAgent,
)
from .validation import ComplianceValidationAgent


PHASE4_POLICY_VERSION = "phase4_live_mcp_workflow_policy_v1"


WorkflowName = Literal["triage", "investigation", "risk_scoring", "sar_drafting"]


@dataclass(frozen=True)
class Phase4WorkflowOutput:
    proposal: AgentProposal
    result: AgentResult


class LiveMCPWorkflowAgent:
    """Phase 4 workflow adapter over the bounded live MCP runtime.

    The wrapped `LiveMCPAgent` still controls live LLM planning and governed
    read-tool execution. This adapter maps the observed evidence into the
    workflow-specific `AgentResult` shapes used by the existing sidecar.
    """

    def __init__(
        self,
        live_agent: LiveMCPAgent,
        validation_agent: ComplianceValidationAgent | None = None,
    ) -> None:
        self.live_agent = live_agent
        self.validation_agent = validation_agent or ComplianceValidationAgent()

    def run_triage(self, request: AgentRunRequest) -> Phase4WorkflowOutput:
        proposal = self.live_agent.run(_with_purpose(request, "triage"))
        from .live_mcp_demo import proposal_to_agent_result

        result = proposal_to_agent_result(proposal)
        result.details["phase4_live_mcp"] = _runtime_details("triage", proposal)
        result.details["material_output_requires_human_review"] = True
        return Phase4WorkflowOutput(proposal=proposal, result=result)

    def run_investigation(self, request: AgentRunRequest) -> Phase4WorkflowOutput:
        proposal = self.live_agent.run(_with_purpose(request, "investigation"))
        result = _investigation_result(proposal)
        return Phase4WorkflowOutput(proposal=proposal, result=result)

    def run_risk_scoring(self, request: AgentRunRequest) -> Phase4WorkflowOutput:
        proposal = self.live_agent.run(_with_purpose(request, "risk_scoring"))
        result = _risk_scoring_result(proposal)
        return Phase4WorkflowOutput(proposal=proposal, result=result)

    def draft_sar(
        self,
        request: AgentRunRequest,
        *,
        officer_context: str = "",
    ) -> Phase4WorkflowOutput:
        proposal = self.live_agent.run(_with_purpose(request, "sar_drafting"))
        result = _sar_draft_result(proposal, officer_context=officer_context)
        return Phase4WorkflowOutput(proposal=proposal, result=result)

    def run_and_persist(
        self,
        workflow: WorkflowName,
        request: AgentRunRequest,
        sidecar: SidecarStore,
        *,
        officer_context: str = "",
    ) -> dict[str, Any]:
        output = self._run(workflow, request, officer_context=officer_context)
        validation = self.validation_agent.validate(output.result)
        if validation.status != "passed":
            output.result.details["validation_blocked"] = True
        sidecar.save_result(
            output.proposal.run_id,
            request.model_dump(mode="json"),
            output.result,
            validation,
        )
        return _workflow_response(output, validation)

    def _run(
        self,
        workflow: WorkflowName,
        request: AgentRunRequest,
        *,
        officer_context: str = "",
    ) -> Phase4WorkflowOutput:
        runners: dict[WorkflowName, Callable[[AgentRunRequest], Phase4WorkflowOutput]] = {
            "triage": self.run_triage,
            "investigation": self.run_investigation,
            "risk_scoring": self.run_risk_scoring,
            "sar_drafting": lambda req: self.draft_sar(req, officer_context=officer_context),
        }
        return runners[workflow](request)


def _investigation_result(proposal: AgentProposal) -> AgentResult:
    evidence = _evidence_from_proposal(proposal)
    fallback_ref = _fallback_ref(evidence, proposal)
    graph_signals = _merged_graph_signals(proposal.observations)
    screening = _screening_counts(proposal.observations)
    typologies = _typology_hypotheses(proposal.observations)
    recommendation = _investigation_recommendation(proposal, graph_signals, screening, typologies)
    score = _investigation_score(graph_signals, screening, typologies)

    reasoning = [
        ReasoningItem(
            statement=(
                "Live MCP investigation used a bounded plan, query, observe, revise loop "
                f"and stopped because {proposal.stop_reason}."
            ),
            source_refs=[fallback_ref],
        ),
        ReasoningItem(
            statement=f"Typology hypotheses tested: {', '.join(typologies) or 'none'}.",
            source_refs=[fallback_ref],
        ),
        ReasoningItem(
            statement=f"Investigation recommendation is {recommendation} for human review.",
            source_refs=[fallback_ref],
        ),
    ]
    claims = _workflow_claims(proposal)
    return AgentResult(
        agent_name="investigation_agent",
        subject_type="alert",
        subject_id=proposal.subject.alert_id or "unknown",
        recommendation=recommendation,
        confidence=_workflow_confidence(proposal, evidence),
        score=score,
        reasoning=reasoning,
        claims=claims,
        evidence=evidence,
        details={
            "investigation_id": new_id("inv"),
            "customer_id": proposal.subject.customer_id,
            "activated_typologies": typologies,
            "graph_signals": graph_signals,
            "screening_counts": screening,
            "human_required": True,
            "material_output_requires_human_review": True,
            "phase4_live_mcp": _runtime_details("investigation", proposal),
        },
    )


def _risk_scoring_result(proposal: AgentProposal) -> AgentResult:
    evidence = _evidence_from_proposal(proposal)
    fallback_ref = _fallback_ref(evidence, proposal)
    score, level, factors = _deterministic_risk_score(proposal.observations)
    factor_names = [factor["factor"] for factor in factors]
    reasoning = [
        ReasoningItem(
            statement="The LLM gathered risk evidence through governed MCP tools.",
            source_refs=[fallback_ref],
        ),
        ReasoningItem(
            statement=(
                "Final risk score was computed by deterministic policy "
                f"{PHASE4_POLICY_VERSION}, not by the LLM."
            ),
            source_refs=[fallback_ref],
        ),
        ReasoningItem(
            statement=f"Risk factors applied: {', '.join(factor_names) or 'none'}.",
            source_refs=[fallback_ref],
        ),
    ]
    claims = _workflow_claims(proposal)
    return AgentResult(
        agent_name="risk_scoring_agent",
        subject_type="customer",
        subject_id=proposal.subject.customer_id or "unknown",
        recommendation="record_risk_score_for_human_review",
        confidence=_workflow_confidence(proposal, evidence),
        score=score,
        reasoning=reasoning,
        claims=claims,
        evidence=evidence,
        details={
            "risk_score_id": new_id("risk"),
            "level": level,
            "factors": factors,
            "weights": {factor["factor"]: factor["weight"] for factor in factors},
            "policy_version": PHASE4_POLICY_VERSION,
            "score_source": "deterministic_policy",
            "llm_may_explain_evidence_only": True,
            "human_override": None,
            "human_required": True,
            "material_output_requires_human_review": True,
            "phase4_live_mcp": _runtime_details("risk_scoring", proposal),
        },
    )


def _sar_draft_result(proposal: AgentProposal, *, officer_context: str) -> AgentResult:
    evidence = _evidence_from_proposal(proposal)
    fallback_ref = _fallback_ref(evidence, proposal)
    narrative, sentence_evidence, missing_fields = _sar_narrative(
        proposal,
        fallback_ref=fallback_ref,
        officer_context=officer_context,
    )
    claims = [
        Claim(statement=item["sentence"], source_refs=item["source_refs"])
        for item in sentence_evidence
    ]
    reasoning = [
        ReasoningItem(
            statement="SAR draft narrative is assembled only from retrieved MCP facts and officer-entered context.",
            source_refs=[fallback_ref],
        ),
        ReasoningItem(
            statement="Draft is confidential, requires authorized human review, and is not a SAR filing.",
            source_refs=[fallback_ref],
        ),
    ]
    return AgentResult(
        agent_name="sar_drafting_agent",
        subject_type="case",
        subject_id=proposal.subject.case_id or proposal.subject.alert_id or "unknown",
        recommendation="draft_for_human_review",
        confidence=_workflow_confidence(proposal, evidence),
        score=0,
        reasoning=reasoning,
        claims=claims,
        evidence=evidence,
        details={
            "sar_draft_id": new_id("sar"),
            "narrative": narrative,
            "sentence_evidence": [
                {
                    "sentence": item["sentence"],
                    "source_refs": [ref.__dict__ for ref in item["source_refs"]],
                }
                for item in sentence_evidence
            ],
            "missing_required_fields": missing_fields,
            "sar_confidential": True,
            "human_required": True,
            "authorized_human_review_required": True,
            "never_file_autonomously": True,
            "material_output_requires_human_review": True,
            "phase4_live_mcp": _runtime_details("sar_drafting", proposal),
        },
    )


def _with_purpose(request: AgentRunRequest, purpose: Purpose) -> AgentRunRequest:
    return request.model_copy(update={"purpose": purpose})


def _workflow_response(
    output: Phase4WorkflowOutput,
    validation: ValidationReport,
) -> dict[str, Any]:
    return {
        "run_id": output.proposal.run_id,
        "proposal": output.proposal.model_dump(mode="json"),
        "result": to_plain(output.result),
        "validation": to_plain(validation),
    }


def _runtime_details(workflow: WorkflowName, proposal: AgentProposal) -> dict[str, Any]:
    return {
        "workflow": workflow,
        "planner_type": "live_mcp_llm",
        "model_id": proposal.model_version,
        "prompt_version": proposal.prompt_version,
        "tool_registry_version": proposal.tool_registry_version,
        "policy_version": proposal.policy_version,
        "stop_reason": proposal.stop_reason,
        "terminal_state": proposal.terminal_state,
        "tool_calls": [item.model_dump(mode="json") for item in proposal.tool_calls],
        "observations": [item.model_dump(mode="json") for item in proposal.observations],
        "trace": [item.model_dump(mode="json") for item in proposal.trace],
        "runtime_events": [item.model_dump(mode="json") for item in proposal.runtime_events],
    }


def _evidence_from_proposal(proposal: AgentProposal) -> list[EvidenceItem]:
    evidence = [
        EvidenceItem(
            evidence_id=f"{_table_for_entity(ref.entity_type)}:{ref.entity_id}",
            source_ref=SourceRef(
                table=_table_for_entity(ref.entity_type),
                key=ref.entity_id,
                columns=tuple(ref.field_names),
            ),
            payload=ref.model_dump(mode="json"),
            retrieved_at=ref.retrieved_at,
        )
        for ref in proposal.evidence_refs
    ]
    if not evidence:
        evidence.append(
            EvidenceItem(
                evidence_id=f"agent_runs:{proposal.run_id}",
                source_ref=SourceRef("agent_runs", proposal.run_id),
                payload={
                    "run_id": proposal.run_id,
                    "stop_reason": proposal.stop_reason,
                    "terminal_state": proposal.terminal_state,
                },
            )
        )
    return evidence


def _fallback_ref(evidence: list[EvidenceItem], proposal: AgentProposal) -> SourceRef:
    if evidence:
        return evidence[0].source_ref
    return SourceRef("agent_runs", proposal.run_id)


def _table_for_entity(entity_type: str) -> str:
    return ENTITY_TABLES.get(entity_type, entity_type)


def _source_refs_for_entities(
    proposal: AgentProposal,
    entity_types: set[str],
    *,
    limit: int = 8,
) -> list[SourceRef]:
    refs: list[SourceRef] = []
    seen = set()
    for observation in proposal.observations:
        for ref in observation.source_refs:
            if ref.entity_type not in entity_types:
                continue
            source_ref = SourceRef(_table_for_entity(ref.entity_type), ref.entity_id, tuple(ref.field_names))
            key = (source_ref.table, source_ref.key)
            if key in seen:
                continue
            refs.append(source_ref)
            seen.add(key)
            if len(refs) >= limit:
                return refs
    return refs


def _workflow_claims(proposal: AgentProposal) -> list[Claim]:
    claims: list[Claim] = []
    if proposal.subject.alert_id is not None:
        refs = _source_refs_for_entities(proposal, {"alert"})
        if refs:
            claims.append(
                Claim(
                    statement=f"Live MCP workflow is linked to alert {proposal.subject.alert_id}.",
                    source_refs=refs,
                )
            )
    if proposal.subject.customer_id is not None:
        refs = _source_refs_for_entities(proposal, {"customer"})
        if refs:
            claims.append(
                Claim(
                    statement=f"Live MCP workflow subject is customer {proposal.subject.customer_id}.",
                    source_refs=refs,
                )
            )
    for claim in proposal.factual_claims:
        refs = [
            SourceRef(_table_for_entity(ref.entity_type), ref.entity_id, tuple(ref.field_names))
            for ref in claim.evidence_refs
        ]
        if refs:
            claims.append(Claim(statement=claim.statement, source_refs=refs))
    return claims


def _workflow_confidence(proposal: AgentProposal, evidence: list[EvidenceItem]) -> float:
    if proposal.terminal_state == "failed_safe":
        return 0.45
    evidence_factor = min(0.15, len(evidence) / 40)
    return round(clamp(0.62 + evidence_factor, 0, 0.9), 2)


def _investigation_recommendation(
    proposal: AgentProposal,
    graph_signals: dict[str, Any],
    screening: dict[str, int],
    typologies: list[str],
) -> str:
    if proposal.stop_reason == CRITICAL_SIGNAL_FOUND:
        return "open_case"
    if screening["sanctions_matches"] or screening["pep_matches"]:
        return "open_case"
    if graph_signals.get("high_risk_endpoint") or int(graph_signals.get("linked_open_case_count") or 0) > 0:
        return "open_case"
    if any(name in {"structuring", "velocity", "geography", "mule", "rapid_pass_through", "fan_out", "many_to_one"} for name in typologies):
        return "continue_investigation"
    if proposal.stop_reason == COMPLETED:
        return "return_to_triage"
    return "continue_investigation"


def _investigation_score(
    graph_signals: dict[str, Any],
    screening: dict[str, int],
    typologies: list[str],
) -> float:
    score = 10 + len(typologies) * 8
    if screening["sanctions_matches"]:
        score += 50
    if screening["pep_matches"]:
        score += 20
    for key in ("rapid_pass_through", "cycle_detected", "fan_out", "many_to_one", "high_risk_endpoint"):
        if graph_signals.get(key):
            score += 12
    score += min(20, int(graph_signals.get("linked_open_case_count") or 0) * 10)
    return round(clamp(score), 2)


def _typology_hypotheses(observations: list[AgentObservation]) -> list[str]:
    typologies: set[str] = set()
    for observation in observations:
        if observation.tool_name == "get_compliance_rule":
            rule = observation.facts.get("compliance_rule") or {}
            rule_type = str(rule.get("rule_type") or "").lower()
            if rule_type:
                typologies.add(rule_type)
        if observation.tool_name == "get_behavioral_baseline":
            computed = observation.facts.get("computed_features") or {}
            factors = computed.get("assessment_factors") or []
            for factor in factors:
                typologies.add(str(factor))
        if observation.tool_name == "trace_counterparty_graph":
            signals = _graph_signals_from_observations([observation])
            for key in ("rapid_pass_through", "fan_out", "many_to_one", "high_risk_endpoint"):
                if signals.get(key):
                    typologies.add(key)
            if int(signals.get("linked_open_case_count") or 0) > 0:
                typologies.add("linked_case_risk")
        if observation.tool_name == "screen_sanctions_pep":
            screening = _screening_counts([observation])
            if screening["sanctions_matches"]:
                typologies.add("sanctions")
            if screening["pep_matches"]:
                typologies.add("pep")
    return sorted(typologies)


def _merged_graph_signals(observations: list[AgentObservation]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for observation in observations:
        if observation.tool_name != "trace_counterparty_graph":
            continue
        for key, value in _graph_signals_from_observations([observation]).items():
            if isinstance(value, bool):
                merged[key] = bool(merged.get(key)) or value
            elif isinstance(value, int):
                merged[key] = max(int(merged.get(key) or 0), value)
            else:
                merged[key] = value
    return merged


def _graph_signals_from_observations(observations: list[AgentObservation]) -> dict[str, Any]:
    for observation in observations:
        computed = observation.facts.get("computed_features") or {}
        signals = computed.get("signals")
        if isinstance(signals, dict):
            return dict(signals)
    return {}


def _screening_counts(observations: list[AgentObservation]) -> dict[str, int]:
    counts = {"sanctions_matches": 0, "pep_matches": 0}
    for observation in observations:
        if observation.tool_name != "screen_sanctions_pep":
            continue
        counts["sanctions_matches"] += len(observation.facts.get("sanctions_matches") or [])
        counts["pep_matches"] += len(observation.facts.get("pep_matches") or [])
    return counts


def _deterministic_risk_score(observations: list[AgentObservation]) -> tuple[float, str, list[dict[str, Any]]]:
    score = 25.0
    factors: list[dict[str, Any]] = [
        {"factor": "base_unknown_or_medium_risk", "weight": 25.0, "source": "deterministic_default"}
    ]
    profile = _first_fact(observations, "get_customer_profile")
    customer = profile.get("customer") or {}
    risk_level = str(customer.get("risk_level") or "").lower()
    base_by_level = {"low": 10.0, "medium": 30.0, "high": 55.0, "critical": 75.0}
    if risk_level in base_by_level:
        score = base_by_level[risk_level]
        factors[0] = {
            "factor": f"base_{risk_level}_customer_risk",
            "weight": score,
            "source": "customer_profile",
        }
    kyc_status = str(customer.get("kyc_status") or "").lower()
    if kyc_status in {"expired", "rejected"}:
        score += 20
        factors.append({"factor": f"kyc_{kyc_status}", "weight": 20.0, "source": "customer_profile"})
    elif kyc_status == "pending":
        score += 8
        factors.append({"factor": "kyc_pending", "weight": 8.0, "source": "customer_profile"})

    prior_alerts = _first_fact(observations, "get_prior_alerts").get("prior_alerts") or []
    critical_alerts = [item for item in prior_alerts if str(item.get("severity") or "").lower() == "critical"]
    if prior_alerts:
        weight = min(20.0, len(prior_alerts) * 5.0)
        score += weight
        factors.append({"factor": "prior_alert_volume", "weight": weight, "source": "get_prior_alerts"})
    if critical_alerts:
        weight = min(20.0, len(critical_alerts) * 10.0)
        score += weight
        factors.append({"factor": "critical_prior_alerts", "weight": weight, "source": "get_prior_alerts"})

    screening = _screening_counts(observations)
    if screening["sanctions_matches"]:
        score += 35
        factors.append({"factor": "sanctions_match", "weight": 35.0, "source": "screen_sanctions_pep"})
    if screening["pep_matches"]:
        score += 10
        factors.append({"factor": "pep_match", "weight": 10.0, "source": "screen_sanctions_pep"})

    graph_signals = _merged_graph_signals(observations)
    if graph_signals.get("high_risk_endpoint"):
        score += 15
        factors.append({"factor": "graph_high_risk_endpoint", "weight": 15.0, "source": "trace_counterparty_graph"})
    if int(graph_signals.get("linked_open_case_count") or 0) > 0:
        weight = min(15.0, int(graph_signals.get("linked_open_case_count") or 0) * 7.5)
        score += weight
        factors.append({"factor": "graph_linked_open_case", "weight": weight, "source": "trace_counterparty_graph"})

    score = round(clamp(score), 2)
    return score, _risk_level(score), factors


def _risk_level(score: float) -> str:
    if score < 25:
        return "low"
    if score < 50:
        return "medium"
    if score < 75:
        return "high"
    return "critical"


def _first_fact(observations: list[AgentObservation], tool_name: str) -> dict[str, Any]:
    for observation in observations:
        if observation.tool_name == tool_name:
            return observation.facts
    return {}


def _sar_narrative(
    proposal: AgentProposal,
    *,
    fallback_ref: SourceRef,
    officer_context: str,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    case_history = _first_fact(proposal.observations, "get_case_history")
    profile = _first_fact(proposal.observations, "get_customer_profile")
    tx_history = _first_fact(proposal.observations, "get_transaction_history")
    cases = case_history.get("cases") or []
    linked_alerts = case_history.get("linked_alerts") or []
    transactions = tx_history.get("transactions") or []
    customer = profile.get("customer") or {}
    missing = []
    if not cases:
        missing.append("case_details")
    if not linked_alerts:
        missing.append("linked_alerts")
    if not transactions:
        missing.append("transaction_history")
    if not officer_context.strip():
        missing.append("officer_entered_context")

    case_ref = _first_source_ref(proposal.evidence_refs, {"case"}) or fallback_ref
    customer_ref = _first_source_ref(proposal.evidence_refs, {"customer"}) or fallback_ref
    alert_ref = _first_source_ref(proposal.evidence_refs, {"alert"}) or fallback_ref
    tx_ref = _first_source_ref(proposal.evidence_refs, {"transaction"}) or fallback_ref

    case = cases[0] if cases else {}
    total_amount = sum(float(tx.get("amount_usd") or 0) for tx in transactions)
    sentence_evidence = [
        {
            "sentence": (
                f"Case {case.get('case_id', proposal.subject.case_id or 'unknown')} concerns customer "
                f"{customer.get('customer_id', proposal.subject.customer_id or 'unknown')}."
            ),
            "source_refs": [case_ref, customer_ref],
        },
        {
            "sentence": f"The retrieved case history includes {len(linked_alerts)} linked alert(s).",
            "source_refs": [case_ref, alert_ref],
        },
        {
            "sentence": (
                f"The retrieved transaction evidence includes {len(transactions)} transaction(s) "
                f"with total amount USD {total_amount:,.2f}."
            ),
            "source_refs": [tx_ref],
        },
    ]
    if officer_context.strip():
        sentence_evidence.append(
            {
                "sentence": "Officer-entered context was provided and must be verified during human review.",
                "source_refs": [fallback_ref],
            }
        )
    narrative = "\n".join(
        [
            "DRAFT REGULATORY REPORT NARRATIVE - HUMAN REVIEW REQUIRED",
            "",
            *[item["sentence"] for item in sentence_evidence],
            "",
            "Missing required fields: " + (", ".join(missing) if missing else "none identified from retrieved facts"),
            "",
            "This draft is confidential and is not a regulatory filing. An authorized human must verify, complete, approve, or reject it.",
        ]
    )
    return narrative, sentence_evidence, missing


def _first_source_ref(refs: list[MCPSourceRef], entity_types: set[str]) -> SourceRef | None:
    for ref in refs:
        if ref.entity_type in entity_types:
            return SourceRef(_table_for_entity(ref.entity_type), ref.entity_id, tuple(ref.field_names))
    return None
