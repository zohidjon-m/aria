# Open AML Compliance Sidecar

An open-source, sidecar-style investigation layer for bank AML alert streams.

The project is designed around one hard constraint: a bank's core database is a
regulated source system and must not be modified. This service reads bank data
through allowlisted, read-only adapters and stores all agent outputs in a
separate sidecar database.

## What This Builds

The system adds automated investigation support on top of an existing
transaction-monitoring system:

- Triage recommendations for incoming alerts.
- Typology-specific investigation signals for structuring, velocity,
  geography, sanctions, and PEP risk.
- Human-readable customer risk scoring.
- Draft SAR narratives for human review.
- Factual validation before recommendations, scores, or drafts are exposed.
- Append-only sidecar records for evidence, agent runs, validation reports,
  recommendations, risk scores, SAR drafts, and human decisions.

Agents propose. Humans decide. The bank source database stays read-only.

## Architecture Choice

We considered three implementation models:

1. Direct agent-to-bank-database app.
   This is simple, but it is not acceptable for bank adoption because it mixes
   generated artifacts with source data and relies too much on prompt or code
   discipline to prevent writes.

2. Microservices for each agent.
   This is scalable, but it creates high operational burden for the first
   open-source version: distributed tracing, service discovery, versioned
   contracts, queue semantics, and several deployment units before the data
   contract has stabilized.

3. Modular sidecar monolith.
   One deployable service with strict internal boundaries: source adapters,
   sidecar persistence, agent workflows, typology modules, validation, and API.

The chosen approach is option 3. It is the best first production-minded
architecture because it gives banks a small adoption footprint while preserving
the boundaries needed to split agents into workers or services later.

See [docs/adr-001-sidecar-monolith.md](docs/adr-001-sidecar-monolith.md).

## Repository Layout

```text
src/compliance_agent/
  adapters/          Read-only bank adapters and sidecar persistence
  agents/            Triage, investigation, risk, SAR, validation logic
  api.py             FastAPI app factory
  config.py          Environment-driven settings
  domain.py          Shared domain objects
  orchestrator.py    Agent workflow coordinator
docs/
  architecture.md
  adoption.md
  data-contract.md
sql/
  sidecar_schema.sql
tests/
  test_agents.py
scripts/
  smoke_test.py
```

The old `backend`, `frontend`, and `mcp_server` folders are historical and are
not the active implementation.

## Quick Start

Run the smoke test with the built-in demo source repository:

```bash
python scripts/smoke_test.py
```

Run unit tests:

```bash
python -m unittest discover -s tests
```

Run the API in demo mode:

```bash
python scripts/run_demo_api.py --port 8000
```

Use PowerShell syntax if needed:

```powershell
python scripts\run_demo_api.py --port 8000
```

Then call:

```bash
curl -X POST http://localhost:8000/api/alerts/1001/triage
curl -X POST http://localhost:8000/api/customers/501/risk-score
curl -X POST http://localhost:8000/api/cases/9001/sar-draft
```

## Bank Integration

For a real bank deployment:

1. Create a database user with read-only privileges only.
2. Configure `BANK_SOURCE_DSN` with that user's connection string.
3. Configure `SIDECAR_DB_PATH` or replace `SidecarStore` with a managed
   sidecar PostgreSQL implementation.
4. Map the bank's source tables to the read-only source adapter methods.
5. Keep all generated records in the sidecar database.

The current reference adapter assumes the schema described by
[docs/data-contract.md](docs/data-contract.md) and the demo DDL in
[`scheme.sql`](scheme.sql).

## Environment

```text
DEMO_MODE=true
BANK_SOURCE_DSN=postgresql://readonly_user:password@host:5432/bank_core
SIDECAR_DB_PATH=data/sidecar.sqlite3
```

## API

- `GET /health`
- `POST /api/alerts/{alert_id}/triage`
- `POST /api/customers/{customer_id}/risk-score`
- `POST /api/cases/{case_id}/sar-draft`
- `GET /api/sidecar/runs/{run_id}`

All outputs include a validation report. A failed validation means the output
must be blocked or reviewed as unsupported.
