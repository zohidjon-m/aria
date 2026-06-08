# Agent Intelligence Progress And Completion Notes

This file tracks what has been completed from
`docs/agent-intelligence-plan.md`, what exists as foundation work, and what is
still pending.

## Current Status

The project has a strong sidecar foundation and phases 1-7 of the dynamic
intelligence plan are implemented for the alert triage path.

Triage now runs a deterministic pre-screen gate before dynamic investigation.
Obvious false positives and obvious escalations are handled through the gate,
while ambiguous alerts enter a bounded ReAct runtime with routed tools. The
heuristic planner remains the default offline planner, and an optional LLM
planner is available behind the same planner interface with strict mocked
contract tests. The repo still does not have a multi-hop graph tracing tool,
queryable trace tables or a shared deterministic confidence engine.

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
- Later phases still require a broader deterministic test suite for planning,
  routing, behavioral baselines, graph tracing, grounded reasoning, and
  confidence.

Relevant files:

- `tests/test_agents.py`
- `tests/test_phase1_tools.py`
- `tests/test_phase2_scope.py`
- `tests/test_phase3_baseline.py`
- `tests/test_phase4_pre_screen.py`

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
| Sidecar trace persistence | Partially completed | Phase 6 persists runtime steps inside result details; first-class queryable trace tables remain pending. |
| Grounded reasoning validation | Completed | `AgentResult.reasoning` now uses source-referenced reasoning records and the validator checks reasoning statements with the same evidence rule as claims. |
| Deterministic confidence engine | Not started | Current agents compute confidence internally; no shared calibrated confidence engine exists. |
| Expanded test suite | Partially completed | Phase 1 registry/observation tests, Phase 2 scope-control tests, Phase 3 baseline tests, Phase 4 pre-screen gate tests, Phase 5 typology-router tests, Phase 6 runtime-control tests, Phase 7 mocked LLM-planner tests, Phase 8 graph-tracing tests, and Phase 9 grounded-reasoning tests exist. Later phase tests remain pending. |

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

Start Phase 10:

1. Add a shared deterministic confidence engine.
2. Compute confidence from controlled signals such as evidence completeness,
   baseline fit, typology corroboration, graph red flags, data limitations, and
   stop reason.
3. Remove agent-local confidence formulas where the shared engine applies.
