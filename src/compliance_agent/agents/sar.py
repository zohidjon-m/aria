from __future__ import annotations

from typing import Any

from ..domain import AgentResult, Claim, SourceRef
from ..utils import new_id
from .common import collect_evidence


class SARDraftingAgent:
    def run(self, context: dict[str, Any]) -> AgentResult:
        case = context["case"]
        customer = context["customer"]
        linked_alerts = context.get("linked_alerts") or []
        transactions = context.get("transactions") or []
        evidence = collect_evidence(context)
        narrative = self._draft_narrative(case, customer, linked_alerts, transactions)

        claims = [
            Claim(
                statement=f"Case {case['case_id']} belongs to customer {customer['customer_id']}.",
                source_refs=[
                    SourceRef("cases", str(case["case_id"])),
                    SourceRef("customers", str(customer["customer_id"])),
                ],
            ),
            Claim(
                statement=f"Case {case['case_id']} has {len(linked_alerts)} linked alert(s).",
                source_refs=[SourceRef("cases", str(case["case_id"]))],
            ),
        ]
        for alert in linked_alerts[:10]:
            claims.append(
                Claim(
                    statement=f"Linked alert {alert['alert_id']} has severity {alert.get('severity')}.",
                    source_refs=[SourceRef("alerts", str(alert["alert_id"]))],
                )
            )
        for tx in transactions[:20]:
            claims.append(
                Claim(
                    statement=(
                        f"Transaction {tx['transaction_id']} amount_usd is "
                        f"{tx.get('amount_usd')}."
                    ),
                    source_refs=[SourceRef("transactions", str(tx["transaction_id"]))],
                )
            )

        return AgentResult(
            agent_name="sar_drafting_agent",
            subject_type="case",
            subject_id=case["case_id"],
            recommendation="draft_for_human_review",
            confidence=0.8 if evidence else 0.45,
            score=0,
            reasoning=[
                "SAR narrative is drafted from linked case, alert, and transaction facts.",
                "Draft is not a regulatory submission and requires officer approval.",
            ],
            claims=claims,
            evidence=evidence,
            details={
                "sar_draft_id": new_id("sar"),
                "narrative": narrative,
                "human_required": True,
            },
        )

    def _draft_narrative(
        self,
        case: dict[str, Any],
        customer: dict[str, Any],
        linked_alerts: list[dict[str, Any]],
        transactions: list[dict[str, Any]],
    ) -> str:
        total_amount = sum(float(tx.get("amount_usd") or 0) for tx in transactions)
        countries = sorted(
            {
                str(tx.get("destination_country"))
                for tx in transactions
                if tx.get("destination_country")
            }
        )
        transaction_lines = []
        for tx in transactions[:10]:
            transaction_lines.append(
                "- Transaction {id}: type={typ}, amount_usd={amount}, "
                "destination={dest}, created_at={created}".format(
                    id=tx.get("transaction_id"),
                    typ=tx.get("transaction_type"),
                    amount=tx.get("amount_usd"),
                    dest=tx.get("destination_country") or "N/A",
                    created=tx.get("created_at"),
                )
            )

        return "\n".join(
            [
                "DRAFT SAR NARRATIVE - HUMAN REVIEW REQUIRED",
                "",
                f"Case {case.get('case_id')} concerns customer {customer.get('customer_id')} "
                f"({customer.get('full_name')}). The case type is {case.get('case_type')} "
                f"with priority {case.get('priority')} and status {case.get('status')}.",
                "",
                f"The case includes {len(linked_alerts)} linked alert(s) and "
                f"{len(transactions)} transaction(s). The total transaction amount in the "
                f"case evidence is USD {total_amount:,.2f}.",
                "",
                "Destination countries observed: "
                + (", ".join(countries) if countries else "none recorded"),
                "",
                "Transactions reviewed:",
                *transaction_lines,
                "",
                "This draft is generated for compliance officer review only. The officer "
                "must verify the facts, complete jurisdiction-specific fields, and approve "
                "or reject the filing decision.",
            ]
        )
