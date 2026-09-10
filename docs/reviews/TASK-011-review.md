I've completed my review. Here is the complete report.

---

# TASK-011 Review — Kafka Metrics

## 1. Review Header

- **Task ID:** TASK-011 — Kafka Metrics
- **Review date:** 2026-09-10
- **Reviewed change set:** `638006c48d87929b1decc151c5264f688b9e5118..781625822bd6b6c7df67fd9d41cf7fc8e6ffa054` (branch `feature/TASK-011`)
- **Scope:** Producer/consumer operational counters, consumer lag sampling, documentation, and tests.
- **Verdict:** **CHANGES REQUIRED** (no blocking defects; three non-blocking test-coverage findings)

---

## 2. Requirements Coverage

Sources: `ai/tasks/TASK-011-kafka-metrics.md`, `ai/SPECIFICATION.md` §20, `ai/PROJECT.md` §10, `ai/AGENTS.md` §7/§9.

| Requirement | Status | Implementation evidence |
| --- | --- | --- |
| Produced events counter | ✅ Met | `ingestion_events_total` (`KafkaMetric.PRODUCED`) incremented only on confirmed delivery in `KafkaEventProducer.publish()` (`libs/common/kafka_producer.py`). Tested (`test_producer_metrics` success). |
| Consumed events counter | ✅ Met | `kafka_events_consumed_total` (`CONSUMED`) on each non-error record fetched in `KafkaConsumer.poll()`. Tested (`test_consumption_...`, `test_poll_outcomes`, integration). |
| Errors counters | ✅ Met | `ingestion_errors_total` (`PRODUCER_ERRORS`), `kafka_consumer_errors_total` (`CONSUMER_ERRORS`), `kafka_processing_errors_total` (`PROCESSING_ERRORS`), `kafka_lag_errors_total` (`LAG_ERRORS`). Tested for most boundaries. |
| Invalid events counter | ✅ Met | `events_invalid_total` (`INVALID`) for producer serialization/validation rejection and consumer decode/validation rejection (incl. tombstones). Tested (`test_producer_metrics` invalid, `test_invalid_counted_once_...`). |
| Consumer lag visibility | ✅ Met | `KafkaConsumer.sample_lag()` → `ConsumerLag(topic, partition, lag)` using broker high-watermark minus committed next offset; `None` = unknown. Tested (unit + integration). |
| Hooks for later Prometheus | ✅ Met | `KafkaMetrics.snapshot()` returns detached `dict[str, int]` of cumulative counters; no exporter in the data path; documented in `docs/kafka-metrics.md`. |
| No secrets | ✅ Met | Counters hold only fixed names/numbers; lag holds topic/partition/offset only. No payload/event-id/source-url/broker/group-id/config/exception text. Tests assert `secret-canary` is absent from snapshots/logs. |

The `SPECIFICATION.md` §20 initial metrics `ingestion_events_total`, `ingestion_errors_total`, `kafka_events_processed_total`, `events_invalid_total` and "consumer lag observable" are all covered. The additional counters (`kafka_events_consumed_total`, `kafka_consumer_errors_total`, `kafka_processing_errors_total`, `kafka_dead_letter_events_total`, `kafka_lag_errors_total`) are reasonable in-scope extensions.

---

## 3. Git Diff Review

- **Scope correctness:** All changes belong to TASK-011.
- **Files changed:** `docs/kafka-metrics.md` (new), `libs/observability/kafka_metrics.py` (new), `libs/observability/__init__.py` (new), `libs/observability/README.md`, `libs/common/kafka_consumer.py`, `libs/common/kafka_producer.py`, `libs/common/README.md`, `tests/test_kafka_metrics.py` (new).
- **Unrelated changes:** None identified.
- **Architectural changes:** None. New `libs/observability` module is consistent with the `libs/observability` boundary in `SPECIFICATION.md` §5 and the existing README.
- **Dependencies/config:** No new third-party dependencies (only stdlib `enum.StrEnum`, `threading.Lock`, `math`). No `pyproject.toml`/`requirements*.txt`/CI/infra changes.
- **Debug/dead code/secrets:** None. No generated artifacts.
- **Branch/task isolation:** Correct — changes are on `feature/TASK-011`; no other TASK content included.

---

## 4. Test and Verification Review

- **Tests examined:** `tests/test_kafka_metrics.py` (210 lines, new) reusing fixtures from `test_kafka_errors.py` (`client`, `consumer`) and `test_kafka_producer.py` (`real_broker`).
- **Adequacy:** Strong overall. Unit tests cover: snapshot thread-safety/detachment/instance-locality; producer success/failure/invalid boundaries; consumer retry vs. processed distinction; invalid-record DLQ (not "processed"); failed-commit (not "processed"); poll outcomes (idle/EOF/transport/exception); lag math across offsets (incl. `None` cases); lag failure vs. assignment-loss; bounded-timeout validation. The `@pytest.mark.integration` test verifies real counters and committed-offset lag against an isolated Compose broker.
- **Independently verified:** None. This review was performed read-only (plan mode); no shell/test commands were executed.
- **Implementation evidence reviewed:** The test logic was traced against the implementation and is internally consistent. No pass/fail test results were reported in the docs (`docs/kafka-metrics.md` only lists the commands), so execution success is otherwise **Unverified** here.

---

## 5. Findings

No Critical or High findings.

**M1 — Minor: Producer shutdown/publish-after-close counter boundary is not asserted**
- File: `libs/common/kafka_producer.py` — `publish()` closed-guard and `close()` increment `KafkaMetric.PRODUCER_ERRORS` (`ingestion_errors_total`).
- Problem: The documented boundary "failed canonical publish **or shutdown call**, … and publishing after close" is exercised by `test_shutdown_and_publish_after_close`, `test_flush_exception_is_reported`, and `test_shutdown_failure_can_be_retried`, but none assert `producer.metrics.snapshot()["ingestion_errors_total"]`.
- Impact: A regression in these specific increments would go unnoticed.
- Recommendation: Add snapshot assertions to those tests, or record this in `docs/reviews/FOLLOWUPS.md`.

**M2 — Minor: Consumer close-failure counter boundary is not tested**
- File: `libs/common/kafka_consumer.py` — `close()` increments `KafkaMetric.CONSUMER_ERRORS` on `KafkaException`.
- Problem: No test sets `client.close.side_effect = KafkaException(...)`, so the documented `kafka_consumer_errors_total` "close errors" boundary is unexercised.
- Impact: Unpinned increment; low risk.
- Recommendation: Add a unit test for the close-failure path, or record in `FOLLOWUPS.md`.

**M3 — Minor: Lag timeout-exhaustion branch (`TimeoutError` → `LAG_ERRORS`) is not tested**
- File: `libs/common/kafka_consumer.py` — `sample_lag()` `remaining()` raises `TimeoutError`; the `except (KafkaException, TimeoutError)` increments `KafkaMetric.LAG_ERRORS`.
- Problem: `test_lag_requires_bounded_timeout` only covers invalid-timeout `ValueError`; the `KafkaException` failure path is covered, but the documented "exhausts its time budget" branch is not directly exercised.
- Impact: The budget-expiry half of the `kafka_lag_errors_total` boundary is unpinned.
- Recommendation: Add a test forcing `remaining()` to expire mid-query (e.g., mock `time.monotonic` to jump past the deadline), or record in `FOLLOWUPS.md`.

---

## 6. Non-Defect Observations

1. **Committed-offset lag semantics.** Lag reflects the committed next offset, not the fetched position. In-flight (fetched-but-uncommitted) work is invisible until commit, and new groups report `None` (unknown) rather than zero. This is explicit and intentional in `docs/kafka-metrics.md`; it is a reasonable "unknown vs. zero" design. Worth revisiting when the TASK-084 Prometheus gauge is built.
2. **Missing-metadata record counts twice.** A record with `None` topic/partition/offset increments both `kafka_events_consumed_total` and `kafka_consumer_errors_total`. This is consistent with the documented boundaries ("each non-error record fetched" + "missing record metadata"), but operators should be aware.
3. **DLQ/standalone diagnostic producer is intentionally unmetered.** `KafkaDeadLetterProducer` exposes no `KafkaMetrics`; its failures are not in any counter. This matches the documented scope ("canonical producer counter excludes standalone diagnostic/DLQ publishers").
4. **Threading.** `sample_lag()` must run on the consumer's owning thread (librdkafka consumers are not thread-safe). This is documented and matches the existing single-threaded library contract.

---

## 7. Verdict

**CHANGES REQUIRED** — the implementation is correct, in-scope, well-documented, secret-free, and meets all TASK-011 acceptance criteria, with no Critical or High findings. Three Minor test-coverage gaps (M1–M3) remain and are neither fixed nor recorded in `docs/reviews/FOLLOWUPS.md`; per the review gate, these must be fixed or documented before `APPROVED`.

---

WORKFLOW_REVIEW: {"head": "781625822bd6b6c7df67fd9d41cf7fc8e6ffa054", "verdict": "CHANGES REQUIRED", "blocking_findings": 0}
