# TASK-105 — DLQ Test

## Objective
Design and implement a test that demonstrates correct dead-letter queue behavior: malformed events are routed to the DLQ, DLQ events are queryable, and the main pipeline continues processing valid events unaffected. Verify DLQ monitoring surfaces alerts.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-104.

## Failure Engineering Rules
- Tests must demonstrate Failure -> Detection -> Metric/log -> Recovery -> No silent data loss.
- Reuse existing DLQ handling semantics; do not change processor behavior.
- Tests must be repeatable and deterministic.
- Document the DLQ scenario and expected behavior.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-105 only.
