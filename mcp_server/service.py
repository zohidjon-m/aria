from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from compliance_agent.contracts.phase1 import (
    DataCompleteness,
    MCPRequestEnvelope,
    MCPResponseEnvelope,
    MCPSourceRef,
    PolicyDecision,
)

from .repository import ReferenceRepository


FORBIDDEN_TOOL_ARG_FIELDS = {
    "alert_id",
    "case_id",
    "customer_id",
    "account_id",
    "transaction_id",
}


class ReferenceMCPTools:
    """Reference AML MCP tools with scope, bounds, source refs, and audit output."""

    def __init__(self, repository: ReferenceRepository) -> None:
        self.repository = repository

    def get_customer_profile(self, request: dict[str, Any]) -> dict[str, Any]:
        parsed = self._parse_request(request, "get_customer_profile")
        if isinstance(parsed, MCPResponseEnvelope):
            return parsed.model_dump(mode="json")
        denied = self._deny_if_not_scoped(parsed)
        if denied:
            return denied.model_dump(mode="json")

        customer_id = self._customer_id(parsed)
        profile = self.repository.get_customer_profile(customer_id)
        refs = [
            *_record_refs("customer", "customer_id", [profile.get("customer")]),
            *_record_refs("account", "account_id", profile.get("accounts") or []),
            *_record_refs("behavioral_baseline", "pattern_id", [profile.get("latest_pattern")]),
        ]
        return self._ok(
            facts=profile,
            source_refs=refs,
            rows_returned=len(profile.get("accounts") or []),
            rows_requested=len(profile.get("accounts") or []),
        ).model_dump(mode="json")

    def get_transaction_history(self, request: dict[str, Any]) -> dict[str, Any]:
        parsed = self._parse_request(request, "get_transaction_history")
        if isinstance(parsed, MCPResponseEnvelope):
            return parsed.model_dump(mode="json")
        denied = self._deny_if_not_scoped(parsed)
        if denied:
            return denied.model_dump(mode="json")

        args = parsed.tool_args
        max_rows = _bounded_int(args.get("max_rows"), default=25, minimum=1, maximum=100)
        lookback_days = _bounded_int(args.get("lookback_days"), default=180, minimum=1, maximum=365)
        rows = self.repository.get_transaction_history(
            self._customer_id(parsed),
            max_rows=max_rows,
            lookback_days=lookback_days,
        )
        return self._ok(
            facts={"transactions": rows},
            source_refs=[
                *_record_refs("transaction", "transaction_id", rows),
                *_record_refs("account", "account_id", rows),
            ],
            rows_returned=len(rows),
            rows_requested=max_rows,
            lookback_days_requested=lookback_days,
            complete=len(rows) < max_rows,
        ).model_dump(mode="json")

    def get_behavioral_baseline(self, request: dict[str, Any]) -> dict[str, Any]:
        parsed = self._parse_request(request, "get_behavioral_baseline")
        if isinstance(parsed, MCPResponseEnvelope):
            return parsed.model_dump(mode="json")
        denied = self._deny_if_not_scoped(parsed)
        if denied:
            return denied.model_dump(mode="json")

        alert_id = parsed.subject.alert_id
        if alert_id is None:
            return self._denied("missing_alert_id", "Behavioral baseline requires an alert subject.").model_dump(mode="json")
        args = parsed.tool_args
        max_rows = _bounded_int(args.get("max_rows"), default=100, minimum=1, maximum=100)
        lookback_days = _bounded_int(args.get("lookback_days"), default=180, minimum=1, maximum=365)
        baseline = self.repository.get_behavioral_baseline(
            self._customer_id(parsed),
            alert_id,
            max_rows=max_rows,
            lookback_days=lookback_days,
        )
        rows = baseline.get("historical_transactions") or []
        refs = [
            *_record_refs("transaction", "transaction_id", [baseline.get("current_transaction")]),
            *_record_refs("transaction", "transaction_id", rows),
            *_record_refs("behavioral_baseline", "pattern_id", [baseline.get("latest_pattern")]),
        ]
        missing = []
        if not baseline.get("latest_pattern"):
            missing.append("transaction_patterns")
        return self._ok(
            facts=baseline,
            source_refs=refs,
            rows_returned=len(rows),
            rows_requested=max_rows,
            lookback_days_requested=lookback_days,
            missing_segments=missing,
            complete=len(rows) < max_rows and not missing,
        ).model_dump(mode="json")

    def get_prior_alerts(self, request: dict[str, Any]) -> dict[str, Any]:
        parsed = self._parse_request(request, "get_prior_alerts")
        if isinstance(parsed, MCPResponseEnvelope):
            return parsed.model_dump(mode="json")
        denied = self._deny_if_not_scoped(parsed)
        if denied:
            return denied.model_dump(mode="json")

        max_rows = _bounded_int(parsed.tool_args.get("max_rows"), default=25, minimum=1, maximum=100)
        rows = self.repository.get_prior_alerts(
            self._customer_id(parsed),
            parsed.subject.alert_id,
            max_rows=max_rows,
        )
        return self._ok(
            facts={"prior_alerts": rows},
            source_refs=[
                *_record_refs("alert", "alert_id", rows),
                *_record_refs("transaction", "transaction_id", rows),
                *_record_refs("compliance_rule", "rule_id", rows),
            ],
            rows_returned=len(rows),
            rows_requested=max_rows,
            complete=len(rows) < max_rows,
        ).model_dump(mode="json")

    def get_case_history(self, request: dict[str, Any]) -> dict[str, Any]:
        parsed = self._parse_request(request, "get_case_history")
        if isinstance(parsed, MCPResponseEnvelope):
            return parsed.model_dump(mode="json")
        denied = self._deny_if_not_scoped(parsed)
        if denied:
            return denied.model_dump(mode="json")

        max_rows = _bounded_int(parsed.tool_args.get("max_rows"), default=25, minimum=1, maximum=100)
        history = self.repository.get_case_history(self._customer_id(parsed), max_rows=max_rows)
        cases = history.get("cases") or []
        return self._ok(
            facts=history,
            source_refs=[
                *_record_refs("case", "case_id", cases),
                *_record_refs("alert", "alert_id", history.get("linked_alerts") or []),
                *_record_refs("alert_comment", "comment_id", history.get("comments") or []),
            ],
            rows_returned=len(cases),
            rows_requested=max_rows,
            complete=len(cases) < max_rows,
        ).model_dump(mode="json")

    def trace_counterparty_graph(self, request: dict[str, Any]) -> dict[str, Any]:
        parsed = self._parse_request(request, "trace_counterparty_graph")
        if isinstance(parsed, MCPResponseEnvelope):
            return parsed.model_dump(mode="json")
        denied = self._deny_if_not_scoped(parsed)
        if denied:
            return denied.model_dump(mode="json")

        alert_id = parsed.subject.alert_id
        if alert_id is None:
            return self._denied("missing_alert_id", "Counterparty graph tracing requires an alert subject.").model_dump(mode="json")
        max_hops = _bounded_int(parsed.tool_args.get("max_hops"), default=2, minimum=1, maximum=4)
        max_rows = _bounded_int(parsed.tool_args.get("max_rows"), default=25, minimum=1, maximum=100)
        graph = self.repository.trace_counterparty_graph(
            alert_id,
            max_hops=max_hops,
            max_rows=max_rows,
        )
        edges = graph.get("edges") or []
        return self._ok(
            facts=graph,
            source_refs=[
                *_record_refs("transaction", "transaction_id", [graph.get("start_transaction")]),
                *_record_refs("transaction", "transaction_id", edges),
                *_record_refs("alert", "alert_id", graph.get("linked_alerts") or []),
                *_record_refs("case", "case_id", graph.get("linked_cases") or []),
            ],
            rows_returned=len(edges),
            rows_requested=max_rows,
            complete=len(edges) < max_rows,
        ).model_dump(mode="json")

    def screen_sanctions_pep(self, request: dict[str, Any]) -> dict[str, Any]:
        parsed = self._parse_request(request, "screen_sanctions_pep")
        if isinstance(parsed, MCPResponseEnvelope):
            return parsed.model_dump(mode="json")
        denied = self._deny_if_not_scoped(parsed)
        if denied:
            return denied.model_dump(mode="json")

        screening = self.repository.screen_sanctions_pep(self._customer_id(parsed))
        sanctions = screening.get("sanctions_matches") or []
        peps = screening.get("pep_matches") or []
        limitations = []
        if not sanctions and not peps:
            limitations.append("Screening is limited to exact-name matches in the demo dataset.")
        return self._ok(
            facts=screening,
            source_refs=[
                *_record_refs("customer", "customer_id", [screening.get("customer")]),
                *_record_refs("sanctions_match", "sanction_id", sanctions),
                *_record_refs("pep_match", "pep_id", peps),
            ],
            rows_returned=len(sanctions) + len(peps),
            rows_requested=None,
            limitations=limitations,
        ).model_dump(mode="json")

    def get_similar_alerts(self, request: dict[str, Any]) -> dict[str, Any]:
        parsed = self._parse_request(request, "get_similar_alerts")
        if isinstance(parsed, MCPResponseEnvelope):
            return parsed.model_dump(mode="json")
        denied = self._deny_if_not_scoped(parsed)
        if denied:
            return denied.model_dump(mode="json")

        alert_id = parsed.subject.alert_id
        if alert_id is None:
            return self._denied("missing_alert_id", "Similar alert lookup requires an alert subject.").model_dump(mode="json")
        max_rows = _bounded_int(parsed.tool_args.get("max_rows"), default=25, minimum=1, maximum=100)
        rows = self.repository.get_similar_alerts(
            self._customer_id(parsed),
            alert_id,
            max_rows=max_rows,
        )
        return self._ok(
            facts={"similar_alerts": rows},
            source_refs=[
                *_record_refs("alert", "alert_id", rows),
                *_record_refs("transaction", "transaction_id", rows),
                *_record_refs("compliance_rule", "rule_id", rows),
            ],
            rows_returned=len(rows),
            rows_requested=max_rows,
            complete=len(rows) < max_rows,
        ).model_dump(mode="json")

    def get_compliance_rule(self, request: dict[str, Any]) -> dict[str, Any]:
        parsed = self._parse_request(request, "get_compliance_rule")
        if isinstance(parsed, MCPResponseEnvelope):
            return parsed.model_dump(mode="json")
        denied = self._deny_if_not_scoped(parsed)
        if denied:
            return denied.model_dump(mode="json")

        alert_id = parsed.subject.alert_id
        if alert_id is None:
            return self._denied("missing_alert_id", "Compliance rule lookup requires an alert subject.").model_dump(mode="json")
        rule = self.repository.get_compliance_rule(alert_id)
        missing = [] if rule else ["compliance_rules"]
        return self._ok(
            facts={"compliance_rule": rule},
            source_refs=[
                *_record_refs("alert", "alert_id", [rule]),
                *_record_refs("transaction", "transaction_id", [rule]),
                *_record_refs("compliance_rule", "rule_id", [rule]),
            ],
            rows_returned=1 if rule else 0,
            rows_requested=1,
            missing_segments=missing,
            complete=bool(rule),
        ).model_dump(mode="json")

    def _parse_request(
        self,
        request: dict[str, Any],
        tool_name: str,
    ) -> MCPRequestEnvelope | MCPResponseEnvelope:
        try:
            parsed = MCPRequestEnvelope.model_validate(request)
        except ValidationError as exc:
            return self._error(tool_name, f"Invalid MCP request envelope: {exc}")
        forbidden = _find_forbidden_entity_args(parsed.tool_args)
        if forbidden:
            return self._denied(
                "forbidden_entity_args",
                "Tool arguments cannot include scoped entity identifiers: "
                + ", ".join(forbidden),
            )
        return parsed

    def _deny_if_not_scoped(self, request: MCPRequestEnvelope) -> MCPResponseEnvelope | None:
        scope = request.scope
        alert_id = request.subject.alert_id
        if alert_id is not None:
            alert_scope = self.repository.get_alert_scope(alert_id)
            if not alert_scope:
                return self._denied("missing_alert", f"Alert {alert_id} was not found.")
            if int(alert_scope["customer_id"]) not in set(scope.allowed_customer_ids):
                return self._denied("customer_scope_violation", "Alert customer is outside allowed scope.")
            if int(alert_scope["account_id"]) not in set(scope.allowed_account_ids):
                return self._denied("account_scope_violation", "Alert account is outside allowed scope.")
            if int(alert_scope["transaction_id"]) not in set(scope.allowed_transaction_ids):
                return self._denied("transaction_scope_violation", "Alert transaction is outside allowed scope.")

        customer_id = request.subject.customer_id
        if customer_id is not None and int(customer_id) not in set(scope.allowed_customer_ids):
            return self._denied("customer_scope_violation", "Subject customer is outside allowed scope.")
        case_id = request.subject.case_id
        if case_id is not None and int(case_id) not in set(scope.allowed_case_ids):
            return self._denied("case_scope_violation", "Subject case is outside allowed scope.")
        return None

    def _customer_id(self, request: MCPRequestEnvelope) -> int:
        if request.subject.customer_id is not None:
            return int(request.subject.customer_id)
        if request.subject.alert_id is not None:
            scope = self.repository.get_alert_scope(int(request.subject.alert_id))
            if scope:
                return int(scope["customer_id"])
        raise ValueError("Request does not identify a scoped customer.")

    def _ok(
        self,
        *,
        facts: dict[str, Any],
        source_refs: list[MCPSourceRef],
        rows_returned: int | None,
        rows_requested: int | None,
        lookback_days_requested: int | None = None,
        missing_segments: list[str] | None = None,
        complete: bool = True,
        limitations: list[str] | None = None,
    ) -> MCPResponseEnvelope:
        status = "ok" if complete else "partial"
        return MCPResponseEnvelope(
            status=status,
            facts=facts,
            source_refs=_dedupe_refs(source_refs),
            data_completeness=DataCompleteness(
                complete=complete,
                rows_returned=rows_returned,
                rows_requested=rows_requested,
                missing_segments=missing_segments or [],
                lookback_days_requested=lookback_days_requested,
            ),
            limitations=limitations or [],
            audit_id=_audit_id(),
            policy_decisions=[
                PolicyDecision(
                    decision="allow",
                    policy="phase1_reference_mcp_scope_v1",
                    reason="Request matched phase 1 scope and bounded argument policy.",
                )
            ],
        )

    def _denied(self, policy: str, reason: str) -> MCPResponseEnvelope:
        return MCPResponseEnvelope(
            status="denied",
            facts={},
            source_refs=[],
            data_completeness=DataCompleteness(complete=False, missing_segments=["denied"]),
            limitations=[reason],
            audit_id=_audit_id(),
            policy_decisions=[
                PolicyDecision(
                    decision="deny",
                    policy=policy,
                    reason=reason,
                )
            ],
        )

    def _error(self, tool_name: str, reason: str) -> MCPResponseEnvelope:
        return MCPResponseEnvelope(
            status="error",
            facts={},
            source_refs=[],
            data_completeness=DataCompleteness(complete=False, missing_segments=["error"]),
            limitations=[reason],
            audit_id=_audit_id(),
            policy_decisions=[
                PolicyDecision(
                    decision="audit",
                    policy="phase1_reference_mcp_error_v1",
                    reason=f"{tool_name}: {reason}",
                )
            ],
        )


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    parsed = int(value)
    return max(minimum, min(maximum, parsed))


def _record_refs(
    entity_type: str,
    id_field: str,
    records: list[dict[str, Any] | None],
) -> list[MCPSourceRef]:
    refs: list[MCPSourceRef] = []
    retrieved_at = _now()
    for record in records:
        if not record:
            continue
        entity_id = record.get(id_field)
        if entity_id is None:
            continue
        refs.append(
            MCPSourceRef(
                entity_type=entity_type,
                entity_id=str(entity_id),
                field_names=sorted(str(key) for key in record.keys()),
                retrieved_at=retrieved_at,
            )
        )
    return refs


def _dedupe_refs(refs: list[MCPSourceRef]) -> list[MCPSourceRef]:
    deduped: list[MCPSourceRef] = []
    seen = set()
    for ref in refs:
        key = (ref.source_system, ref.entity_type, ref.entity_id, tuple(ref.field_names))
        if key in seen:
            continue
        deduped.append(ref)
        seen.add(key)
    return deduped


def _find_forbidden_entity_args(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_TOOL_ARG_FIELDS:
                found.append(child_path)
            found.extend(_find_forbidden_entity_args(nested, child_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_find_forbidden_entity_args(item, f"{path}[{index}]"))
    return found


def _audit_id() -> str:
    return f"audit-{uuid4().hex}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
