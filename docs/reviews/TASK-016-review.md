# TASK-016 Review — Deduplication

**Reviewed commit:** ef91811
**Reviewer:** Qoder (automated review)
**Date:** 2026-09-11

## Verdict: APPROVED

## Summary

Implementation adds `services/processor/deduplication.py` and `tests/test_deduplication.py` providing replay-safe deduplication for valid processor records. The module uses `event_id` as the observation-event identity and deterministically splits input into unique records, exact duplicates, and conflicts.

## Requirements Coverage

| # | Requirement | Status | Evidence |
|---|------------|--------|----------|
| 1 | Use `event_id` as identity | PASS | `_HASH_COLUMNS` excludes `event_id`; grouping by `event_id` in `_mark_within_batch_status` |
| 2 | Repeated delivery → no duplicates | PASS | `test_two_identical_rows_keep_one`, `test_second_batch_duplicate_detected` |
| 3 | Deterministic | PASS | `rank("ordinal")` for consistent ordering; `test_same_input_same_output` |
| 4 | Never claim exactly-once | PASS | Module docstring explicitly states "at-least-once + idempotent" |
| 5 | Don't collapse legitimate observations | PASS | `test_same_product_different_times_kept_separate` — different event_ids preserved |
| 6 | Respect Kafka partition/ordering | PASS | No global ordering; within-batch only + optional state |
| 7 | Conflicting payloads surfaced | PASS | `test_same_event_id_different_name_is_conflict`; `conflicts` DataFrame |
| 8 | Independently testable | PASS | Pure function with optional `state` parameter |
| 9 | Document state lifetime | PASS | `DeduplicationState` docstring documents in-memory scope and restart behavior |

## Required Tests Coverage

| Test | Status | Test Class |
|------|--------|------------|
| Exact duplicate in one batch | PASS | `TestExactDuplicateInOneBatch` (5 tests) |
| Duplicate across processor calls | PASS | `TestDuplicateAcrossProcessorCalls` (4 tests) |
| Same product different times | PASS | `TestSameProductDifferentCollectionTimes` (2 tests) |
| Same event ID + conflicting payload | PASS | `TestConflictingPayloadSameEventId` (5 tests) |
| Replay-order determinism | PASS | `TestReplayOrderDeterminism` (4 tests) |

## Quality Checks

- **ruff format:** PASS (2 files already formatted)
- **ruff check:** PASS (all checks passed)
- **mypy:** PASS (31 source files, no issues)
- **pytest:** PASS (355 tests total, 24 new deduplication tests)

## Architecture Assessment

### Strengths

1. **Clean separation of concerns**: `DeduplicationResult` mirrors `ValidationResult` pattern, making pipeline integration natural.
2. **Explicit conflict handling**: Rather than silently dropping conflicting payloads, they are surfaced in a dedicated DataFrame for downstream routing.
3. **Well-documented state boundary**: The `DeduplicationState` docstring clearly communicates that this is in-memory only and durable dedup is out of scope.
4. **Polars-native implementation**: Uses window functions (`n_unique`, `rank`) for efficient batch processing without Python loops over rows.
5. **Comprehensive test coverage**: 24 tests covering all required scenarios plus interface contracts and edge cases.

### Design Decisions

1. **Payload hashing**: Uses `concat_str` + `hash()` on all non-event_id columns. This is deterministic and handles all column types via `cast(Utf8, strict=False)`.

2. **Within-batch vs cross-batch**: Two-phase approach — cross-batch state checked first, then within-batch window functions. This correctly handles the case where a batch contains both a replay and new duplicates.

3. **Conflict = all rows in group**: When same event_id has different payloads, ALL rows in that group are marked as conflicts (none kept as "deduplicated"). This is conservative and correct — the downstream system must decide how to handle conflicts.

### No Blocking Issues Found

The implementation is complete, correct, and well-tested. All TASK-016 requirements are met.

## Files Changed

- `services/processor/deduplication.py` (217 lines) — new module
- `tests/test_deduplication.py` (328 lines) — new test file

## Recommendations (non-blocking)

1. **Future**: Consider adding metrics for duplicates_removed and conflicts_count when TASK-018 (metrics) is implemented.
2. **Future**: When TASK-017 (DLQ) is implemented, conflicts may need DLQ routing.
3. **Future**: Durable cross-instance dedup (PostgreSQL uniqueness) should be addressed in warehouse loading tasks.
