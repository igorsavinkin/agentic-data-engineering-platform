# TASK-108 — Load Test Harness

## Objective
Build a reusable load-test harness that can produce events at configurable rates and measure end-to-end pipeline latency, throughput, and resource utilization. The harness must be scriptable and produce structured results.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-107.

## Performance Rules
- Do not invent benchmark numbers; record actual results.
- Harness must be reusable across different load levels.
- Tests must not degrade production-like infrastructure.
- Keep the harness independent of specific source adapters.
- Document how to run the harness and interpret results.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-108 only.
