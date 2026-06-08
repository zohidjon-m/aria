# ADR 001: Modular Sidecar Monolith

## Status

Accepted.

## Context

The bank source database cannot be modified. Any AML assistant must read from
the bank's existing data model, keep generated outputs separately, and preserve
human authority over final decisions.

The project also needs to be adoptable as open source. Banks should be able to
evaluate it without deploying a distributed platform or changing source system
schemas.

## Options

### Option 1: Direct agent application

The agent talks directly to the bank database and returns answers to officers.

This is rejected. Even with prompt instructions and SQL filtering, it does not
create a strong enough boundary between source data and generated data.

### Option 2: Agent microservices

Each agent is a separate service, connected by queues and shared contracts.

This is deferred. It can scale later, but it increases operational burden before
the source contract, validation model, and workflows are stable.

### Option 3: Modular sidecar monolith

One service contains strict internal modules:

- Read-only source adapters.
- Agent workflows.
- Typology modules.
- Validation.
- Sidecar persistence.
- API.

This is accepted.

## Decision

Use a modular sidecar monolith for the first production-minded version.

## Reasons

- It enforces the database constraint in code and deployment: read-only source
  adapter plus separate sidecar store.
- It gives banks a small adoption footprint.
- It keeps audit and validation behavior easy to inspect.
- It supports future extraction into workers or services because the internal
  boundaries are already explicit.

## Consequences

The initial system favors deterministic, explainable agent logic over opaque
LLM-first behavior. LLM summarization can be added behind validated tool outputs,
but factual claims must still pass validation before reaching a human workflow.
