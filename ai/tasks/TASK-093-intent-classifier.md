# TASK-093 — Intent Classifier

## Objective
Implement an intent classifier that maps natural-language user questions to structured agent intents (price analytics, pipeline status, data quality, source health, product history, general). The classifier must be deterministic for test inputs and gracefully handle unrecognized intents.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-092.

## Agent Rules
- Agent must use controlled tools and read-only SQL; never hallucinate platform state.
- Classifier must be testable with deterministic inputs; do not require live LLM calls in unit tests.
- Intents must map cleanly to tool selections in the routing layer.
- Agent must not have write access to PostgreSQL.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-093 only.
