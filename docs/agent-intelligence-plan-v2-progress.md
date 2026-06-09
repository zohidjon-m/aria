# Agent Intelligence Plan V2 Progress

This file tracks implementation progress for `docs/agent-intelligence-plan-v2.md`
so future agents can continue from the current state without rediscovering what
has already been completed.

## Current Status

V2 Phase 1 through Phase 5 are implemented for the contract-first proof of
concept, including a focused backend/frontend connection for the Phase 2 live
MCP runtime, a formal Phase 3 bank-facing MCP contract specification, and Phase
4 live MCP workflow adapters for triage, investigation, risk scoring, and SAR
drafting, plus Phase 5 API/UI review surfaces for officer decisions and
explicit audited export records.

The project now has shared Phase 1 contracts, generated JSON schemas, a
read-only reference MCP server, deterministic demo fixtures, a live/mockable MCP
agent loop, a manual live demo script, an explicit live-runtime state machine,
a replayable runtime event ledger, fail-safe terminal stop behavior, and
CI-safe mocked tests. The sidecar trace API now exposes Phase 2 runtime events,
the backend has a separate live MCP triage launch endpoint, and the frontend can
run live MCP triage without replacing deterministic agent triage. Phase 3 now
defines the portable bank MCP contract, read/write/proposal tool catalogs,
policy and RBAC decisions, audit events, and graph scope expansion behavior.
Phase 4 connects the live LLM planner to workflow-specific sidecar outputs while
keeping final risk scores deterministic and SAR drafts evidence-grounded. Phase
5 connects those workflows to backend launch/review endpoints, sidecar
human-decision and export records, runtime configuration, and minimal frontend
entrypoints on alert, customer, and case pages.

The live cloud LLM demo has not been executed in this session. It is available
as a manual operator step because it requires a configured demo PostgreSQL
database, the `mcp` package, `LLM_API_KEY`, and `LLM_MODEL`.

## Phase 1 Completed

Phase 1 from the V2 plan is complete for implementation and CI-safe validation.

Completed requirements:

- Local reference MCP server backed by the demo schema path.
- Demo script for an OpenAI-compatible live LLM endpoint.
- Single agent run flow over the reference MCP tool boundary.
- Dynamic LLM tool choice in the live/mockable agent loop.
- Hypothesis updates after tool observations.
- Evidence-grounded final proposal shape.
- Human-review output only; no automatic dismissal or SAR filing.
- Live LLM demo excluded from CI by default.

Minimum Phase 1 MCP read tools implemented:

- `get_customer_profile`
- `get_transaction_history`
- `get_behavioral_baseline`
- `get_prior_alerts`
- `get_case_history`
- `trace_counterparty_graph`
- `screen_sanctions_pep`
- `get_similar_alerts`
- `get_compliance_rule`

Minimum demo scenarios are represented in deterministic fixtures and mocked
tests:

- Clean false-positive candidate.
- Hard-red-flag escalation candidate.
- Ambiguous graph investigation candidate.

## Phase 2 Completed

Phase 2 from the V2 plan is complete for implementation and CI-safe validation
on the live MCP proof-of-concept path.

Completed requirements:

- Explicit runtime states for the live MCP agent:
  `created`, `context_loaded`, `planning`, `tool_requested`,
  `tool_executed`, `observing`, `revising`, `validating`, `proposed`, and
  `failed_safe`.
- Append-only runtime events for planning, tool request, tool response,
  observation, hypothesis revision, validation, and terminal proposal/fail-safe
  outcomes.
- Terminal stop reasons on every proposal:
  `completed`, `critical_signal_found`, `insufficient_evidence`,
  `tool_denied`, `tool_error`, `schema_error`, `no_progress`,
  `budget_exhausted`, and `timeout`.
- Fail-safe mapping for incomplete evidence, malformed model output, tool
  denial, tool error, repeated tool calls, budget exhaustion, and timeout.
- Critical signal mapping to `escalate`.
- Runtime bounds now include a cost budget field. The current OpenAI-compatible
  provider does not return token usage, so metered cost is recorded as zero
  with the budget policy documented in the runtime event ledger.
- Persisted sidecar proposal details now include replayable runtime events
  without requiring new sidecar tables.
- Sidecar trace responses now expose `runtime_events`, `terminal_state`,
  `stop_reason`, and a Phase 1 proposal summary when present.
- Backend exposes a separate live MCP launch path at
  `POST /api/agent-runs/live-mcp-triage` without changing the existing
  deterministic `POST /api/agent-runs/triage` behavior.
- Frontend alert details now offer separate `Run Agent Triage` and
  `Run Live MCP` actions, and the proposal/trace UI renders Phase 2 terminal
  metadata and ordered runtime events when available.

## Phase 3 Completed

Phase 3 from the V2 plan is complete as a contract specification milestone.
Executable bank-write MCP tools are still intentionally not enabled.

Completed requirements:

- Formal bank-facing MCP contract document.
- Phase 3 request and response envelope schemas.
- Phase 3 tool metadata schema.
- Phase 3 policy/RBAC decision schema.
- Phase 3 audit event schema.
- Phase 3 read-tool, bank-write, and sidecar-only write/proposal catalog.
- RBAC denial behavior for structured denied responses.
- Audit behavior for success, denial, partial response, and error.
- Bounded scope expansion policy for `trace_counterparty_graph`.
- Contract examples for every Phase 3 tool in `phase3_tool_catalog.json`.

Phase 3 intentionally preserves the existing Phase 1 read-only MCP server and
the Phase 2 live MCP runtime allowlist.

## Phase 4 Completed

Phase 4 from the V2 plan is complete for demo-mode implementation and CI-safe
mocked validation.

Completed requirements:

- Triage workflow can run through the live MCP LLM planner and persist
  human-review outputs.
- Investigation workflow uses the same bounded plan, query, observe, revise
  runtime and maps observed graph/screening/typology evidence into
  `open_case`, `continue_investigation`, or `return_to_triage` proposals.
- Risk scoring workflow lets the LLM gather evidence through governed MCP read
  tools, then computes the final score through deterministic policy
  `phase4_live_mcp_workflow_policy_v1`.
- Risk scoring records factors, weights, policy version, confidence, and a
  human-override placeholder.
- SAR drafting workflow assembles draft narrative sentences only from retrieved
  MCP facts and officer-entered context.
- SAR drafting records sentence-level evidence links, missing required fields,
  SAR confidentiality, human review requirement, and no autonomous filing.
- All material Phase 4 workflow outputs remain proposals requiring human
  review.

Phase 4 does not register executable Phase 3 write tools and does not replace
the existing deterministic backend triage endpoint.

## Phase 5 Completed

Phase 5 from the V2 plan is complete for product/API integration and CI-safe
mocked validation.

Completed requirements:

- Backend exposes unified live workflow launch at
  `POST /api/agent-runs/live-mcp` for triage, investigation, risk scoring, and
  SAR drafting.
- Existing `POST /api/agent-runs/live-mcp-triage` remains as a compatibility
  wrapper over the unified triage workflow.
- Backend exposes run review, trace, human-decision, export, and non-secret live
  MCP configuration endpoints.
- Reference repository scope helpers now support alert, customer, and case
  workflow scopes.
- Sidecar persistence now stores Phase 4 runtime versions, trace steps, tool
  calls, observations, hypotheses, baseline snapshots, graph paths, human
  decisions, and explicit bank export records.
- Human decisions remain separate from agent proposals.
- Bank exports are explicit audited sidecar/backend records only; they do not
  mutate source-bank data.
- SAR draft decisions/exports require `can_file_sar`; other human decisions and
  exports require `can_manage_cases`.
- Frontend alert, customer, and case pages can start live workflow reviews and
  render normalized officer-facing output with decision/export controls.

Phase 5 does not enable executable MCP bank-write tools and does not file SARs
autonomously.

## Implemented Artifacts

Shared contracts:

- `src/compliance_agent/contracts/`
- `contracts/agent_run_request.schema.json`
- `contracts/agent_proposal.schema.json`
- `contracts/mcp_request_envelope.schema.json`
- `contracts/mcp_response_envelope.schema.json`
- `contracts/phase1_tool_catalog.json`
- `contracts/phase3_mcp_request_envelope.schema.json`
- `contracts/phase3_mcp_response_envelope.schema.json`
- `contracts/phase3_tool_metadata.schema.json`
- `contracts/phase3_policy_decision.schema.json`
- `contracts/phase3_audit_event.schema.json`
- `contracts/phase3_scope_expansion_policy.schema.json`
- `contracts/phase3_tool_catalog.json`
- `docs/phase1-contracts.md`
- `docs/mcp-contract-phase3.md`
- Runtime state and event contract fields in `AgentProposal`.

Reference MCP server:

- Removed old `mcp_server/db.py`.
- Replaced the historical SQL-query MCP server with the new read-only Phase 1
  reference MCP server.
- `mcp_server/server.py` exposes the Phase 1 MCP tools.
- `mcp_server/service.py` validates request envelopes, enforces scope, bounds
  arguments, rejects forbidden entity jumps, and returns structured MCP response
  envelopes.
- `mcp_server/repository.py` owns parameterized PostgreSQL reads against the
  `scheme.sql` table contract.
- `mcp_server/repository.py` now includes alert, customer, and case scope
  helpers for Phase 5 workflow launch.
- `mcp_server/fixtures.py` loads deterministic Phase 1 demo fixtures.

Live/mockable agent loop:

- `src/compliance_agent/agents/live_mcp_demo.py`
- Supports strict planner output schema.
- Uses MCP request and response contracts.
- Uses a local state-machine helper to enforce allowed runtime transitions.
- Emits replayable runtime events for every important loop action.
- Converts terminal proposals into existing sidecar-compatible `AgentResult`
  records.
- Fails safe to `needs_investigation` on insufficient evidence, schema errors,
  tool errors, tool denial, repeated calls, budget exhaustion, or timeout.
- Accepts configured prompt, tool registry, and policy versions while preserving
  existing defaults.

Phase 4 workflow adapters:

- `src/compliance_agent/agents/live_mcp_workflows.py`
- Wraps the existing `LiveMCPAgent` for triage, investigation, risk scoring,
  and SAR drafting demo workflows.
- Converts live MCP observations into existing `AgentResult` records for
  sidecar persistence and validation.
- Keeps final risk scoring deterministic and SAR drafting evidence-grounded.

Demo and dependency updates:

- `scripts/run_live_mcp_demo.py`
- `scripts/export_phase1_contracts.py`
- `scripts/export_phase3_contracts.py`
- Added `mcp` to `pyproject.toml`.
- Added `mcp` to `requirements.txt`.

Tests added:

- `tests/test_phase1_contracts.py`
- `tests/test_phase1_mcp_server.py`
- `tests/test_phase1_live_mcp_agent.py`
- `tests/test_phase2_live_mcp_runtime.py`
- `tests/test_phase3_mcp_contracts.py`
- `tests/test_phase4_live_mcp_workflows.py`
- `tests/test_phase5_product_surface.py`
- `tests/test_agent_runs.py` coverage for the live MCP backend route and
  Phase 2/Phase 5 trace and launch normalization.

Backend/frontend Phase 2 integration:

- `backend/routes/agent_runs.py` exposes the separate live MCP triage endpoint.
- `src/compliance_agent/adapters/sidecar_store.py` normalizes Phase 2 runtime
  event data into trace responses.
- `frontend/src/api/client.js` adds the live MCP triage client call.
- `frontend/src/pages/AlertDetailPage.jsx` adds the separate live MCP action
  and preserves the existing deterministic triage action.
- `frontend/src/components/AgentProposalPanel.jsx` displays Phase 2 runtime
  metadata when present.
- `frontend/src/components/AgentTraceDrawer.jsx` renders ordered runtime events
  and safely formats object-valued step details.

Backend/frontend Phase 5 integration:

- `backend/routes/agent_runs.py` exposes unified live workflow launch, config,
  review, human-decision, and explicit export endpoints.
- `src/compliance_agent/adapters/sidecar_store.py` persists Phase 4 replay
  records plus human decisions and bank export records.
- `src/compliance_agent/config.py` exposes runtime budget, prompt version, tool
  registry version, and policy version settings.
- `frontend/src/api/client.js` adds unified workflow, config, review, decision,
  and export client calls.
- `frontend/src/components/AgentReviewPanel.jsx` renders officer-facing
  recommendation, confidence, evidence, reasoning, limitations, missing data,
  stop reason, required human action, audit IDs, decisions, and export history.
- `frontend/src/pages/AlertDetailPage.jsx`,
  `frontend/src/pages/CustomerRiskPage.jsx`, and
  `frontend/src/pages/CaseWorkspacePage.jsx` add minimal live workflow review
  entrypoints.

## Verification

CI-safe verification completed:

```text
python -m unittest discover -s tests
```

Result:

```text
Ran 195 tests
OK
```

Focused Phase 5 product-surface validation completed:

```text
python -m unittest tests.test_agent_runs tests.test_phase4_live_mcp_workflows tests.test_phase5_product_surface
```

Result:

```text
Ran 24 tests
OK
```

Focused Phase 3/Phase 4 contract and live workflow validation completed:

```text
python -m unittest tests.test_phase1_contracts tests.test_phase1_mcp_server tests.test_phase2_live_mcp_runtime tests.test_phase3_mcp_contracts tests.test_phase4_live_mcp_workflows
```

Result:

```text
Ran 30 tests
OK
```

Demo CLI load check completed:

```text
python scripts/run_live_mcp_demo.py --help
```

Result:

```text
Help output loaded successfully.
```

Demo smoke test completed:

```text
python scripts/smoke_test.py
```

Result:

```text
triage: escalate passed
risk: critical passed
sar: draft_for_human_review passed
```

Frontend validation completed with the bundled Node runtime because `npm` was
not available on PATH in this environment:

```text
node node_modules/eslint/bin/eslint.js .
node node_modules/vite/bin/vite.js build
```

Result:

```text
lint passed
vite build completed successfully
```

## Known Limitations

- The live cloud LLM demo was not executed in this session.
- Manual live demo execution requires a configured demo PostgreSQL database.
- Manual live demo execution requires the `mcp` package to be installed in the
  runtime environment.
- Manual live demo execution requires `LLM_API_KEY` and `LLM_MODEL`.
- Phase 1 MCP tools are intentionally read-only.
- Phase 2 replayability is stored in the proposal/sidecar JSON details. No
  dedicated event-ledger sidecar table is introduced yet.
- Phase 2 cost-budget enforcement records zero metered cost because the current
  provider wrapper does not expose token usage metadata.
- Phase 2 is scoped to the live MCP proof-of-concept path, not a full rebuild
  of the older alert-triage ReAct runtime.
- Backend live MCP triage requires configured source DB and LLM environment
  values; tests mock these dependencies and do not make live LLM calls.
- The backend live MCP route does not auto-load Phase 1 fixtures, so it will not
  mutate the source database just to start a live run.
- Executable MCP write tools are not enabled yet. Phase 3 defines the
  bank-system write catalog, sidecar-only write/proposal catalog, RBAC policy,
  and audit behavior as contract artifacts.
- Phase 5 export records are explicit POC audit/export records. They do not
  write to bank systems of record or file SARs.
- The frontend shows runtime events only when they are present in persisted
  output or sidecar trace records; older/non-live runs remain compatible but may
  have no event ledger to render.
- No production false-positive reduction claim is supported yet. That remains
  blocked until the evaluation harness exists.

## Remaining V2 Work

| Phase | Status | Next work |
| --- | --- | --- |
| Phase 1: Live LLM and reference MCP proof of concept | Complete for implementation and CI-safe validation | Run manual live demo with configured DB and LLM credentials. |
| Phase 2: Agent runtime state machine | Complete for implementation, backend/frontend connection, and CI-safe validation | Run manual live MCP triage through the backend/UI with configured DB and LLM credentials. |
| Phase 3: MCP contract specification | Complete for contract artifacts and CI-safe validation | Implement executable write/proposal tools only in later phases after policy and product workflow integration. |
| Phase 4: LLM-backed agent capabilities | Complete for demo-mode workflow adapters and CI-safe validation | Run manual workflow demos with configured DB and LLM credentials. |
| Phase 5: Connections and product surface | Complete for API/UI integration and CI-safe validation | Run manual end-to-end UI review with configured DB and LLM credentials. |
| Phase 6: Evaluation harness | Pending | Add historical/synthetic replay, metrics, benchmark reports, and false-positive/false-negative analysis. |
| Phase 7: Security, governance, and production controls | Pending | Add MCP auth requirements, token audience validation, prompt-injection tests, model governance, monitoring, and production readiness mapping. |

## Handoff Notes For Future Agents

- Do not mutate `docs/agent-intelligence-plan-v2.md` when updating progress.
- Use this file for progress updates after each V2 phase.
- Treat `contracts/` as the backend/frontend/agent-service integration source
  of truth for Phase 1.
- Keep the Phase 1 MCP server read-only. Phase 3 defines write/proposal
  catalogs and authorization behavior, but does not register executable
  bank-write MCP tools.
- Keep bank workflow writes in the backend API for now.
- Do not claim the live cloud demo has run unless it has been executed with a
  configured demo database and live LLM credentials.
- Continue to keep live LLM calls out of default CI.
- Keep `POST /api/agent-runs/triage` deterministic unless explicitly asked to
  replace it; live MCP currently has its own launch endpoint.
