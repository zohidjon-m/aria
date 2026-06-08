# Agent Intelligence Implementation Plan

## Goal

Upgrade the AML sidecar from fixed scoring workflows into bounded, dynamic
investigation agents.

The target design is:

```text
alert
-> scoped evidence pack
-> cheap deterministic pre-screen
-> dynamic typology routing
-> bounded plan/act/observe loop
-> allowlisted factual tools
-> grounded final reasoning
-> validation gate
-> sidecar audit trail
-> human decision
```

The safety boundary remains deterministic. The intelligence lives inside that
boundary.

## Non-Negotiable Contracts

- Agents never write to the bank source database.
- Agents never run arbitrary SQL.
- Planner-selected tools must be allowlisted.
- Tool arguments must be schema-validated and bounded.
- The runtime controls entity scope; the planner cannot read arbitrary IDs.
- Graph tracing may widen scope only by following fetched transaction edges.
- Tool outputs contain facts, computed features, source refs, data completeness,
  and limitations. They do not contain narrative.
- Final claims and reasoning must both be source-referenced.
- Confidence is computed deterministically by the runtime, not trusted from an
  LLM.
- Humans make final compliance decisions.

## Phase 1: Tool Registry And Observation Contract

Create a tool registry used by both heuristic and LLM planners.

Each tool must define:

- name
- purpose
- per-tool input schema
- numeric bounds
- required runtime scope
- output schema
- source reference behavior

Tool response shape:

```json
{
  "facts": {},
  "computed_features": {},
  "source_refs": [],
  "data_completeness": {
    "lookback_days_requested": 180,
    "lookback_days_available": 140,
    "missing_segments": []
  },
  "limitations": []
}
```

Initial tools:

- `get_alert_context`
- `get_customer_profile`
- `get_recent_transactions`
- `get_prior_alerts`
- `get_open_cases`
- `screen_sanctions_pep`
- `compute_behavioral_baseline`
- `run_structuring_check`
- `run_velocity_check`
- `run_geography_check`
- `trace_money_flow`

## Phase 2: Entity Scope Control

The runtime injects scoped entity IDs into tool calls.

Rules:

- Alert investigations are scoped to the alert customer.
- The planner cannot provide arbitrary `customer_id`, `account_id`, or
  `transaction_id`.
- Tool schemas reject unbounded arguments.
- Suggested defaults:
  - `lookback_days <= 365`
  - `max_hops <= 4`
  - `max_rows <= configured_limit`

Graph tracing is the deliberate exception. It may expand scope only through
observed `counterparty_account_id` edges already present in fetched evidence.

## Phase 3: Behavioral Baseline Tool

Build customer-relative analysis before adding LLM planning.

The baseline tool should compute:

- amount percentile for this customer
- cash amount percentile
- customer `cash_pct`
- average, median, and max transaction size
- prior similar alert count
- prior similar dismissal/escalation count
- same-day transaction count
- usual transaction types
- usual countries
- new country flag
- new counterparty flag
- baseline assessment:
  - `consistent`
  - `mild_deviation`
  - `strong_deviation`

Example target reasoning:

```text
The transaction is a 9,500 USD cash deposit. For this customer, cash activity is
80% of observed transactions, the median cash transaction is 9,200 USD, and this
amount is at the 61st percentile. This is consistent with the customer's
established cash baseline.
```

## Phase 4: Tiered Pre-Screen Gate

Do not run the full ReAct loop on every alert.

The deterministic gate uses alert context, behavioral baseline, and obvious
typology signals to classify:

- `obvious_clear`
- `obvious_escalate`
- `ambiguous`

Only `ambiguous` alerts enter the expensive dynamic loop.

This preserves cost and latency while focusing deeper reasoning on the uncertain
middle.

## Phase 5: Dynamic Typology Router

Run the typology router before planning.

The router is not a planner-callable tool. It is a runtime control step that
narrows the tool registry for the current run.

Example output:

```json
{
  "activated": ["structuring", "velocity"],
  "skipped": ["geography", "sanctions"],
  "reasons": {
    "structuring": "Cash amount is near the reporting threshold.",
    "velocity": "Multiple same-day cash transactions are present.",
    "geography": "No destination country is present."
  }
}
```

If geography is skipped, `run_geography_check` must not be available to the
planner in that run.

## Phase 6: ReAct Runtime With Heuristic Planner

Implement the bounded plan/act/observe loop with a heuristic planner first.

The heuristic planner is a permanent deployment mode, not throwaway scaffolding.
It supports banks that are air-gapped or cannot use external LLMs.

Loop:

```text
observe
form hypothesis
choose allowed tool
act
observe result
update hypothesis
repeat
final recommendation
```

Runtime controls:

- max steps
- max tool calls
- repeated tool-call detection
- no-progress detection
- per-agent allowed dispositions
- persisted trace for every step

Stop reason mapping:

| Stop reason | Safe disposition |
| --- | --- |
| `completed` | use final recommendation |
| `critical_signal_found` | `escalate` |
| `max_steps_exhausted` | `investigate` |
| `tool_error` | `investigate` |
| `schema_error` | `investigate` |
| `insufficient_evidence` | `investigate` |
| `no_progress` | `investigate` |

An exhausted or inconclusive loop must never produce `likely_false_positive`.

## Phase 7: LLM Planner Behind The Same Interface

Add LLM planning after the heuristic planner works.

The LLM can:

- choose the next allowed tool
- generate hypotheses
- compare explanations
- explain why it chose a tool
- draft final reasoning from evidence

The LLM cannot:

- assert facts without source refs
- choose arbitrary entity IDs
- run SQL
- mutate source data
- decide final human outcome
- self-certify confidence

Planner output must be strict JSON and JSON-schema validated. Malformed output
is a runtime error.

Example planner action:

```json
{
  "thought": "Need to test whether the cash alert is normal for this customer.",
  "next_tool": "compute_behavioral_baseline",
  "tool_args": {
    "lookback_days": 180
  },
  "stop": false
}
```

## Phase 8: Graph Tracing Tool

Use `transactions.counterparty_account_id` to trace money movement.

Capabilities:

- trace up to configured hops
- detect rapid pass-through
- detect circular flows
- detect fan-out
- detect many-to-one aggregation
- detect high-risk country endpoints
- detect links to flagged accounts/customers
- detect links to open cases

Output shape:

```json
{
  "paths": [],
  "signals": {
    "rapid_pass_through": true,
    "cycle_detected": false,
    "high_risk_endpoint": true,
    "linked_alert_count": 2
  },
  "source_refs": []
}
```

Graph tracing widens the read surface, so adopters must explicitly understand
that AML graph investigation may read linked accounts and customers reached via
transaction edges.

## Phase 9: Grounded Final Output And Validation

Final output must validate both claims and reasoning.

Reasoning is structured, not free text:

```json
{
  "statement": "Transaction amount is consistent with the customer's cash baseline.",
  "source_refs": []
}
```

The validator checks every source ref against retrieved evidence. Unsupported
claims or reasoning lines block the output from being treated as validated.

## Phase 10: Deterministic Confidence Engine

Confidence is computed by the runtime from controlled signals:

- baseline assessment
- evidence completeness
- number of corroborating typology signals
- prior similar alert outcomes
- graph red flags
- sanctions/PEP certainty
- data limitations
- loop stop reason

The LLM may explain uncertainty, but it does not set the confidence value.

## Phase 11: Sidecar Trace Persistence

Persist the investigation spine in queryable sidecar tables.

Add or extend sidecar persistence for:

- `agent_steps`
- `tool_calls`
- `observations`
- `hypotheses`
- `typology_routes`
- `baseline_snapshots`
- `money_flow_paths`
- `runtime_versions`

Persist version metadata:

- `planner_type`
- `model_id`
- `prompt_version`
- `tool_registry_version`
- `runtime_bounds`
- `input_hash`

Add idempotency using:

```text
subject_id + input_hash + planner_type + prompt_version + tool_registry_version
```

The orchestrator can then return a cached trace or force a rerun intentionally.

## Phase 12: Test Plan

Deterministic tests come first.

Required tests:

- tool schemas reject unbounded args
- planner cannot call unknown tools
- planner cannot read unrelated customer IDs
- repeated tool call is blocked
- max steps maps to `investigate`
- reasoning without source refs fails validation
- 9,500 USD high-cash baseline recommends dismiss
- 9,500 USD low-cash baseline routes to structuring
- router narrows available tools
- graph tracing follows allowed edges only
- graph tracing respects max hops
- heuristic planner works with no LLM
- LLM planner contract is tested with mocked responses only

No live LLM calls should run in CI.

## Final Build Order

1. Tool registry, schemas, and bounded args.
2. Entity scope control.
3. Behavioral baseline tool.
4. Deterministic pre-screen gate.
5. Typology router that narrows available tools.
6. ReAct runtime with permanent heuristic planner.
7. LLM planner behind the same interface.
8. Graph tracing tool.
9. Sidecar trace persistence and version metadata.
10. Grounded reasoning validation.
11. Deterministic confidence engine.
12. Full test suite.
