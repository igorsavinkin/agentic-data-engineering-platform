# TASK-095 — Pipeline Status Tool

## Objective
Implement an agent tool that reports current pipeline health: Kafka consumer lag, recent processing rates, last successful write timestamps, and any active alerts. The tool must aggregate data from existing metrics/health endpoints without duplicating logic.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-094.

## Agent Rules
- Agent must use controlled tools and read-only SQL; never hallucinate platform state.
- Reuse existing health/freshness/metrics endpoints; do not duplicate business logic.
- Tool must return structured data suitable for agent reasoning and user display.
- Agent must not have write access to PostgreSQL.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-095 only.
