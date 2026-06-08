# Agent Intelligence Progress And Completion Notes

This file tracks what has been completed from
`docs/agent-intelligence-plan.md`, what exists as foundation work, and what is
still pending.

## Current Status

The project has a strong sidecar foundation and the first four phases of the
dynamic intelligence plan are implemented.

Triage now runs a deterministic pre-screen gate before the legacy fixed scoring
agent. Obvious false positives and obvious escalations are handled through the
gate, while ambiguous alerts fall back to the existing triage agent. The repo
also has a planner-facing, scoped tool registry, observation contract,
first-class entity scope guard, and customer-relative behavioral baseline tool.
It does not yet have a bounded ReAct runtime, runtime typology routing, LLM
planner, or multi-hop graph tracing tool.

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

Partially completed.

Notes:

- The validation agent checks that claims cite source evidence.
- The new plan requires validation to also cover structured reasoning lines.
- Current reasoning is still a list of strings and is not source-ref validated.

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
| Dynamic typology router | Not started | Typologies exist but are not routed to narrow available tools. |
| ReAct runtime with heuristic planner | Not started | No plan/act/observe loop exists yet. |
| LLM planner behind same interface | Not started | No LLM planner exists in the new sidecar implementation. |
| Graph tracing tool | Partially completed | Phase 2 records immediate `TrustedGraphEdge` facts when present. Multi-hop tracing remains Phase 8. |
| Sidecar trace persistence | Not started | Current sidecar stores results, not step-level traces. |
| Grounded reasoning validation | Not started | Claims are validated; reasoning is not yet structured or validated. |
| Deterministic confidence engine | Not started | Current agents compute confidence internally; no shared calibrated confidence engine exists. |
| Expanded test suite | Partially completed | Phase 1 registry/observation tests, Phase 2 scope-control tests, Phase 3 baseline tests, and Phase 4 pre-screen gate tests exist. Later phase tests remain pending. |

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

Start Phase 5:

1. Add a runtime typology router before planning.
2. Use alert context, baseline facts, and obvious typology signals to activate
   only relevant typology tool groups.
3. Keep the router deterministic and separate from planner-callable tools.

Only after the router is tested should the bounded ReAct runtime be introduced.
