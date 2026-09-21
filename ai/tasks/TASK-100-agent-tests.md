# TASK-100 — Agent Tests

## Objective
Implement comprehensive tests for the LangGraph agent covering intent classification, tool invocation, routing logic, API endpoint, and end-to-end question answering. Tests must verify the agent uses tools rather than hallucinating state, and must cover edge cases like unrecognized intents and tool failures.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-099.

## Agent Rules
- Agent must use controlled tools and read-only SQL; never hallucinate platform state.
- Tests must be deterministic; mock LLM calls and external dependencies.
- Verify agent answers questions like "Which products had the largest price increases?", "Why did observations drop yesterday?", "Which sources have freshness problems?" using tools.
- Agent must not have write access to PostgreSQL.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-100 only.
