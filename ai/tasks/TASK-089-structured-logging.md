# TASK-089 — Structured Logging

## Objective
Standardize machine-readable logs across core services with service/environment/timestamp/level and safe correlation context. Define exception conventions; avoid secrets, excessive payloads and duplicate logging.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-083.

## Observability Rules
- Observe the established architecture; do not redesign business flow for telemetry.
- Reuse established health/freshness/data-quality/Kafka semantics.
- Keep metric labels and telemetry attributes bounded and low-cardinality.
- Never expose secrets or sensitive payloads.
- Instrumentation failure must not alter core processing semantics.
- Keep dashboards/provisioning version-controlled and reproducible.

## Engineering Rules
Implement this task only. Follow existing Kubernetes/Helm conventions. Add deterministic validation/tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant telemetry/performance issues.

## Definition of Done
Acceptance behavior is demonstrated, observability artifacts are reproducible, checks pass, documentation is updated, and no unrelated architecture changes/secrets are introduced.

## Agent Instructions
Implement TASK-089 only.
