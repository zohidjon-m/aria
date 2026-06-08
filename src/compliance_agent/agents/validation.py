from __future__ import annotations

from ..domain import AgentResult, SourceRef, ValidationFinding, ValidationReport
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
            if not claim.source_refs:
                findings.append(
                    ValidationFinding(
                        claim=claim.statement,
                        issue="Claim has no source references.",
                    )
                )
                continue

            for source_ref in claim.source_refs:
                if not self._has_source_ref(source_ref, available_refs):
                    findings.append(
                        ValidationFinding(
                            claim=claim.statement,
                            issue=(
                                f"Missing evidence for {source_ref.table}"
                                f":{source_ref.key}."
                            ),
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
