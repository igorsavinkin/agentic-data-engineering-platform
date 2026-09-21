# TASK-103 — Processor Crash Test

## Objective
Design and implement a test that demonstrates platform behavior when the processor crashes mid-batch. The test must verify that after restart, the processor resumes from the last committed offset, no events are silently dropped, and at-least-once semantics hold.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-102.

## Failure Engineering Rules
- Tests must demonstrate Failure -> Detection -> Metric/log -> Recovery -> No silent data loss.
- Reuse existing consumer offset commit and idempotent processing semantics.
- Tests must be repeatable and deterministic.
- Document the failure scenario and expected recovery behavior.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-103 only.
