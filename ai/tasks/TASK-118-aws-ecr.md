# TASK-118 — AWS ECR

## Objective
Implement Terraform for AWS ECR repositories for each service (ingestion, processor, raw-writer, lake-writer, warehouse-loader, api, agent). Configure image lifecycle policies and IAM access for EKS nodes to pull images.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-117.

## Terraform/AWS Rules
- Never commit credentials, access keys, or secrets.
- One ECR repository per service boundary.
- Configure image lifecycle policies to manage storage.
- IAM access must follow least-privilege principles.
- ECR must be reachable from EKS nodes.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-118 only.
