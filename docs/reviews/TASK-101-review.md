# TASK-101 Review — Qwen (Round 3, APPROVED)

**Task:** TASK-101 — Kafka Failure Test
**Reviewer:** Qwen Code CLI
**Round:** 3 (final)
**Verdict:** APPROVED

## Summary

Adds `tests/test_kafka_failure.py` — four integration tests demonstrating the full Kafka failure lifecycle: Baseline → Failure → Detection (metrics) → Recovery → No silent data loss.

## Tests Added

| Test | Purpose |
|------|---------|
| `test_broker_restart_no_silent_data_loss` | Full lifecycle: produce, partial commit, broker stop, verify PublishError + consumer error metrics, restart, verify uncommitted event replayed |
| `test_producer_failure_detected_and_reported` | Producer error counter increments on failed publish during outage |
| `test_consumer_lag_detected_after_partial_commit` | Lag detected via sample_lag after partial commit on same-partition events |
| `test_committed_offsets_survive_broker_restart` | Committed offsets persist across broker restart |

## Review Rounds

### Round 1 — CHANGES REQUIRED
5 findings (2 critical, 1 medium, 1 low/medium, 1 low):
1. Lag test never polled → no partition assignment
2. Partition-dependent lag assertion (3 partitions, different keys)
3. `_wait_for_broker` didn't verify readiness (lazy Producer creation)
4. 30s blocking during outage (default delivery timeout)
5. Consumer connectivity loss not actually verified

### Round 2 — CHANGES REQUIRED
4 of 5 fixed. 2 remaining:
1. `_wait_for_broker` still broken (probe topic `__probe__` can't exist — auto-create disabled; no delivery callback; flush return ignored)
2. Consumer error check fragile (single poll may not trigger error)

### Round 3 — APPROVED
Both remaining issues fixed:
1. `_wait_for_broker` now uses `AdminClient.list_topics()` metadata request
2. Consumer error check polls in loop until `CONSUMER_ERRORS > 0` or 10s deadline

## Quality Checks
- ruff check: PASS
- mypy: PASS
- ruff format: PASS
- pytest --collect-only: 4 tests collected
