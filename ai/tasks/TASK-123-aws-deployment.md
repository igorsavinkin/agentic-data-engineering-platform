# TASK-123 — AWS Deployment

## Objective
Deploy the complete platform to AWS using Terraform and Helm. Verify end-to-end functionality: ingestion produces events, processing works, Parquet is written to S3, PostgreSQL is loaded, API responds, and the agent can answer questions. Document the deployment process.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-122.

## Terraform/AWS Rules
- Never commit credentials, access keys, or secrets.
- Deployment must use existing Helm charts and Terraform modules.
- Verify end-to-end functionality after deployment.
- Document the deployment process and prerequisites.
- Tear-down instructions must be included.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-123 only.
