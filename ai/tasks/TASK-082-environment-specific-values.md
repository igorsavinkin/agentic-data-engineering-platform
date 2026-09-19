# TASK-082 — Environment-Specific Values

## Objective
Add base plus environment overrides (at least local/development and production-like example) without template forks or credentials. Demonstrate justified differences and document helm upgrade --install commands.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed work through TASK-079.

Dependency gate: before this milestone, resolve the TASK-073 cross-cutting APP_* configuration issue and complete TASK-073–079 successfully. Helm must package a healthy deployment, not hide an unresolved application/config defect.

## Engineering Rules
- Implement this task only.
- Package, do not redesign, the established Kubernetes architecture.
- Preserve service boundaries, probes, resources and configuration semantics.
- Never commit real secrets.
- Keep templates understandable; avoid unnecessary Helm metaprogramming.
- Validate rendered YAML as well as Helm syntax.
- Do not weaken tests for green CI.
- Inspect final diff and escalate architecture-significant changes.

## Definition of Done
Acceptance behavior is demonstrated; lint/render/deployment checks relevant to the task pass; documentation is updated; no real secrets or unrelated changes are introduced.

## Agent Instructions
Implement TASK-082 only.
