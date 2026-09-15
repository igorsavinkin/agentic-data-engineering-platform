# TASK-043 — Seller / Listing Normalization

## Objective
Normalize eBay-specific seller/listing data into the generic marketplace model. Normalize IDs, URLs, exact price/currency, availability/condition where supported, and timestamps. Preserve diagnostic/source identity. Keep transformations deterministic and separate from HTTP I/O. Do not perform fuzzy product matching.

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
Normalize eBay-specific seller/listing data into the generic marketplace model. Normalize IDs, URLs, exact price/currency, availability/condition where supported, and timestamps. Preserve diagnostic/source identity. Keep transformations deterministic and separate from HTTP I/O. Do not perform fuzzy product matching.

## Tests
Add unit/integration tests appropriate to this task, including success, malformed/partial input, deterministic identity/mapping, and relevant failure/replay cases. Normal CI must not depend on live external credentials.

## Acceptance Criteria
eBay records yield generic marketplace representations; missing/partial metadata is handled deterministically; distinct sellers/listings are never silently collapsed; tests cover malformed and repeated inputs.

## Definition of Done
Relevant tests, lint, format and type checks pass; acceptance criteria are verified; diff is inspected; documentation is updated where required; no secrets are introduced.

## Agent Instructions
Implement TASK-043 only.
