# Open AML Compliance Sidecar

Open AML Compliance Sidecar is a public-alpha, sidecar-style investigation
layer for bank AML alert streams.

The project is built around one hard constraint: a bank's core database is a
regulated source system and must not be modified by agent outputs. The sidecar
reads bank data through allowlisted adapters and stores generated artifacts in a
separate sidecar database.

Agents propose. Humans decide. Bank source systems remain controlled by the
bank.

## What It Does

The active implementation under `src/compliance_agent` provides:

- Triage recommendations for incoming alerts.
- Typology-specific investigation signals for structuring, velocity,
  geography, sanctions, and PEP risk.
- Human-readable customer risk scoring.
- Draft SAR narratives for human review.
- Factual validation before recommendations, scores, or drafts are exposed.
- Append-only sidecar records for evidence, agent runs, validation reports,
  recommendations, risk scores, SAR drafts, and human decisions.

This project does not autonomously dismiss alerts, file SARs, change officer
permissions, or claim production false-positive reduction. It is not legal,
regulatory, compliance, or model-risk advice. Banks must validate any deployment
against their own BSA/AML, OFAC, privacy, security, model-risk, and governance
requirements.

## Architecture

The public product surface is the sidecar package:

```text
src/compliance_agent/
  adapters/          Read-only bank adapters and sidecar persistence
  agents/            Triage, investigation, risk, SAR, validation logic
  api.py             FastAPI app factory
  config.py          Environment-driven settings
  domain.py          Shared domain objects
  orchestrator.py    Agent workflow coordinator
```

The repository also includes reference tooling for evaluation and demos:

```text
backend/             Optional workbench API for the demo UI
frontend/            Optional Vite/React officer workbench demo
mcp_server/          Reference MCP-style tool server
contracts/           JSON schemas and tool catalogs
docs/                Architecture, adoption, production-readiness notes
sql/                 Sidecar schema
scripts/             Smoke tests and demo entrypoints
tests/               Unit and contract tests
```

The first version is a modular sidecar monolith. It keeps source adapters,
sidecar persistence, agent workflows, validation, and API behavior in one
deployable shape while preserving internal boundaries that can be split into
workers or services later. See
[docs/adr-001-sidecar-monolith.md](docs/adr-001-sidecar-monolith.md).

## Quick Start

Create an environment and install the project:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e . -r requirements.txt
```

On Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e . -r requirements.txt
```

Run the smoke test with the built-in demo source repository:

```bash
python scripts/smoke_test.py
```

Run the tests:

```bash
python -m unittest discover -s tests
```

Run the sidecar API in demo mode:

```bash
python scripts/run_demo_api.py --port 8000
```

Then call:

```bash
curl -X POST http://localhost:8000/api/alerts/1001/triage
curl -X POST http://localhost:8000/api/customers/501/risk-score
curl -X POST http://localhost:8000/api/cases/9001/sar-draft
```

## Demo Workbench

The optional full-stack demo starts Postgres, seeds demo data, launches the
reference backend, and serves the React workbench:

```bash
docker compose up --build
```

Then open:

- Workbench UI: http://localhost:5173
- API docs: http://localhost:8000/docs
- Demo Postgres: `localhost:5433`

The Compose credentials are for local demo use only. Do not reuse them in a
pilot or production environment. See [DOCKER.md](DOCKER.md).

## Bank Integration

For a real bank evaluation:

1. Create a source-system user with read-only privileges only.
2. Configure `BANK_SOURCE_DSN` with that user's connection string, or implement
   a bank-owned adapter/API with equivalent read-only behavior.
3. Configure `SIDECAR_DB_PATH` for local evaluation, or replace `SidecarStore`
   with managed sidecar storage for a pilot.
4. Map source tables, views, APIs, or event streams to the
   `BankSourceRepository` methods.
5. Keep generated records in sidecar storage. Do not write agent outputs back
   to source systems unless the bank builds a separate governed integration
   path with RBAC and audit.

The reference adapter assumes the schema described by
[docs/data-contract.md](docs/data-contract.md) and the demo DDL in
[`scheme.sql`](scheme.sql).

## Configuration

Environment variables are loaded from the process environment and, for local
development, `.env`.

```text
DEMO_MODE=true
BANK_SOURCE_DSN=postgresql://readonly_user:password@host:5432/bank_core
SIDECAR_DB_PATH=data/sidecar.sqlite3
TENANT_ID=demo-bank
PLANNER_TYPE=heuristic
LLM_API_KEY=
LLM_MODEL=
LLM_ENDPOINT=https://api.openai.com/v1/chat/completions
LLM_TIMEOUT_SECONDS=30
LLM_PROMPT_VERSION=phase1_live_mcp_agent_v1
MCP_TOOL_REGISTRY_VERSION=phase1_reference_mcp_v1
AGENT_POLICY_VERSION=phase1_reference_mcp_policy_v1
RUNTIME_MAX_STEPS=6
RUNTIME_MAX_TOOL_CALLS=6
RUNTIME_MAX_ROWS=100
RUNTIME_MAX_GRAPH_HOPS=4
RUNTIME_TIMEOUT_SECONDS=60
RUNTIME_MAX_COST_USD=1
```

Use `PLANNER_TYPE=heuristic` for local, no-key evaluation. Set
`PLANNER_TYPE=llm`, `LLM_API_KEY`, and `LLM_MODEL` only when you want the LLM
planner path.

## API

- `GET /health`
- `POST /api/alerts/{alert_id}/triage`
- `POST /api/alerts/{alert_id}/investigate`
- `POST /api/customers/{customer_id}/risk-score`
- `POST /api/cases/{case_id}/sar-draft`
- `GET /api/sidecar/runs/{run_id}`

All outputs include a validation report. A failed validation means the output
must be blocked or reviewed as unsupported.

## Release Status

This repository is a public alpha. Before any bank pilot, review
[docs/production-readiness.md](docs/production-readiness.md), run the full test
suite, complete a threat model, and validate behavior against bank-specific
historical alert data.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
