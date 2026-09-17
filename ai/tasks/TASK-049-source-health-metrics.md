# TASK-049 — Source-Health Metrics

## Objective and Scope
Add operational health metrics to the completed retailer adapter from TASK-046–048.

Requirements:
- Reuse the existing `SourceMetrics`/metrics conventions from earlier source work; do not introduce a second metrics framework.
- Track fetch attempts, successes/failures, pages fetched, records/events emitted, malformed records, retry activity, and fetch/parse latency where existing abstractions support them.
- Track or expose the last successful collection/fresh observation timestamp so freshness can be evaluated.
- Distinguish: successful zero-result collection, network/source failure, parser degradation, partial pagination failure, and stale data.
- Keep labels low-cardinality. Source/status/reason categories are acceptable; URL, product ID, external ID, event ID, exception text, and page URL are not metric labels.
- Add structured logs for degraded/partial source runs without logging secrets or full page bodies.
- Metrics/logging failures must not change ingestion semantics.
- Integrate with the retry/pagination behavior already implemented in TASK-048 rather than duplicating it.
- Do not implement Grafana dashboards, alerts, or Airflow DAGs.

Tests:
- successful fetch metrics
- zero-result successful fetch
- network failure
- parser/malformed-record degradation
- retry metrics
- partial pagination failure
- record/event counts
- freshness/last-success state
- no high-cardinality labels

Acceptance:
The retailer source exposes enough programmatic information to distinguish healthy collection, zero results, network failure, parser degradation, partial collection, and stale data without changing canonical ingestion behavior.

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
Implement TASK-049 only. Stop when its acceptance criteria and final verification are satisfied.
