# TASK-041 — eBay API Adapter

## Objective
Implement eBay behind the existing source-adapter interface. Add typed API models, externalized auth/config, bounded product/listing retrieval, explicit HTTP/auth/rate-limit failure handling, and mapping into the canonical ingestion boundary. Preserve listing/item and seller identifiers needed downstream. Do not leak eBay response structures downstream or solve cross-source identity here.

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
Implement eBay behind the existing source-adapter interface. Add typed API models, externalized auth/config, bounded product/listing retrieval, explicit HTTP/auth/rate-limit failure handling, and mapping into the canonical ingestion boundary. Preserve listing/item and seller identifiers needed downstream. Do not leak eBay response structures downstream or solve cross-source identity here.

## Tests
Add unit/integration tests appropriate to this task, including success, malformed/partial input, deterministic identity/mapping, and relevant failure/replay cases. Normal CI must not depend on live external credentials.

## Acceptance Criteria
eBay can feed the same ingestion architecture as existing sources; marketplace identifiers remain traceable; deterministic mocked tests cover mapping, missing fields, auth/errors/rate limits; no credentials are required in CI.

## Definition of Done
Relevant tests, lint, format and type checks pass; acceptance criteria are verified; diff is inspected; documentation is updated where required; no secrets are introduced.

## Agent Instructions
Implement TASK-041 only.
