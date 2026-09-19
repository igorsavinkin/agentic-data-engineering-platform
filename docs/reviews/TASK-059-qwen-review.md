# TASK-059 — Qwen Post-Merge Review

**Reviewer:** Qwen Code CLI
**Date:** 2026-09-19
**Scope:** Post-merge review of PR #72 (commits fd15b3b..e1d214a)
**Verdict:** APPROVED with findings

## Summary

Idempotency/replay safety and the freshness path are solid and well-tested. The blocking gap is **H1**: the scheduled DAG never sources fetch outcomes, so the "degradation" dimension the task calls for is dead in production and the `state` column is effectively constant `"healthy"`.

## Findings

### HIGH

**H1 — Degradation detection is inert in the scheduled DAG; `state` will always be `healthy`.**
`_query_source_observations()` returns only `source_name`, `last_observation_at`, and `total_observations`. It never populates `SourceObservation.recent_fetch_outcomes`, so `IngestionHealthEvaluator._build_outcomes()` always yields `[]`. `SourceHealthAssessor.assess()` short-circuits on `if not outcomes: return HEALTHY` *before* the STALE/EMPTY/PARTIALLY_PARSEABLE checks. Result: in the real DAG path, the persisted `state` column is a constant `"healthy"` for every source, and only the separate `freshness_state` column carries signal. An actually-degraded source that keeps producing fresh observations (e.g. EMPTY_RESULT, PARTIALLY_PARSEABLE, STRUCTURALLY_CHANGED, or RATE_LIMITED) would be recorded as `state="healthy"` + `freshness_state="fresh"`.

The evaluator supports all these states and they are unit-tested — but only because the tests inject `recent_fetch_outcomes` directly. The DAG cannot feed that input, so the "degradation semantics" half of the task objective is not operationalized in the scheduled check.

### MEDIUM

**M1 — `evaluated_at` is written as a naive `datetime.now()` into a `TIMESTAMP(timezone=True)` column.**
`write_evaluations()` uses `now = evaluated_at or datetime.now()` (naive), unlike sibling `MetricsResultWriter` which uses `datetime.now(timezone.utc)`. Naive timestamps into `timestamptz` are interpreted in the server session timezone, so `evaluated_at` can be offset or inconsistent with `assessed_at`.

**M2 — Query-failure fallback can persist misleading HEALTHY/NEVER_COLLECTED rows.**
`_evaluate_and_persist()` catches *all* exceptions from `_query_source_observations()` with only a `logger.warning`, then substitutes `SourceObservation(source_name=name)` per configured source, which evaluates to `state="healthy"` + `freshness_state="never_collected"`. If the failure is query-specific (SQL/schema error) rather than total DB unavailability, the subsequent write succeeds and records false "healthy/never_collected" results while hiding the real error.

**M3 — `IngestionHealthResultReader.degraded_sources()` ignores `freshness_state`.**
It filters only `r.state != "healthy"`. A never-collected source is stored as `state="healthy"` + `freshness_state="never_collected"`, and a stale source may be `healthy` + `stale`. These freshness problems are invisible to a method named `degraded_sources`.

### LOW

**L1 — `written` misreports on replay; `skipped` is never populated.** `write_result.written = len(values)` counts *attempted* rows, not rows actually inserted. With `ON CONFLICT DO NOTHING`, a full idempotent replay still reports `written == N`.

**L2 — `_query_source_observations()` doesn't normalize the DB URL driver suffix.** The writer/reader and both sibling DAGs call `db_url.replace("postgresql+psycopg2://", "postgresql://")` before connecting, but this helper passes `db_url` straight to `psycopg2.connect`.

**L3 — `_get_source_config()` exception handler can reference unbound `raw`.** If `Variable.get(...)` itself raises, `raw` is undefined inside the `except` block's `extra={"raw": raw}` -> `NameError`.

**L4 — `IngestionHealthResultReader` is entirely untested.** No coverage for `latest_per_source`, `recent_evaluations`, `degraded_sources`, `_connect`, or `_map_row`.

**L5 — DAG tests are brittle string-matching.** `test_ingestion_health_dag.py` only asserts substrings in the source text; it never imports, parses, or executes the DAG.

**L6 — Evaluator degradation branches are only partially tested.** `rate_limited`, `structurally_changed`, `partially_parseable`, and `min_expected_records` paths are never exercised through `IngestionHealthEvaluator`.

**L7 — `reasons`/`signals` use `sa.JSON()` while sibling migration 004 uses `sa.dialects.postgresql.JSONB()`.** Inconsistent column type for analogous result tables.

**L8 — Redundant HEALTHY override in `evaluate_source()`.** The `NEVER_COLLECTED and HEALTHY and not outcomes` block rebuilds a `SourceHealthAssessment` solely to change the reason.

## What's Right

- **Replay safety is correct:** `replay_key = source_name:logical_date` (deterministic), `ON CONFLICT (replay_key) DO NOTHING` makes retries/replays no-ops.
- **Freshness computation is correct:** `_compute_freshness_age` clamps to `>= 0`, and `_compute_freshness_state` maps correctly.
- **Migration chain is consistent** at the TASK-059 point in time.
- **Determinism:** evaluator is stateless and accepts an injectable clock; `assessed_at` is UTC-aware.
