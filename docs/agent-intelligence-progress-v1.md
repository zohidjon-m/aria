# Agent Intelligence Progress And Completion Notes

This file tracks what has been completed from
`docs/agent-intelligence-plan.md`, what exists as foundation work, and what is
still pending.

## Current Status

The project has a strong sidecar foundation and phases 1-11 of the dynamic
intelligence plan are implemented for the alert triage path.

Triage now runs a deterministic pre-screen gate before dynamic investigation.
Obvious false positives and obvious escalations are handled through the gate,
while ambiguous alerts enter a bounded ReAct runtime with routed tools. The
heuristic planner remains the default offline planner, and an optional LLM
planner is available behind the same planner interface with strict mocked
contract tests. Multi-hop graph tracing, grounded reasoning validation, a shared
deterministic confidence engine, and first-class queryable trace tables are
implemented.

## Completed Foundation

These items were completed before the intelligence plan and are useful building
blocks for it.

### Modular Sidecar Architecture

Completed.

Notes:

- The active implementation lives under `src/compliance_agent`.
- The architecture is a modular sidecar monolith.
- Bank source data is read through adapters.
- Agent-generated artifacts are stored in sidecar persistence.
- Humans remain responsible for final decisions.

Relevant files:

- `src/compliance_agent/orchestrator.py`
- `src/compliance_agent/api.py`
- `docs/adr-001-sidecar-monolith.md`
- `docs/architecture.md`

### Read-Only Source Boundary

Partially completed.

Notes:

- `PostgresBankSourceRepository` uses allowlisted, parameterized queries.
- It opens PostgreSQL sessions in read-only mode.
- There is no arbitrary SQL tool in the new implementation.
- This is a good foundation, but the future planner still needs entity scope
  enforcement so it cannot request unrelated customer IDs.

Relevant files:

- `src/compliance_agent/adapters/postgres_source.py`
- `src/compliance_agent/adapters/source.py`

### Sidecar Persistence

Partially completed.

Notes:

- Sidecar persistence exists for agent runs, evidence, validation reports,
  recommendations, risk scores, SAR drafts, and human decisions.
- SQLite is used for local/demo mode.
- The current trace is not yet persisted as a detailed queryable spine with
  `agent_steps`, `tool_calls`, `observations`, `hypotheses`,
  `typology_routes`, `baseline_snapshots`, and `money_flow_paths`.

Relevant files:

- `src/compliance_agent/adapters/sidecar_store.py`
- `sql/sidecar_schema.sql`

### Deterministic Agents

Completed as initial baseline.

Notes:

- Triage, investigation, risk scoring, SAR drafting, and validation agents
  exist.
- The current triage agent is still fixed scoring, not a plan/act/observe
  investigator.
- This deterministic baseline should remain useful as the heuristic deployment
  mode evolves.

Relevant files:

- `src/compliance_agent/agents/triage.py`
- `src/compliance_agent/agents/investigation.py`
- `src/compliance_agent/agents/risk.py`
- `src/compliance_agent/agents/sar.py`
- `src/compliance_agent/agents/validation.py`

### Basic Typology Checks

Partially completed.

Notes:

- The code has deterministic typology checks for geography, structuring,
  velocity, sanctions, and PEP.
- There is no runtime typology router yet.
- Typology tools are not yet dynamically narrowed per run.

Relevant files:

- `src/compliance_agent/agents/typologies.py`

### Validation Gate

Completed for claims and reasoning.

Notes:

- The validation agent checks that claims and structured reasoning lines cite
  retrieved source evidence.
- Unsupported claim or reasoning references fail validation.

Relevant files:

- `src/compliance_agent/agents/validation.py`
- `src/compliance_agent/domain.py`

### API And Demo Mode

Completed for the current foundation.

Notes:

- The API exposes triage, investigation, risk scoring, SAR draft, and sidecar
  run lookup endpoints.
- Demo mode uses an in-memory source repository.
- The API was verified with a transient local run.

Relevant files:

- `src/compliance_agent/api.py`
- `src/compliance_agent/adapters/fake_source.py`
- `scripts/run_demo_api.py`
- `scripts/smoke_test.py`

### Tests

Completed for the current foundation and Phase 1 tooling.

Notes:

- Unit tests cover basic triage persistence, risk scoring, SAR draft behavior,
  and unsupported claim validation.
- Unit tests also cover the Phase 1 registry, bounded tool schemas, scoped ID
  rejection, observation contracts, minimal Phase 1 tool handlers, Phase 2
  scope policies, unsafe schema blocking, trusted graph edge recording, and
  Phase 3 behavioral baseline features.
- Unit tests cover the Phase 4 pre-screen gate classifications, live triage
  wiring, fallback behavior for ambiguous alerts, and validation of
  gate-produced recommendations.
- Later phase tests cover planning, routing, graph tracing, grounded reasoning,
  deterministic confidence behavior, and queryable trace persistence.

Relevant files:

- `tests/test_agents.py`
- `tests/test_phase1_tools.py`
- `tests/test_phase2_scope.py`
- `tests/test_phase3_baseline.py`
- `tests/test_phase4_pre_screen.py`
- `tests/test_phase10_confidence_engine.py`
- `tests/test_phase11_trace_persistence.py`
- `tests/test_phase12_acceptance.py`

Verification already run:

```text
python -m unittest discover -s tests
python scripts/smoke_test.py
python -m compileall src tests scripts
```

## Intelligence Plan Progress

| Plan phase | Status | Notes |
| --- | --- | --- |
| Tool registry and observation contract | Completed | `ToolRegistry`, `ToolDefinition`, `ToolExecutionContext`, `InvestigationScope`, `ToolObservation`, `DataCompleteness`, and `ToolLimitation` are implemented. |
| Entity scope control | Completed for tooling | `InvestigationScope` tracks root and allowed IDs, `ScopePolicy` is declared per tool, registry execution rejects planner-supplied entity IDs generically, and scope mismatch errors are controlled. Full ReAct-loop enforcement remains Phase 6. |
| Behavioral baseline tool | Completed for tooling | `compute_behavioral_baseline` now uses bounded source methods to compute percentiles, aggregates, cash share, novelty flags, similar-alert status counts, and a deterministic baseline assessment. |
| Tiered pre-screen gate | Completed | `PreScreenGate` uses scoped tool observations to classify `obvious_clear`, `obvious_escalate`, or `ambiguous`; live triage uses gate decisions and falls back to the old triage agent for ambiguous alerts. |
| Dynamic typology router | Completed for runtime | `TypologyRouter` deterministically activates typology tool groups and returns a filtered planner-facing `ToolRegistry`. |
| ReAct runtime with heuristic planner | Completed for ambiguous triage | Ambiguous pre-screen alerts now use a bounded ReAct runtime with heuristic planning, routed tools, stop-reason disposition mapping, and persisted trace details. |
| LLM planner behind same interface | Completed for planner contract | `LLMPlanner` implements the same planner protocol with strict JSON validation, routed-tool enforcement, bounded tool-arg validation, mocked tests, and optional OpenAI-compatible provider wiring. |
| Graph tracing tool | Completed for runtime | `trace_money_flow` performs bounded multi-hop traversal through source-adapter graph edge reads and detects rapid pass-through, cycles, fan-out, many-to-one aggregation, high-risk endpoints, and linked alerts/cases. |
| Sidecar trace persistence | Completed for alert triage | Triage runs now persist runtime version metadata, idempotency keys, pre-screen tool calls and observations, ReAct steps, hypotheses, typology routes, baseline snapshots, and money-flow paths in first-class sidecar tables while keeping existing JSON output details. |
| Grounded reasoning validation | Completed | `AgentResult.reasoning` now uses source-referenced reasoning records and the validator checks reasoning statements with the same evidence rule as claims. |
| Deterministic confidence engine | Completed for alert triage | `ConfidenceEngine` computes pre-screen and ReAct triage confidence from controlled runtime signals and persists an auditable `confidence_breakdown`; investigation, risk, and SAR confidence remain out of Phase 10 scope. |
| Expanded test suite | Completed | Phase 1–11 unit tests exist. A dedicated `tests/test_phase12_acceptance.py` covers all 13 Phase 12 acceptance criteria explicitly: unbounded-arg rejection, unknown-tool guard, forbidden entity-field enforcement, repeated-call detection, max-steps → investigate (never false-positive), reasoning source-ref validation, 9 500 USD high/low-cash end-to-end scenarios, router tool-narrowing, graph edge-following, max-hops truncation, heuristic-planner-only run, and mocked LLM-planner contract. No live LLM calls are made in CI. |

## Completion Notes And Design Decisions

### Keep The Heuristic Planner Permanent

The future heuristic planner should not be treated as scaffolding. It is a real
deployment mode for banks that are air-gapped, cannot use external LLMs, or want
deterministic behavior for early validation.

### Add The Gate Before The Loop

The plan must not run the expensive loop on every alert. Obvious false positives
and obvious critical escalations should be handled by a cheap deterministic
pre-screen. The dynamic loop should focus on ambiguous alerts.

### Do Not Trust Planner IDs

The runtime must inject scoped entity IDs. The planner can request a tool, but it
cannot decide to read customer `999999` during an investigation for customer
`501`.

### Exhaustion Must Fail Safe

If the loop exhausts max steps or hits a schema/tool error, the result should
default to more human attention, such as `investigate`, never
`likely_false_positive`.

### Reasoning Must Be Grounded

Claims and reasoning must follow the same validation rule. If a persisted
statement contains a factual assertion, it needs source refs.

### Confidence Must Be Runtime-Derived

LLM confidence values should not be trusted as final. Confidence should be
computed from controlled signals such as evidence completeness, baseline fit,
typology corroboration, graph red flags, and stop reason.

### Prefer Queryable Trace Tables

The sidecar should eventually store the investigation spine in first-class
tables. JSON payloads are still useful for variable details, but regulators and
operators will need to query tool calls, observations, and graph signals.

## Next Implementation Step

All 12 phases are complete. The next step is to wire the project for real bank
source data (Phase 2 entity-scope enforcement in a live PostgreSQL environment)
and run the acceptance suite against a staging database to validate the
PostgreSQL adapter paths.
