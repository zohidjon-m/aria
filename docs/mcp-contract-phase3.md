# Phase 3 MCP Contract

This contract defines the bank-facing MCP boundary for the AML agent sidecar.
It is a specification milestone only: Phase 3 documents read tools, write and
proposal catalogs, policy behavior, RBAC behavior, audit events, and graph
scope expansion. It does not enable executable bank-write MCP tools.

Generated contract artifacts live in `contracts/`:

- `phase3_mcp_request_envelope.schema.json`
- `phase3_mcp_response_envelope.schema.json`
- `phase3_tool_metadata.schema.json`
- `phase3_policy_decision.schema.json`
- `phase3_audit_event.schema.json`
- `phase3_scope_expansion_policy.schema.json`
- `phase3_tool_catalog.json`

## Request And Response Envelope

Every Phase 3 MCP tool request uses `Phase3MCPRequestEnvelope`. The request
includes tenant, officer, agent run, purpose, requested-by actor, scoped subject,
active scope, tool name, bounded `tool_args`, auth context, policy version,
idempotency key, and correlation ID.

Every response uses `Phase3MCPResponseEnvelope`. A response includes status,
structured facts, source references, data completeness, limitations, an audit
event, and policy decisions. Denied and error responses are still structured and
auditable.

The LLM may propose tool calls inside the runtime boundary, but the bank MCP
server and sidecar policy decide what executes. The LLM never supplies scoped
entity identifiers directly in `tool_args`, never grants permissions, never
files a SAR, and never dismisses an alert autonomously.

## Tool Catalog

The Phase 3 registry version is `phase3_bank_mcp_contract_v1`.

Read tools:

| Tool | Primary purpose | Required permission |
| --- | --- | --- |
| `get_customer_profile` | `triage` | `can_view_alerts` |
| `get_transaction_history` | `triage` | `can_view_alerts` |
| `get_behavioral_baseline` | `triage` | `can_view_alerts` |
| `get_prior_alerts` | `triage` | `can_view_alerts` |
| `get_case_history` | `investigation` | `can_view_alerts` |
| `trace_counterparty_graph` | `investigation` | `can_view_alerts` |
| `screen_sanctions_pep` | `investigation` | `can_view_alerts` |
| `get_similar_alerts` | `triage` | `can_view_alerts` |
| `get_compliance_rule` | `triage` | `can_view_alerts` |
| `get_officer_permissions` | `triage` | `can_view_alerts` |

Bank-system write tools:

| Tool | Required permission | Human review |
| --- | --- | --- |
| `add_alert_comment` | `can_view_alerts` | Required |
| `open_case` | `can_manage_cases` | Required |
| `link_alert_to_case` | `can_manage_cases` | Required |
| `export_human_decision` | `can_manage_cases` | Required |

Sidecar-only write or proposal tools:

| Tool | Required permission | Effect |
| --- | --- | --- |
| `record_agent_trace` | `service_identity` | Sidecar persistence |
| `propose_alert_disposition` | `service_identity` | Proposal only |
| `store_agent_risk_score` | `service_identity` | Sidecar persistence |
| `draft_regulatory_report` | `service_identity`, `can_file_sar` | Draft only |
| `record_evaluation_result` | `service_identity` | Sidecar persistence |

`draft_regulatory_report` creates a draft narrative only. SAR filing is never an
agent action.

## Policy And RBAC

Every tool requires deterministic policy evaluation. Read tools enforce tenant,
scope, purpose, bounded-argument, and RBAC policy before returning facts. Write
and proposal tools require deterministic policy approval before execution or
sidecar persistence.

RBAC decisions use these permission flags:

- `can_view_alerts`
- `can_manage_cases`
- `can_file_sar`
- `can_manage_rules`
- `can_manage_users`
- `service_identity`

Denial behavior:

- The response status is `denied`.
- `facts` is empty.
- `data_completeness.complete` is `false`.
- `limitations` explains the denial without leaking unauthorized data.
- `policy_decisions` includes `decision="deny"`, `decision_source="rbac"` or
  the applicable deterministic policy source, required permissions, granted
  permissions, and missing permissions.
- The audit event outcome is `denial`.

The agent may request a bank write, but only the bank MCP server can approve and
execute it. The sidecar may persist sidecar-only records, but only after
service-identity and deterministic sidecar policy checks pass.

## Audit Behavior

Every request and response carries a correlation ID and idempotency key. Every
response includes a `Phase3AuditEvent`.

Audit outcomes:

| Outcome | Response status | Required behavior |
| --- | --- | --- |
| `success` | `ok` | Record tool, actor, scope, policy decisions, source refs, and any written entity refs. |
| `denial` | `denied` | Record the failed RBAC or policy decision and do not return unauthorized facts. |
| `partial_response` | `partial` | Record the limit or missing data policy, rows returned/requested, and limitations. |
| `error` | `error` | Record the error policy decision and return a structured error response. |

Bank-system writes must audit the acting officer, affected alert or case, action
name, idempotency key, policy version, and correlation ID. Sidecar writes must
audit the service identity, agent run, tool registry version, policy version,
and target sidecar record.

## Scope Expansion

The starting scope is supplied by the runtime in the request envelope. Tools may
not accept `alert_id`, `case_id`, `customer_id`, `account_id`, or
`transaction_id` in `tool_args`; scoped identifiers come from `subject` and
`scope`.

`trace_counterparty_graph` is the only Phase 3 read tool with scope expansion.
It may traverse from the active alert transaction to related accounts,
customers, transactions, alerts, and cases only through bank-owned graph policy.
The generated scope policy bounds traversal to `max_hops <= 4` and
`max_rows <= 100`.

Graph expansion must:

- Use only observed graph edges from bank MCP data.
- Record source references for returned graph facts.
- Return `partial` when rows or hops are limited.
- Return `denied` when requested scope expansion violates policy.
- Never grant the agent a reusable broader scope outside the audited tool call.
