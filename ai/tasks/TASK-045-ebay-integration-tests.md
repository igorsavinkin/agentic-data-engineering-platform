# TASK-045 — eBay Integration Tests

## Objective
Create deterministic integration tests from mocked eBay responses through adapter, marketplace normalization, canonical ingestion, Kafka, processor, Parquet, and PostgreSQL where the established test infrastructure supports those boundaries. Cover multiple sellers/listings, replay, repeated observations, ambiguity, malformed input, and regression smoke tests for existing sources.

## Required Context Before Coding
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and the relevant contracts/implementations from prior tasks. Higher-authority repository documents win on conflicts.

## Requirements
- Keep source-specific structures behind the adapter/normalization boundary.
- Preserve stable source, listing/product, event, and timestamp identity as applicable.
- Use typed Python, explicit configuration, deterministic tests, and existing repository conventions.
- Consider retries, replay, duplicates, partial failure, and idempotency where applicable.
- Never commit or log credentials.
- Do not begin later roadmap tasks.
- Escalate if implementation requires a fundamental incompatible canonical model or warehouse schema change.

## Task-Specific Scope
Create deterministic integration tests from mocked eBay responses through adapter, marketplace normalization, canonical ingestion, Kafka, processor, Parquet, and PostgreSQL where the established test infrastructure supports those boundaries. Cover multiple sellers/listings, replay, repeated observations, ambiguity, malformed input, and regression smoke tests for existing sources.

## Tests
Add unit/integration tests appropriate to this task, including success, malformed/partial input, deterministic identity/mapping, and relevant failure/replay cases. Normal CI must not depend on live external credentials.

## Acceptance Criteria
The platform demonstrates multiple marketplace listings for one logical product without breaking the canonical pipeline; final stored state and replay/idempotency are asserted; tests need no live eBay credentials and pass repository quality checks.

## Definition of Done
Relevant tests, lint, format and type checks pass; acceptance criteria are verified; diff is inspected; documentation is updated where required; no secrets are introduced.

## Agent Instructions
Implement TASK-045 only.
