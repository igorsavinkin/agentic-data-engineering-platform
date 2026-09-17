# TASK-053 — Source Degradation Detection

## Objective and Scope
Detect when the difficult source is technically reachable but data collection quality has degraded.

Requirements:
- Define explicit degradation states using existing source-health abstractions.
- Distinguish at minimum:
  - healthy
  - unreachable/fetch failure
  - rate limited
  - structurally changed/parser failure
  - partially parseable
  - successful but unexpectedly empty where determinable
- Use measurable signals such as fetch outcomes, parse success ratio, malformed count, emitted record count, and structural selector/schema failures.
- Avoid brittle hard-coded production thresholds unless justified/configurable.
- Preserve diagnostic reason categories without high-cardinality metric labels.
- A degraded source must not silently report healthy merely because HTTP returned 200.
- Degradation detection must not mutate canonical downstream data.
- Add structured diagnostic logging and metrics/state suitable for later Airflow/data-quality checks.
- Do not implement Airflow or alert delivery here.

Tests:
- healthy source
- HTTP success + parser structural failure
- partially parseable response
- rate-limited state
- unreachable state
- empty-result scenario
- recovery from degraded to healthy
- metric/state classification

Acceptance:
The platform can programmatically distinguish source availability from source data quality and identify meaningful degradation without changing downstream schemas.

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
Implement TASK-053 only. Stop when its acceptance criteria and final verification are satisfied.
