# TASK-094 — Read-Only SQL and Dataset Metadata Tools

## Objective
Implement agent tools that execute read-only SQL queries against PostgreSQL and retrieve dataset metadata (table schemas, row counts, partition info). Tools must enforce read-only constraints, reject dangerous SQL, and return structured results.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-093.

## Agent Rules
- Agent must use controlled tools and read-only SQL; never hallucinate platform state.
- SQL tools must enforce read-only access at the connection and query level.
- Reject DDL, DML, and any non-SELECT statements.
- Return structured results suitable for agent reasoning.
- Agent must not have write access to PostgreSQL.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-094 only.
