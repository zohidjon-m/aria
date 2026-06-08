# Agent Intelligence Plan V2

## Purpose

This plan is the next roadmap after `docs/agent-intelligence-plan.md`.
The v1 plan built a strong deterministic and heuristic foundation: bounded
tools, scoped investigations, typology routing, grounded reasoning validation,
trace persistence, and a mocked LLM planner contract.

V2 changes the goal from "prove the runtime can be controlled" to "prove live
LLM agents can help AML officers investigate alerts over a governed MCP
boundary."

The first milestone must be a visible proof of concept: a live cloud LLM uses a
local reference MCP server with fake AML data, dynamically chooses tools,
revises a hypothesis, grounds its findings in evidence, and produces a
human-review proposal. After that proof exists, the project can connect the same
runtime to broader agent workflows, evaluation, security, and production
readiness.

## Why These Pieces Are Required

### MCP Contract Spec

Banks have different schemas, vendors, case systems, alert tables, and workflow
rules. The agent sidecar should not know or depend on each bank's DDL.

The MCP contract lets each bank expose governed tools that map its internal
systems into a stable investigation interface. This makes the project portable
while keeping the bank in control of credentials, SQL, RBAC, audit, and source
system writes.

### Agent Runtime State Machine

An LLM with tools is not enough. The runtime state machine turns the model into a
bounded, replayable, fail-safe investigation process.

The state machine controls tool budgets, scope, stop reasons, validation,
evidence capture, trace persistence, and fallback behavior. The LLM can reason
inside those limits, but it cannot grant itself permission, widen scope, skip
audit, file SARs, or dismiss alerts.

### Live LLM Proof Of Concept

Mocked LLM tests prove contracts. They do not prove the product idea.

The first v2 milestone must show real model behavior against fake AML data:
tool choice, hypothesis revision, evidence synthesis, and an officer-facing
recommendation. This is the fastest way to demonstrate that LLM reasoning adds
value beyond the current deterministic baseline.

### Evaluation Harness

The project cannot credibly claim false-positive reduction until it measures
that claim.

The evaluation harness must replay historical or synthetic labeled alerts,
compare baseline outcomes with agent outcomes, and report false-positive
reduction, false-negative impact, analyst agreement, SAR conversion, latency,
and cost.

### Security And Governance Gates

MCP authorization is optional unless a deployment implements it. AML workflows
also require strict controls around suspicious activity research, SAR drafting,
human approval, audit, confidentiality, and model governance.

Security and governance gates are therefore not optional add-ons. They are the
controls that make the live LLM agent deployable instead of just impressive in a
demo.

Reference anchors:

- MCP Authorization:
  https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization
- MCP Security Best Practices:
  https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices
- FFIEC Suspicious Activity Reporting guidance:
  https://bsaaml.ffiec.gov/manual/AssessingComplianceWithBSARegulatoryRequirements/04
- NIST AI Risk Management Framework:
  https://www.nist.gov/itl/ai-risk-management-framework

## Build Order

V2 must be implemented in this order:

1. Live LLM plus local reference MCP proof of concept.
2. Agent runtime state machine.
3. MCP contract specification.
4. LLM-backed triage and investigation agents.
5. Connections to risk scoring, SAR drafting, sidecar persistence, API/UI, and
   bank export workflows.
6. Historical evaluation harness.
7. Security, governance, production readiness, and open-source release controls.

This order is intentional. The project first needs to prove that live LLM agents
can help with AML investigation. Once that proof exists, the surrounding
contracts, integrations, evaluation, and production controls can be hardened
phase by phase.

## Non-Negotiable Contracts

- Agents never hold source database credentials.
- Agents never generate or execute raw SQL.
- Bank source data is accessed through bank-owned or bank-approved MCP tools.
- MCP tools enforce scope, RBAC, bounded arguments, and audit mechanically.
- The LLM can request tools, but the runtime and MCP server decide whether a
  request is allowed.
- The LLM cannot file SARs, dismiss alerts, grant permissions, or skip human
  review.
- Every factual output must be grounded in source references.
- Every user-facing output is a proposal for human review.
- Failed or incomplete investigations fail safe to more human attention, never
  automatic clearance.
- No production false-positive claim is allowed until the evaluation harness
  proves it.

## Required Interfaces

### MCP Request Contract

Every MCP tool request must include enough context for scope, permission, audit,
and replay.

Required fields:

```json
{
  "tenant_id": "demo-bank",
  "officer_id": "officer-123",
  "agent_run_id": "run-abc",
  "purpose": "triage",
  "subject": {
    "alert_id": 1001,
    "case_id": null,
    "customer_id": 501
  },
  "scope": {
    "allowed_customer_ids": [501],
    "allowed_account_ids": [3001],
    "allowed_transaction_ids": [7001],
    "allowed_case_ids": []
  },
  "tool_args": {},
  "idempotency_key": "stable-request-key",
  "correlation_id": "trace-abc"
}
```

Purpose values:

- `triage`
- `investigation`
- `risk_scoring`
- `sar_drafting`
- `evaluation`

### MCP Response Contract

Every MCP response must be structured, source-grounded, and auditable.

Required fields:

```json
{
  "status": "ok",
  "facts": {},
  "source_refs": [],
  "data_completeness": {
    "complete": true,
    "rows_returned": 10,
    "rows_requested": 25,
    "missing_segments": []
  },
  "limitations": [],
  "audit_id": "audit-123",
  "policy_decisions": []
}
```

Status values:

- `ok`
- `partial`
- `denied`
- `error`

Denied and error responses must include a limitation or policy decision that can
be persisted in the agent trace.

### Source Reference Contract

Source references must map to evidence records, not free-text citations only.

Required shape:

```json
{
  "source_system": "bank_mcp",
  "entity_type": "transaction",
  "entity_id": "7001",
  "field_names": ["amount_usd", "created_at"],
  "retrieved_at": "2026-06-08T00:00:00Z"
}
```

### Agent Runtime States

The runtime must persist state transitions so a run can be replayed.

Required states:

- `created`
- `context_loaded`
- `planning`
- `tool_requested`
- `tool_executed`
- `observing`
- `revising`
- `validating`
- `proposed`
- `failed_safe`

Allowed terminal states:

- `proposed`
- `failed_safe`

### Agent Output Contract

Every agent output must include:

- recommendation or proposal
- confidence
- score if applicable
- structured reasoning
- factual claims
- evidence refs
- limitations
- data completeness summary
- required human action
- model version
- prompt version
- tool registry version
- policy version
- runtime bounds
- validation status

### Evaluation Contract

Each evaluated alert must include:

- historical alert input
- existing rule or baseline outcome
- analyst or case outcome
- SAR outcome if available
- agent outcome
- confidence
- false-positive label
- false-negative label
- latency
- tool-call count
- model cost
- explanation of disagreements

## Phase 1: Live LLM And Reference MCP Proof Of Concept

Goal: show that live LLM reasoning adds useful AML investigation behavior beyond
the deterministic v1 baseline.

Build:

- A local reference MCP server backed by fake AML data.
- A demo script that uses a live cloud OpenAI-compatible LLM endpoint.
- A single agent run that performs triage or investigation over the reference
  MCP server.
- Dynamic tool choice by the LLM.
- Hypothesis updates after observations.
- Evidence-grounded final proposal.
- Human-review output, never automatic dismissal.

Minimum reference MCP tools:

- `get_customer_profile`
- `get_transaction_history`
- `get_behavioral_baseline`
- `get_prior_alerts`
- `get_case_history`
- `trace_counterparty_graph`
- `screen_sanctions_pep`
- `get_similar_alerts`
- `get_compliance_rule`

Minimum demo scenarios:

- A clean, baseline-consistent alert that can be proposed as likely false
  positive for human review.
- A hard-red-flag alert that must escalate.
- An ambiguous alert that requires graph tracing before recommendation.

Acceptance criteria:

- The demo works with fake data and a configured live LLM key.
- The LLM chooses at least two tools based on observations.
- The trace shows at least one hypothesis revision.
- Every final factual claim has source refs.
- The result is persisted as a proposal requiring human review.
- The live LLM demo is excluded from CI by default.

## Phase 2: Agent Runtime State Machine

Goal: make the live LLM loop controlled, replayable, and fail-safe.

Build:

- State transition model for all runtime states.
- Runtime event ledger for planning, tool request, tool response, observation,
  revision, validation, and proposal.
- Stop reasons.
- Tool-call budget.
- Row, lookback, graph-hop, timeout, and cost budgets.
- Strict model-output schemas.
- Fail-safe policy for incomplete evidence, malformed model output, tool
  denial, tool error, repeated tool call, no progress, and budget exhaustion.

Required stop reasons:

- `completed`
- `critical_signal_found`
- `insufficient_evidence`
- `tool_denied`
- `tool_error`
- `schema_error`
- `no_progress`
- `budget_exhausted`
- `timeout`

Fail-safe mapping:

- `critical_signal_found` maps to `escalate`.
- All uncertainty, error, denial, timeout, and budget exhaustion states map to
  `needs_investigation`.
- No failed or inconclusive run may produce `likely_false_positive`.

Acceptance criteria:

- Runtime traces are replayable from persisted events.
- Tool calls are blocked when outside budget or scope.
- Malformed model output produces `failed_safe`.
- Repeated tool calls produce `no_progress`.
- Every terminal state records a stop reason.

## Phase 3: MCP Contract Specification

Goal: define the bank-facing interface that makes the sidecar portable and
safe.

Build:

- A formal MCP contract document.
- Tool metadata schema.
- Request and response schemas.
- Read-tool catalog.
- Bank-system write-tool catalog.
- Sidecar-only write/proposal catalog.
- RBAC and policy-decision model.
- Audit event contract.
- Scope model.
- Reference MCP server behavior.

Read tools:

- `get_customer_profile`
- `get_transaction_history`
- `get_behavioral_baseline`
- `get_prior_alerts`
- `get_case_history`
- `trace_counterparty_graph`
- `screen_sanctions_pep`
- `get_similar_alerts`
- `get_compliance_rule`
- `get_officer_permissions`

Bank-system write tools:

- `add_alert_comment`
- `open_case`
- `link_alert_to_case`
- `export_human_decision`

Sidecar-only write or proposal tools:

- `record_agent_trace`
- `propose_alert_disposition`
- `store_agent_risk_score`
- `draft_regulatory_report`
- `record_evaluation_result`

Write tool rule:

The LLM can request a write action, but only deterministic policy and RBAC can
approve execution. SAR filing is never an agent action.

Acceptance criteria:

- Contract examples cover every tool.
- RBAC denial behavior is specified.
- Audit behavior is specified for success, denial, partial response, and error.
- Scope expansion is specified for graph traversal.
- Bank writes and sidecar writes are clearly separated.

## Phase 4: LLM-Backed Agent Capabilities

Goal: connect the live LLM runtime to the agent workflows that matter most to
AML officers.

### Triage Agent

Capabilities:

- Trigger on new alert or manual officer request.
- Gather customer profile, rule metadata, transaction history, behavioral
  baseline, prior alerts, prior cases, sanctions/PEP matches, similar alerts,
  and graph signals when needed.
- Compare the alert to the customer's historical baseline.
- Identify brittle threshold alerts and likely false positives.
- Enforce hard-red-flag overrides.
- Produce a ranked proposal: `likely_false_positive`, `needs_investigation`, or
  `escalate`.

### Investigation Agent

Capabilities:

- Trigger when triage cannot confidently propose a low-noise disposition.
- Run a true plan, query, observe, revise loop.
- Test typology hypotheses: structuring, velocity, sanctions, geography, mule
  behavior, rapid pass-through, fan-out, many-to-one aggregation, and linked
  case risk.
- Trace counterparty graph paths through governed MCP tools only.
- Recommend `open_case`, `continue_investigation`, or `return_to_triage`.
- Persist the full investigation trail.

### Risk Scoring Agent

Capabilities:

- Let the LLM gather and explain risk evidence.
- Compute the final proposed score through deterministic policy or calibrated
  model logic.
- Record factors, weights, policy version, confidence, and human overrides.
- Run standalone, periodically, or during investigation.

### SAR Drafting Agent

Capabilities:

- Draft narrative only from retrieved case facts and officer-entered context.
- Link factual sentences to evidence refs.
- List missing required fields.
- Preserve SAR confidentiality.
- Require authorized human review.
- Never file a SAR autonomously.

Acceptance criteria:

- Triage and investigation use live LLM planning in demo mode.
- Risk scoring does not let the LLM invent the final numeric score.
- SAR drafting produces evidence-grounded narrative only.
- All material outputs require human review.

## Phase 5: Connections And Product Surface

Goal: make the POC usable as an officer-assist workflow rather than a script.

Build:

- API endpoints for starting agent runs and fetching traces.
- Sidecar persistence for MCP requests, responses, policy decisions, evidence,
  hypotheses, validation reports, proposals, and human decisions.
- Optional UI view for officer review.
- Export path for bank systems of record.
- Config for provider endpoint, model, prompt version, tool registry version,
  policy version, and runtime budgets.

Officer-facing output must show:

- recommendation
- confidence
- evidence
- reasoning
- limitations
- missing data
- stop reason
- required human action
- audit IDs

Acceptance criteria:

- An officer can inspect why a recommendation was made.
- A run can be replayed from sidecar records.
- Human decision is recorded separately from agent proposal.
- Bank export is explicit and audited.

## Phase 6: Evaluation Harness

Goal: prove or disprove false-positive reduction.

Build:

- Historical alert replay runner.
- Synthetic labeled alert dataset for open-source demos.
- Metric calculator.
- Benchmark report generator.
- Regression thresholds.
- Disagreement analysis.

Required metrics:

- alert volume evaluated
- existing false-positive rate
- agent-assisted false-positive rate
- false-positive reduction
- false-negative rate
- false-negative delta from baseline
- escalation precision
- analyst agreement
- SAR conversion rate
- average latency
- average tool calls
- average model cost

Acceptance criteria:

- Benchmark runs without live bank data using synthetic labels.
- Metrics are reproducible.
- False-positive reduction is never reported without false-negative impact.
- Results can be grouped by rule type, typology, geography, risk level, and
  customer segment.

## Phase 7: Security, Governance, And Production Controls

Goal: prepare the project for controlled pilots after the POC and evaluation
layers exist.

Build:

- MCP auth requirements.
- Token audience validation requirements.
- No token passthrough requirement.
- Per-tool scopes.
- RBAC tests.
- Prompt-injection tests for source data, comments, case notes, and tool
  descriptions.
- Model inventory.
- Prompt registry.
- Tool registry versioning.
- Evaluation-before-promotion process.
- Rollback process.
- Monitoring for unsupported-claim rate, tool denial rate, analyst
  disagreement, latency, and cost.
- Production readiness mapping to `docs/production-readiness.md`.

Acceptance criteria:

- Security controls are documented and tested.
- Prompt-injection attempts cannot expand tool access.
- Model and prompt changes require evaluation.
- Production claims remain blocked until production readiness gates pass.

## Test Plan

### POC Tests

- Live LLM demo script runs outside CI.
- Mocked LLM contract tests run in CI.
- Reference MCP fake-data smoke test runs in CI.
- Demo validates dynamic tool choice and hypothesis revision.

### MCP Tests

- Tool schemas reject invalid args.
- Scope violations are denied.
- RBAC denial is recorded.
- Audit IDs are emitted.
- Row, lookback, and graph-hop limits are enforced.
- Tool output prompt injection is treated as untrusted content.

### Runtime Tests

- Valid loop completes.
- Malformed model output fails safe.
- Repeated tool call fails safe.
- Tool denial fails safe.
- Max budget exhaustion fails safe.
- Timeout fails safe.
- Every terminal run has a stop reason.

### Agent Tests

- Clean evidence can produce `likely_false_positive` proposal for human review.
- Hard red flags override false-positive proposals.
- Graph risk can escalate an alert.
- Insufficient evidence produces `needs_investigation`.
- Risk score is policy-computed.
- SAR draft requires human approval.

### Evaluation Tests

- Confusion matrix generation.
- Metric calculation.
- Regression threshold checks.
- Benchmark report generation.
- False-positive reduction always paired with false-negative impact.

## Open-Source Release Expectations

V2 should eventually include:

- Reference MCP server with fake data.
- MCP contract documentation.
- Live demo instructions.
- CI-safe mocked LLM tests.
- Synthetic evaluation dataset.
- Example benchmark report.
- Accurate README claims and limitations.
- Clear separation between active implementation and historical folders.
- `SECURITY.md`.
- `CONTRIBUTING.md`.
- Production pilot checklist.

## Assumptions And Defaults

- Branch: `agent-intelligence`.
- New file path: `docs/agent-intelligence-plan-v2.md`.
- First POC target: live LLM plus local reference MCP server.
- First model posture: cloud-first through an OpenAI-compatible provider.
- Local/private model support is planned after the first live cloud POC.
- Current v1 plan remains intact because it documents completed foundation
  work.
- No production claim is allowed until the evaluation harness proves reduced
  false positives without unacceptable false-negative impact.
- No commit is required merely to create this plan file; review should happen
  before committing broader implementation work.
