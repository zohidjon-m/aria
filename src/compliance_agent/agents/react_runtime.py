from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..adapters.source import BankSourceRepository
from ..domain import AgentResult, Claim, EvidenceItem, ReasoningItem, SourceRef
from ..utils import clamp, new_id, stable_hash
from .common import collect_evidence
from .confidence import ConfidenceEngine
from .phase1_tools import (
    TOOL_REGISTRY_VERSION,
    build_phase1_tool_registry,
    build_scope_for_alert,
)
from .tooling import (
    ScopeViolationError,
    ToolArgumentError,
    ToolExecutionContext,
    ToolObservation,
    ToolRegistry,
    ToolRegistryError,
    UnknownToolError,
)
from .typology_router import TypologyRouteResult, TypologyRouter


COMPLETED = "completed"
CRITICAL_SIGNAL_FOUND = "critical_signal_found"
MAX_STEPS_EXHAUSTED = "max_steps_exhausted"
TOOL_ERROR = "tool_error"
SCHEMA_ERROR = "schema_error"
INSUFFICIENT_EVIDENCE = "insufficient_evidence"
NO_PROGRESS = "no_progress"

SAFE_STOP_DISPOSITIONS = {
    CRITICAL_SIGNAL_FOUND: "escalate",
    MAX_STEPS_EXHAUSTED: "investigate",
    TOOL_ERROR: "investigate",
    SCHEMA_ERROR: "investigate",
    INSUFFICIENT_EVIDENCE: "investigate",
    NO_PROGRESS: "investigate",
}

DEFAULT_TRIAGE_DISPOSITIONS = (
    "escalate",
    "investigate",
    "likely_false_positive",
)


class PlannerError(RuntimeError):
    """Base error for planner failures handled by the runtime."""


class PlannerOutputError(PlannerError):
    """Planner returned malformed or contract-violating output."""


class PlannerProviderError(PlannerError):
    """Planner provider failed before returning a usable action."""


@dataclass(frozen=True)
class ReActRuntimeConfig:
    max_steps: int = 6
    max_tool_calls: int = 5
    allowed_dispositions: tuple[str, ...] = DEFAULT_TRIAGE_DISPOSITIONS


@dataclass(frozen=True)
class PlannerAction:
    thought: str
    next_tool: str | None = None
    tool_args: dict[str, Any] = field(default_factory=dict)
    stop: bool = False


@dataclass(frozen=True)
class ReActState:
    alert_context: dict[str, Any]
    route: TypologyRouteResult
    observations: dict[str, ToolObservation]
    tool_call_count: int
    step_number: int


class Planner(Protocol):
    def next_action(self, state: ReActState) -> PlannerAction:
        ...


class HeuristicPlanner:
    """Permanent deterministic planner for air-gapped deployments."""

    planner_type = "heuristic"

    TOOL_ORDER = (
        "get_alert_context",
        "compute_behavioral_baseline",
        "screen_sanctions_pep",
        "run_geography_check",
        "run_structuring_check",
        "run_velocity_check",
        "trace_money_flow",
    )

    def next_action(self, state: ReActState) -> PlannerAction:
        for tool_name in self.TOOL_ORDER:
            if tool_name in state.route.registry.names and tool_name not in state.observations:
                return PlannerAction(
                    thought=f"Need scoped facts from {tool_name}.",
                    next_tool=tool_name,
                    tool_args={},
                )
        return PlannerAction(
            thought="All routed tools needed by the heuristic planner have been observed.",
            stop=True,
        )


class ReActRuntime:
    """Bounded plan/act/observe runtime for alert triage."""

    def __init__(
        self,
        *,
        config: ReActRuntimeConfig | None = None,
        registry: ToolRegistry | None = None,
        router: TypologyRouter | None = None,
        planner: Planner | None = None,
        confidence_engine: ConfidenceEngine | None = None,
    ) -> None:
        self.config = config or ReActRuntimeConfig()
        self.registry = registry or build_phase1_tool_registry()
        self.router = router or TypologyRouter(self.registry)
        self.planner = planner or HeuristicPlanner()
        self.confidence_engine = confidence_engine or ConfidenceEngine()

    def run_triage(
        self,
        source: BankSourceRepository,
        alert_id: int,
        *,
        pre_screen_result: Any | None = None,
    ) -> AgentResult:
        alert_context = source.get_alert_context(alert_id)
        baseline_features, pre_screen_signals = self._pre_screen_inputs(pre_screen_result)
        route = self.router.route(
            alert_context,
            baseline_features=baseline_features,
            pre_screen_signals=pre_screen_signals,
        )
        execution_context = ToolExecutionContext(
            source=source,
            scope=build_scope_for_alert(source, alert_id),
        )

        observations: dict[str, ToolObservation] = {}
        trace_steps: list[dict[str, Any]] = []
        executed_calls: set[str] = set()
        stop_reason: str | None = None
        tool_call_count = 0

        for step_number in range(1, self.config.max_steps + 1):
            if tool_call_count >= self.config.max_tool_calls:
                stop_reason = MAX_STEPS_EXHAUSTED
                trace_steps.append(
                    self._control_step(
                        step_number,
                        "Tool call limit reached before planner selected another action.",
                        stop_reason,
                    )
                )
                break

            state = ReActState(
                alert_context=alert_context,
                route=route,
                observations=observations,
                tool_call_count=tool_call_count,
                step_number=step_number,
            )
            hypothesis = self._hypothesis(observations)
            try:
                action = self.planner.next_action(state)
            except PlannerOutputError as exc:
                stop_reason = SCHEMA_ERROR
                trace_steps.append(
                    self._error_step(
                        step_number,
                        "Planner returned malformed output.",
                        hypothesis,
                        None,
                        {},
                        stop_reason,
                        str(exc),
                    )
                )
                break
            except PlannerError as exc:
                stop_reason = TOOL_ERROR
                trace_steps.append(
                    self._error_step(
                        step_number,
                        "Planner provider failed.",
                        hypothesis,
                        None,
                        {},
                        stop_reason,
                        str(exc),
                    )
                )
                break
            if action.stop:
                stop_reason = self._terminal_stop_reason(observations)
                trace_steps.append(
                    {
                        "step_number": step_number,
                        "status": "stopped",
                        "thought": action.thought,
                        "hypothesis": hypothesis,
                        "tool_name": None,
                        "tool_args": {},
                        "stop_reason": stop_reason,
                    }
                )
                break

            tool_name = action.next_tool
            tool_args = dict(action.tool_args or {})
            if not tool_name or tool_name not in route.registry.names:
                stop_reason = SCHEMA_ERROR
                trace_steps.append(
                    self._error_step(
                        step_number,
                        action.thought,
                        hypothesis,
                        tool_name,
                        tool_args,
                        stop_reason,
                        "Planner selected a tool outside the routed registry.",
                    )
                )
                break

            call_hash = stable_hash({"tool_name": tool_name, "tool_args": tool_args})
            if call_hash in executed_calls:
                stop_reason = NO_PROGRESS
                trace_steps.append(
                    self._error_step(
                        step_number,
                        action.thought,
                        hypothesis,
                        tool_name,
                        tool_args,
                        stop_reason,
                        "Planner repeated an already executed tool call.",
                    )
                )
                break

            try:
                observation, execution_context = route.registry.execute_with_context(
                    tool_name,
                    execution_context,
                    tool_args,
                )
            except (ToolArgumentError, UnknownToolError, ScopeViolationError) as exc:
                stop_reason = SCHEMA_ERROR
                trace_steps.append(
                    self._error_step(
                        step_number,
                        action.thought,
                        hypothesis,
                        tool_name,
                        tool_args,
                        stop_reason,
                        str(exc),
                    )
                )
                break
            except ToolRegistryError as exc:
                stop_reason = TOOL_ERROR
                trace_steps.append(
                    self._error_step(
                        step_number,
                        action.thought,
                        hypothesis,
                        tool_name,
                        tool_args,
                        stop_reason,
                        str(exc),
                    )
                )
                break

            executed_calls.add(call_hash)
            tool_call_count += 1
            observations[tool_name] = observation
            trace_steps.append(
                {
                    "step_number": step_number,
                    "status": "observed",
                    "thought": action.thought,
                    "hypothesis": hypothesis,
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "observation": self._observation_summary(observation),
                }
            )

            if self._critical_signal_found(observations):
                stop_reason = CRITICAL_SIGNAL_FOUND
                trace_steps[-1]["stop_reason"] = stop_reason
                break
        else:
            stop_reason = MAX_STEPS_EXHAUSTED
            trace_steps.append(
                self._control_step(
                    len(trace_steps) + 1,
                    "Runtime reached max steps before a terminal planner action.",
                    stop_reason,
                )
            )

        final_stop_reason = stop_reason or MAX_STEPS_EXHAUSTED
        recommendation, score = self._recommendation(observations, final_stop_reason)
        confidence_result = self.confidence_engine.compute_react(
            recommendation=recommendation,
            stop_reason=final_stop_reason,
            observations=observations,
            reason_codes=list(getattr(pre_screen_result, "reason_codes", [])),
        )
        reasoning = self._reasoning(
            alert_id=alert_id,
            recommendation=recommendation,
            stop_reason=final_stop_reason,
            route=route,
            observations=observations,
        )
        claims = self._claims(
            alert_context=alert_context,
            recommendation=recommendation,
            stop_reason=final_stop_reason,
            observations=observations,
        )
        evidence = self._evidence(alert_context, observations)
        customer = alert_context.get("customer") or {}
        planner_type = getattr(self.planner, "planner_type", "unknown")
        planner_metadata = self._planner_metadata()

        details = {
            "recommendation_id": new_id("rec"),
            "customer_id": customer.get("customer_id"),
            "triage_path": "pre_screen_ambiguous_react",
            "activated_typologies": list(route.activated),
            "human_required": True,
            "confidence_breakdown": confidence_result.to_details(),
            "runtime_version": self._runtime_version_details(
                planner_type=planner_type,
                planner_metadata=planner_metadata,
            ),
            "typology_route": route.to_details(),
            "react_runtime": {
                "planner": planner_type,
                "planner_metadata": planner_metadata,
                "stop_reason": final_stop_reason,
                "max_steps": self.config.max_steps,
                "max_tool_calls": self.config.max_tool_calls,
                "tool_call_count": tool_call_count,
                "steps": trace_steps,
                "tool_observations": {
                    name: observation.model_dump(mode="json")
                    for name, observation in observations.items()
                },
            },
        }
        if pre_screen_result is not None:
            details["pre_screen_gate"] = pre_screen_result.to_details()
            details["baseline_assessment"] = pre_screen_result.baseline_assessment
            details["reason_codes"] = list(pre_screen_result.reason_codes)
            details["selected_typology_signals"] = dict(
                pre_screen_result.selected_typology_signals
            )

        return AgentResult(
            agent_name="triage_agent",
            subject_type="alert",
            subject_id=alert_id,
            recommendation=recommendation,
            confidence=confidence_result.final_confidence,
            score=score,
            reasoning=reasoning,
            claims=claims,
            evidence=evidence,
            details=details,
        )

    def _planner_metadata(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        for attr in ("model_id", "prompt_version"):
            value = getattr(self.planner, attr, None)
            if value:
                metadata[attr] = value
        return metadata

    def _runtime_version_details(
        self,
        *,
        planner_type: str,
        planner_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "planner_type": planner_type,
            "model_id": planner_metadata.get("model_id"),
            "prompt_version": planner_metadata.get("prompt_version", ""),
            "tool_registry_version": TOOL_REGISTRY_VERSION,
            "runtime_bounds": {
                "max_steps": self.config.max_steps,
                "max_tool_calls": self.config.max_tool_calls,
                "allowed_dispositions": list(self.config.allowed_dispositions),
            },
        }

    def _pre_screen_inputs(self, pre_screen_result: Any | None) -> tuple[dict[str, Any], dict[str, Any]]:
        if pre_screen_result is None:
            return {}, {}
        baseline_observation = pre_screen_result.tool_observations.get(
            "compute_behavioral_baseline"
        )
        baseline = baseline_observation.computed_features if baseline_observation else {}
        return baseline, dict(pre_screen_result.selected_typology_signals)

    def _terminal_stop_reason(self, observations: dict[str, ToolObservation]) -> str:
        baseline = observations.get("compute_behavioral_baseline")
        if baseline and baseline.computed_features.get("baseline_assessment") == "insufficient_data":
            return INSUFFICIENT_EVIDENCE
        if not observations:
            return INSUFFICIENT_EVIDENCE
        return COMPLETED

    def _critical_signal_found(self, observations: dict[str, ToolObservation]) -> bool:
        screening = observations.get("screen_sanctions_pep")
        if screening:
            features = screening.computed_features
            if int(features.get("sanctions_match_count") or 0) > 0:
                return True

        geography = observations.get("run_geography_check")
        if geography:
            features = geography.computed_features
            fatf_status = str(features.get("fatf_status") or "").lower()
            if bool(features.get("is_sanctioned_country")) or fatf_status == "blacklist":
                return True

        velocity = observations.get("run_velocity_check")
        if velocity and bool(velocity.computed_features.get("velocity_threshold_met")):
            return True
        graph = observations.get("trace_money_flow")
        if graph:
            signals = graph.computed_features.get("signals") or {}
            if bool(signals.get("high_risk_endpoint")):
                return True
            if int(signals.get("linked_open_case_count") or 0) > 0:
                return True
        return False

    def _recommendation(
        self,
        observations: dict[str, ToolObservation],
        stop_reason: str,
    ) -> tuple[str, float]:
        if stop_reason in SAFE_STOP_DISPOSITIONS:
            return self._allowed(SAFE_STOP_DISPOSITIONS[stop_reason]), self._score(stop_reason, observations)

        final = self._completed_recommendation(observations)
        return self._allowed(final), self._score(stop_reason, observations)

    def _completed_recommendation(self, observations: dict[str, ToolObservation]) -> str:
        baseline_features = self._features(observations, "compute_behavioral_baseline")
        structuring_features = self._features(observations, "run_structuring_check")
        geography_features = self._features(observations, "run_geography_check")
        screening_features = self._features(observations, "screen_sanctions_pep")
        velocity_features = self._features(observations, "run_velocity_check")
        graph_features = self._features(observations, "trace_money_flow")
        graph_signals = graph_features.get("signals") or {}

        if int(screening_features.get("sanctions_match_count") or 0) > 0:
            return "escalate"
        fatf_status = str(geography_features.get("fatf_status") or "").lower()
        if bool(geography_features.get("is_sanctioned_country")) or fatf_status == "blacklist":
            return "escalate"
        if bool(velocity_features.get("velocity_threshold_met")):
            return "escalate"
        if bool(graph_signals.get("high_risk_endpoint")):
            return "escalate"
        if int(graph_signals.get("linked_open_case_count") or 0) > 0:
            return "escalate"

        baseline = str(baseline_features.get("baseline_assessment") or "insufficient_data")
        structuring_signal = bool(
            structuring_features.get("current_transaction_in_structuring_band")
        ) or int(structuring_features.get("structuring_band_count") or 0) >= 3
        graph_red_flag = (
            bool(graph_signals.get("rapid_pass_through"))
            or bool(graph_signals.get("cycle_detected"))
            or bool(graph_signals.get("fan_out"))
            or bool(graph_signals.get("many_to_one"))
            or int(graph_signals.get("linked_alert_count") or 0) > 0
        )
        if baseline == "strong_deviation" and structuring_signal:
            return "escalate"
        if baseline == "consistent" and not structuring_signal and not graph_red_flag:
            return "likely_false_positive"
        return "investigate"

    def _allowed(self, recommendation: str) -> str:
        if recommendation in self.config.allowed_dispositions:
            return recommendation
        if "investigate" in self.config.allowed_dispositions:
            return "investigate"
        return self.config.allowed_dispositions[0]

    def _score(self, stop_reason: str, observations: dict[str, ToolObservation]) -> float:
        if stop_reason == CRITICAL_SIGNAL_FOUND:
            return 90.0
        if stop_reason in {MAX_STEPS_EXHAUSTED, TOOL_ERROR, SCHEMA_ERROR, NO_PROGRESS}:
            return 50.0
        if stop_reason == INSUFFICIENT_EVIDENCE:
            return 55.0
        baseline = str(
            self._features(observations, "compute_behavioral_baseline").get(
                "baseline_assessment"
            )
            or "insufficient_data"
        )
        if baseline == "strong_deviation":
            return 78.0
        if baseline == "consistent":
            return 25.0
        return 58.0

    def _reasoning(
        self,
        *,
        alert_id: int,
        recommendation: str,
        stop_reason: str,
        route: TypologyRouteResult,
        observations: dict[str, ToolObservation],
    ) -> list[ReasoningItem]:
        baseline = self._features(observations, "compute_behavioral_baseline")
        alert_ref = SourceRef("alerts", str(alert_id))
        baseline_observation = observations.get("compute_behavioral_baseline")
        baseline_refs = (
            self._source_refs(baseline_observation)
            if baseline_observation
            else [alert_ref]
        )
        return [
            ReasoningItem(
                statement=(
                    f"ReAct runtime evaluated alert {alert_id} with "
                    f"{getattr(self.planner, 'planner_type', 'unknown')} planner "
                    f"and stopped because {stop_reason}."
                ),
                source_refs=[alert_ref],
            ),
            ReasoningItem(
                statement=f"Routed typologies activated: {', '.join(route.activated) or 'none'}.",
                source_refs=[alert_ref],
            ),
            ReasoningItem(
                statement=(
                    "Behavioral baseline assessment is "
                    f"{baseline.get('baseline_assessment', 'not_observed')}."
                ),
                source_refs=baseline_refs[:3],
            ),
            ReasoningItem(
                statement=f"Runtime recommends {recommendation} for human review.",
                source_refs=[alert_ref],
            ),
        ]

    def _claims(
        self,
        *,
        alert_context: dict[str, Any],
        recommendation: str,
        stop_reason: str,
        observations: dict[str, ToolObservation],
    ) -> list[Claim]:
        alert = alert_context["alert"]
        transaction = alert_context["transaction"]
        customer = alert_context["customer"]
        claims = [
            Claim(
                statement=(
                    f"Alert {alert['alert_id']} is linked to transaction "
                    f"{transaction['transaction_id']}."
                ),
                source_refs=[
                    SourceRef("alerts", str(alert["alert_id"])),
                    SourceRef("transactions", str(transaction["transaction_id"])),
                ],
            ),
            Claim(
                statement=f"ReAct investigation subject is customer {customer['customer_id']}.",
                source_refs=[SourceRef("customers", str(customer["customer_id"]))],
            ),
            Claim(
                statement=f"ReAct runtime stop reason is {stop_reason}.",
                source_refs=[SourceRef("alerts", str(alert["alert_id"]))],
            ),
            Claim(
                statement=f"ReAct runtime recommends {recommendation}.",
                source_refs=[SourceRef("alerts", str(alert["alert_id"]))],
            ),
        ]
        baseline = observations.get("compute_behavioral_baseline")
        if baseline:
            refs = self._source_refs(baseline)
            if refs:
                claims.append(
                    Claim(
                        statement=(
                            "Behavioral baseline assessment is "
                            f"{baseline.computed_features.get('baseline_assessment')}."
                        ),
                        source_refs=refs[:3],
                    )
                )
        return claims

    def _evidence(
        self,
        alert_context: dict[str, Any],
        observations: dict[str, ToolObservation],
    ) -> list[EvidenceItem]:
        evidence = {item.evidence_id: item for item in collect_evidence(alert_context)}
        for observation in observations.values():
            for ref in self._source_refs(observation):
                evidence_id = f"{ref.table}:{ref.key}"
                evidence.setdefault(
                    evidence_id,
                    EvidenceItem(
                        evidence_id=evidence_id,
                        source_ref=ref,
                        payload={
                            "source_table": ref.table,
                            "source_key": ref.key,
                            "source_columns": list(ref.columns),
                        },
                    ),
                )
        return list(evidence.values())

    def _source_refs(self, observation: ToolObservation) -> list[SourceRef]:
        refs = []
        for ref in observation.source_refs:
            refs.append(
                SourceRef(
                    table=ref.table,
                    key=str(ref.key),
                    columns=tuple(ref.columns),
                )
            )
        return refs

    def _hypothesis(self, observations: dict[str, ToolObservation]) -> str:
        if not observations:
            return "Initial hypothesis requires scoped alert and baseline facts."
        if self._critical_signal_found(observations):
            return "A critical red flag has been observed."
        baseline = self._features(observations, "compute_behavioral_baseline")
        assessment = baseline.get("baseline_assessment")
        if assessment:
            return f"Current baseline hypothesis is {assessment}."
        return "Additional routed tool evidence is needed."

    def _features(
        self,
        observations: dict[str, ToolObservation],
        tool_name: str,
    ) -> dict[str, Any]:
        observation = observations.get(tool_name)
        return observation.computed_features if observation else {}

    def _observation_summary(self, observation: ToolObservation) -> dict[str, Any]:
        return {
            "fact_keys": sorted(observation.facts),
            "computed_features": dict(observation.computed_features),
            "source_refs": [
                ref.model_dump(mode="json")
                for ref in observation.source_refs
            ],
            "data_completeness": observation.data_completeness.model_dump(mode="json"),
            "limitations": [
                limitation.model_dump(mode="json")
                for limitation in observation.limitations
            ],
        }

    def _control_step(
        self,
        step_number: int,
        thought: str,
        stop_reason: str,
    ) -> dict[str, Any]:
        return {
            "step_number": step_number,
            "status": "stopped",
            "thought": thought,
            "hypothesis": "Runtime control stopped the loop.",
            "tool_name": None,
            "tool_args": {},
            "stop_reason": stop_reason,
        }

    def _error_step(
        self,
        step_number: int,
        thought: str,
        hypothesis: str,
        tool_name: str | None,
        tool_args: dict[str, Any],
        stop_reason: str,
        error: str,
    ) -> dict[str, Any]:
        return {
            "step_number": step_number,
            "status": "error",
            "thought": thought,
            "hypothesis": hypothesis,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "stop_reason": stop_reason,
            "error": error,
        }
