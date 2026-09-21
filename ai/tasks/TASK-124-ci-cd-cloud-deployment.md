# TASK-124 — CI/CD Cloud Deployment

## Objective
Extend CI/CD to support automated cloud deployment to AWS. Configure GitHub Actions (or existing CI) for Terraform plan/apply, Docker build/push to ECR, and Helm upgrade on EKS. Include environment separation and deployment safety checks.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-123.

## Terraform/AWS Rules
- Never commit credentials, access keys, or secrets.
- CI/CD must use OIDC or equivalent; no long-lived AWS credentials in CI.
- Include Terraform plan before apply for safety.
- Environment separation must be enforced.
- Document the CI/CD pipeline and required secrets configuration.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-124 only.
