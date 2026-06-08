from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .utils import utc_now


@dataclass(frozen=True)
class SourceRef:
    table: str
    key: str
    columns: tuple[str, ...] = ()


@dataclass
class EvidenceItem:
    evidence_id: str
    source_ref: SourceRef
    payload: dict[str, Any]
    retrieved_at: str = field(default_factory=utc_now)


@dataclass
class Claim:
    statement: str
    source_refs: list[SourceRef]


@dataclass
class ValidationFinding:
    claim: str
    issue: str
    severity: str = "high"


@dataclass
class ValidationReport:
    validation_id: str
    status: str
    findings: list[ValidationFinding]
    checked_at: str = field(default_factory=utc_now)

    @property
    def unsupported_count(self) -> int:
        return len(self.findings)


@dataclass
class AgentResult:
    agent_name: str
    subject_type: str
    subject_id: int | str
    recommendation: str
    confidence: float
    score: float
    reasoning: list[str]
    claims: list[Claim]
    evidence: list[EvidenceItem]
    details: dict[str, Any] = field(default_factory=dict)
