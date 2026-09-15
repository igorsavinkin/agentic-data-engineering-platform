# TASK-044 — Product / Listing Identity Mapping

## Objective
Define stable replay-safe listing identity and mapping from listings to logical products. Prefer explicit/stable identifiers. Ambiguous matches must remain unresolved/separate rather than be merged by title similarity. Preserve independent seller listings and observation history. Do not introduce ML/fuzzy entity resolution.

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
Define stable replay-safe listing identity and mapping from listings to logical products. Prefer explicit/stable identifiers. Ambiguous matches must remain unresolved/separate rather than be merged by title similarity. Preserve independent seller listings and observation history. Do not introduce ML/fuzzy entity resolution.

## Tests
Add unit/integration tests appropriate to this task, including success, malformed/partial input, deterministic identity/mapping, and relevant failure/replay cases. Normal CI must not depend on live external credentials.

## Acceptance Criteria
The same listing resolves consistently across replay; legitimate multiple listings remain distinct; multiple listings may map to one product only when justified; ambiguity is explicit; existing retailer identity semantics do not regress.

## Definition of Done
Relevant tests, lint, format and type checks pass; acceptance criteria are verified; diff is inspected; documentation is updated where required; no secrets are introduced.

## Agent Instructions
Implement TASK-044 only.
