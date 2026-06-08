from __future__ import annotations

from typing import Any

from ..domain import AgentResult, Claim, ReasoningItem, SourceRef
from ..utils import clamp, new_id
from .common import collect_evidence
from .typologies import TypologyEngine


SEVERITY_POINTS = {
    "low": 5,
    "medium": 12,
    "high": 24,
    "critical": 40,
}


class TriageAgent:
    def __init__(self, typology_engine: TypologyEngine | None = None) -> None:
        self.typology_engine = typology_engine or TypologyEngine()

    def run(self, context: dict[str, Any]) -> AgentResult:
        alert = context["alert"]
        transaction = context["transaction"]
        customer = context["customer"]
        rule = context.get("rule") or {}
        pattern = context.get("pattern") or {}
        prior_alerts = context.get("prior_alerts") or []
        evidence = collect_evidence(context)
        signals = self.typology_engine.evaluate(context)

        severity = str(alert.get("severity") or rule.get("severity") or "medium").lower()
        score = SEVERITY_POINTS.get(severity, 12)
        reasoning = [
            ReasoningItem(
                statement=f"Alert severity contributes {score} points.",
                source_refs=self._non_empty_refs(
                    [
                        SourceRef("alerts", str(alert["alert_id"])),
                        self._optional_rule_ref(rule),
                    ]
                ),
            )
        ]

        amount = float(transaction.get("amount_usd") or 0)
        avg_amount = float(pattern.get("avg_transaction") or 0)
        if avg_amount > 0:
            ratio = amount / avg_amount
            if ratio >= 5:
                score += 20
                reasoning.append(
                    ReasoningItem(
                        statement=(
                            f"Transaction amount is {ratio:.1f}x the customer's average."
                        ),
                        source_refs=[
                            SourceRef("transactions", str(transaction["transaction_id"])),
                            SourceRef("transaction_patterns", str(pattern["pattern_id"])),
                        ],
                    )
                )
            elif ratio >= 2:
                score += 10
                reasoning.append(
                    ReasoningItem(
                        statement=(
                            f"Transaction amount is {ratio:.1f}x the customer's average."
                        ),
                        source_refs=[
                            SourceRef("transactions", str(transaction["transaction_id"])),
                            SourceRef("transaction_patterns", str(pattern["pattern_id"])),
                        ],
                    )
                )
            else:
                reasoning.append(
                    ReasoningItem(
                        statement="Transaction amount is close to the customer's baseline.",
                        source_refs=[
                            SourceRef("transactions", str(transaction["transaction_id"])),
                            SourceRef("transaction_patterns", str(pattern["pattern_id"])),
                        ],
                    )
                )

        for signal in signals:
            score += signal.score
            reasoning.append(
                ReasoningItem(
                    statement=f"{signal.typology}: {signal.rationale}",
                    source_refs=signal.source_refs,
                )
            )

        if len(prior_alerts) >= 3:
            score += 12
            reasoning.append(
                ReasoningItem(
                    statement=f"Customer has {len(prior_alerts)} prior alerts.",
                    source_refs=[
                        SourceRef("alerts", str(alert["alert_id"]))
                        for alert in prior_alerts
                        if alert.get("alert_id") is not None
                    ][:5],
                )
            )
        elif prior_alerts:
            score += 5
            reasoning.append(
                ReasoningItem(
                    statement=f"Customer has {len(prior_alerts)} prior alert(s).",
                    source_refs=[
                        SourceRef("alerts", str(alert["alert_id"]))
                        for alert in prior_alerts
                        if alert.get("alert_id") is not None
                    ][:5],
                )
            )

        score = clamp(score)
        recommendation = self._recommend(score, severity, signals)
        confidence = self._confidence(score, evidence_count=len(evidence))
        claims = self._claims(context, signals)

        return AgentResult(
            agent_name="triage_agent",
            subject_type="alert",
            subject_id=alert["alert_id"],
            recommendation=recommendation,
            confidence=confidence,
            score=score,
            reasoning=reasoning,
            claims=claims,
            evidence=evidence,
            details={
                "recommendation_id": new_id("rec"),
                "customer_id": customer.get("customer_id"),
                "activated_typologies": [signal.typology for signal in signals],
                "human_required": True,
            },
        )

    def _recommend(self, score: float, severity: str, signals: list[Any]) -> str:
        critical_typologies = {
            signal.typology
            for signal in signals
            if signal.severity == "critical"
        }
        if severity == "critical" or critical_typologies or score >= 70:
            return "escalate"
        if score >= 35:
            return "investigate"
        return "likely_false_positive"

    def _confidence(self, score: float, evidence_count: int) -> float:
        evidence_factor = min(0.15, evidence_count / 100)
        score_factor = min(0.7, abs(score - 35) / 100 + abs(score - 70) / 200)
        return round(clamp(0.55 + evidence_factor + score_factor, 0, 0.95), 2)

    def _optional_rule_ref(self, rule: dict[str, Any]) -> SourceRef | None:
        if not rule or rule.get("rule_id") is None:
            return None
        return SourceRef("compliance_rules", str(rule["rule_id"]))

    def _non_empty_refs(self, refs: list[SourceRef | None]) -> list[SourceRef]:
        return [ref for ref in refs if ref is not None]

    def _claims(self, context: dict[str, Any], signals: list[Any]) -> list[Claim]:
        alert = context["alert"]
        rule = context.get("rule") or {}
        transaction = context["transaction"]
        customer = context["customer"]
        pattern = context.get("pattern") or {}
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
                    f"Customer {customer['customer_id']} is the owner of account "
                    f"{context['account']['account_id']}."
                ),
                source_refs=[
                    SourceRef("customers", str(customer["customer_id"])),
                    SourceRef("accounts", str(context["account"]["account_id"])),
                ],
            ),
        ]
        if rule:
            claims.append(
                Claim(
                    statement=(
                        f"Alert rule is {rule.get('rule_name', 'unknown')} "
                        f"with severity {rule.get('severity', alert.get('severity'))}."
                    ),
                    source_refs=[
                        SourceRef("alerts", str(alert["alert_id"])),
                        SourceRef("compliance_rules", str(rule["rule_id"])),
                    ],
                )
            )
        if pattern:
            claims.append(
                Claim(
                    statement=(
                        "Customer baseline contains average transaction "
                        f"{pattern.get('avg_transaction')}."
                    ),
                    source_refs=[SourceRef("transaction_patterns", str(pattern["pattern_id"]))],
                )
            )
        for signal in signals:
            claims.append(
                Claim(
                    statement=signal.rationale,
                    source_refs=signal.source_refs,
                )
            )
        return claims
