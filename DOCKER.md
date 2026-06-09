# Running Open AML Compliance Sidecar with Docker

One command brings up the optional local demo stack: Postgres with seeded demo
data, the FastAPI demo backend plus agent sidecar, and the Vite-built frontend.

```bash
docker compose up --build
```

Then open:

- **Workbench UI** -> http://localhost:5173
- **API docs** -> http://localhost:8000/docs
- **Postgres** -> localhost:**5433** (user `postgres`, password `postgres`, db `aml_platform`)

The Postgres username and password in `docker-compose.yml` are demo-only
credentials for local evaluation. Do not reuse them for a pilot or production
environment.

To run detached and follow logs:

```bash
docker compose up --build -d
docker compose logs -f backend
```

Stop / reset:

```bash
docker compose down            # stop containers, keep data
docker compose down -v         # stop AND wipe the database volume (re-seeds next up)
```

## What happens on first start

1. **db** initializes an empty volume and applies `scheme.sql` automatically
   (mounted into `/docker-entrypoint-initdb.d`).
2. **backend** waits for Postgres, drops the schema's auto-alert / audit triggers
   (the seeder generates its own deterministic, linked alerts and the API writes
   its own audit rows), then runs `seed_database.py` **only if the DB is empty**.
3. **frontend** was built with `VITE_API_URL=http://localhost:8000` and is served
   with `vite preview` (SPA deep links work).

Re-running `docker compose up` reuses the seeded volume and skips seeding. Use
`docker compose down -v` to start fresh.

## Port conflicts

The frontend must be published on **5173** because the backend's CORS allow-list
is `http://localhost:5173`. Before `docker compose up`, stop any local dev server
on 5173 and any local backend on 8000. Postgres is on host **5433** to avoid
clashing with a local Postgres on 5432.

## Optional: enable the LLM planner

The agent uses the **heuristic** planner by default, so "Run Agent Triage" works
with no API keys. To use an LLM instead, put these in a `.env` file next to
`docker-compose.yml` (Compose reads it automatically):

```env
PLANNER_TYPE=llm
LLM_API_KEY=replace-with-your-key
LLM_MODEL=gpt-5.5
LLM_ENDPOINT=https://api.openai.com/v1/chat/completions
```
