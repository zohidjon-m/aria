from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..domain import SourceRef
from ..utils import parse_datetime


@dataclass
class TypologySignal:
    typology: str
    score: float
    severity: str
    rationale: str
    source_refs: list[SourceRef]


class TypologyEngine:
    def evaluate(self, context: dict[str, Any]) -> list[TypologySignal]:
        signals = [
            self._geography(context),
            self._structuring(context),
            self._velocity(context),
            self._sanctions(context),
        ]
        return [signal for signal in signals if signal is not None and signal.score > 0]

    def _geography(self, context: dict[str, Any]) -> TypologySignal | None:
        transaction = context.get("transaction") or {}
        country = context.get("destination_country") or {}
        destination = transaction.get("destination_country")
        if not destination:
            return None

        refs = [SourceRef("transactions", str(transaction["transaction_id"]))]
        if country.get("country_code"):
            refs.append(SourceRef("countries", str(country["country_code"])))

        fatf_status = str(country.get("fatf_status") or "").lower()
        is_sanctioned = bool(country.get("is_sanctioned"))
        risk_score = float(country.get("risk_score") or 0)

        if is_sanctioned or fatf_status == "blacklist":
            return TypologySignal(
                typology="geography",
                score=40,
                severity="critical",
                rationale=f"Destination country {destination} is sanctioned or blacklisted.",
                source_refs=refs,
            )
        if fatf_status == "greylist" or risk_score >= 4:
            return TypologySignal(
                typology="geography",
                score=20,
                severity="high",
                rationale=f"Destination country {destination} has elevated country risk.",
                source_refs=refs,
            )
        return TypologySignal(
            typology="geography",
            score=4,
            severity="low",
            rationale=f"Destination country {destination} is present but not elevated.",
            source_refs=refs,
        )

    def _structuring(self, context: dict[str, Any]) -> TypologySignal | None:
        transaction = context.get("transaction") or {}
        recent = context.get("recent_transactions") or []
        tx_date = parse_datetime(transaction.get("created_at"))
        current_ref = SourceRef("transactions", str(transaction.get("transaction_id")))
        if not tx_date:
            return None

        same_day_candidates = []
        for tx in recent:
            amount = float(tx.get("amount_usd") or 0)
            created_at = parse_datetime(tx.get("created_at"))
            if created_at and created_at.date() == tx_date.date() and 9000 <= amount <= 9999:
                same_day_candidates.append(tx)

        if len(same_day_candidates) >= 3:
            refs = [
                SourceRef("transactions", str(tx["transaction_id"]))
                for tx in same_day_candidates
                if tx.get("transaction_id") is not None
            ]
            return TypologySignal(
                typology="structuring",
                score=35,
                severity="critical",
                rationale=(
                    f"{len(same_day_candidates)} same-day transactions fall in the "
                    "9000-9999 USD structuring band."
                ),
                source_refs=refs,
            )

        amount = float(transaction.get("amount_usd") or 0)
        if 9000 <= amount <= 9999:
            return TypologySignal(
                typology="structuring",
                score=12,
                severity="medium",
                rationale="Current transaction falls in the 9000-9999 USD structuring band.",
                source_refs=[current_ref],
            )
        return None

    def _velocity(self, context: dict[str, Any]) -> TypologySignal | None:
        transaction = context.get("transaction") or {}
        recent = context.get("recent_transactions") or []
        tx_date = parse_datetime(transaction.get("created_at"))
        if not tx_date:
            return None

        same_day = []
        for tx in recent:
            created_at = parse_datetime(tx.get("created_at"))
            if created_at and created_at.date() == tx_date.date():
                same_day.append(tx)

        if len(same_day) >= 10:
            refs = [
                SourceRef("transactions", str(tx["transaction_id"]))
                for tx in same_day
                if tx.get("transaction_id") is not None
            ]
            return TypologySignal(
                typology="velocity",
                score=25,
                severity="high",
                rationale=f"{len(same_day)} transactions occurred on the same day.",
                source_refs=refs,
            )
        return None

    def _sanctions(self, context: dict[str, Any]) -> TypologySignal | None:
        sanctions_matches = context.get("sanctions_matches") or []
        pep_matches = context.get("pep_matches") or []
        if sanctions_matches:
            refs = [
                SourceRef("sanctions_list", str(match["sanction_id"]))
                for match in sanctions_matches
                if match.get("sanction_id") is not None
            ]
            return TypologySignal(
                typology="sanctions",
                score=50,
                severity="critical",
                rationale=f"{len(sanctions_matches)} active sanctions screening match(es).",
                source_refs=refs,
            )
        if pep_matches:
            refs = [
                SourceRef("pep_list", str(match["pep_id"]))
                for match in pep_matches
                if match.get("pep_id") is not None
            ]
            return TypologySignal(
                typology="pep",
                score=10,
                severity="medium",
                rationale=f"{len(pep_matches)} active PEP screening match(es).",
                source_refs=refs,
            )
        return None
