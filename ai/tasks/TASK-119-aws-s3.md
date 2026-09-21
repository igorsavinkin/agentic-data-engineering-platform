# TASK-119 — AWS S3

## Objective
Implement Terraform for AWS S3 buckets replacing MinIO for the data lake layer. Configure bucket structure (bronze/silver/gold), lifecycle policies, versioning, encryption, and IAM access for raw-writer, lake-writer, and Airflow.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-118.

## Terraform/AWS Rules
- Never commit credentials, access keys, or secrets.
- S3 must mirror the established lake structure (bronze/silver/gold).
- Enable encryption and versioning.
- Lifecycle policies must manage storage costs.
- IAM access must follow least-privilege per service.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-119 only.
