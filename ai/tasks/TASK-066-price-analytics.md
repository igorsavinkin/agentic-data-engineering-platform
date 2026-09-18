# TASK-066 — Price Analytics

## Objective
Expose established warehouse analytical queries: latest price, changes and bounded min/max/average/source-listing comparisons where supported. Reuse existing SQL/query layer; never aggregate unlike currencies without established conversion.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and relevant implementations through TASK-062. Higher-authority repository documents win on conflicts.

## Engineering Rules
- Implement this task only.
- Use typed FastAPI/Pydantic/Python and existing DB/config conventions.
- Keep route handlers thin; query/business logic belongs in reusable layers.
- Preserve established source/listing/observation/quality/pipeline semantics.
- Bound queries and pagination.
- Never expose secrets or internal stack traces.
- Do not weaken tests for green CI.
- Run relevant tests, lint, format and type checks; inspect final diff.
- Escalate fundamental schema/architecture changes.

## Definition of Done
Acceptance behavior has deterministic tests, API schemas are typed, configured quality checks pass, documentation/OpenAPI is updated where appropriate, and no unrelated changes are introduced.

## Agent Instructions
Implement TASK-066 only.
