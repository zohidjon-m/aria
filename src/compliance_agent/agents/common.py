from __future__ import annotations

from typing import Any

from ..domain import EvidenceItem, SourceRef


TABLE_KEYS = {
    "alert": ("alerts", "alert_id"),
    "rule": ("compliance_rules", "rule_id"),
    "transaction": ("transactions", "transaction_id"),
    "account": ("accounts", "account_id"),
    "customer": ("customers", "customer_id"),
    "destination_country": ("countries", "country_code"),
    "pattern": ("transaction_patterns", "pattern_id"),
    "latest_pattern": ("transaction_patterns", "pattern_id"),
    "case": ("cases", "case_id"),
}

LIST_TABLE_KEYS = {
    "recent_transactions": ("transactions", "transaction_id"),
    "transactions": ("transactions", "transaction_id"),
    "prior_alerts": ("alerts", "alert_id"),
    "open_alerts": ("alerts", "alert_id"),
    "linked_alerts": ("alerts", "alert_id"),
    "sanctions_matches": ("sanctions_list", "sanction_id"),
    "pep_matches": ("pep_list", "pep_id"),
    "comments": ("alert_comments", "comment_id"),
    "accounts": ("accounts", "account_id"),
}


def collect_evidence(context: dict[str, Any]) -> list[EvidenceItem]:
    evidence: dict[str, EvidenceItem] = {}

    for context_key, (table, key_name) in TABLE_KEYS.items():
        record = context.get(context_key)
        if isinstance(record, dict):
            item = _evidence_from_record(table, key_name, record)
            if item:
                evidence[item.evidence_id] = item

    for context_key, (table, key_name) in LIST_TABLE_KEYS.items():
        records = context.get(context_key) or []
        for record in records:
            if isinstance(record, dict):
                item = _evidence_from_record(table, key_name, record)
                if item:
                    evidence[item.evidence_id] = item

    return list(evidence.values())


def ref_for(record: dict[str, Any] | None, table: str, key_name: str) -> SourceRef | None:
    if not record or record.get(key_name) is None:
        return None
    return SourceRef(table=table, key=str(record[key_name]))


def require_ref(record: dict[str, Any], table: str, key_name: str) -> SourceRef:
    ref = ref_for(record, table, key_name)
    if not ref:
        raise ValueError(f"Record does not contain key {key_name}")
    return ref


def _evidence_from_record(
    table: str,
    key_name: str,
    record: dict[str, Any],
) -> EvidenceItem | None:
    key = record.get(key_name)
    if key is None:
        return None
    return EvidenceItem(
        evidence_id=f"{table}:{key}",
        source_ref=SourceRef(table=table, key=str(key)),
        payload=dict(record),
    )
