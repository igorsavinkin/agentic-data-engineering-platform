# TASK-042 — Marketplace Listing Model

## Objective
Introduce generic marketplace Listing and Seller concepts so one logical product can have multiple seller listings and historical observations. Define relationships among source, product, listing, seller, and observation. Preserve compatibility with non-marketplace sources. Any fundamental canonical/schema change must follow ADR/escalation rules.

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
Introduce generic marketplace Listing and Seller concepts so one logical product can have multiple seller listings and historical observations. Define relationships among source, product, listing, seller, and observation. Preserve compatibility with non-marketplace sources. Any fundamental canonical/schema change must follow ADR/escalation rules.

## Tests
Add unit/integration tests appropriate to this task, including success, malformed/partial input, deterministic identity/mapping, and relevant failure/replay cases. Normal CI must not depend on live external credentials.

## Acceptance Criteria
Multiple listings can represent one logical product without breaking existing product-observation semantics; listing and seller identities are stable; historical observations remain possible; existing sources continue to work.

## Definition of Done
Relevant tests, lint, format and type checks pass; acceptance criteria are verified; diff is inspected; documentation is updated where required; no secrets are introduced.

## Agent Instructions
Implement TASK-042 only.
