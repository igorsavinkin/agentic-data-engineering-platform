# TASK-121 — AWS EKS

## Objective
Implement Terraform for AWS EKS cluster with managed node groups, including Kafka deployment (Strimzi or equivalent) reachable from ingestion and processor services. Configure cluster networking, IAM roles for service accounts (IRSA), and node group sizing.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-120.

## Terraform/AWS Rules
- Never commit credentials, access keys, or secrets.
- EKS must host all platform services and Kafka.
- Kafka must be reachable from ingestion and processor services within the cluster.
- Use IRSA for pod-level AWS permissions.
- Default to Strimzi or equivalent K8s-native Kafka; do not introduce MSK merely to increase technology count.
- Document cluster configuration and sizing.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-121 only.
