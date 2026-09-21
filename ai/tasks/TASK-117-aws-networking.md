# TASK-117 — AWS Networking

## Objective
Implement Terraform for AWS VPC, subnets (public/private), internet gateway, NAT gateway, route tables, and security groups. The network must support EKS, RDS, and internal service communication while following AWS networking best practices.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-116.

## Terraform/AWS Rules
- Never commit credentials, access keys, or secrets.
- Network must support EKS, RDS, and internal communication.
- Use private subnets for compute and database; public subnets only for load balancers/NAT.
- Security groups must follow least-privilege principles.
- Document the network topology.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-117 only.
