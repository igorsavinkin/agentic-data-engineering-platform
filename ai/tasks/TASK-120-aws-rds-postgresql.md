# TASK-120 — AWS RDS PostgreSQL

## Objective
Implement Terraform for AWS RDS PostgreSQL replacing local PostgreSQL for the warehouse layer. Configure instance size, storage, backups, security groups, and connection from EKS. Credentials must be managed via AWS Secrets Manager or equivalent.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-119.

## Terraform/AWS Rules
- Never commit credentials, access keys, or secrets.
- RDS must be in private subnets; accessible only from EKS security group.
- Enable automated backups and appropriate retention.
- Credentials must use AWS Secrets Manager or equivalent; never hardcoded.
- Instance sizing should be documented and justifiable.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-120 only.
