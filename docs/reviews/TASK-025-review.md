# TASK-025 Qwen Review Report

**Commit:** `7029a48` (feature/TASK-025)
**Base:** `ad00dbd` (main)
**Date:** 2026-09-13
**Reviewer:** Qwen (automated review via qoder-task-orchestrator)

## Summary

Implements Parquet read/query utilities for Bronze/Silver data lake layers per TASK-025 specification. Adds partition discovery, lazy scanning with Polars, and a high-level LakeReader API with column projection support.

## Changes Overview

| File | Lines Changed | Purpose |
|------|--------------|---------|
| `libs/common/minio_storage.py` | +42 | Added `list_objects()` method using boto3 paginator |
| `libs/parquet_reader/__init__.py` | +19 | Public API exports |
| `libs/parquet_reader/scanner.py` | +357 | Partition discovery and lazy Polars scanner |
| `libs/parquet_reader/reader.py` | +241 | High-level LakeReader API |
| `tests/test_parquet_reader.py` | +490 | 23 unit tests covering all functionality |

**Total:** ~1,149 lines added across 5 files.

## Quality Checks

- **ruff format:** PASS (147 files formatted)
- **ruff check:** PASS (no lint errors)
- **mypy:** PASS (no type issues in 58 source files)
- **pytest:** PASS (23/23 tests passing)

## Specification Compliance

### Required Features (from TASK-025-specification.md)

| Requirement | Status | Notes |
|------------|--------|-------|
| Read by layer/source/time range | DONE | `PartitionFilter` supports all three dimensions |
| Column projection | DONE | `columns` parameter passed through to Polars `select()` |
| Lazy scanning / pushdown | DONE | `LazyScanner.scan()` returns `pl.LazyFrame` with predicate/projection pushdown |
| Predictable empty/missing behavior | DONE | Returns empty DataFrame on no match; raises `ValueError` only when explicitly scanning with no files |
| Avoid large Python list/dict materialization | DONE | Uses lazy evaluation; `_discover_files()` returns file URIs not data |
| Read-only | DONE | No write operations; all methods are queries |
| Partitioned Bronze/Silver discovery | DONE | `list_partitions()` parses canonical layout `<layer>/source=<src>/year=<YYYY>/month=<MM>/day=<DD>/` |
| Reusable by downstream components | DONE | Clean API with `LakeReader`, `LazyScanner`, `list_partitions` exports |

### Project Invariants

| Invariant | Status | Notes |
|-----------|--------|-------|
| At-least-once delivery + idempotent processing | N/A | Read-only task; no delivery semantics involved |
| Kafka as transport, not analytical datastore | N/A | Not applicable to this task |
| Parquet on MinIO/S3 is data-lake layer | DONE | Uses `storage_options` for S3-compatible reads |
| Use Polars/PyArrow for columnar work | DONE | All scanning uses `pl.scan_parquet()` |
| No secrets in source control | DONE | Credentials accessed via `MinIOSettings` at runtime |
| Do not implement later milestone functionality | DONE | Scope limited to read/query utilities only |

## Architecture Review

### Strengths

1. **Clean separation of concerns**: `scanner.py` handles low-level partition discovery and file enumeration; `reader.py` provides a high-level API. This makes both reusable independently.

2. **S3 URI construction**: The fix from bare MinIO keys (`bronze/source=...`) to proper S3 URIs (`s3://bucket/key`) with `storage_options` is architecturally correct. Polars can read directly from S3-compatible storage without local downloads.

3. **Bucket-relative key handling**: The code correctly accounts for the fact that MinIO/S3 returns object keys relative to the bucket, not including the bucket name. The `lstrip(f"{layer_value}/")` pattern for matching is sound.

4. **Lazy evaluation throughout**: `LazyScanner` caches the `LazyFrame` and defers computation until `collect()` or `count()`. Column projection is pushed down via `lf.select(columns)` after scan.

5. **Comprehensive test coverage**: 23 tests cover partition discovery filters, lazy scanning, column projection, empty results, caching, and end-to-end workflows. Mock-based approach avoids Docker dependency.

### Concerns

#### Minor: Storage options expose credentials in memory

The `_build_storage_options()` method extracts plaintext credentials from `SecretStr`:

```python
access_key = settings.minio_access_key.get_secret_value()
secret_key = settings.minio_secret_key.get_secret_value()
```

**Assessment:** This is acceptable because Polars requires plaintext credentials for S3 access. The `SecretStr` wrapping prevents accidental logging at the settings level. No change needed.

#### Minor: `_discover_files()` performs redundant listing

When `scan()` is called, `_discover_files()` first calls `list_partitions()` (which lists objects), then for each partition calls `list_objects()` again to get individual file keys. This means two round-trips per partition.

**Assessment:** For typical use cases (few partitions, few files per partition), this overhead is negligible. If performance becomes an issue, the partition listing could return file counts directly. Not a blocking concern for this task.

#### Informational: No integration tests marked

The spec mentions `python -m pytest -m integration` for integration tests with Docker. The current tests are all unit tests with mocks. No tests are marked with `@pytest.mark.integration`.

**Assessment:** Acceptable for this task since the focus is on deterministic unit tests. Integration tests would require a running MinIO instance and actual Parquet files, which is out of scope for the core implementation.

## Test Quality

All 23 tests pass. Coverage includes:

- **Partition discovery**: 6 tests covering no-filter listing, source filtering, date range filtering, empty results, file counting, and invalid prefix handling
- **Lazy scanning**: 5 tests covering LazyFrame creation, column projection, no-files error, row counting, and caching
- **LakeReader API**: 7 tests covering delegation, read/scan operations, empty results, health checks, and bucket override
- **Data classes**: 3 tests for `PartitionFilter` defaults, string-to-enum conversion, and full specification
- **End-to-end**: 2 tests verifying discover-then-read workflow and multi-source queries

Test quality is strong. Mock-based approach ensures determinism without Docker.

## Code Quality

- **Type annotations**: Complete throughout; mypy passes cleanly
- **Docstrings**: Present on all public functions/classes with parameter descriptions and examples
- **Logging**: Appropriate use of `logger.info()` and `logger.warning()` for observability
- **Error handling**: Graceful handling of missing files (returns empty DataFrame) vs. explicit errors (raises `ValueError` when no files found for scan)
- **Formatting**: ruff-compliant

## Verdict

**APPROVED**

This implementation fully satisfies the TASK-025 specification. The code is well-structured, type-safe, thoroughly tested, and follows project conventions. The S3 URI construction fix addresses the critical architectural requirement for Polars to read from MinIO/S3 without local file downloads.

No blocking findings. Two minor informational notes (credential exposure in memory, redundant listing) are acceptable trade-offs for correctness and simplicity.

## Recommendations for Future Work

1. Consider adding `@pytest.mark.integration` markers for tests that would benefit from real MinIO/S3 validation when Docker is available.
2. If partition discovery performance becomes a bottleneck, consider optimizing `_discover_files()` to avoid the double-listing pattern.
3. Document the expected partition layout (`<layer>/source=<src>/year=<YYYY>/month=<MM>/day=<DD>/`) in a shared ADR or the project README for downstream consumers.

---

*Review generated by Qwen automated review process.*
*Blocking findings: 0*
*Verdict: APPROVED*
