from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..utils import clamp
from .tooling import ToolObservation


ENGINE_VERSION = "confidence_v1"

REACT_ERROR_STOPS = {
    "max_steps_exhausted",
    "tool_error",
    "schema_error",
    "no_progress",
}


@dataclass(frozen=True)
class ConfidenceResult:
    engine_version: str
    mode: str
    base_confidence: float
    final_confidence: float
    signals: dict[str, Any]
    factors: list[dict[str, Any]]

    def to_details(self) -> dict[str, Any]:
        return {
            "engine_version": self.engine_version,
            "mode": self.mode,
            "base_confidence": self.base_confidence,
            "final_confidence": self.final_confidence,
            "signals": dict(self.signals),
            "factors": [dict(factor) for factor in self.factors],
        }


class ConfidenceEngine:
    """Runtime-derived confidence for alert triage outputs."""

    engine_version = ENGINE_VERSION

    def compute_pre_screen(
        self,
        *,
        recommendation: str,
        gate_decision: str,
        observations: dict[str, ToolObservation],
        reason_codes: list[str],
    ) -> ConfidenceResult:
        signals = self._signals(
            observations,
            recommendation=recommendation,
            reason_codes=reason_codes,
            gate_decision=gate_decision,
            stop_reason=None,
        )
        base = self._pre_screen_base(gate_decision)
        factors = self._pre_screen_factors(
            recommendation=recommendation,
            gate_decision=gate_decision,
            signals=signals,
        )
        factors.extend(self._common_factors(recommendation, signals))
        return self._result("pre_screen_gate", base, signals, factors)

    def compute_react(
        self,
        *,
        recommendation: str,
        stop_reason: str,
        observations: dict[str, ToolObservation],
        reason_codes: list[str] | None = None,
    ) -> ConfidenceResult:
        signals = self._signals(
            observations,
            recommendation=recommendation,
            reason_codes=reason_codes or [],
            gate_decision=None,
            stop_reason=stop_reason,
        )
        base = self._react_base(stop_reason)
        factors = self._react_factors(stop_reason)
        factors.extend(self._common_factors(recommendation, signals))
        return self._result("react_runtime", base, signals, factors)

    def _result(
        self,
        mode: str,
        base: float,
        signals: dict[str, Any],
        factors: list[dict[str, Any]],
    ) -> ConfidenceResult:
        final = base + sum(float(factor["adjustment"]) for factor in factors)
        return ConfidenceResult(
            engine_version=self.engine_version,
            mode=mode,
            base_confidence=round(base, 2),
            final_confidence=round(clamp(final, 0.10, 0.95), 2),
            signals=signals,
            factors=factors,
        )

    def _pre_screen_base(self, gate_decision: str) -> float:
        if gate_decision in {"obvious_clear", "obvious_escalate"}:
            return 0.70
        return 0.55

    def _react_base(self, stop_reason: str) -> float:
        if stop_reason == "critical_signal_found":
            return 0.72
        if stop_reason == "completed":
            return 0.64
        if stop_reason == "insufficient_evidence":
            return 0.50
        if stop_reason in REACT_ERROR_STOPS:
            return 0.45
        return 0.55

    def _pre_screen_factors(
        self,
        *,
        recommendation: str,
        gate_decision: str,
        signals: dict[str, Any],
    ) -> list[dict[str, Any]]:
        factors: list[dict[str, Any]] = []
        if gate_decision == "obvious_clear":
            factors.append(self._factor("gate_obvious_clear", 0.05))
        elif gate_decision == "obvious_escalate":
            factors.append(self._factor("gate_obvious_escalate", 0.05))
        elif gate_decision == "ambiguous":
            factors.append(self._factor("gate_ambiguous", -0.04))

        if recommendation == "escalate" and signals["hard_red_flag_count"] > 0:
            factors.append(self._factor("hard_red_flags_confirm_escalation", 0.10))
        return factors

    def _react_factors(self, stop_reason: str) -> list[dict[str, Any]]:
        if stop_reason == "critical_signal_found":
            return [self._factor("stop_critical_signal_found", 0.08)]
        if stop_reason == "completed":
            return [self._factor("stop_completed", 0.03)]
        if stop_reason == "insufficient_evidence":
            return [self._factor("stop_insufficient_evidence", -0.08)]
        if stop_reason in REACT_ERROR_STOPS:
            return [self._factor(f"stop_{stop_reason}", -0.12)]
        return []

    def _common_factors(
        self,
        recommendation: str,
        signals: dict[str, Any],
    ) -> list[dict[str, Any]]:
        factors: list[dict[str, Any]] = []
        baseline = signals["baseline_assessment"]
        if baseline == "consistent" and recommendation == "likely_false_positive":
            factors.append(self._factor("baseline_consistent_false_positive", 0.08))
        elif baseline == "strong_deviation" and recommendation in {"escalate", "investigate"}:
            factors.append(self._factor("baseline_strong_deviation", 0.06))
        elif baseline == "mild_deviation" and recommendation == "investigate":
            factors.append(self._factor("baseline_mild_deviation", 0.03))
        elif baseline == "insufficient_data":
            factors.append(self._factor("baseline_insufficient_data", -0.08))
        elif baseline == "not_observed":
            factors.append(self._factor("baseline_not_observed", -0.04))

        if signals["evidence_complete"]:
            factors.append(self._factor("evidence_complete", 0.04))
        else:
            factors.append(self._factor("evidence_incomplete", -0.07))

        missing_count = len(signals["missing_segments"])
        if missing_count:
            factors.append(
                self._factor("missing_data_segments", -min(0.06, 0.02 * missing_count))
            )

        warning_count = signals["warning_limitation_count"]
        if warning_count:
            factors.append(
                self._factor("warning_limitations", -min(0.09, 0.03 * warning_count))
            )
        info_count = signals["info_limitation_count"]
        if info_count:
            factors.append(self._factor("info_limitations", -min(0.03, 0.01 * info_count)))

        signal_count = signals["corroborating_typology_signal_count"]
        if recommendation == "escalate" and signal_count:
            factors.append(
                self._factor(
                    "corroborating_typology_signals",
                    min(0.10, 0.04 * signal_count),
                )
            )
        elif recommendation == "investigate" and signal_count:
            factors.append(
                self._factor(
                    "corroborating_typology_signals",
                    min(0.05, 0.02 * signal_count),
                )
            )
        elif recommendation == "likely_false_positive" and signal_count == 0:
            factors.append(self._factor("no_corroborating_typology_signals", 0.04))
        elif recommendation == "likely_false_positive" and signal_count:
            factors.append(
                self._factor(
                    "typology_signals_conflict_with_false_positive",
                    -min(0.10, 0.03 * signal_count),
                )
            )

        dismissed = signals["similar_dismissed_count"]
        escalated = signals["similar_escalated_count"]
        if dismissed > escalated and recommendation == "likely_false_positive":
            factors.append(self._factor("prior_similar_dismissals", 0.06))
        elif escalated > dismissed and recommendation in {"escalate", "investigate"}:
            factors.append(self._factor("prior_similar_escalations", 0.05))
        elif escalated > dismissed and recommendation == "likely_false_positive":
            factors.append(self._factor("prior_similar_escalations_conflict", -0.08))

        graph_red_flags = signals["graph_red_flags"]
        if graph_red_flags and recommendation in {"escalate", "investigate"}:
            factors.append(self._factor("graph_red_flags", 0.04))
        elif graph_red_flags and recommendation == "likely_false_positive":
            factors.append(self._factor("graph_red_flags_conflict", -0.10))
        if signals["graph_critical_flag_count"] and recommendation == "escalate":
            factors.append(self._factor("graph_critical_flags", 0.08))

        if signals["sanctions_match_count"] > 0 and recommendation == "escalate":
            factors.append(self._factor("sanctions_match_certainty", 0.10))
        if signals["pep_match_count"] > 0 and recommendation == "escalate":
            factors.append(self._factor("pep_match_certainty", 0.04))
        if signals["hard_red_flag_count"] and recommendation != "escalate":
            factors.append(self._factor("hard_red_flags_conflict", -0.12))
        return factors

    def _signals(
        self,
        observations: dict[str, ToolObservation],
        *,
        recommendation: str,
        reason_codes: list[str],
        gate_decision: str | None,
        stop_reason: str | None,
    ) -> dict[str, Any]:
        baseline_features = self._features(observations, "compute_behavioral_baseline")
        screening_features = self._features(observations, "screen_sanctions_pep")
        geography_features = self._features(observations, "run_geography_check")
        structuring_features = self._features(observations, "run_structuring_check")
        velocity_features = self._features(observations, "run_velocity_check")
        graph_features = self._features(observations, "trace_money_flow")
        graph_signals = graph_features.get("signals") or {}

        sanctions_count = int(screening_features.get("sanctions_match_count") or 0)
        pep_count = int(screening_features.get("pep_match_count") or 0)
        fatf_status = str(geography_features.get("fatf_status") or "").lower()
        country_risk_score = float(geography_features.get("country_risk_score") or 0)
        structuring_signal = bool(
            structuring_features.get("current_transaction_in_structuring_band")
        ) or int(structuring_features.get("structuring_band_count") or 0) >= 3
        velocity_signal = bool(velocity_features.get("velocity_threshold_met"))
        geography_signal = (
            bool(geography_features.get("is_sanctioned_country"))
            or fatf_status in {"blacklist", "greylist"}
            or country_risk_score >= 4
        )
        graph_red_flags = self._graph_red_flags(graph_signals)
        hard_red_flags = self._hard_red_flags(
            sanctions_count=sanctions_count,
            geography_features=geography_features,
            fatf_status=fatf_status,
            velocity_signal=velocity_signal,
            graph_signals=graph_signals,
        )

        observations_present = bool(observations)
        incomplete_tools = [
            name
            for name, observation in observations.items()
            if not observation.data_completeness.complete
        ]
        missing_segments = sorted(
            {
                str(segment)
                for observation in observations.values()
                for segment in observation.data_completeness.missing_segments
            }
        )
        limitations = [
            {
                "tool_name": tool_name,
                "code": limitation.code,
                "severity": limitation.severity,
            }
            for tool_name, observation in observations.items()
            for limitation in observation.limitations
        ]
        warning_limitations = [
            item for item in limitations if item["severity"] in {"warning", "high", "critical"}
        ]
        info_limitations = [
            item for item in limitations if item["severity"] not in {"warning", "high", "critical"}
        ]

        typology_signal_count = sum(
            1
            for present in (
                sanctions_count > 0 or pep_count > 0,
                geography_signal,
                structuring_signal,
                velocity_signal,
                bool(graph_red_flags),
            )
            if present
        )
        return {
            "recommendation": recommendation,
            "gate_decision": gate_decision,
            "stop_reason": stop_reason,
            "reason_codes": list(reason_codes),
            "baseline_assessment": str(
                baseline_features.get("baseline_assessment") or "not_observed"
            ),
            "similar_dismissed_count": int(
                baseline_features.get("similar_dismissed_count") or 0
            ),
            "similar_escalated_count": int(
                baseline_features.get("similar_escalated_count") or 0
            ),
            "evidence_complete": observations_present and not incomplete_tools,
            "incomplete_tools": incomplete_tools,
            "missing_segments": missing_segments,
            "limitations": limitations,
            "warning_limitation_count": len(warning_limitations),
            "info_limitation_count": len(info_limitations),
            "sanctions_match_count": sanctions_count,
            "pep_match_count": pep_count,
            "sanctions_pep_certainty": self._screening_certainty(
                observations,
                sanctions_count,
                pep_count,
            ),
            "structuring_signal": structuring_signal,
            "velocity_threshold_met": velocity_signal,
            "geography_signal": geography_signal,
            "fatf_status": fatf_status or None,
            "graph_red_flags": graph_red_flags,
            "graph_critical_flag_count": self._graph_critical_flag_count(graph_signals),
            "hard_red_flags": hard_red_flags,
            "hard_red_flag_count": len(hard_red_flags),
            "corroborating_typology_signal_count": typology_signal_count,
        }

    def _features(
        self,
        observations: dict[str, ToolObservation],
        tool_name: str,
    ) -> dict[str, Any]:
        observation = observations.get(tool_name)
        return observation.computed_features if observation else {}

    def _hard_red_flags(
        self,
        *,
        sanctions_count: int,
        geography_features: dict[str, Any],
        fatf_status: str,
        velocity_signal: bool,
        graph_signals: dict[str, Any],
    ) -> list[str]:
        flags: list[str] = []
        if sanctions_count > 0:
            flags.append("sanctions_match")
        if bool(geography_features.get("is_sanctioned_country")):
            flags.append("sanctioned_country")
        if fatf_status == "blacklist":
            flags.append("fatf_blacklist")
        if velocity_signal:
            flags.append("velocity_threshold_met")
        if bool(graph_signals.get("high_risk_endpoint")):
            flags.append("graph_high_risk_endpoint")
        if int(graph_signals.get("linked_open_case_count") or 0) > 0:
            flags.append("graph_linked_open_case")
        return flags

    def _graph_red_flags(self, graph_signals: dict[str, Any]) -> list[str]:
        flags = [
            name
            for name in (
                "rapid_pass_through",
                "cycle_detected",
                "fan_out",
                "many_to_one",
                "high_risk_endpoint",
            )
            if bool(graph_signals.get(name))
        ]
        if int(graph_signals.get("linked_alert_count") or 0) > 0:
            flags.append("linked_alert_count")
        if int(graph_signals.get("linked_open_case_count") or 0) > 0:
            flags.append("linked_open_case_count")
        return flags

    def _graph_critical_flag_count(self, graph_signals: dict[str, Any]) -> int:
        count = 0
        if bool(graph_signals.get("high_risk_endpoint")):
            count += 1
        if int(graph_signals.get("linked_open_case_count") or 0) > 0:
            count += 1
        return count

    def _screening_certainty(
        self,
        observations: dict[str, ToolObservation],
        sanctions_count: int,
        pep_count: int,
    ) -> str:
        if sanctions_count > 0:
            return "sanctions_match"
        if pep_count > 0:
            return "pep_match"
        if "screen_sanctions_pep" in observations:
            return "no_match_observed"
        return "not_observed"

    def _factor(self, name: str, adjustment: float) -> dict[str, Any]:
        return {
            "name": name,
            "adjustment": round(adjustment, 2),
        }
