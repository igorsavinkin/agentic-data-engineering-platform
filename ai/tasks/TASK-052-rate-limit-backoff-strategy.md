# TASK-052 — Rate-Limit / Backoff Strategy

## Objective and Scope
Implement and document the difficult source's bounded rate-limit and retry/backoff policy.

Requirements:
- Classify retryable and non-retryable failures explicitly.
- Handle 429/rate-limit responses and respect `Retry-After` when supplied.
- Use bounded exponential backoff with jitter where appropriate.
- Configure maximum attempts and maximum wait bounds.
- Avoid synchronized retry storms.
- Do not retry deterministic parser/schema/configuration errors.
- Preserve partial-success behavior when a bounded collection has already produced valid observations.
- Ensure retries/replays do not create duplicate logical events or warehouse observations.
- Expose retry/rate-limit outcomes through existing metrics/logging conventions.
- Tests must inject/mock clocks/sleep; no long real waits in CI.
- Do not claim that backoff guarantees source availability.

Tests:
- 429 + Retry-After
- 429 without Retry-After
- transient 5xx then recovery
- timeout/connection retry
- exhausted retry budget
- non-retryable failure
- bounded maximum wait/attempts
- partial success
- replay/idempotency
- retry metrics/logging

Acceptance:
Rate limiting and transient failures cause bounded, observable retries; persistent failures terminate clearly; partial valid work is preserved according to existing semantics; retries do not create duplicate logical data.

## Required Context Before Coding
Read the current repository versions of `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and relevant completed source-adapter tasks. Higher-authority repository documents win on conflicts.

## Engineering Rules
- Implement this task only.
- Use typed Python, explicit interfaces, deterministic tests, and existing repository conventions.
- Preserve source-adapter isolation and canonical downstream contracts.
- Preserve documented at-least-once/idempotent semantics; never claim exactly-once without proof.
- Never commit/log credentials or secrets.
- Do not weaken/delete tests to make CI green.
- Run relevant unit/integration tests plus configured lint/format/type checks after final edits.
- Inspect the final Git diff and verify acceptance criteria.
- Escalate if implementation requires a fundamental architecture/schema change or broad unrelated refactoring.

## Agent Instructions
Implement TASK-052 only. Stop when its acceptance criteria and final verification are satisfied.
