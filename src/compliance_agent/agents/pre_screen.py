from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..adapters.source import BankSourceRepository
from ..domain import AgentResult, Claim, EvidenceItem, SourceRef
from ..utils import clamp, new_id
from .common import collect_evidence
from .phase1_tools import build_phase1_tool_registry, build_scope_for_alert
from .tooling import ToolExecutionContext, ToolObservation, ToolRegistry


ALWAYS_RUN_TOOLS = (
    "get_alert_context",
    "compute_behavioral_baseline",
    "screen_sanctions_pep",
    "run_geography_check",
    "run_structuring_check",
    "run_velocity_check",
)


OBSERVATION_RECORD_KEYS = {
    "alert": ("alerts", "alert_id"),
    "rule": ("compliance_rules", "rule_id"),
    "transaction": ("transactions", "transaction_id"),
    "current_transaction": ("transactions", "transaction_id"),
    "start_transaction": ("transactions", "transaction_id"),
    "account": ("accounts", "account_id"),
    "customer": ("customers", "customer_id"),
    "pattern": ("transaction_patterns", "pattern_id"),
    "destination_country": ("countries", "country_code"),
}


OBSERVATION_LIST_KEYS = {
    "historical_transactions": ("transactions", "transaction_id"),
    "structuring_band_transactions": ("transactions", "transaction_id"),
    "similar_alerts": ("alerts", "alert_id"),
    "sanctions_matches": ("sanctions_list", "sanction_id"),
    "pep_matches": ("pep_list", "pep_id"),
}


@dataclass(frozen=True)
class PreScreenResult:
    alert_id: int
    customer_id: int | None
    gate_decision: str
    recommended_disposition: str
    confidence: float
    score: float
    reason_codes: list[str]
    reasoning: list[str]
    claims: list[Claim]
    evidence: list[EvidenceItem]
    tool_observations: dict[str, ToolObservation]
    limitations: list[dict[str, Any]]
    baseline_assessment: str
    selected_typology_signals: dict[str, Any] = field(default_factory=dict)

    def to_agent_result(self) -> AgentResult:
        return AgentResult(
            agent_name="triage_agent",
            subject_type="alert",
            subject_id=self.alert_id,
            recommendation=self.recommended_disposition,
            confidence=self.confidence,
            score=self.score,
            reasoning=list(self.reasoning),
            claims=list(self.claims),
            evidence=list(self.evidence),
            details={
                "recommendation_id": new_id("rec"),
                "customer_id": self.customer_id,
                "triage_path": "pre_screen_gate",
                "pre_screen_gate": self.to_details(),
                "baseline_assessment": self.baseline_assessment,
                "reason_codes": list(self.reason_codes),
                "selected_typology_signals": dict(self.selected_typology_signals),
                "human_required": True,
            },
        )

    def to_details(self) -> dict[str, Any]:
        return {
            "gate_decision": self.gate_decision,
            "recommended_disposition": self.recommended_disposition,
            "confidence": self.confidence,
            "score": self.score,
            "reason_codes": list(self.reason_codes),
            "baseline_assessment": self.baseline_assessment,
            "selected_typology_signals": dict(self.selected_typology_signals),
            "limitations": list(self.limitations),
            "tool_observations": {
                name: observation.model_dump(mode="json")
                for name, observation in self.tool_observations.items()
            },
        }


class PreScreenGate:
    """Cheap deterministic triage gate before deeper investigation."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or build_phase1_tool_registry()

    def run(self, source: BankSourceRepository, alert_id: int) -> PreScreenResult:
        alert_context = source.get_alert_context(alert_id)
        execution_context = ToolExecutionContext(
            source=source,
            scope=build_scope_for_alert(source, alert_id),
        )
        observations: dict[str, ToolObservation] = {}

        for tool_name in ALWAYS_RUN_TOOLS:
            observation, execution_context = self.registry.execute_with_context(
                tool_name,
                execution_context,
                {},
            )
            observations[tool_name] = observation

        transaction = observations["get_alert_context"].facts.get("transaction") or {}
        if transaction.get("counterparty_account_id") is not None:
            observation, execution_context = self.registry.execute_with_context(
                "trace_money_flow",
                execution_context,
                {},
            )
            observations["trace_money_flow"] = observation

        return self._build_result(alert_context, observations)

    def _build_result(
        self,
        alert_context: dict[str, Any],
        observations: dict[str, ToolObservation],
    ) -> PreScreenResult:
        alert = alert_context["alert"]
        customer = alert_context.get("customer") or {}
        alert_id = int(alert["alert_id"])
        customer_id = customer.get("customer_id")
        baseline_features = observations["compute_behavioral_baseline"].computed_features
        screening_features = observations["screen_sanctions_pep"].computed_features
        geography_features = observations["run_geography_check"].computed_features
        structuring_features = observations["run_structuring_check"].computed_features
        velocity_features = observations["run_velocity_check"].computed_features

        baseline_assessment = str(
            baseline_features.get("baseline_assessment") or "insufficient_data"
        )
        selected_typology_signals = self._selected_typology_signals(
            screening_features=screening_features,
            geography_features=geography_features,
            structuring_features=structuring_features,
            velocity_features=velocity_features,
            observations=observations,
        )
        reason_codes = self._reason_codes(
            baseline_features=baseline_features,
            screening_features=screening_features,
            geography_features=geography_features,
            structuring_features=structuring_features,
            velocity_features=velocity_features,
        )
        gate_decision = self._gate_decision(
            reason_codes=reason_codes,
            baseline_assessment=baseline_assessment,
        )
        recommended_disposition = {
            "obvious_clear": "likely_false_positive",
            "obvious_escalate": "escalate",
            "ambiguous": "investigate",
        }[gate_decision]
        score, confidence = self._score_and_confidence(
            gate_decision=gate_decision,
            reason_codes=reason_codes,
            baseline_observation=observations["compute_behavioral_baseline"],
        )
        evidence = self._evidence(alert_context, observations)

        return PreScreenResult(
            alert_id=alert_id,
            customer_id=customer_id,
            gate_decision=gate_decision,
            recommended_disposition=recommended_disposition,
            confidence=confidence,
            score=score,
            reason_codes=reason_codes,
            reasoning=self._reasoning(
                alert_id=alert_id,
                gate_decision=gate_decision,
                recommended_disposition=recommended_disposition,
                baseline_features=baseline_features,
                screening_features=screening_features,
                geography_features=geography_features,
                structuring_features=structuring_features,
                velocity_features=velocity_features,
            ),
            claims=self._claims(
                alert_context=alert_context,
                baseline_assessment=baseline_assessment,
                gate_decision=gate_decision,
                observations=observations,
            ),
            evidence=evidence,
            tool_observations=observations,
            limitations=self._limitations(observations),
            baseline_assessment=baseline_assessment,
            selected_typology_signals=selected_typology_signals,
        )

    def _reason_codes(
        self,
        *,
        baseline_features: dict[str, Any],
        screening_features: dict[str, Any],
        geography_features: dict[str, Any],
        structuring_features: dict[str, Any],
        velocity_features: dict[str, Any],
    ) -> list[str]:
        codes: list[str] = []
        baseline_assessment = str(
            baseline_features.get("baseline_assessment") or "insufficient_data"
        )
        sanctions_count = int(screening_features.get("sanctions_match_count") or 0)
        pep_count = int(screening_features.get("pep_match_count") or 0)
        fatf_status = str(geography_features.get("fatf_status") or "").lower()

        if sanctions_count > 0:
            codes.append("sanctions_match")
        if pep_count > 0:
            codes.append("pep_match")
        if bool(geography_features.get("is_sanctioned_country")) or fatf_status == "blacklist":
            codes.append("sanctioned_or_blacklisted_country")
        if bool(velocity_features.get("velocity_threshold_met")):
            codes.append("velocity_threshold_met")

        structuring_signal = bool(
            structuring_features.get("current_transaction_in_structuring_band")
        ) or int(structuring_features.get("structuring_band_count") or 0) >= 3
        geography_signal = bool(geography_features.get("has_destination_country"))
        if baseline_assessment == "strong_deviation" and structuring_signal:
            codes.append("strong_deviation_with_structuring_signal")
        if baseline_assessment == "strong_deviation" and geography_signal:
            codes.append("strong_deviation_with_geography_signal")

        if baseline_assessment == "consistent":
            codes.append("baseline_consistent")
        elif baseline_assessment == "mild_deviation":
            codes.append("baseline_mild_deviation")
        elif baseline_assessment == "strong_deviation":
            codes.append("baseline_strong_deviation")
        else:
            codes.append("insufficient_baseline_history")

        if bool(baseline_features.get("new_destination_country")):
            codes.append("new_destination_country")
        if bool(baseline_features.get("new_counterparty")):
            codes.append("new_counterparty")

        dismissed_count = int(baseline_features.get("similar_dismissed_count") or 0)
        escalated_count = int(baseline_features.get("similar_escalated_count") or 0)
        if dismissed_count > escalated_count:
            codes.append("prior_similar_dismissals_exceed_escalations")
        if escalated_count > 0 and dismissed_count == 0:
            codes.append("prior_similar_escalations_without_dismissals")

        if not self._hard_red_flag_present(codes):
            codes.append("no_hard_red_flags")
        return codes

    def _gate_decision(self, *, reason_codes: list[str], baseline_assessment: str) -> str:
        if self._hard_red_flag_present(reason_codes):
            return "obvious_escalate"
        if (
            "strong_deviation_with_structuring_signal" in reason_codes
            or "strong_deviation_with_geography_signal" in reason_codes
        ):
            return "obvious_escalate"
        if (
            baseline_assessment == "consistent"
            and "no_hard_red_flags" in reason_codes
            and "new_destination_country" not in reason_codes
            and "new_counterparty" not in reason_codes
            and "prior_similar_dismissals_exceed_escalations" in reason_codes
        ):
            return "obvious_clear"
        return "ambiguous"

    def _hard_red_flag_present(self, reason_codes: list[str]) -> bool:
        hard_red_flags = {
            "sanctions_match",
            "sanctioned_or_blacklisted_country",
            "velocity_threshold_met",
        }
        return any(code in hard_red_flags for code in reason_codes)

    def _score_and_confidence(
        self,
        *,
        gate_decision: str,
        reason_codes: list[str],
        baseline_observation: ToolObservation,
    ) -> tuple[float, float]:
        if gate_decision == "obvious_escalate":
            hard_flag_bonus = 8 if self._hard_red_flag_present(reason_codes) else 0
            return clamp(82 + hard_flag_bonus, 0, 100), 0.9 if hard_flag_bonus else 0.84
        if gate_decision == "obvious_clear":
            complete_bonus = 0.03 if baseline_observation.data_completeness.complete else 0
            return 15.0, round(clamp(0.84 + complete_bonus, 0, 0.95), 2)
        return 50.0, 0.58

    def _reasoning(
        self,
        *,
        alert_id: int,
        gate_decision: str,
        recommended_disposition: str,
        baseline_features: dict[str, Any],
        screening_features: dict[str, Any],
        geography_features: dict[str, Any],
        structuring_features: dict[str, Any],
        velocity_features: dict[str, Any],
    ) -> list[str]:
        reasoning = [
            (
                f"Pre-screen gate classified alert {alert_id} as {gate_decision} "
                f"and recommends {recommended_disposition}."
            ),
            (
                "Behavioral baseline assessment is "
                f"{baseline_features.get('baseline_assessment')} with "
                f"{baseline_features.get('deviation_points')} deviation point(s)."
            ),
            (
                "Screening found "
                f"{screening_features.get('sanctions_match_count', 0)} sanctions match(es) "
                f"and {screening_features.get('pep_match_count', 0)} PEP match(es)."
            ),
            (
                "Geography check has sanctioned_country="
                f"{bool(geography_features.get('is_sanctioned_country'))} "
                f"and fatf_status={geography_features.get('fatf_status')}."
            ),
            (
                "Structuring check has current_in_band="
                f"{bool(structuring_features.get('current_transaction_in_structuring_band'))} "
                f"and band_count={structuring_features.get('structuring_band_count')}."
            ),
            (
                "Velocity check has threshold_met="
                f"{bool(velocity_features.get('velocity_threshold_met'))} "
                f"and max_same_day_count="
                f"{velocity_features.get('max_same_day_transaction_count')}."
            ),
        ]
        return reasoning

    def _claims(
        self,
        *,
        alert_context: dict[str, Any],
        baseline_assessment: str,
        gate_decision: str,
        observations: dict[str, ToolObservation],
    ) -> list[Claim]:
        alert = alert_context["alert"]
        transaction = alert_context["transaction"]
        pattern = alert_context.get("pattern") or {}
        country = alert_context.get("destination_country") or {}
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
                statement=(
                    "Pre-screen behavioral baseline assessment is "
                    f"{baseline_assessment}."
                ),
                source_refs=self._non_empty_refs(
                    [
                        SourceRef("transactions", str(transaction["transaction_id"])),
                        self._optional_ref(pattern, "transaction_patterns", "pattern_id"),
                    ]
                ),
            ),
            Claim(
                statement=f"Pre-screen gate decision is {gate_decision}.",
                source_refs=[
                    SourceRef("alerts", str(alert["alert_id"])),
                    SourceRef("transactions", str(transaction["transaction_id"])),
                ],
            ),
        ]

        geography = observations["run_geography_check"].computed_features
        if bool(geography.get("is_sanctioned_country")) and country:
            claims.append(
                Claim(
                    statement=(
                        f"Destination country {country.get('country_code')} is sanctioned."
                    ),
                    source_refs=[
                        SourceRef("transactions", str(transaction["transaction_id"])),
                        SourceRef("countries", str(country["country_code"])),
                    ],
                )
            )

        screening = observations["screen_sanctions_pep"].facts
        sanctions_matches = screening.get("sanctions_matches") or []
        if sanctions_matches:
            refs = [
                SourceRef("sanctions_list", str(match["sanction_id"]))
                for match in sanctions_matches
                if match.get("sanction_id") is not None
            ]
            claims.append(
                Claim(
                    statement=f"Screening returned {len(sanctions_matches)} sanctions match(es).",
                    source_refs=refs,
                )
            )
        return claims

    def _selected_typology_signals(
        self,
        *,
        screening_features: dict[str, Any],
        geography_features: dict[str, Any],
        structuring_features: dict[str, Any],
        velocity_features: dict[str, Any],
        observations: dict[str, ToolObservation],
    ) -> dict[str, Any]:
        graph_observation = observations.get("trace_money_flow")
        graph_features = graph_observation.computed_features if graph_observation else {}
        return {
            "sanctions": {
                "sanctions_match_count": screening_features.get("sanctions_match_count", 0),
                "pep_match_count": screening_features.get("pep_match_count", 0),
            },
            "geography": {
                "has_destination_country": geography_features.get("has_destination_country"),
                "is_sanctioned_country": geography_features.get("is_sanctioned_country"),
                "fatf_status": geography_features.get("fatf_status"),
                "country_risk_score": geography_features.get("country_risk_score"),
            },
            "structuring": {
                "current_transaction_in_structuring_band": structuring_features.get(
                    "current_transaction_in_structuring_band"
                ),
                "structuring_band_count": structuring_features.get("structuring_band_count"),
            },
            "velocity": {
                "velocity_threshold_met": velocity_features.get("velocity_threshold_met"),
                "max_same_day_transaction_count": velocity_features.get(
                    "max_same_day_transaction_count"
                ),
            },
            "graph": {
                "trace_executed": "trace_money_flow" in observations,
                "has_immediate_counterparty": graph_features.get(
                    "has_immediate_counterparty",
                    False,
                ),
            },
        }

    def _limitations(self, observations: dict[str, ToolObservation]) -> list[dict[str, Any]]:
        limitations: list[dict[str, Any]] = []
        for tool_name, observation in observations.items():
            for limitation in observation.limitations:
                payload = limitation.model_dump(mode="json")
                payload["tool_name"] = tool_name
                limitations.append(payload)
        return limitations

    def _evidence(
        self,
        alert_context: dict[str, Any],
        observations: dict[str, ToolObservation],
    ) -> list[EvidenceItem]:
        evidence = {item.evidence_id: item for item in collect_evidence(alert_context)}
        for observation in observations.values():
            for key, value in observation.facts.items():
                if key in OBSERVATION_RECORD_KEYS and isinstance(value, dict):
                    item = self._evidence_from_record(value, *OBSERVATION_RECORD_KEYS[key])
                    if item:
                        evidence[item.evidence_id] = item
                elif key in OBSERVATION_LIST_KEYS and isinstance(value, list):
                    table, key_name = OBSERVATION_LIST_KEYS[key]
                    for record in value:
                        if isinstance(record, dict):
                            item = self._evidence_from_record(record, table, key_name)
                            if item:
                                evidence[item.evidence_id] = item
        return list(evidence.values())

    def _evidence_from_record(
        self,
        record: dict[str, Any],
        table: str,
        key_name: str,
    ) -> EvidenceItem | None:
        key = record.get(key_name)
        if key is None:
            return None
        return EvidenceItem(
            evidence_id=f"{table}:{key}",
            source_ref=SourceRef(table=table, key=str(key)),
            payload=dict(record),
        )

    def _optional_ref(
        self,
        record: dict[str, Any],
        table: str,
        key_name: str,
    ) -> SourceRef | None:
        key = record.get(key_name)
        if key is None:
            return None
        return SourceRef(table=table, key=str(key))

    def _non_empty_refs(self, refs: list[SourceRef | None]) -> list[SourceRef]:
        return [ref for ref in refs if ref is not None]
