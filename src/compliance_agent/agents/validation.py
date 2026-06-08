from __future__ import annotations

from ..domain import AgentResult, ReasoningItem, SourceRef, ValidationFinding, ValidationReport
from ..utils import new_id


class ComplianceValidationAgent:
    """Checks that every factual claim points to source evidence."""

    def validate(self, result: AgentResult) -> ValidationReport:
        available_refs = {
            (item.source_ref.table, item.source_ref.key)
            for item in result.evidence
        }
        findings: list[ValidationFinding] = []

        for claim in result.claims:
            findings.extend(
                self._validate_statement(
                    statement=claim.statement,
                    source_refs=claim.source_refs,
                    available_refs=available_refs,
                    kind="claim",
                )
            )

        for reasoning in result.reasoning:
            if not isinstance(reasoning, ReasoningItem):
                findings.append(
                    ValidationFinding(
                        claim=str(reasoning),
                        issue="Reasoning item is not structured.",
                        kind="reasoning",
                    )
                )
                continue
            findings.extend(
                self._validate_statement(
                    statement=reasoning.statement,
                    source_refs=reasoning.source_refs,
                    available_refs=available_refs,
                    kind="reasoning",
                )
            )

        status = "passed" if not findings else "failed"
        return ValidationReport(
            validation_id=new_id("validation"),
            status=status,
            findings=findings,
        )

    def _has_source_ref(
        self,
        source_ref: SourceRef,
        available_refs: set[tuple[str, str]],
    ) -> bool:
        return (source_ref.table, source_ref.key) in available_refs

    def _validate_statement(
        self,
        *,
        statement: str,
        source_refs: list[SourceRef],
        available_refs: set[tuple[str, str]],
        kind: str,
    ) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        if not source_refs:
            findings.append(
                ValidationFinding(
                    claim=statement,
                    issue=f"{kind.title()} has no source references.",
                    kind=kind,
                )
            )
            return findings

        for source_ref in source_refs:
            if not self._has_source_ref(source_ref, available_refs):
                findings.append(
                    ValidationFinding(
                        claim=statement,
                        issue=(
                            f"Missing evidence for {source_ref.table}"
                            f":{source_ref.key}."
                        ),
                        kind=kind,
                    )
                )
        return findings
