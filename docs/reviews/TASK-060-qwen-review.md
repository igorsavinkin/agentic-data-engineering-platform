# TASK-060 — Qwen Post-Merge Review

**Reviewer:** Qwen Code CLI
**Date:** 2026-09-19
**Scope:** Post-merge review of PR #73 (commits e1d214a..600b6af)
**Verdict:** NEEDS FIXES — 2 critical defects

## Summary

The DAG is well-shaped as a thin orchestration layer (all check logic correctly delegated to `libs.quality.*`), but it has **two critical defects** that make it functionally broken, and its test suite would pass while both are present. The core task objective — "make logical-interval reruns idempotent" — is not met.

## Findings

### CRITICAL

**C1 — `p.sku` column does not exist; the warehouse query always fails silently**
`airflow/dags/daily_data_quality_dag.py:121`

The `products` table has columns `id`, `canonical_name`, `category`, `created_at`, `updated_at` — **no `sku` column**. The canonical identity is `p.id`. At runtime this SQL raises `column p.sku does not exist`. Because `_run_quality_checks` wraps the query in a bare `except Exception` and falls back to an empty frame, the error is swallowed and the DAG records "all required fields present / all prices valid" with `records_checked=0` on every run. The DAG is effectively dead on arrival and the defect is invisible.

Fix: use `p.id AS product_id`.

**C2 — Idempotency is not achieved: `logical_date` is computed but never used in the replay key**
`airflow/dags/daily_data_quality_dag.py:160-183`

The DAG computes `logical_date_str` and even claims in its docstring that "rerunning the same logical interval does not duplicate results," but it calls:
```python
writer.write_suite_result(suite_result)   # no pipeline_run_id, no logical interval
```

`write_suite_result` only forwards `pipeline_run_id=None` to `write_results`, and all four default checks have `source=None`. In `make_replay_key`, the replay key falls back to `checked_at.isoformat()` — a **fresh wall-clock timestamp on every execution**. Each rerun of the same logical interval produces 4 new rows.

This directly contradicts the task objective. Contrast with the two sibling DAGs, which both bind the logical date into the replay key.

### HIGH

**H1 — Warehouse outage is masked and reported as success**
`airflow/dags/daily_data_quality_dag.py:176-190`

The `except Exception` around `_query_observations` conflates "warehouse unreachable" with "legitimately no data in the last 24h." On an empty frame, checks return PASSED, and the DAG returns success. The result is a green task that records "passed" quality checks while the warehouse is down.

### MEDIUM

**M1 — Default `duplicates` check key is semantically wrong**
`airflow/dags/daily_data_quality_dag.py:54-57`

`product_observations` is an append-only historical fact table — the same canonical product is legitimately observed many times per day. A duplicate key of `(source_name, product_id)` will report a duplicate rate near 100% on every run.

**M2 — Tests are superficial and cover none of the acceptance criteria**
All 28 tests are `ast.parse` plus substring assertions. They never import or exercise the actual logic, never verify idempotency, never validate the SQL against the actual schema.

### LOW

**L1 — Unvalidated Airflow Variable crashes uncaught in `_build_checks`**
A Variable with a non-dict entry or an invalid severity string will crash the task rather than falling back to defaults.

**L2 — `written`/`skipped` summary fields are misleading**
`write_result.written` is set to `len(values)` regardless of how many rows `ON CONFLICT DO NOTHING` actually inserted, and `WriteResult.skipped` is never incremented.

**L3 — `LIMIT 100000` and fallback-frame column mismatch are undocumented**

## Verdict

The thin-DAG structure is correct, but the implementation has critical defects: **C1** makes the DAG non-functional, and **C2** means the stated idempotency guarantee is false. **H1** additionally turns both into a silent, falsely-green run. Recommended fixes: fix `p.sku` -> `p.id`, extend the persistence writer to bind a logical interval into the replay key, treat query failure as a hard error.
