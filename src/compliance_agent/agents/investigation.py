from __future__ import annotations

from typing import Any

from ..domain import AgentResult, Claim, SourceRef
from ..utils import clamp, new_id
from .common import collect_evidence
from .typologies import TypologyEngine


class InvestigationAgent:
    """Hypothesis-oriented investigation pass for non-clearable alerts."""

    def __init__(self, typology_engine: TypologyEngine | None = None) -> None:
        self.typology_engine = typology_engine or TypologyEngine()

    def run(self, context: dict[str, Any]) -> AgentResult:
        alert = context["alert"]
        customer = context["customer"]
        evidence = collect_evidence(context)
        signals = self.typology_engine.evaluate(context)

        score = clamp(sum(signal.score for signal in signals))
        if score >= 60:
            recommendation = "open_case"
        elif score >= 25:
            recommendation = "continue_investigation"
        else:
            recommendation = "return_to_triage"

        reasoning = [
            f"Activated {len(signals)} relevant typology sub-agent(s).",
            *[signal.rationale for signal in signals],
        ]
        claims = [
            Claim(
                statement=f"Investigation is linked to alert {alert['alert_id']}.",
                source_refs=[SourceRef("alerts", str(alert["alert_id"]))],
            ),
            Claim(
                statement=f"Investigation subject is customer {customer['customer_id']}.",
                source_refs=[SourceRef("customers", str(customer["customer_id"]))],
            ),
        ]
        for signal in signals:
            claims.append(Claim(statement=signal.rationale, source_refs=signal.source_refs))

        return AgentResult(
            agent_name="investigation_agent",
            subject_type="alert",
            subject_id=alert["alert_id"],
            recommendation=recommendation,
            confidence=0.78 if signals else 0.55,
            score=score,
            reasoning=reasoning,
            claims=claims,
            evidence=evidence,
            details={
                "investigation_id": new_id("inv"),
                "customer_id": customer["customer_id"],
                "activated_typologies": [signal.typology for signal in signals],
                "human_required": True,
            },
        )
