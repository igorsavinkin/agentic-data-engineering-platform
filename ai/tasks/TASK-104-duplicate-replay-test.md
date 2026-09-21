# TASK-104 — Duplicate/Replay Test

## Objective
Design and implement a test that demonstrates correct handling of duplicate events and Kafka replay scenarios. The test must verify that replayed events do not create duplicate logical records in PostgreSQL or Parquet, and that deduplication works across service boundaries.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-103.

## Failure Engineering Rules
- Tests must demonstrate Failure -> Detection -> Metric/log -> Recovery -> No silent data loss.
- Reuse existing deduplication and idempotent processing semantics.
- Tests must be repeatable and deterministic.
- Document the replay scenario and expected behavior.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-104 only.
