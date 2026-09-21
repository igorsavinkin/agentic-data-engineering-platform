# TASK-129 — Security Review

## Objective
Conduct a security review of the platform covering credential management, network exposure, IAM policies, API authentication, SQL injection prevention, and secret handling. Document findings, remediation actions taken, and residual risks.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and completed implementation through TASK-128.

## Security Rules
- Never commit credentials, access keys, or secrets.
- Review must cover all service boundaries and external interfaces.
- Document both findings and remediation actions.
- Do not weaken security controls for convenience.
- Target audience: experienced engineer evaluating the portfolio.

## Engineering Rules
Implement this task only. Follow existing conventions and service boundaries. Add deterministic tests where applicable, run repository quality checks, inspect final diff, and escalate architecture-significant issues.

## Definition of Done
Objective and acceptance behavior are verified by focused tests, checks pass, documentation is updated where needed, and no unrelated architecture changes or secrets are introduced.

## Agent Instructions
Implement TASK-129 only.
