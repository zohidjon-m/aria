# Production Readiness Definition

This document defines what "production ready" means for Aria after the
LLM-backed agentic loop and bank MCP integration are implemented.

Production ready does not mean the system autonomously clears alerts, files
SARs, or replaces AML officers. It means the system can be deployed as a
governed analyst-assist sidecar where agents investigate, explain, and propose,
while banks retain control over data access, permissions, audit, and final
decisions.

This is not legal or regulatory advice. A bank must validate the deployment
against its own BSA/AML, OFAC, privacy, security, model risk, and internal
governance requirements.

## Readiness Standard

The project is production ready only when all of these are true:

1. The agent can run a bounded plan, tool, observe, revise loop over bank
   MCP tools without direct database credentials or raw SQL access.
2. Every tool call is scoped, permissioned, typed, rate-limited, audited, and
   persisted with source references.
3. Every user-facing recommendation, risk score, case recommendation, or SAR
   draft is grounded in retrieved evidence and marked as a human-review
   proposal.
4. The system can prove, using historical alert replay, that it reduces
   operational noise without materially increasing missed suspicious activity.
5. The system can be monitored, tested, rolled back, upgraded, and investigated
   by bank engineering, compliance, audit, and security teams.

## Non-Negotiable Product Claims

Allowed claims:

- "LLM-powered AML investigation sidecar."
- "Agents investigate and propose; humans decide."
- "Bank-owned MCP tools control source data, writes, RBAC, and audit."
- "Designed to reduce analyst workload and improve alert explainability."

Disallowed claims until proven by bank-specific evaluation:

- "Automatically reduces AML false positives."
- "Safely dismisses alerts without analyst review."
- "Replaces transaction monitoring systems."
- "Files SARs automatically."
- "Works out of the box for production AML decisions."

## Gate 1: Bank MCP Security Boundary

The bank MCP server is the security boundary. The agent sidecar must never hold
source database credentials and must never generate or execute SQL against bank
systems.

Production requirements:

- MCP server is bank-owned or bank-approved.
- Authentication uses a bank-approved identity provider.
- Authorization is enforced per tool, not only per server.
- Access tokens are audience-bound to the MCP server.
- Token passthrough to downstream systems is forbidden.
- Tool scopes are least-privilege and purpose-specific.
- Write tools require acting officer identity and role checks.
- Sensitive tools support additional approval or step-up authorization.
- Tool schemas reject unbounded lookbacks, row counts, graph hops, and entity
  IDs outside the active investigation scope.
- Tool output is treated as untrusted content for prompt-injection purposes.
- Every MCP request and response has a correlation ID.

Acceptance evidence:

- MCP threat model.
- Authentication and authorization tests.
- RBAC tests for every write tool.
- Token audience validation tests.
- Prompt-injection and malicious tool-output tests.
- Audit log samples for successful and rejected tool calls.

## Gate 2: Agentic Runtime Harness

The LLM must run inside a deterministic harness. The harness controls what the
agent can do; the LLM controls investigation reasoning within those limits.

Production requirements:

- Every run has tenant, officer, alert or case scope, policy version, model
  version, prompt version, tool registry version, and idempotency key.
- Agent-specific tool allowlists are enforced mechanically.
- The runtime enforces max steps, max tool calls, max rows, max lookback days,
  max graph hops, timeout, and cost limits.
- The runtime records each thought, action, observation, hypothesis revision,
  stop reason, and final proposal.
- The runtime fails safe to "needs investigation" when evidence is incomplete,
  tools fail, model output is malformed, or the agent exceeds limits.
- The LLM cannot directly choose high-impact writes. It can request an action;
  deterministic policy and RBAC decide whether the action is allowed.
- The LLM cannot decide SAR filing, alert dismissal, or officer permissions.

Acceptance evidence:

- Runtime contract tests.
- Tool allowlist tests per agent.
- Scope escape tests.
- Malformed model-output tests.
- Budget exhaustion tests.
- Replayable traces for representative alert runs.

## Gate 3: Agent Capabilities

### Triage Agent

Production requirements:

- Triggered on new alerts or manually by an officer.
- Pulls customer profile, transaction history, behavioral baseline, prior
  alerts, prior cases, screening results, rule metadata, and similar alerts.
- Uses LLM reasoning to compare current behavior against customer context.
- Produces a ranked proposal: likely false positive, needs investigation, or
  escalate.
- Never auto-dismisses an alert.
- Hard red flags override false-positive proposals.
- Output includes source-backed reasoning, data limitations, confidence, and
  recommended next step.

### Investigation Agent

Production requirements:

- Triggered when triage cannot confidently classify an alert.
- Runs a real plan, query, observe, revise loop.
- Tests hypotheses against typologies such as structuring, velocity, sanctions,
  geography, mule behavior, rapid pass-through, and counterparty graph risk.
- Can trace `counterparty_account_id` paths only through governed graph tools.
- Recommends open case, continue investigation, or return to triage.
- Produces a full auditable trail.

### Risk Scoring Agent

Production requirements:

- Can run periodically, manually, or during investigation.
- LLM gathers and explains evidence.
- A deterministic scoring policy or calibrated scoring model computes the final
  proposed score.
- Score factors, weights, policy version, and confidence are recorded.
- Human overrides are captured with rationale.

### SAR Drafting Agent

Production requirements:

- Triggered only from an eligible case workflow.
- Drafts narrative from retrieved case facts, alerts, transactions, comments,
  and investigation traces.
- Every factual sentence must be linked to source evidence or clearly marked as
  officer-entered context.
- Missing required fields are listed.
- Only authorized humans can approve or submit SARs.
- SAR confidentiality controls are documented and enforced.

Acceptance evidence:

- Agent-level tests for all four agents.
- Human approval flow tests.
- Evidence-grounding tests.
- False-positive recommendation blocked by hard-red-flag tests.
- SAR permission and confidentiality tests.

## Gate 4: Evidence, Validation, And Grounding

Production requirements:

- Every factual claim has source references.
- Source references map to MCP evidence records, not free-text citations only.
- Validation checks missing evidence, unsupported claims, contradictory facts,
  stale evidence, incomplete data, and scope violations.
- Validation failures block user-facing conclusions or mark them as unsupported.
- Evidence records are immutable or append-only.
- The system distinguishes facts, model reasoning, policy decisions, and human
  decisions.

Acceptance evidence:

- Claim validation tests.
- Contradiction tests.
- Data completeness tests.
- Unsupported claim rejection tests.
- Examiner-readable evidence trail examples.

## Gate 5: Evaluation And False-Positive Proof

The system cannot claim false-positive reduction until this gate passes.

Production requirements:

- Historical alert replay harness.
- Bank-specific labeled evaluation set.
- Baseline comparison against existing transaction monitoring outcomes.
- Metrics by customer segment, rule type, typology, geography, and risk level.
- False-positive reduction measured against analyst or case outcomes.
- False-negative impact measured explicitly.
- Analyst agreement rate measured.
- Confidence calibration measured.
- Investigation time and tool-cost impact measured.
- Regression suite protects against degraded detection.

Minimum reported metrics:

- Alert volume evaluated.
- Existing false-positive rate.
- Agent-assisted false-positive rate.
- False-positive reduction.
- False-negative rate and change from baseline.
- Escalation precision.
- Analyst agreement.
- SAR conversion rate.
- Average tool calls per alert.
- Average latency per alert.
- Average cost per alert.

Acceptance evidence:

- Reproducible benchmark report.
- Evaluation dataset documentation.
- Confusion matrix.
- Threshold and policy calibration report.
- Regression test results.
- Known limitations and excluded populations.

## Gate 6: AML Workflow Controls

Production requirements:

- The system supports alert management, case investigation, SAR decisioning,
  SAR drafting, human approval, and continuing-activity review workflows.
- No autonomous alert dismissal.
- No autonomous SAR filing.
- Filing deadlines and review queues are visible to officers.
- Officer decisions are captured as separate human decisions.
- The bank can export records to its system of record.
- The sidecar does not mutate bank source systems unless a bank-approved write
  MCP tool does so with RBAC and audit.

Acceptance evidence:

- Workflow tests for alert, case, risk score, and SAR draft lifecycle.
- Human decision audit examples.
- Export integration tests.
- Reviewer permission tests.

## Gate 7: LLM Governance

Production requirements:

- Model inventory documents provider, model ID, version, purpose, limits, and
  approved use cases.
- Prompt registry documents prompt versions and expected outputs.
- Tool registry documents tool versions and schemas.
- Model and prompt changes require evaluation before promotion.
- Production can roll back model, prompt, tool, and policy versions.
- Ongoing monitoring tracks drift, failure modes, hallucination rate,
  unsupported-claim rate, and analyst disagreement.
- Red-team tests cover prompt injection, data exfiltration, hidden instructions
  in source data, malicious counterparties, and tool misuse.
- Vendor or third-party model dependencies are documented.

Acceptance evidence:

- Model card or system card.
- Prompt and tool version registry.
- Change approval process.
- Red-team report.
- Monitoring dashboard.
- Rollback runbook.

## Gate 8: Security, Privacy, And Compliance Operations

Production requirements:

- Tenant isolation for multi-bank or multi-environment deployments.
- Encryption in transit and at rest.
- PII-aware logs with masking or minimization.
- Secrets managed by approved vault or secret manager.
- Audit logs are tamper-evident or append-only.
- Data retention and deletion policies are documented.
- SAR confidentiality and restricted-access records are protected.
- Security incident response runbook exists.
- Dependency and container vulnerability scanning is enabled.
- Supply-chain controls are documented for open-source releases.

Acceptance evidence:

- Security architecture review.
- Data flow diagram.
- Privacy impact assessment template.
- Vulnerability scan results.
- Secrets handling tests.
- Incident response runbook.

## Gate 9: Reliability And Operations

Production requirements:

- Health checks for API, MCP connectivity, sidecar storage, model provider, and
  queue workers.
- Structured logs and metrics.
- Distributed trace or correlation IDs across agent, MCP, and sidecar records.
- Retry, timeout, and circuit-breaker behavior for MCP and model calls.
- Backpressure for alert bursts.
- Dead-letter handling for failed runs.
- Backup and restore process for sidecar storage.
- Database migrations are versioned and reversible where practical.
- Service-level objectives are defined for latency, availability, and run
  completion.

Acceptance evidence:

- Load test report.
- Failure-mode tests.
- Backup and restore drill.
- Migration tests.
- Monitoring dashboard.
- On-call runbook.

## Gate 10: Open-Source Release Readiness

Production readiness for an open-source project also requires that adopters can
understand, evaluate, and extend the project safely.

Production requirements:

- Clear README with accurate claims and limitations.
- Architecture documentation.
- MCP tool contract specification.
- Reference MCP server with fake/demo data.
- Docker Compose or equivalent local deployment.
- CI for backend tests, frontend tests if applicable, linting, and security
  checks.
- `CONTRIBUTING.md`.
- `SECURITY.md`.
- Code of conduct.
- License and third-party notices.
- Example evaluation report.
- Example production pilot checklist.
- Clear separation between active implementation and legacy code.

Acceptance evidence:

- Fresh-clone setup succeeds.
- Tests pass in CI.
- Demo run succeeds without external secrets.
- Documentation review completed.
- Release checklist completed.

## Production Readiness Levels

### Level 0: Prototype

- Deterministic or mocked agent behavior.
- Demo data only.
- No production claim.

### Level 1: Agentic Alpha

- LLM loop works against a reference MCP server.
- Tool scope, evidence, and trace persistence work.
- No bank pilot claim.

### Level 2: Controlled Pilot

- Bank MCP server integrated in a non-production environment.
- Historical replay completed.
- Human review only.
- False-positive claim limited to pilot results.

### Level 3: Production Pilot

- Security, RBAC, audit, evaluation, and monitoring gates pass.
- Limited production users and alert scope.
- Bank governance approval obtained.
- Rollback and incident response tested.

### Level 4: Production

- All gates pass.
- Ongoing monitoring and periodic validation are active.
- Bank compliance, security, audit, and engineering owners have signed off.
- Examiner-readable documentation and evidence are available.

## Final Production-Ready Statement

The project can be called production ready only when it can truthfully say:

"This system is a governed AML investigation sidecar. Bank-controlled MCP tools
enforce data access, RBAC, writes, and audit. LLM agents perform bounded,
evidence-grounded investigation and produce human-review proposals. Historical
evaluation demonstrates the system improves alert handling without unacceptable
false-negative impact. Operations, security, model governance, and AML workflow
controls are documented, tested, monitored, and owned."

## Reference Guidance

- FFIEC BSA/AML Examination Manual:
  https://bsaaml.ffiec.gov/manual
- FFIEC Suspicious Activity Reporting:
  https://bsaaml.ffiec.gov/manual/AssessingComplianceWithBSARegulatoryRequirements/04
- FinCEN and federal banking agencies innovation statement:
  https://www.fincen.gov/news/news-releases/treasurys-fincen-and-federal-banking-agencies-issue-joint-statement-encouraging
- Federal Reserve model risk management guidance:
  https://www.federalreserve.gov/frrs/guidance/supervisory-guidance-on-model-risk-management.htm
- NIST AI Risk Management Framework:
  https://www.nist.gov/itl/ai-risk-management-framework
- MCP Authorization:
  https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization
- MCP Security Best Practices:
  https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices
