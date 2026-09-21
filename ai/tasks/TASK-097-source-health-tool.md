# TASK-097 — Source Health Tool

## Objective
Implement an agent tool that reports source-level health: freshness, availability, error rates, and degradation status for each configured source adapter. The tool must aggregate from existing source-health metrics without duplicating logic.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-096.

## Agent Rules
- Agent must use controlled tools and read-only SQL; never hallucinate platform state.
- Reuse existing source-health metrics; do not duplicate logic.
- Tool must return structured results suitable for agent reasoning.
- Agent must not have write access to PostgreSQL.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-097 only.
