# TASK-060 — daily_data_quality DAG

## Objective
Create scheduled daily_data_quality DAG that executes TASK-056 checks and persists TASK-057 results. Keep orchestration separate from check logic and make logical-interval reruns idempotent.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and relevant implementations through TASK-055. Higher-authority repository documents win on conflicts.

## Engineering Rules
- Implement this task only.
- Use typed Python, explicit configuration/interfaces and deterministic tests.
- Preserve existing service boundaries and replay/idempotency semantics.
- DAGs orchestrate reusable application/domain code; do not bury business logic in DAG files.
- Never commit/log secrets or weaken tests for green CI.
- Run relevant tests, lint, format and type checks; inspect the final diff.
- Escalate fundamental architecture/schema changes or broad unrelated refactors.

## Definition of Done
Objective and acceptance behavior are verified by focused tests; configured quality checks pass; documentation is updated where needed; no unrelated changes are introduced.

## Agent Instructions
Implement TASK-060 only.
