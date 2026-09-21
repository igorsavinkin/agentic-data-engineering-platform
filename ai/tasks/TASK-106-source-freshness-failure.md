# TASK-106 — Source Freshness Failure

## Objective
Design and implement a test that demonstrates platform behavior when a source adapter stops producing events (stale/missing data). The test must verify that freshness metrics detect the problem, alerts are raised, and downstream components do not serve stale data as current.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-105.

## Failure Engineering Rules
- Tests must demonstrate Failure -> Detection -> Metric/log -> Recovery -> No silent data loss.
- Reuse existing source-health and freshness monitoring semantics.
- Tests must be repeatable and deterministic.
- Document the freshness failure scenario and expected detection behavior.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-106 only.
