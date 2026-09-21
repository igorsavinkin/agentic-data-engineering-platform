# TASK-103 Qwen Review Report

## Round 1 — CHANGES REQUIRED

### F1 — CRITICAL — `process_next()` polls internally; pre-fetching with `_consume_all()` makes the crash never happen
**Status:** Fixed in round 2

`KafkaConsumer.process_next()` calls `self.poll()` itself. The test pre-fetched messages with `_consume_all()` (which calls `poll()` directly) and then called `process_next()`, which polled *additional* messages — discarding the pre-fetched ones. The crash callback was never invoked.

**Fix:** Removed `_consume_all()` pre-fetching. Created `_process_one()` helper that calls `process_next()` in a bounded loop until it processes one message or times out.

### F2 — MINOR — Multi-partition scatter undermines determinism
**Status:** Fixed in round 2

Events had distinct `external_id` values, scattering across partitions. The "process event 1, crash on event 2" narrative was not well-defined across partitions.

**Fix:** All events now use `_SAME_EXTERNAL_ID = "crash-test-product"` ensuring same partition key (`crash-test:crash-test-product`) and deterministic single-partition ordering.

### F3 — MINOR — "Log" detection claimed but never asserted
**Status:** Fixed in round 2

The failure pattern requires "Failure -> Detection -> Metric/log -> Recovery". The test asserted `PROCESSING_ERRORS` metric but never asserted any log output.

**Fix:** Added `caplog.at_level(logging.ERROR, logger="libs.common.kafka_consumer")` with assertion for `kafka_processing_stopped` log message in both crash tests.

## Round 2 — CHANGES REQUIRED

### F1 — MINOR — `first_committed == processed_event_ids[0]` is tautological
**Status:** Fixed in round 3

`first_committed` was captured as `processed_event_ids[0]`, and consumer2 only appends to the list, so the comparison was always True.

**Fix:** Capture produced event IDs during publishing, then assert `processed_event_ids == produced_event_ids` — verifying exact sequence, no loss, no duplicates.

## Round 3 — CHANGES REQUIRED

### R3-1 — CRITICAL — `test_processing_error_metric_on_crash` non-deterministic due to rebalance race
**Status:** Fixed

Single-shot `process_next()` immediately after `subscribe()` could return False before consumer-group rebalance completed, causing `pytest.raises(RuntimeError)` to fail with "DID NOT RAISE".

**Fix:** Wrapped crash trigger in `_process_one()` bounded retry loop.

### R3-2 — Suggestion — Same race pattern in `test_crash_uncommitted_event_redelivered` crash step
**Status:** Fixed

Lower risk because consumer was already warm, but applied same fix for full determinism.

## Final Status: APPROVED (after 3 rounds of fixes)

All findings resolved. Tests demonstrate the full failure lifecycle:
- Baseline (produce events with deterministic partition key)
- Failure (processor crash via RuntimeError in process callback)
- Detection (PROCESSING_ERRORS metric + kafka_processing_stopped log)
- Recovery (new consumer with same group resumes from last committed offset)
- No silent data loss (exact event sequence verified: produced == processed)
