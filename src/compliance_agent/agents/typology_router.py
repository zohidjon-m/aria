from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .phase1_tools import build_phase1_tool_registry
from .tooling import ToolRegistry


CORE_TOOL_NAMES = (
    "get_alert_context",
    "get_customer_profile",
    "get_recent_transactions",
    "get_prior_alerts",
    "get_open_cases",
    "compute_behavioral_baseline",
)

TYPOLOGY_TOOL_GROUPS = {
    "structuring": ("run_structuring_check",),
    "velocity": ("run_velocity_check",),
    "geography": ("run_geography_check",),
    "sanctions": ("screen_sanctions_pep",),
    "graph": ("trace_money_flow",),
}

TYPOLOGY_ORDER = (
    "structuring",
    "velocity",
    "geography",
    "sanctions",
    "graph",
)


@dataclass(frozen=True)
class TypologyRouteResult:
    activated: list[str]
    skipped: list[str]
    reasons: dict[str, str]
    allowed_tools: list[str]
    registry: ToolRegistry

    def to_details(self) -> dict[str, Any]:
        return {
            "activated": list(self.activated),
            "skipped": list(self.skipped),
            "reasons": dict(self.reasons),
            "allowed_tools": list(self.allowed_tools),
        }


class TypologyRouter:
    """Deterministically narrows planner-facing typology tools for one run."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or build_phase1_tool_registry()

    def route(
        self,
        alert_context: dict[str, Any],
        *,
        baseline_features: dict[str, Any] | None = None,
        pre_screen_signals: dict[str, Any] | None = None,
    ) -> TypologyRouteResult:
        baseline = baseline_features or {}
        signals = pre_screen_signals or {}
        decisions = {
            "structuring": self._structuring(alert_context, signals),
            "velocity": self._velocity(alert_context, baseline, signals),
            "geography": self._geography(alert_context, baseline, signals),
            "sanctions": self._sanctions(alert_context, signals),
            "graph": self._graph(alert_context, baseline, signals),
        }

        activated = [
            typology for typology in TYPOLOGY_ORDER if decisions[typology][0]
        ]
        skipped = [
            typology for typology in TYPOLOGY_ORDER if not decisions[typology][0]
        ]
        reasons = {
            typology: decisions[typology][1]
            for typology in TYPOLOGY_ORDER
        }
        allowed_tool_set = set(CORE_TOOL_NAMES)
        for typology in activated:
            allowed_tool_set.update(TYPOLOGY_TOOL_GROUPS[typology])
        routed_registry = self.registry.subset(allowed_tool_set)
        allowed_tools = [
            name for name in self.registry.names if name in routed_registry.names
        ]

        return TypologyRouteResult(
            activated=activated,
            skipped=skipped,
            reasons=reasons,
            allowed_tools=sorted(allowed_tools),
            registry=routed_registry,
        )

    def _geography(
        self,
        alert_context: dict[str, Any],
        baseline: dict[str, Any],
        signals: dict[str, Any],
    ) -> tuple[bool, str]:
        transaction = alert_context.get("transaction") or {}
        destination = transaction.get("destination_country")
        if destination:
            return True, f"Transaction has destination country {destination}."
        if self._rule_mentions(alert_context, "geography", "country", "destination"):
            return True, "Alert rule is geography-related."
        if bool(baseline.get("new_destination_country")):
            return True, "Baseline marks a new destination country."
        geography_signals = signals.get("geography") or {}
        if bool(geography_signals.get("has_destination_country")):
            return True, "Pre-screen geography facts include a destination country."
        return (
            False,
            "No destination country, geography rule, or new-country baseline signal is present.",
        )

    def _structuring(
        self,
        alert_context: dict[str, Any],
        signals: dict[str, Any],
    ) -> tuple[bool, str]:
        if self._rule_mentions(alert_context, "structuring"):
            return True, "Alert rule is structuring-related."

        transaction = alert_context.get("transaction") or {}
        amount = float(transaction.get("amount_usd") or 0)
        transaction_type = str(transaction.get("transaction_type") or "").lower()
        if transaction_type == "cash" and 9000 <= amount <= 9999:
            return True, "Current cash transaction is in the 9000-9999 USD band."

        structuring_signals = signals.get("structuring") or {}
        if bool(structuring_signals.get("current_transaction_in_structuring_band")):
            return True, "Pre-screen structuring facts mark the current transaction in band."
        if int(structuring_signals.get("structuring_band_count") or 0) > 0:
            return True, "Pre-screen structuring facts show band activity."
        return False, "No structuring rule or cash-band activity is present."

    def _velocity(
        self,
        alert_context: dict[str, Any],
        baseline: dict[str, Any],
        signals: dict[str, Any],
    ) -> tuple[bool, str]:
        if self._rule_mentions(alert_context, "velocity"):
            return True, "Alert rule is velocity-related."

        velocity_signals = signals.get("velocity") or {}
        if bool(velocity_signals.get("velocity_threshold_met")):
            return True, "Pre-screen velocity threshold is met."
        max_same_day = int(velocity_signals.get("max_same_day_transaction_count") or 0)
        if max_same_day >= 10:
            return True, "Pre-screen same-day transaction count meets velocity threshold."
        if int(baseline.get("same_day_transaction_count") or 0) >= 10:
            return True, "Baseline same-day transaction count meets velocity threshold."
        return False, "No velocity rule or same-day burst signal is present."

    def _sanctions(
        self,
        alert_context: dict[str, Any],
        signals: dict[str, Any],
    ) -> tuple[bool, str]:
        if self._rule_mentions(alert_context, "sanctions", "sanction", "pep", "screening"):
            return True, "Alert rule is screening-related."

        sanctions_matches = alert_context.get("sanctions_matches") or []
        pep_matches = alert_context.get("pep_matches") or []
        if sanctions_matches:
            return True, "Alert context includes sanctions screening matches."
        if pep_matches:
            return True, "Alert context includes PEP screening matches."

        sanctions_signals = signals.get("sanctions") or {}
        if int(sanctions_signals.get("sanctions_match_count") or 0) > 0:
            return True, "Pre-screen facts include sanctions screening matches."
        if int(sanctions_signals.get("pep_match_count") or 0) > 0:
            return True, "Pre-screen facts include PEP screening matches."
        return False, "No screening rule, sanctions match, or PEP match is present."

    def _graph(
        self,
        alert_context: dict[str, Any],
        baseline: dict[str, Any],
        signals: dict[str, Any],
    ) -> tuple[bool, str]:
        transaction = alert_context.get("transaction") or {}
        if transaction.get("counterparty_account_id") is not None:
            return True, "Transaction has an immediate counterparty account."
        if bool(baseline.get("new_counterparty")):
            return True, "Baseline marks a new counterparty."
        graph_signals = signals.get("graph") or {}
        if bool(graph_signals.get("has_immediate_counterparty")):
            return True, "Pre-screen graph facts include an immediate counterparty."
        return False, "No immediate counterparty or new-counterparty signal is present."

    def _rule_mentions(self, alert_context: dict[str, Any], *needles: str) -> bool:
        rule = alert_context.get("rule") or {}
        rule_text = " ".join(
            str(rule.get(field) or "")
            for field in ("rule_type", "rule_name")
        ).lower()
        return any(needle in rule_text for needle in needles)
