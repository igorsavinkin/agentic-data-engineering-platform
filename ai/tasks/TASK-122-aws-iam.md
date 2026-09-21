# TASK-122 — AWS IAM

## Objective
Implement comprehensive IAM policies and roles for all platform services. Each service must have least-privilege access to only the AWS resources it needs. Configure IRSA mappings for EKS pods and document the IAM topology.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-121.

## Terraform/AWS Rules
- Never commit credentials, access keys, or secrets.
- IAM must follow least-privilege per service.
- IRSA must map each K8s service account to its specific IAM role.
- Document the IAM topology and trust relationships.
- No wildcard permissions except where AWS requires them.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-122 only.
