# TASK-061 — Qwen Post-Merge Review

**Reviewer:** Qwen Code CLI
**Date:** 2026-09-19
**Scope:** Post-merge review of PR #74 (commits 600b6af..fa4bea4)
**Verdict:** NEEDS FIXES — critical idempotency defect

## Summary

The CRITICAL idempotency/replay defect contradicts the task's core objective and can silently duplicate lake data under a partial failure — exactly the case the DAG claims to handle. The HIGH bucket-hardcoding issue is a silent no-op risk in production.

## Findings

### CRITICAL — Replay/partial failure is not idempotent and can duplicate data

`libs/compaction/compactor.py` — `compact_partition`

The safety invariant the task asks for ("validate replacement before source removal and handle replay/partial failure safely") is broken:

1. `compact_partition` writes `compacted-{uuid4}.parquet`, then deletes sources in a plain `for` loop.
2. If the process crashes after `put_object` but before/partway through the delete loop — or a single `delete_object` raises a transient `StorageError` — the compacted file is left coexisting with the remaining source files.
3. On the next run, `parquet_keys` includes the prior `compacted-*.parquet`. The compactor re-reads it together with the surviving sources and writes *another* compacted file, duplicating every record that was already absorbed.

**Concrete sequence:** sources A..E -> write `compacted-x` (A..E) -> delete A,B,C, then fail on D -> state is `compacted-x` + D + E. Once two new files arrive, the partition has 5 files again, and the next compaction reads `compacted-x` (A..E) + D + E + F + G -> D and E are duplicated.

**Root cause:** Non-deterministic UUID filename plus failure to exclude `compacted-*` files from the source set.

**Fix:** Exclude already-compacted files from `parquet_keys` (and from `discover_partitions`'s file count), and/or derive a deterministic compaction key, and/or write the compacted file to a staging prefix and rename it into place only after sources are deleted.

### HIGH — DAG hardcodes the bucket name, ignoring `MinIOSettings`

`airflow/dags/parquet_compaction_dag.py`

`ParquetCompactor(storage, bucket=layer, ...)` uses `layer` from `DEFAULT_LAYERS = ["bronze"]`, i.e. the literal string `"bronze"`. Writers (BronzeWriter/SilverWriter) instead honor `MinIOSettings.minio_bucket_bronze` (configurable via `APP_MINIO_BUCKET_BRONZE`). If the bucket is customized, the DAG silently lists/compacts a nonexistent `"bronze"` bucket and does nothing.

### MEDIUM

**M1 — `max_source_file_bytes` is dead configuration**
The field is exposed in `CompactionConfig` and wired through the Airflow Variable, but `compact_partition` never references it. "Compact eligible *small* files" is not implemented: every parquet file in a partition is read and rewritten regardless of size.

**M2 — `CompactionPlan` is a speculative, unused abstraction**
`libs/compaction/compactor.py` defines `CompactionPlan` and `__init__.py` exports it, but nothing constructs or consumes it. AGENTS.md discourages speculative abstractions.

**M3 — No coverage for the dangerous paths**
- `test_compact_all` asserts `len(results) >= 0`, which is trivially true.
- No test covers partial-delete failure, re-run after a prior successful compaction, or the coexistence of `compacted-*` with sources.
- `MinIOStorage.delete_object` has **no unit test**.
- DAG tests are 20 string-substring assertions against the DAG's source text.

### LOW

**L1 — `delete_object` is not serialized by `self._lock`**
Unlike `put_object`/`ensure_bucket`, `delete_object` does not acquire `self._lock`.

**L2 — `_get_sources` returns the mutable module-level default directly**
A caller mutating it corrupts the module default.

**L3 — Docstrings contradict the implementation**
Module docstring says "a deterministic compaction key" but the key is `uuid.uuid4().hex[:8]` (non-deterministic).

**L4 — Schema preservation is achieved by refusing, not reconciling**
`pl.concat(frames, rechunk=True)` raises on heterogeneous schemas, so a partition with schema-evolved files simply fails to compact.

## Verdict

Do not merge as-is. The CRITICAL idempotency/replay defect contradicts the task's core objective and can silently duplicate lake data under a partial failure. The HIGH bucket-hardcoding issue is a silent no-op risk in production. Both need fixes and tests (partial-failure and re-run idempotency scenarios) before approval.
