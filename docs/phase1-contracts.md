# Phase 1 Contracts

These contracts define the first shared boundary between the backend, frontend,
reference MCP server, and agent service.

Generated JSON Schema files live in `contracts/` and are produced from the
Pydantic models in `src/compliance_agent/contracts/`.

## MCP Tool Calls

Every MCP tool accepts a single `request` object shaped as
`MCPRequestEnvelope`. The runtime supplies tenant, officer, run, purpose,
subject, scope, idempotency, and correlation fields. The model may choose a tool
and bounded `tool_args`, but it must not supply scoped entity IDs.

Every MCP tool returns `MCPResponseEnvelope` with structured facts, source refs,
data completeness, limitations, audit id, and policy decisions. Denied and error
responses are still structured and auditable.

## Agent Runs

`AgentRunRequest` is the shared request shape for a phase 1 agent run. It names
the subject alert or case and carries the starting scope.

`AgentProposal` is the terminal output. It is always a proposal for human
review, includes the model/prompt/tool/policy versions, and includes trace,
tool-call, observation, validation, limitation, and evidence fields.

## Tool Catalog

`phase1_tool_catalog.json` is the canonical tool list for phase 1:

- `get_customer_profile`
- `get_transaction_history`
- `get_behavioral_baseline`
- `get_prior_alerts`
- `get_case_history`
- `trace_counterparty_graph`
- `screen_sanctions_pep`
- `get_similar_alerts`
- `get_compliance_rule`

The reference MCP server owns database access and queries tables from
`scheme.sql` through parameterized SQL. Agents and LLMs never receive database
credentials and never generate or execute SQL.
