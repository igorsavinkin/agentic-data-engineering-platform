# TASK-112 — Measure Kafka Lag

## Objective
Implement systematic Kafka consumer lag measurement across load tests. Report lag per partition and consumer group, identify lag growth patterns under sustained load, and document thresholds where lag becomes operationally concerning.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-111.

## Performance Rules
- Do not invent benchmark numbers; record actual results.
- Reuse existing Kafka metrics and monitoring infrastructure.
- Measurements must be reproducible.
- Document lag behavior and operational thresholds.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-112 only.
