# TASK-101 — Kafka Failure Test

## Objective
Design and implement a test that demonstrates platform behavior when Kafka becomes unavailable: producer cannot publish, consumer loses connectivity, or broker restarts. The test must verify that no silent data loss occurs, events are replayed after recovery, and consumer lag is detected and reported.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-100.

## Failure Engineering Rules
- Tests must demonstrate Failure -> Detection -> Metric/log -> Recovery -> No silent data loss.
- Use Docker Compose or kind infrastructure; do not require production-like environments.
- Tests must be repeatable and deterministic.
- Document the failure scenario and expected recovery behavior.
- Do not weaken existing tests or processing semantics.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-101 only.
