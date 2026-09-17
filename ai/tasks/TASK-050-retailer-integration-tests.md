# TASK-050 — Retailer Integration Tests

## Objective and Scope
Create the Milestone 5B integration gate for the retailer implemented in TASK-046–049.

Required flow:
`retailer fixture/mock → adapter → HTML parser → pagination/retry → canonical event → Kafka → Processor → Parquet → PostgreSQL`

Requirements:
- Normal CI must be deterministic and must not depend on the live retailer.
- Use fixed HTML/HTTP fixtures at the external boundary while exercising real internal integration boundaries where the repository infrastructure supports them.
- Verify at least one retailer observation is traceable through the full pipeline.
- Verify multiple pages are aggregated correctly.
- Verify malformed/unparseable records do not silently enter valid downstream data.
- Verify transient failure followed by retry/recovery.
- Verify partial pagination failure behavior from TASK-048.
- Verify replay/idempotency: replaying the same logical observation must not create duplicate logical warehouse observations.
- Verify source-health metrics/status for healthy and degraded runs.
- Include regression smoke coverage for existing API/marketplace adapters where practical.
- Do not begin TASK-051 difficult-source implementation.

Acceptance:
A valid retailer observation can traverse the canonical pipeline into PostgreSQL. The retailer may fail independently without silent data loss or downstream schema changes. Retry, partial failure, replay, malformed input, and source-health behavior are deterministic and tested.

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
Implement TASK-050 only. Stop when its acceptance criteria and final verification are satisfied.
