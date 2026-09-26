# TASK-135 — Automated Secret Scanning Guardrail

## Objective
Add automated secret detection to prevent credentials, API keys, passwords, tokens, Fernet keys, and similar sensitive values from being committed again.

Provide two protection layers:
- local pre-commit scanning for early developer feedback;
- CI secret scanning as the required enforcement gate for pull requests.

Use one primary scanner for both local and CI checks where practical.

## Required Context
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and the completed TASK-134 secret-handling remediation.

## Security Rules
- Never commit real credentials, access keys, or secrets.
- CI must fail when a blocking secret is detected.
- Local pre-commit scanning must detect representative synthetic/test secrets.
- Use only synthetic/non-functional secrets for validation.
- Do not reuse the Fernet key exposed during TASK-134 as a test fixture.
- Keep exclusions narrow, explicit, and documented.
- If an existing suspected real secret is discovered, report it instead of silently modifying unrelated configuration.
- Do not rewrite Git history or force-push `main`.

## Implementation Requirements
- Configure a mature secret-scanning tool suitable for local and CI use.
- Add repository-supported pre-commit configuration.
- Add or extend GitHub Actions secret scanning for pull requests.
- Document installation, manual scanning, CI behavior, false-positive handling, and justified exclusions.
- Verify the clean repository passes the configured scanner.
- Verify a representative synthetic secret causes the scanner to fail.
- Preserve existing CI and repository conventions.

## Out of Scope
- Git history rewriting.
- Production credential rotation.
- Reworking TASK-134 Airflow secret handling.
- Replacing Kubernetes Secrets with Vault, AWS Secrets Manager, External Secrets Operator, or similar systems.
- Unrelated security or infrastructure changes.
- Remediation of pre-existing development placeholders unless they block the scanner.

## Definition of Done
Local pre-commit and CI secret scanning are configured, synthetic-secret detection is verified, the clean repository passes, relevant tests and quality checks pass, documentation is updated, exclusions are justified, and no real secrets or unrelated architecture changes are introduced.

## Agent Instructions
Implement TASK-135 only.

Use a dedicated TASK-135 branch/worktree according to repository governance.

Do not rewrite Git history, force-push `main`, rotate external credentials, or silently fix unrelated findings.

Stop after implementation, tests, self-review, and commit so the task can proceed to independent Qwen review.