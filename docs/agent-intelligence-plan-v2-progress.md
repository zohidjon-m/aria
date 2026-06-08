# Agent Intelligence Plan V2 Progress

This file tracks implementation progress for `docs/agent-intelligence-plan-v2.md`
so future agents can continue from the current state without rediscovering what
has already been completed.

## Current Status

V2 Phase 1 is implemented for the contract-first proof of concept.

The project now has shared Phase 1 contracts, generated JSON schemas, a
read-only reference MCP server, deterministic demo fixtures, a live/mockable MCP
agent loop, a manual live demo script, and CI-safe mocked tests.

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

## Implemented Artifacts

Shared contracts:

- `src/compliance_agent/contracts/`
- `contracts/agent_run_request.schema.json`
- `contracts/agent_proposal.schema.json`
- `contracts/mcp_request_envelope.schema.json`
- `contracts/mcp_response_envelope.schema.json`
- `contracts/phase1_tool_catalog.json`
- `docs/phase1-contracts.md`

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
- `mcp_server/fixtures.py` loads deterministic Phase 1 demo fixtures.

Live/mockable agent loop:

- `src/compliance_agent/agents/live_mcp_demo.py`
- Supports strict planner output schema.
- Uses MCP request and response contracts.
- Converts terminal proposals into existing sidecar-compatible `AgentResult`
  records.
- Fails safe to `needs_investigation` on schema errors, tool errors, tool
  denial, repeated calls, or budget exhaustion.

Demo and dependency updates:

- `scripts/run_live_mcp_demo.py`
- `scripts/export_phase1_contracts.py`
- Added `mcp` to `pyproject.toml`.
- Added `mcp` to `requirements.txt`.

Tests added:

- `tests/test_phase1_contracts.py`
- `tests/test_phase1_mcp_server.py`
- `tests/test_phase1_live_mcp_agent.py`

## Verification

CI-safe verification completed:

```text
python -m unittest discover -s tests
```

Result:

```text
Ran 125 tests
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

## Known Limitations

- The live cloud LLM demo was not executed in this session.
- Manual live demo execution requires a configured demo PostgreSQL database.
- Manual live demo execution requires the `mcp` package to be installed in the
  runtime environment.
- Manual live demo execution requires `LLM_API_KEY` and `LLM_MODEL`.
- Phase 1 MCP tools are intentionally read-only.
- MCP write tools, RBAC write policies, and bank-system write catalogs are not
  implemented yet.
- The backend and frontend still need to be rebuilt against the new contracts;
  the historical backend imports the removed `mcp_server.db` and should not be
  treated as current.
- No production false-positive reduction claim is supported yet. That remains
  blocked until the evaluation harness exists.

## Remaining V2 Work

| Phase | Status | Next work |
| --- | --- | --- |
| Phase 1: Live LLM and reference MCP proof of concept | Complete for implementation and CI-safe validation | Run manual live demo with configured DB and LLM credentials. |
| Phase 2: Agent runtime state machine | Pending | Harden runtime states, stop reasons, event ledger, timeout/cost budgets, replay, and fail-safe behavior. |
| Phase 3: MCP contract specification | Pending | Write formal bank-facing MCP contract, including read tools, write/proposal catalogs, RBAC, audit behavior, and scope expansion rules. |
| Phase 4: LLM-backed agent capabilities | Pending | Extend live LLM planning into triage, investigation, risk scoring, and SAR drafting workflows. |
| Phase 5: Connections and product surface | Pending | Add API/UI integration for starting runs, fetching traces, reviewing proposals, recording human decisions, and exporting audited bank actions. |
| Phase 6: Evaluation harness | Pending | Add historical/synthetic replay, metrics, benchmark reports, and false-positive/false-negative analysis. |
| Phase 7: Security, governance, and production controls | Pending | Add MCP auth requirements, token audience validation, prompt-injection tests, model governance, monitoring, and production readiness mapping. |

## Handoff Notes For Future Agents

- Do not mutate `docs/agent-intelligence-plan-v2.md` when updating progress.
- Use this file for progress updates after each V2 phase.
- Treat `contracts/` as the backend/frontend/agent-service integration source
  of truth for Phase 1.
- Keep the Phase 1 MCP server read-only until Phase 3 defines write/proposal
  catalogs and authorization behavior.
- Keep bank workflow writes in the backend API for now.
- Do not claim the live cloud demo has run unless it has been executed with a
  configured demo database and live LLM credentials.
- Continue to keep live LLM calls out of default CI.
