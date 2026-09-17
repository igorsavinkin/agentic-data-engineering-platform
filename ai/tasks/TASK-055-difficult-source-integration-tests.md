# TASK-055 — Difficult-Source Integration Tests

## Objective and Scope
Create the Milestone 5C integration gate proving graceful degradation of the difficult source.

Required flow:
`difficult-source fixture/mock → adapter → retry/backoff → degradation/freshness state → canonical event → Kafka → Processor → Parquet → PostgreSQL`

Required scenarios:
1. healthy observation through the pipeline
2. rate-limited then recovered
3. persistent rate limiting
4. source unavailable
5. structural/parser change
6. partially parseable source
7. freshness becomes stale
8. recovery from degraded/stale state
9. replay/duplicate delivery
10. regression smoke test for earlier sources

Requirements:
- CI must be deterministic and independent of live difficult-source access.
- Exercise real internal infrastructure boundaries where practical.
- Validate final stored state and health/degradation state, not only process exit codes.
- Verify failure of this source does not require downstream schema changes or corrupt observations from other sources.
- Verify valid partial data follows documented semantics.
- Verify replay/idempotency.
- Verify no source-specific branching leaked into processor/lake/warehouse.
- Document the demonstrated failure/recovery scenarios.

Acceptance:
The platform demonstrates graceful degradation when the source becomes unavailable, rate limited, structurally changed, stale, or partially parseable. The difficult source remains replaceable without changing downstream architecture. Repository quality checks and the milestone integration gate pass.

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
Implement TASK-055 only. Stop when its acceptance criteria and final verification are satisfied.
