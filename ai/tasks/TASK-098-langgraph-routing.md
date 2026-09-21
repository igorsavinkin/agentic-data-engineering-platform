# TASK-098 — LangGraph Routing

## Objective
Implement LangGraph graph construction and routing logic that connects intent classification to tool selection and response generation. The graph must route based on classified intent, invoke the appropriate tools, and compose a final response from tool results.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-097.

## Agent Rules
- Agent must use controlled tools and read-only SQL; never hallucinate platform state.
- Routing must be deterministic for test inputs.
- Graph must handle unrecognized intents gracefully (fallback response).
- Agent must not have write access to PostgreSQL.
- Keep graph structure simple and testable.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-098 only.
