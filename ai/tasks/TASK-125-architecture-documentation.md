# TASK-125 — Architecture Documentation

## Objective
Write comprehensive architecture documentation covering the event-driven data platform design, service boundaries, data flow, technology choices, and operational model. Documentation must be understandable to an experienced engineer evaluating the portfolio.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-124.

## Documentation Rules
- Documentation must reflect actual implemented architecture, not aspirational design.
- Reference actual code paths and configuration.
- Do not introduce new code or architecture changes; document what exists.
- Documentation must be version-controlled and maintainable.
- Target audience: experienced engineer evaluating the portfolio.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-125 only.
