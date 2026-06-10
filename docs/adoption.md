# Aria Bank Adoption Guide

## Non-Negotiable Controls

- Use a read-only source database user.
- Do not add sidecar tables to the bank core schema.
- Do not let agents execute arbitrary SQL.
- Treat every agent output as a proposal until a human decides.
- Persist evidence, reasoning, validation status, and human decisions.

## Integration Steps

1. Identify the bank alert source.

   This can be a table, view, event stream, case-management API, or exported
   alert queue.

2. Map source context.

   Implement the `BankSourceRepository` protocol:

   - `get_alert_context(alert_id)`
   - `get_customer_context(customer_id)`
   - `get_case_context(case_id)`

3. Provision sidecar storage.

   Start with SQLite for local evaluation. Use a dedicated PostgreSQL database
   for a production pilot.

4. Run deterministic agents first.

   Validate that the rule and typology outputs match analyst expectations before
   introducing LLM summarization.

5. Connect human workflow.

   Feed recommendations to the bank's alert or case UI through an API, queue, or
   export. Do not write into source tables unless the bank explicitly builds a
   controlled integration path outside this project.

6. Audit.

   Review sidecar records for each recommendation:

   - Input hash.
   - Source evidence.
   - Agent reasoning.
   - Validation result.
   - Human decision.

## Deployment Shape

Recommended first pilot:

```text
Bank source DB/read API -> compliance sidecar API -> sidecar DB
                                      |
                                      v
                              officer review UI
```

Recommended production hardening:

- Private network deployment.
- Read-only credentials managed by vault.
- Sidecar database encryption.
- PII-aware logging.
- Role-based access control.
- Model and policy versioning.
- Batch and event-driven alert ingestion.
- Human decision export to the bank's system of record.

## Open-Source Maintainer Rules

- Keep source adapters narrow and explicit.
- Keep generated artifacts separate from source data.
- Prefer explainable deterministic checks for factual work.
- Let LLMs draft language, not invent facts.
- Require validation reports for all user-facing outputs.
