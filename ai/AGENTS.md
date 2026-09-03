# AGENTS.md

# AI Data Platform — Agent Operating Rules

This file contains the persistent operational rules for AI coding agents working in this repository.

## 1. Authority Order

Before implementing a task, follow repository guidance in this order:

```text
ai/PROJECT.md
    ↓
Architecture Decision Records (ADRs)
    ↓
ai/SPECIFICATION.md
    ↓
ai/ROADMAP.md
    ↓
ai/tasks/TASK-xxx.md
    ↓
this AGENTS.md
```

If two documents conflict, stop implementation and report the conflict rather than silently choosing a new architecture.

`ai/PROJECT.md` is the highest-level architectural authority.

## 2. Required Context Before Coding

For every implementation task, read at minimum:

- `ai/PROJECT.md`
- `ai/SPECIFICATION.md`
- the relevant section of `ai/ROADMAP.md`
- the active `ai/tasks/TASK-xxx.md`
- `ai/AGENT_WORKFLOW.md` when workflow or escalation rules matter

Do not implement from the task title alone.

## 3. Scope Discipline

Implement only the active task.

Do not:

- redesign unrelated components
- rename public interfaces without a requirement
- add technologies merely because they are popular
- introduce speculative abstractions
- refactor unrelated code unless required for correctness
- silently change architecture

If a necessary change exceeds task scope, document it and propose a follow-up task or ADR.

## 4. Architecture Rules

The platform is an event-driven data platform. Preserve these constraints:

- ingestion publishes observations to Kafka
- ingestion does not write directly to PostgreSQL
- downstream components consume the canonical event contract, not source-specific formats
- external data sources are isolated behind source adapters
- delivery semantics are at-least-once with idempotent processing
- Kafka is transport/buffering/replay infrastructure, not the analytical datastore
- Parquet on MinIO/S3 provides the data-lake layer
- Raw Writer owns Bronze persistence; Lake Writer owns Silver persistence; Airflow owns Gold construction; Warehouse Loader owns Gold-to-PostgreSQL loading.
- PostgreSQL provides the serving/analytical query layer
- Airflow handles scheduled/batch workflows and does not replace Kafka streaming
- the LangGraph agent uses controlled tools and read-only SQL
- the project must work locally before cloud complexity is introduced

## 5. Source Adapter Rules

Every external data source must be implemented behind an adapter.

Adapters may use REST APIs, HTTP, HTML parsing, or browser automation as appropriate, but must emit the same canonical event model.

Do not leak source-specific response structures into Kafka consumers, Polars transformations, the warehouse, FastAPI, or the LangGraph agent.

Web-scraping complexity is secondary to the platform objective. Prefer the simplest reliable collection method.

Initial source progression is:

```text
Fake Store API + Best Buy
        ↓
eBay
        ↓
one retailer web source
        ↓
Amazon or equivalent difficult source
```

## 6. Implementation Standards

Prefer:

- typed Python
- small focused modules
- explicit interfaces
- Pydantic models for external/event contracts where appropriate
- Polars/PyArrow for columnar processing
- structured logging
- explicit configuration
- deterministic tests
- idempotent operations where replay is possible

Avoid hidden global state and unnecessary framework abstractions.

## 7. Testing Requirements

Every task must include tests appropriate to its scope.

Before declaring a task complete:

1. run relevant unit tests
2. run relevant integration tests
3. run lint/format/type checks configured by the repository
4. inspect the git diff
5. confirm acceptance criteria
6. consider failure/retry behavior
7. confirm no secrets were introduced

Do not weaken or delete tests merely to obtain a green build.

## 8. Failure and Distributed-System Semantics

For Kafka and persistence code, explicitly reason about:

- retries
- duplicate delivery
- offset commit timing
- consumer restart
- partial failure
- replay
- idempotency
- DLQ behavior

Never claim exactly-once semantics unless the implementation genuinely demonstrates them end to end.

## 9. Observability

New runtime components should expose appropriate:

- health information
- structured logs
- metrics
- trace context where applicable

Source adapters should expose failures, freshness, request outcomes, and record counts when applicable.

## 10. Security

Never:

- commit credentials or API keys
- print secrets in logs
- hardcode AWS credentials
- give the LangGraph agent write access to PostgreSQL
- bypass repository security controls for convenience

Use environment/configuration and least privilege.

## 11. Agent Roles

Default role assignment:

- **Qoder:** primary implementation environment
- **Qwen Code:** independent reviewer, preferably review-only
- **DeepSeek/Qwen models:** high-volume straightforward implementation where appropriate
- **Claude Code:** difficult architecture, distributed-systems reasoning, debugging, Kubernetes, Terraform/AWS, security, and performance analysis
- **Human owner:** final architecture and merge decisions

Do not divide ownership permanently by technology or directory. Divide work by task and role.

## 12. Escalation

Stop and escalate when:

- requirements conflict
- a fundamental architecture decision appears wrong
- schema compatibility would be broken
- delivery/idempotency semantics are uncertain
- a security-sensitive design decision is required
- Kubernetes/cloud behavior is not understood
- fixing the task requires major unrelated changes

For fundamental architecture changes, propose an ADR before implementation.

## 13. Definition of Done

A task is not Done because code was generated.

Done means:

- requirements implemented
- acceptance criteria satisfied
- tests added and passing
- repository checks passing
- failure behavior considered
- metrics/logging added where appropriate
- documentation updated where required
- diff reviewed
- architecture preserved
- no secrets introduced

## 14. Human Learning Rule

AI assistance must not hide core engineering concepts.

When implementing Kafka, SQL, Airflow, Kubernetes, AWS, observability, or distributed-system behavior, make the implementation understandable and explain consequential trade-offs in code comments or documentation where useful.

The human owner must be able to explain and troubleshoot the resulting system.
