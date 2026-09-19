# TASK-062 — Qwen Post-Merge Review

**Reviewer:** Qwen Code CLI
**Date:** 2026-09-19
**Scope:** Post-merge review of PR #75 (commits fa4bea4..14f9aec)
**Verdict:** NEEDS FIXES — 2 HIGH correctness/observability defects

## Summary

Clean thin-DAG separation and well-unit-tested calculator, but two HIGH findings should be fixed: #1 changes the actual analytical output (off-by-one date), and #2 masks total infrastructure failure as success.

## Findings

### HIGH

**H1 — `metric_date` is off-by-one: `logical_date - 1 day` selects the wrong data interval**
`airflow/dags/build_daily_metrics_dag.py:93`

The code's premise — "The logical date represents the end of the interval" — is factually wrong for Airflow 2.x. `logical_date` **is** `data_interval_start` (the *start* of the interval); `data_interval_end = logical_date + schedule_interval`. For `schedule=timedelta(days=1)`, a run with `logical_date = D` covers `[D, D+1)`.

So `metric_date` should be `logical_date` (or `context["data_interval_start"]`), not `logical_date - 1 day`. The current code queries and labels `[D-1, D)`, i.e. the *previous* interval.

**Impact:**
- Every run computes the day *before* its data interval, introducing a permanent one-day lag.
- The first interval (`start_date` day) is never processed.
- Backfill/clear semantics break: re-running `logical_date = D` rebuilds D-1, not D — directly violating the "reproducible" objective.

**H2 — Warehouse query failure is silently converted into a green, zero-metric run**
`airflow/dags/build_daily_metrics_dag.py:99-110`

A DB outage / connection error / bad credentials produces an empty frame -> `calculator.compute` returns 0 metrics -> `write_metrics` writes nothing -> no `raise` -> **the DAG run is marked SUCCESS**. A total warehouse failure is therefore invisible.

The task objective explicitly calls for "explicit missing/late-data behavior" — the code conflates "genuinely no observations for a day" (legitimate empty) with "couldn't reach the warehouse" (should fail and be retried).

### MEDIUM

**M1 — DAG "structure" tests are string-matching, and there are no tests for the DAG logic or persistence**
All 20 tests are `source = DAG_PATH.read_text()` followed by `assert "substring" in source` or `ast.parse`. They verify nothing about behavior:
- No test exercises `_build_daily_metrics`, so the off-by-one in finding #1 is not caught.
- No test exercises `_query_observations` or `MetricsResultWriter`.
- No test covers replay/idempotency of the actual write path.

**M2 — Day-boundary query is timezone-dependent, inconsistent with repo convention**
`airflow/dags/build_daily_metrics_dag.py:43-44`

`collected_at` is `TIMESTAMP(timezone=True)`. Casting `'YYYY-MM-DD'::date` and comparing against `timestamptz` resolves the date at the DB session's timezone. If the session timezone isn't UTC, the "day" window shifts. The rest of the codebase handles this with `collected_at AT TIME ZONE 'UTC'`.

### LOW

**L1 — `written` count is inaccurate on replay; `skipped` is never populated**
With `ON CONFLICT (replay_key) DO NOTHING`, `written` reports *attempted* rows, not rows actually inserted.

**L2 — Docstring type mismatch and minor dead/duplicate code**
- `product_id: text` docstring but `p.id` is `BigInteger`.
- Dead `else` branch with `metric_date = str(logical_date)`.
- `summary["errors"] = metrics_result.errors + write_result.errors` — `write_result.errors` is always empty.

## Strengths

- Clean thin-DAG separation: computation in `libs/metrics/calculator.py`, persistence in `libs/metrics/persistence.py`, DAG is orchestration only.
- Stateless, well-unit-tested calculator with correct empty/null handling.
- Migration and migration tests updated consistently (version `006`, table counts, downgrade).
- Replay-key determinism (`metric_name:metric_date:dimension`) and `ON CONFLICT (replay_key) DO NOTHING` are correctly implemented.

## Verdict

The two HIGH findings should be fixed: #1 changes the actual analytical output and #2 masks total infrastructure failure as success.
