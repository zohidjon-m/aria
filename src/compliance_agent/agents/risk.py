from __future__ import annotations

from typing import Any

from ..domain import AgentResult, Claim, ReasoningItem, SourceRef
from ..utils import clamp, new_id
from .common import collect_evidence


BASE_RISK = {
    "low": 10,
    "medium": 30,
    "high": 55,
    "critical": 75,
}


class RiskScoringAgent:
    def run(self, context: dict[str, Any]) -> AgentResult:
        customer = context["customer"]
        pattern = context.get("latest_pattern") or context.get("pattern") or {}
        open_alerts = context.get("open_alerts") or []
        prior_alerts = context.get("prior_alerts") or []
        sanctions_matches = context.get("sanctions_matches") or []
        pep_matches = context.get("pep_matches") or []
        evidence = collect_evidence(context)

        score = float(BASE_RISK.get(str(customer.get("risk_level")).lower(), 25))
        customer_ref = SourceRef("customers", str(customer["customer_id"]))
        reasoning = [
            ReasoningItem(
                statement=f"Base customer risk level is {customer.get('risk_level')}.",
                source_refs=[customer_ref],
            )
        ]

        kyc_status = str(customer.get("kyc_status") or "").lower()
        if kyc_status in {"expired", "rejected"}:
            score += 20
            reasoning.append(
                ReasoningItem(
                    statement=f"KYC status is {kyc_status}.",
                    source_refs=[customer_ref],
                )
            )
        elif kyc_status == "pending":
            score += 8
            reasoning.append(
                ReasoningItem(
                    statement="KYC status is pending.",
                    source_refs=[customer_ref],
                )
            )

        critical_alerts = [
            alert for alert in prior_alerts + open_alerts
            if str(alert.get("severity")).lower() == "critical"
        ]
        if open_alerts:
            score += min(20, len(open_alerts) * 5)
            reasoning.append(
                ReasoningItem(
                    statement=f"{len(open_alerts)} open alert(s) are active.",
                    source_refs=self._alert_refs(open_alerts),
                )
            )
        if critical_alerts:
            score += min(20, len(critical_alerts) * 10)
            reasoning.append(
                ReasoningItem(
                    statement=f"{len(critical_alerts)} critical alert(s) are present.",
                    source_refs=self._alert_refs(critical_alerts),
                )
            )

        if pattern:
            international_pct = float(pattern.get("international_pct") or 0)
            cash_pct = float(pattern.get("cash_pct") or 0)
            if international_pct >= 50:
                score += 8
                reasoning.append(
                    ReasoningItem(
                        statement="International transfer share is elevated.",
                        source_refs=[
                            SourceRef("transaction_patterns", str(pattern["pattern_id"]))
                        ],
                    )
                )
            if cash_pct >= 30:
                score += 8
                reasoning.append(
                    ReasoningItem(
                        statement="Cash transaction share is elevated.",
                        source_refs=[
                            SourceRef("transaction_patterns", str(pattern["pattern_id"]))
                        ],
                    )
                )

        if sanctions_matches:
            score += 35
            reasoning.append(
                ReasoningItem(
                    statement="Active sanctions screening match is present.",
                    source_refs=[
                        SourceRef("sanctions_list", str(match["sanction_id"]))
                        for match in sanctions_matches
                        if match.get("sanction_id") is not None
                    ],
                )
            )
        if pep_matches:
            score += 10
            reasoning.append(
                ReasoningItem(
                    statement="Active PEP screening match is present.",
                    source_refs=[
                        SourceRef("pep_list", str(match["pep_id"]))
                        for match in pep_matches
                        if match.get("pep_id") is not None
                    ],
                )
            )

        score = round(clamp(score), 2)
        level = self._level(score)
        claims = self._claims(customer, pattern, open_alerts, prior_alerts)

        return AgentResult(
            agent_name="risk_scoring_agent",
            subject_type="customer",
            subject_id=customer["customer_id"],
            recommendation="record_risk_score_for_human_review",
            confidence=0.82 if evidence else 0.5,
            score=score,
            reasoning=reasoning,
            claims=claims,
            evidence=evidence,
            details={
                "risk_score_id": new_id("risk"),
                "level": level,
                "human_required": True,
            },
        )

    def _level(self, score: float) -> str:
        if score < 25:
            return "low"
        if score < 50:
            return "medium"
        if score < 75:
            return "high"
        return "critical"

    def _alert_refs(self, alerts: list[dict[str, Any]]) -> list[SourceRef]:
        return [
            SourceRef("alerts", str(alert["alert_id"]))
            for alert in alerts[:5]
            if alert.get("alert_id") is not None
        ]

    def _claims(
        self,
        customer: dict[str, Any],
        pattern: dict[str, Any],
        open_alerts: list[dict[str, Any]],
        prior_alerts: list[dict[str, Any]],
    ) -> list[Claim]:
        claims = [
            Claim(
                statement=f"Customer {customer['customer_id']} has risk level {customer.get('risk_level')}.",
                source_refs=[SourceRef("customers", str(customer["customer_id"]))],
            )
        ]
        if pattern:
            claims.append(
                Claim(
                    statement=(
                        "Customer transaction pattern includes international_pct "
                        f"{pattern.get('international_pct')} and cash_pct {pattern.get('cash_pct')}."
                    ),
                    source_refs=[SourceRef("transaction_patterns", str(pattern["pattern_id"]))],
                )
            )
        for alert in open_alerts[:5] + prior_alerts[:5]:
            claims.append(
                Claim(
                    statement=f"Alert {alert['alert_id']} has severity {alert.get('severity')}.",
                    source_refs=[SourceRef("alerts", str(alert["alert_id"]))],
                )
            )
        return claims
