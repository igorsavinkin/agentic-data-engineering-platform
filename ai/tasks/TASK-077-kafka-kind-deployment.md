# TASK-077 — Kafka Deployment and Configuration for kind

## Objective
Deploy/configure Kafka for kind consistently with current architecture. Make it reachable by ingestion/processor/writers, create/verify established topics, preserve delivery/consumer semantics and document diagnosis.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and relevant implementation through TASK-069. Higher-authority repository documents win.

## Human Kubernetes Practice
Where relevant personally use: `kubectl get`, `describe`, `logs`, `exec`, `apply`, `delete`, `rollout`, `port-forward`, and `get events`. Do not hide troubleshooting behind opaque automation.

## Engineering Rules
- Implement this task only.
- Preserve service boundaries and canonical data flow.
- Use declarative manifests and consistent labels/selectors.
- Never commit real secrets.
- Do not redesign application architecture merely to simplify Kubernetes.
- Do not weaken tests for green CI.
- Validate manifests/tests and inspect the final diff.
- Remain compatible with later Helm work without implementing Helm early.
- Escalate architecture-significant or difficult Kubernetes issues.

## Definition of Done
Acceptance behavior is demonstrated; manifests are reproducible/reviewable; relevant checks pass; documentation is updated; no unrelated changes or real secrets are introduced.

## Agent Instructions
Implement TASK-077 only.
