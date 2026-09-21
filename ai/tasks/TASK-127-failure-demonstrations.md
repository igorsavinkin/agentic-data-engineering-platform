# TASK-127 — Failure Demonstrations

## Objective
Create reproducible failure demonstration scripts or documentation that walk through each Milestone 12 failure scenario step by step. Each demonstration must show the failure injection, detection, recovery, and confirmation of no data loss. This has high portfolio value.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-126.

## Documentation Rules
- Demonstrations must be reproducible from documentation alone.
- Reference actual failure tests from Milestone 12.
- Each demonstration must follow: Failure -> Detection -> Metric/log -> Recovery -> No silent data loss.
- Do not introduce new failure tests; document and demonstrate existing ones.
- Target audience: experienced engineer evaluating the portfolio.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-127 only.
