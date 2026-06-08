from __future__ import annotations

from collections import Counter
from statistics import mean, median
from typing import Any

from pydantic import BaseModel

from ..utils import parse_datetime
from .tooling import (
    BehavioralBaselineArgs,
    DataCompleteness,
    EmptyToolArgs,
    InvestigationScope,
    RowLimitToolArgs,
    ScopePolicy,
    ScopeViolationError,
    SourceRefRecord,
    ToolDefinition,
    ToolExecutionContext,
    ToolLimitation,
    ToolObservation,
    ToolRegistry,
    TraceMoneyFlowArgs,
)


PHASE1_TOOL_NAMES = {
    "get_alert_context",
    "get_customer_profile",
    "get_recent_transactions",
    "get_prior_alerts",
    "get_open_cases",
    "screen_sanctions_pep",
    "compute_behavioral_baseline",
    "run_structuring_check",
    "run_velocity_check",
    "run_geography_check",
    "trace_money_flow",
}

TOOL_REGISTRY_VERSION = "phase1_tools_v1"


def build_phase1_tool_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            ToolDefinition(
                name="get_alert_context",
                purpose="Return scoped alert, customer, account, transaction, and rule facts.",
                args_model=EmptyToolArgs,
                handler=get_alert_context,
            ),
            ToolDefinition(
                name="get_customer_profile",
                purpose="Return scoped customer profile and account facts.",
                args_model=EmptyToolArgs,
                handler=get_customer_profile,
            ),
            ToolDefinition(
                name="get_recent_transactions",
                purpose="Return recent transactions for the scoped customer.",
                args_model=RowLimitToolArgs,
                handler=get_recent_transactions,
            ),
            ToolDefinition(
                name="get_prior_alerts",
                purpose="Return prior alerts for the scoped customer.",
                args_model=RowLimitToolArgs,
                handler=get_prior_alerts,
            ),
            ToolDefinition(
                name="get_open_cases",
                purpose="Return open cases for the scoped customer.",
                args_model=RowLimitToolArgs,
                handler=get_open_cases,
            ),
            ToolDefinition(
                name="screen_sanctions_pep",
                purpose="Return sanctions and PEP screening facts for the scoped customer.",
                args_model=EmptyToolArgs,
                handler=screen_sanctions_pep,
            ),
            ToolDefinition(
                name="compute_behavioral_baseline",
                purpose="Return scoped customer-relative behavioral baseline facts.",
                args_model=BehavioralBaselineArgs,
                handler=compute_behavioral_baseline,
            ),
            ToolDefinition(
                name="run_structuring_check",
                purpose="Return deterministic structuring facts for the scoped alert.",
                args_model=RowLimitToolArgs,
                handler=run_structuring_check,
            ),
            ToolDefinition(
                name="run_velocity_check",
                purpose="Return deterministic velocity facts for the scoped alert.",
                args_model=RowLimitToolArgs,
                handler=run_velocity_check,
            ),
            ToolDefinition(
                name="run_geography_check",
                purpose="Return deterministic geography facts for the scoped alert.",
                args_model=EmptyToolArgs,
                handler=run_geography_check,
            ),
            ToolDefinition(
                name="trace_money_flow",
                purpose="Return immediate counterparty facts for the scoped transaction.",
                args_model=TraceMoneyFlowArgs,
                handler=trace_money_flow,
                scope_policy=ScopePolicy.graph_expandable(),
            ),
        ]
    )


def build_scope_for_alert(source: Any, alert_id: int) -> InvestigationScope:
    return InvestigationScope.from_alert_context(source.get_alert_context(alert_id))


def get_alert_context(context: ToolExecutionContext, args: BaseModel) -> ToolObservation:
    alert_context = _alert_context(context)
    facts = {
        "alert": alert_context.get("alert"),
        "rule": alert_context.get("rule"),
        "transaction": alert_context.get("transaction"),
        "account": alert_context.get("account"),
        "customer": alert_context.get("customer"),
        "destination_country": alert_context.get("destination_country"),
    }
    return _observation(
        facts=facts,
        source_refs=_context_source_refs(alert_context),
        data_completeness=DataCompleteness(complete=True),
    )


def get_customer_profile(context: ToolExecutionContext, args: BaseModel) -> ToolObservation:
    alert_context = _alert_context(context)
    facts = {
        "customer": alert_context.get("customer"),
        "account": alert_context.get("account"),
        "pattern": alert_context.get("pattern"),
    }
    return _observation(
        facts=facts,
        source_refs=[
            *_record_refs("customers", "customer_id", [alert_context.get("customer")]),
            *_record_refs("accounts", "account_id", [alert_context.get("account")]),
            *_record_refs("transaction_patterns", "pattern_id", [alert_context.get("pattern")]),
        ],
    )


def get_recent_transactions(context: ToolExecutionContext, args: BaseModel) -> ToolObservation:
    parsed = _as_row_args(args)
    alert_context = _alert_context(context)
    transactions = list(alert_context.get("recent_transactions") or [])[: parsed.max_rows]
    return _observation(
        facts={"recent_transactions": transactions},
        computed_features={"transaction_count": len(transactions)},
        source_refs=_record_refs("transactions", "transaction_id", transactions),
        data_completeness=DataCompleteness(
            lookback_days_requested=parsed.lookback_days,
            rows_requested=parsed.max_rows,
            rows_returned=len(transactions),
            complete=len(transactions) < parsed.max_rows,
        ),
    )


def get_prior_alerts(context: ToolExecutionContext, args: BaseModel) -> ToolObservation:
    parsed = _as_row_args(args)
    alert_context = _alert_context(context)
    prior_alerts = list(alert_context.get("prior_alerts") or [])[: parsed.max_rows]
    return _observation(
        facts={"prior_alerts": prior_alerts},
        computed_features={"prior_alert_count": len(prior_alerts)},
        source_refs=_record_refs("alerts", "alert_id", prior_alerts),
        data_completeness=DataCompleteness(
            lookback_days_requested=parsed.lookback_days,
            rows_requested=parsed.max_rows,
            rows_returned=len(prior_alerts),
            complete=len(prior_alerts) < parsed.max_rows,
        ),
    )


def get_open_cases(context: ToolExecutionContext, args: BaseModel) -> ToolObservation:
    parsed = _as_row_args(args)
    cases = context.source.get_open_cases_for_customer(
        context.scope.customer_id,
        max_rows=parsed.max_rows,
    )
    return _observation(
        facts={"open_cases": cases},
        computed_features={"open_case_count": len(cases)},
        source_refs=_record_refs("cases", "case_id", cases),
        data_completeness=DataCompleteness(
            rows_requested=parsed.max_rows,
            rows_returned=len(cases),
            complete=len(cases) < parsed.max_rows,
        ),
    )


def screen_sanctions_pep(context: ToolExecutionContext, args: BaseModel) -> ToolObservation:
    alert_context = _alert_context(context)
    sanctions_matches = list(alert_context.get("sanctions_matches") or [])
    pep_matches = list(alert_context.get("pep_matches") or [])
    limitations = []
    if not sanctions_matches and not pep_matches:
        limitations.append(
            ToolLimitation(
                code="exact_name_match_only",
                message="Phase 1 screening facts are limited to adapter-provided matches.",
            )
        )
    return _observation(
        facts={
            "sanctions_matches": sanctions_matches,
            "pep_matches": pep_matches,
        },
        computed_features={
            "sanctions_match_count": len(sanctions_matches),
            "pep_match_count": len(pep_matches),
        },
        source_refs=[
            *_record_refs("sanctions_list", "sanction_id", sanctions_matches),
            *_record_refs("pep_list", "pep_id", pep_matches),
            *_record_refs("customers", "customer_id", [alert_context.get("customer")]),
        ],
        limitations=limitations,
    )


def compute_behavioral_baseline(context: ToolExecutionContext, args: BaseModel) -> ToolObservation:
    parsed = BehavioralBaselineArgs.model_validate(args.model_dump())
    alert_context = _alert_context(context)
    pattern = alert_context.get("pattern") or {}
    transaction = alert_context.get("transaction") or {}
    historical_transactions = context.source.get_customer_transactions_for_baseline(
        context.scope.customer_id,
        context.scope.transaction_id,
        parsed.lookback_days,
        parsed.max_rows,
    )
    amount_usd = float(transaction.get("amount_usd") or 0)
    transaction_type = str(transaction.get("transaction_type") or "")
    similar_alerts = context.source.get_similar_alerts_for_customer(
        context.scope.customer_id,
        transaction_type,
        amount_usd,
        parsed.amount_tolerance_pct,
        parsed.lookback_days,
        parsed.max_rows,
    )

    features, limitations = _compute_baseline_features(
        transaction=transaction,
        historical_transactions=historical_transactions,
        similar_alerts=similar_alerts,
        pattern=pattern,
        lookback_days=parsed.lookback_days,
        max_rows=parsed.max_rows,
    )

    return _observation(
        facts={
            "current_transaction": transaction,
            "historical_transactions": historical_transactions,
            "similar_alerts": similar_alerts,
            "pattern": pattern,
        },
        computed_features=features,
        source_refs=[
            *_record_refs("transaction_patterns", "pattern_id", [pattern]),
            *_record_refs("transactions", "transaction_id", [transaction]),
            *_record_refs("transactions", "transaction_id", historical_transactions),
            *_record_refs("alerts", "alert_id", similar_alerts),
        ],
        data_completeness=DataCompleteness(
            lookback_days_requested=parsed.lookback_days,
            lookback_days_available=features.get("lookback_days_available"),
            rows_requested=parsed.max_rows,
            rows_returned=len(historical_transactions),
            complete=len(historical_transactions) < parsed.max_rows,
            missing_segments=[] if pattern else ["transaction_patterns"],
        ),
        limitations=limitations,
    )


def run_structuring_check(context: ToolExecutionContext, args: BaseModel) -> ToolObservation:
    parsed = _as_row_args(args)
    alert_context = _alert_context(context)
    transaction = alert_context.get("transaction") or {}
    recent_transactions = list(alert_context.get("recent_transactions") or [])[: parsed.max_rows]
    structuring_band_transactions = [
        tx for tx in recent_transactions if 9000 <= float(tx.get("amount_usd") or 0) <= 9999
    ]
    current_amount = float(transaction.get("amount_usd") or 0)
    return _observation(
        facts={"structuring_band_transactions": structuring_band_transactions},
        computed_features={
            "current_transaction_in_structuring_band": 9000 <= current_amount <= 9999,
            "structuring_band_count": len(structuring_band_transactions),
        },
        source_refs=[
            *_record_refs("transactions", "transaction_id", [transaction]),
            *_record_refs("transactions", "transaction_id", structuring_band_transactions),
        ],
        data_completeness=DataCompleteness(
            lookback_days_requested=parsed.lookback_days,
            rows_requested=parsed.max_rows,
            rows_returned=len(recent_transactions),
            complete=len(recent_transactions) < parsed.max_rows,
        ),
    )


def run_velocity_check(context: ToolExecutionContext, args: BaseModel) -> ToolObservation:
    parsed = _as_row_args(args)
    alert_context = _alert_context(context)
    transactions = list(alert_context.get("recent_transactions") or [])[: parsed.max_rows]
    counts_by_date = Counter(str(tx.get("created_at", ""))[:10] for tx in transactions)
    max_same_day_count = max(counts_by_date.values(), default=0)
    return _observation(
        facts={"transaction_dates": dict(counts_by_date)},
        computed_features={
            "max_same_day_transaction_count": max_same_day_count,
            "velocity_threshold_met": max_same_day_count >= 10,
        },
        source_refs=_record_refs("transactions", "transaction_id", transactions),
        data_completeness=DataCompleteness(
            lookback_days_requested=parsed.lookback_days,
            rows_requested=parsed.max_rows,
            rows_returned=len(transactions),
            complete=len(transactions) < parsed.max_rows,
        ),
    )


def run_geography_check(context: ToolExecutionContext, args: BaseModel) -> ToolObservation:
    alert_context = _alert_context(context)
    transaction = alert_context.get("transaction") or {}
    country = alert_context.get("destination_country") or {}
    destination = transaction.get("destination_country")
    return _observation(
        facts={
            "destination_country": country,
            "transaction_destination_country": destination,
        },
        computed_features={
            "has_destination_country": bool(destination),
            "is_sanctioned_country": bool(country.get("is_sanctioned")),
            "fatf_status": country.get("fatf_status"),
            "country_risk_score": country.get("risk_score"),
        },
        source_refs=[
            *_record_refs("transactions", "transaction_id", [transaction]),
            *_record_refs("countries", "country_code", [country]),
        ],
        data_completeness=DataCompleteness(
            complete=bool(destination) == bool(country),
            missing_segments=[] if not destination or country else ["countries"],
        ),
    )


def trace_money_flow(context: ToolExecutionContext, args: BaseModel) -> ToolObservation:
    parsed = TraceMoneyFlowArgs.model_validate(args.model_dump())
    alert_context = _alert_context(context)
    transaction = alert_context.get("transaction") or {}
    transaction_id = transaction.get("transaction_id")
    source_account_id = transaction.get("account_id")
    if transaction_id is None or source_account_id is None:
        return _observation(
            facts={
                "start_transaction": transaction,
                "paths": [],
                "edges": [],
                "reached_accounts": [],
                "linked_alerts": [],
                "linked_cases": [],
            },
            computed_features={
                "max_hops_requested": parsed.max_hops,
                "max_rows_requested": parsed.max_rows,
                "has_immediate_counterparty": False,
                "signals": _empty_graph_signals(),
                "trusted_graph_edges": [],
            },
            source_refs=_record_refs("transactions", "transaction_id", [transaction]),
            data_completeness=DataCompleteness(rows_requested=parsed.max_rows, complete=True),
        )

    trace = _trace_money_flow(
        context=context,
        source_account_id=int(source_account_id),
        anchor_transaction_id=int(transaction_id),
        max_hops=parsed.max_hops,
        max_rows=parsed.max_rows,
    )
    limitations = []
    if trace["row_limit_reached"]:
        limitations.append(
            ToolLimitation(
                code="graph_row_limit_reached",
                message="Money-flow tracing reached the requested row limit.",
                severity="warning",
            )
        )
    if trace["max_hops_reached"]:
        limitations.append(
            ToolLimitation(
                code="graph_max_hops_reached",
                message="Money-flow tracing stopped at the requested hop limit.",
            )
        )
    signals = _graph_signals(trace["edges"], trace["paths"])
    return _observation(
        facts={
            "start_transaction": transaction,
            "paths": trace["paths"],
            "edges": trace["edges"],
            "reached_accounts": sorted(trace["reached_accounts"]),
            "linked_alerts": trace["linked_alerts"],
            "linked_cases": trace["linked_cases"],
        },
        computed_features={
            "max_hops_requested": parsed.max_hops,
            "max_rows_requested": parsed.max_rows,
            "has_immediate_counterparty": bool(trace["paths"]),
            "signals": signals,
            "trusted_graph_edges": trace["trusted_graph_edges"],
        },
        source_refs=_money_flow_source_refs(transaction, trace),
        data_completeness=DataCompleteness(
            rows_requested=parsed.max_rows,
            rows_returned=len(trace["edges"]),
            complete=not trace["row_limit_reached"],
        ),
        limitations=limitations,
    )


def _trace_money_flow(
    *,
    context: ToolExecutionContext,
    source_account_id: int,
    anchor_transaction_id: int,
    max_hops: int,
    max_rows: int,
) -> dict[str, Any]:
    edges_by_id: dict[int, dict[str, Any]] = {}
    edge_hops: dict[int, int] = {}
    linked_alerts_by_id: dict[int, dict[str, Any]] = {}
    linked_cases_by_id: dict[int, dict[str, Any]] = {}
    trusted_graph_edges_by_id: dict[int, dict[str, Any]] = {}
    paths: list[dict[str, Any]] = []
    active_paths = [
        {
            "account_path": [source_account_id],
            "transaction_ids": [],
            "amount_usd_path": [],
            "created_at_path": [],
        }
    ]
    reached_accounts = {source_account_id}
    row_limit_reached = False
    max_hops_reached = False

    for hop in range(1, max_hops + 1):
        frontier = {
            int(path["account_path"][-1])
            for path in active_paths
            if path["account_path"]
        }
        if not frontier:
            break

        remaining_rows = max_rows - len(edges_by_id)
        if remaining_rows <= 0:
            row_limit_reached = True
            break

        fetched = context.source.get_money_flow_edges(
            sorted(frontier),
            anchor_transaction_id,
            remaining_rows,
        )
        if len(fetched) >= remaining_rows:
            row_limit_reached = True

        normalized_fetched = [_normalize_money_flow_edge(row) for row in fetched]
        for edge in normalized_fetched:
            edge_id = edge["transaction_id"]
            if edge_id not in edges_by_id:
                edges_by_id[edge_id] = edge
            edge_hops.setdefault(edge_id, hop)
            for alert in edge["linked_alerts"]:
                if alert.get("alert_id") is not None:
                    linked_alerts_by_id[int(alert["alert_id"])] = alert
            for case in edge["linked_cases"]:
                if case.get("case_id") is not None:
                    linked_cases_by_id[int(case["case_id"])] = case

        next_paths: list[dict[str, Any]] = []
        outgoing = [
            edge
            for edge in normalized_fetched
            if edge["source_account_id"] in frontier
            and edge["counterparty_account_id"] is not None
        ]
        for path in active_paths:
            current_account = int(path["account_path"][-1])
            for edge in outgoing:
                if edge["source_account_id"] != current_account:
                    continue
                if edge["transaction_id"] in path["transaction_ids"]:
                    continue
                next_account = int(edge["counterparty_account_id"])
                extended = {
                    "account_path": [*path["account_path"], next_account],
                    "transaction_ids": [
                        *path["transaction_ids"],
                        edge["transaction_id"],
                    ],
                    "amount_usd_path": [
                        *path["amount_usd_path"],
                        edge["amount_usd"],
                    ],
                    "created_at_path": [
                        *path["created_at_path"],
                        edge["created_at"],
                    ],
                    "hop_count": hop,
                }
                paths.append(extended)
                next_paths.append(extended)
                reached_accounts.add(next_account)
                trusted_graph_edges_by_id.setdefault(
                    edge["transaction_id"],
                    {
                        "source_transaction_id": edge["transaction_id"],
                        "source_account_id": edge["source_account_id"],
                        "counterparty_account_id": next_account,
                        "evidence_refs": [
                            {
                                "table": "transactions",
                                "key": str(edge["transaction_id"]),
                                "columns": ["counterparty_account_id"],
                            }
                        ],
                    },
                )

        if not next_paths:
            break
        active_paths = next_paths
        if hop == max_hops:
            max_hops_reached = True

    edges = sorted(
        edges_by_id.values(),
        key=lambda edge: (
            edge_hops.get(edge["transaction_id"], max_hops + 1),
            str(edge["created_at"] or ""),
            edge["transaction_id"],
        ),
    )
    trusted_graph_edges = [
        trusted_graph_edges_by_id[edge["transaction_id"]]
        for edge in edges
        if edge["transaction_id"] in trusted_graph_edges_by_id
    ]
    return {
        "paths": paths,
        "edges": edges,
        "reached_accounts": reached_accounts,
        "linked_alerts": list(linked_alerts_by_id.values()),
        "linked_cases": list(linked_cases_by_id.values()),
        "trusted_graph_edges": trusted_graph_edges,
        "row_limit_reached": row_limit_reached,
        "max_hops_reached": max_hops_reached,
    }


def _normalize_money_flow_edge(row: dict[str, Any]) -> dict[str, Any]:
    transaction = row.get("transaction") or {}
    source_account = row.get("source_account") or {}
    source_customer = row.get("source_customer") or {}
    counterparty_account = row.get("counterparty_account") or {}
    counterparty_customer = row.get("counterparty_customer") or {}
    country = row.get("destination_country") or {}
    return {
        "transaction_id": int(transaction["transaction_id"]),
        "source_account_id": int(transaction["account_id"]),
        "counterparty_account_id": _optional_int(transaction.get("counterparty_account_id")),
        "amount_usd": float(transaction.get("amount_usd") or 0),
        "created_at": transaction.get("created_at"),
        "destination_country": transaction.get("destination_country"),
        "transaction_status": transaction.get("status"),
        "is_flagged": bool(transaction.get("is_flagged")),
        "source_customer_id": _optional_int(source_customer.get("customer_id")),
        "source_customer_risk_level": source_customer.get("risk_level"),
        "counterparty_customer_id": _optional_int(counterparty_customer.get("customer_id")),
        "counterparty_customer_risk_level": counterparty_customer.get("risk_level"),
        "counterparty_account_status": counterparty_account.get("status"),
        "country_fatf_status": country.get("fatf_status"),
        "country_risk_score": country.get("risk_score"),
        "country_is_sanctioned": bool(country.get("is_sanctioned")),
        "linked_alert_ids": [
            int(alert["alert_id"])
            for alert in row.get("linked_alerts") or []
            if alert.get("alert_id") is not None
        ],
        "linked_case_ids": [
            int(case["case_id"])
            for case in row.get("linked_cases") or []
            if case.get("case_id") is not None
        ],
        "linked_alerts": list(row.get("linked_alerts") or []),
        "linked_cases": list(row.get("linked_cases") or []),
    }


def _graph_signals(edges: list[dict[str, Any]], paths: list[dict[str, Any]]) -> dict[str, Any]:
    fan_out_counts: dict[int, set[int]] = {}
    many_to_one_counts: dict[int, set[int]] = {}
    for edge in edges:
        source_account_id = edge.get("source_account_id")
        counterparty_account_id = edge.get("counterparty_account_id")
        if source_account_id is None or counterparty_account_id is None:
            continue
        fan_out_counts.setdefault(int(source_account_id), set()).add(int(counterparty_account_id))
        many_to_one_counts.setdefault(int(counterparty_account_id), set()).add(int(source_account_id))

    linked_alert_ids = {
        alert_id
        for edge in edges
        for alert_id in edge.get("linked_alert_ids", [])
    }
    linked_case_ids = {
        case_id
        for edge in edges
        for case_id in edge.get("linked_case_ids", [])
    }
    return {
        "rapid_pass_through": _rapid_pass_through(edges),
        "cycle_detected": any(
            len(path["account_path"]) != len(set(path["account_path"]))
            for path in paths
        ),
        "fan_out": any(len(counterparties) >= 3 for counterparties in fan_out_counts.values()),
        "many_to_one": any(len(sources) >= 3 for sources in many_to_one_counts.values()),
        "high_risk_endpoint": any(_edge_has_high_risk_endpoint(edge) for edge in edges),
        "linked_alert_count": len(linked_alert_ids),
        "linked_open_case_count": len(linked_case_ids),
    }


def _rapid_pass_through(edges: list[dict[str, Any]]) -> bool:
    for inbound in edges:
        intermediate = inbound.get("counterparty_account_id")
        inbound_dt = parse_datetime(inbound.get("created_at"))
        if intermediate is None or not inbound_dt:
            continue
        inbound_amount = float(inbound.get("amount_usd") or 0)
        for outbound in edges:
            if outbound.get("source_account_id") != intermediate:
                continue
            outbound_dt = parse_datetime(outbound.get("created_at"))
            if not outbound_dt:
                continue
            hours = (outbound_dt - inbound_dt).total_seconds() / 3600
            if 0 <= hours <= 24 and float(outbound.get("amount_usd") or 0) >= inbound_amount * 0.8:
                return True
    return False


def _edge_has_high_risk_endpoint(edge: dict[str, Any]) -> bool:
    risk_level = str(edge.get("counterparty_customer_risk_level") or "").lower()
    account_status = str(edge.get("counterparty_account_status") or "").lower()
    fatf_status = str(edge.get("country_fatf_status") or "").lower()
    country_risk_score = float(edge.get("country_risk_score") or 0)
    return (
        risk_level in {"high", "critical"}
        or account_status in {"frozen", "suspended"}
        or bool(edge.get("is_flagged"))
        or bool(edge.get("country_is_sanctioned"))
        or fatf_status in {"blacklist", "greylist"}
        or country_risk_score >= 4
    )


def _empty_graph_signals() -> dict[str, Any]:
    return {
        "rapid_pass_through": False,
        "cycle_detected": False,
        "fan_out": False,
        "many_to_one": False,
        "high_risk_endpoint": False,
        "linked_alert_count": 0,
        "linked_open_case_count": 0,
    }


def _money_flow_source_refs(
    transaction: dict[str, Any],
    trace: dict[str, Any],
) -> list[SourceRefRecord]:
    refs = [
        *_record_refs("transactions", "transaction_id", [transaction]),
    ]
    for edge in trace["edges"]:
        refs.append(SourceRefRecord(table="transactions", key=str(edge["transaction_id"])))
        if edge.get("source_account_id") is not None:
            refs.append(SourceRefRecord(table="accounts", key=str(edge["source_account_id"])))
        if edge.get("counterparty_account_id") is not None:
            refs.append(SourceRefRecord(table="accounts", key=str(edge["counterparty_account_id"])))
        if edge.get("source_customer_id") is not None:
            refs.append(SourceRefRecord(table="customers", key=str(edge["source_customer_id"])))
        if edge.get("counterparty_customer_id") is not None:
            refs.append(SourceRefRecord(table="customers", key=str(edge["counterparty_customer_id"])))
        if edge.get("destination_country"):
            refs.append(SourceRefRecord(table="countries", key=str(edge["destination_country"])))
    for alert in trace["linked_alerts"]:
        if alert.get("alert_id") is not None:
            refs.append(SourceRefRecord(table="alerts", key=str(alert["alert_id"])))
    for case in trace["linked_cases"]:
        if case.get("case_id") is not None:
            refs.append(SourceRefRecord(table="cases", key=str(case["case_id"])))
    return _dedupe_source_refs(refs)


def _dedupe_source_refs(refs: list[SourceRefRecord]) -> list[SourceRefRecord]:
    deduped: list[SourceRefRecord] = []
    seen = set()
    for ref in refs:
        key = (ref.table, ref.key, tuple(ref.columns))
        if key in seen:
            continue
        deduped.append(ref)
        seen.add(key)
    return deduped


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _compute_baseline_features(
    *,
    transaction: dict[str, Any],
    historical_transactions: list[dict[str, Any]],
    similar_alerts: list[dict[str, Any]],
    pattern: dict[str, Any],
    lookback_days: int,
    max_rows: int,
) -> tuple[dict[str, Any], list[ToolLimitation]]:
    amounts = [float(tx.get("amount_usd") or 0) for tx in historical_transactions]
    amount_usd = float(transaction.get("amount_usd") or 0)
    transaction_type = str(transaction.get("transaction_type") or "")
    historical_count = len(historical_transactions)
    transaction_type_counts = Counter(
        str(tx.get("transaction_type") or "") for tx in historical_transactions
    )
    transaction_type_shares = {
        tx_type: round((count / historical_count) * 100, 2)
        for tx_type, count in transaction_type_counts.items()
        if historical_count
    }
    country_counts = Counter(
        str(tx.get("destination_country"))
        for tx in historical_transactions
        if tx.get("destination_country")
    )
    counterparty_ids = {
        tx.get("counterparty_account_id")
        for tx in historical_transactions
        if tx.get("counterparty_account_id") is not None
    }
    current_country = transaction.get("destination_country")
    current_counterparty = transaction.get("counterparty_account_id")
    cash_transactions = [
        tx for tx in historical_transactions if str(tx.get("transaction_type") or "") == "cash"
    ]
    cash_amounts = [float(tx.get("amount_usd") or 0) for tx in cash_transactions]
    similar_alert_counts = Counter(str(alert.get("status") or "unknown") for alert in similar_alerts)

    amount_percentile = _percentile(amount_usd, amounts)
    cash_amount_percentile = (
        _percentile(amount_usd, cash_amounts) if transaction_type == "cash" and cash_amounts else None
    )
    same_day_transaction_count = _same_day_count(transaction, historical_transactions)
    lookback_days_available = _lookback_days_available(transaction, historical_transactions)
    observed_cash_pct = round((len(cash_transactions) / historical_count) * 100, 2) if historical_count else 0.0
    transaction_type_count = transaction_type_counts.get(transaction_type, 0)
    transaction_type_share = transaction_type_shares.get(transaction_type, 0.0)
    new_destination_country = bool(current_country) and current_country not in country_counts
    new_counterparty = bool(current_counterparty) and current_counterparty not in counterparty_ids

    limitations: list[ToolLimitation] = []
    if historical_count >= max_rows:
        limitations.append(
            ToolLimitation(
                code="history_truncated",
                message="Historical transactions reached the requested row limit.",
            )
        )
    if historical_count < 5:
        limitations.append(
            ToolLimitation(
                code="insufficient_history",
                message="Fewer than 5 historical transactions are available for baseline assessment.",
                severity="warning",
            )
        )
    if transaction_type == "cash" and not cash_amounts:
        limitations.append(
            ToolLimitation(
                code="no_cash_history",
                message="Current transaction is cash, but no historical cash transactions were found.",
                severity="warning",
            )
        )

    deviation_points, assessment_factors = _baseline_deviation_points(
        amount_percentile=amount_percentile,
        transaction_type_count=transaction_type_count,
        transaction_type_share=transaction_type_share,
        new_destination_country=new_destination_country,
        new_counterparty=new_counterparty,
        same_day_transaction_count=same_day_transaction_count,
        similar_alert_counts=similar_alert_counts,
        historical_count=historical_count,
    )
    baseline_assessment = _baseline_assessment(deviation_points, historical_count)

    features = {
        "lookback_days": lookback_days,
        "lookback_days_available": lookback_days_available,
        "historical_transaction_count": historical_count,
        "amount_usd": amount_usd,
        "amount_percentile": amount_percentile,
        "cash_amount_percentile": cash_amount_percentile,
        "average_transaction_amount": round(mean(amounts), 2) if amounts else None,
        "median_transaction_amount": round(median(amounts), 2) if amounts else None,
        "max_transaction_amount": round(max(amounts), 2) if amounts else None,
        "observed_cash_pct": observed_cash_pct,
        "pattern_cash_pct": pattern.get("cash_pct"),
        "pattern_international_pct": pattern.get("international_pct"),
        "same_day_transaction_count": same_day_transaction_count,
        "transaction_type_counts": dict(transaction_type_counts),
        "transaction_type_shares": transaction_type_shares,
        "usual_transaction_types": [
            tx_type for tx_type, share in transaction_type_shares.items() if share >= 10
        ],
        "usual_countries": sorted(country_counts),
        "new_destination_country": new_destination_country,
        "new_counterparty": new_counterparty,
        "similar_alert_counts_by_status": dict(similar_alert_counts),
        "similar_dismissed_count": similar_alert_counts.get("dismissed", 0),
        "similar_escalated_count": similar_alert_counts.get("escalated", 0),
        "deviation_points": deviation_points,
        "assessment_factors": assessment_factors,
        "baseline_assessment": baseline_assessment,
    }
    return features, limitations


def _percentile(value: float, population: list[float]) -> float | None:
    if not population:
        return None
    less_than_or_equal = sum(1 for item in population if item <= value)
    return round((less_than_or_equal / len(population)) * 100, 2)


def _same_day_count(
    transaction: dict[str, Any],
    historical_transactions: list[dict[str, Any]],
) -> int:
    current_dt = parse_datetime(transaction.get("created_at"))
    if not current_dt:
        return 1
    count = 1
    for tx in historical_transactions:
        tx_dt = parse_datetime(tx.get("created_at"))
        if tx_dt and tx_dt.date() == current_dt.date():
            count += 1
    return count


def _lookback_days_available(
    transaction: dict[str, Any],
    historical_transactions: list[dict[str, Any]],
) -> int | None:
    current_dt = parse_datetime(transaction.get("created_at"))
    historical_dates = [
        parse_datetime(tx.get("created_at"))
        for tx in historical_transactions
        if parse_datetime(tx.get("created_at"))
    ]
    if not current_dt or not historical_dates:
        return None
    oldest = min(historical_dates)
    return abs((current_dt - oldest).days)


def _baseline_deviation_points(
    *,
    amount_percentile: float | None,
    transaction_type_count: int,
    transaction_type_share: float,
    new_destination_country: bool,
    new_counterparty: bool,
    same_day_transaction_count: int,
    similar_alert_counts: Counter,
    historical_count: int,
) -> tuple[int, list[str]]:
    if historical_count < 5:
        return 0, ["insufficient_history"]

    points = 0
    factors: list[str] = []
    if amount_percentile is not None:
        if amount_percentile >= 95 or amount_percentile <= 5:
            points += 2
            factors.append("amount_percentile_extreme")
        elif amount_percentile >= 90 or amount_percentile <= 10:
            points += 1
            factors.append("amount_percentile_elevated")

    if transaction_type_count == 0:
        points += 2
        factors.append("transaction_type_unseen")
    elif transaction_type_share < 10:
        points += 1
        factors.append("transaction_type_rare")

    if new_destination_country:
        points += 1
        factors.append("new_destination_country")
    if new_counterparty:
        points += 1
        factors.append("new_counterparty")
    if same_day_transaction_count >= 10:
        points += 1
        factors.append("same_day_velocity")
    if similar_alert_counts.get("escalated", 0) > 0 and similar_alert_counts.get("dismissed", 0) == 0:
        points += 1
        factors.append("similar_escalations_without_dismissals")

    return points, factors


def _baseline_assessment(deviation_points: int, historical_count: int) -> str:
    if historical_count < 5:
        return "insufficient_data"
    if deviation_points == 0:
        return "consistent"
    if deviation_points <= 2:
        return "mild_deviation"
    return "strong_deviation"


def _alert_context(context: ToolExecutionContext) -> dict[str, Any]:
    alert_context = context.source.get_alert_context(context.scope.alert_id)
    scope = InvestigationScope.from_alert_context(alert_context)
    expected = (
        scope.alert_id,
        scope.customer_id,
        scope.account_id,
        scope.transaction_id,
    )
    actual = (
        context.scope.alert_id,
        context.scope.customer_id,
        context.scope.account_id,
        context.scope.transaction_id,
    )
    if expected != actual:
        raise ScopeViolationError("Source alert context does not match execution scope.")
    return alert_context


def _observation(
    *,
    facts: dict[str, Any],
    computed_features: dict[str, Any] | None = None,
    source_refs: list[SourceRefRecord] | None = None,
    data_completeness: DataCompleteness | None = None,
    limitations: list[ToolLimitation] | None = None,
) -> ToolObservation:
    return ToolObservation(
        facts=facts,
        computed_features=computed_features or {},
        source_refs=source_refs or [],
        data_completeness=data_completeness or DataCompleteness(),
        limitations=limitations or [],
    )


def _record_refs(
    table: str,
    key_name: str,
    records: list[dict[str, Any] | None],
) -> list[SourceRefRecord]:
    refs: list[SourceRefRecord] = []
    for record in records:
        if not record:
            continue
        key = record.get(key_name)
        if key is None:
            continue
        refs.append(SourceRefRecord(table=table, key=str(key)))
    return refs


def _context_source_refs(alert_context: dict[str, Any]) -> list[SourceRefRecord]:
    return [
        *_record_refs("alerts", "alert_id", [alert_context.get("alert")]),
        *_record_refs("compliance_rules", "rule_id", [alert_context.get("rule")]),
        *_record_refs("transactions", "transaction_id", [alert_context.get("transaction")]),
        *_record_refs("accounts", "account_id", [alert_context.get("account")]),
        *_record_refs("customers", "customer_id", [alert_context.get("customer")]),
        *_record_refs("countries", "country_code", [alert_context.get("destination_country")]),
    ]


def _as_row_args(args: BaseModel) -> RowLimitToolArgs:
    return RowLimitToolArgs.model_validate(args.model_dump())
