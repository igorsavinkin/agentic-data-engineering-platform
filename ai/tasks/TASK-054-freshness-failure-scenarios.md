# TASK-054 — Freshness Failure Scenarios

## Objective and Scope
Implement and demonstrate freshness failure detection for the difficult source.

Requirements:
- Define freshness using the project's established collection/observation timestamp semantics.
- Track last successful usable observation/collection as appropriate to existing source-health design.
- Add configurable freshness thresholds rather than hard-coding environment-specific values.
- Distinguish:
  - source currently failing but data still within freshness threshold
  - stale source
  - never successfully collected
  - successful zero-result run
  - recovery after stale/degraded state
- Ensure retries do not falsely refresh freshness when no usable data was obtained.
- Expose freshness state programmatically for later `ingestion_health`/data-quality Airflow work.
- Use deterministic clock injection/freezing in tests.
- Do not implement Airflow DAGs or alert notifications.

Tests:
- fresh source
- threshold boundary
- stale source
- never-successful source
- failed run after prior success
- zero-result semantics
- recovery refreshes state
- retry without usable data does not refresh freshness

Acceptance:
Freshness failures are reproducible, deterministic, distinguishable from temporary fetch failures, and consumable by later orchestration/data-quality components.

## Required Context Before Coding
Read the current repository versions of `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and relevant completed source-adapter tasks. Higher-authority repository documents win on conflicts.

## Engineering Rules
- Implement this task only.
- Use typed Python, explicit interfaces, deterministic tests, and existing repository conventions.
- Preserve source-adapter isolation and canonical downstream contracts.
- Preserve documented at-least-once/idempotent semantics; never claim exactly-once without proof.
- Never commit/log credentials or secrets.
- Do not weaken/delete tests to make CI green.
- Run relevant unit/integration tests plus configured lint/format/type checks after final edits.
- Inspect the final Git diff and verify acceptance criteria.
- Escalate if implementation requires a fundamental architecture/schema change or broad unrelated refactoring.

## Agent Instructions
Implement TASK-054 only. Stop when its acceptance criteria and final verification are satisfied.
