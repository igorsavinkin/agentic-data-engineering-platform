# TASK-099 — Agent API

## Objective
Expose the LangGraph agent through a FastAPI endpoint that accepts natural-language questions and returns structured agent responses. The endpoint must integrate with the existing API service, support streaming or synchronous response, and handle timeouts/errors gracefully.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-098.

## Agent Rules
- Agent must use controlled tools and read-only SQL; never hallucinate platform state.
- API must integrate with existing FastAPI patterns and error handling.
- Agent must not have write access to PostgreSQL.
- Keep the API surface minimal; do not over-engineer the agent interface.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-099 only.
