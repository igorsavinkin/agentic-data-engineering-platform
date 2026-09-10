I have completed my read-only review. All required context has been read and the fix commit (`0c39634`) has been verified against the three findings from the prior review cycle. Here is the complete report.

---

# TASK-011 Review — Kafka Metrics (Re-review after fix `0c39634`)

## 1. Review Header

- **Task ID:** TASK-011 — Kafka Metrics
- **Review date:** 2026-09-10
- **Reviewed change set:** `638006c48d87929b1decc151c5264f688b9e5118..0c39634cd1ea22fda8bdaafa74efeb4ed28c6e27` (branch `feature/TASK-011`)
- **Scope:** Producer/consumer operational counters, consumer lag sampling, documentation, and tests. This re-review focuses on the resolution of the three Minor test-coverage findings (M1–M3) and the deferred observation from the prior review (`7816258`).
- **Verdict:** **APPROVED** (no blocking defects; all non-blocking findings fixed or documented in `docs/reviews/FOLLOWUPS.md`)

---

## 2. Requirements Coverage

Sources: `ai/tasks/TASK-011-kafka-metrics.md`, `ai/SPECIFICATION.md` §20, `ai/PROJECT.md` §10, `ai/AGENTS.md` §7/§9.

| Requirement | Status | Implementation evidence |
| --- | --- | --- |
| Produced events counter | ✅ Met | `ingestion_events_total` (`KafkaMetric.PRODUCED`) incremented only on confirmed delivery in `KafkaEventProducer.publish()` (`libs/common/kafka_producer.py`). Tested (`test_producer_metrics`, `test_kafka_producer.py` additions). |
| Consumed events counter | ✅ Met | `kafka_events_consumed_total` (`CONSUMED`) on each non-error record fetched in `KafkaConsumer.poll()`. Tested (`test_consumption_retries_and_commits_are_distinct`, `test_poll_outcomes`, integration). |
| Errors counters | ✅ Met | `ingestion_errors_total` (`PRODUCER_ERRORS`), `kafka_consumer_errors_total` (`CONSUMER_ERRORS`), `kafka_processing_errors_total` (`PROCESSING_ERRORS`), `kafka_lag_errors_total` (`LAG_ERRORS`). Now tested across all documented boundaries (see §5). |
| Invalid events counter | ✅ Met | `events_invalid_total` (`INVALID`) for producer serialization/validation rejection and consumer decode/validation rejection (incl. tombstones). Tested (`test_producer_metrics` invalid, `test_invalid_counted_once_and_dlq_not_processed`). |
| Consumer lag visibility | ✅ Met | `KafkaConsumer.sample_lag()` → `ConsumerLag(topic, partition, lag)` using broker high-watermark minus committed next offset; `None` = unknown. Tested (unit + integration). |
| Hooks for later Prometheus | ✅ Met | `KafkaMetrics.snapshot()` returns detached `dict[str, int]` of cumulative counters; no exporter in the data path; documented in `docs/kafka-metrics.md`. |
| No secrets | ✅ Met | Counters hold only fixed names/numbers; lag holds topic/partition/offset only. No payload/event-id/source-url/broker/group-id/config/exception text. Tests assert `secret-canary` is absent from snapshots/logs. |

The `SPECIFICATION.md` §20 initial metrics `ingestion_events_total`, `ingestion_errors_total`, `kafka_events_processed_total`, `events_invalid_total`, and "consumer lag observable" are all covered. The additional counters (`kafka_events_consumed_total`, `kafka_consumer_errors_total`, `kafka_processing_errors_total`, `kafka_dead_letter_events_total`, `kafka_lag_errors_total`) remain reasonable in-scope extensions.

---

## 3. Git Diff Review

- **Scope correctness:** All changes belong to TASK-011. The fix commit `0c39634` addresses exactly the three prior test-coverage findings and the deferred observation.
- **Files changed:** `docs/kafka-metrics.md` (new), `docs/reviews/TASK-011-review.md` (prior review), `docs/reviews/FOLLOWUPS.md`, `libs/observability/kafka_metrics.py` (new), `libs/observability/__init__.py` (new), `libs/observability/README.md`, `libs/common/kafka_consumer.py`, `libs/common/kafka_producer.py`, `libs/common/README.md`, `tests/test_kafka_metrics.py` (new), `tests/test_kafka_producer.py`.
- **Unrelated changes:** None identified.
- **Architectural changes:** None. New `libs/observability` module is consistent with the `libs/observability` boundary in `SPECIFICATION.md` §5 and the existing README.
- **Dependencies/config:** No new third-party dependencies (only stdlib `enum.StrEnum`, `threading.Lock`, `math`, `time`). No `pyproject.toml`/`requirements*.txt`/CI/infra changes.
- **Debug/dead code/secrets:** None. No generated artifacts.
- **Branch/task isolation:** Correct — changes are on `feature/TASK-011`; no other TASK content included.

---

## 4. Test and Verification Review

- **Tests examined:** `tests/test_kafka_metrics.py` (241 lines, new), `tests/test_kafka_producer.py` (3 assertions added), reusing fixtures from `test_kafka_errors.py` (`client`, `consumer`) and `test_kafka_producer.py` (`real_broker`).
- **Adequacy:** Strong and now complete. Unit tests cover: snapshot thread-safety/detachment/instance-locality; producer success/failure/invalid/closed/shutdown boundaries; consumer retry vs. processed distinction; invalid-record DLQ (not "processed"); failed-commit (not "processed"); poll outcomes (idle/EOF/transport/exception); close-failure; lag math across offsets (incl. `None` cases); lag failure, budget-exhaustion, and assignment-loss; bounded-timeout validation. The `@pytest.mark.integration` test verifies real counters and committed-offset lag against an isolated Compose broker.
- **Independently verified:** None. This review was performed read-only (no shell/test commands executed).
- **Implementation evidence reviewed:** The test logic — including the new `test_consumer_close_failure_counted_once`, `test_lag_budget_exhaustion_is_counted_and_recoverable`, and the three `test_kafka_producer.py` assertion additions — was traced against the implementation and is internally consistent. The timeout-exhaustion test correctly patches `time.monotonic` so the `remaining()` guard raises `TimeoutError` before `get_watermark_offsets` is invoked, matching `get_watermark_offsets.assert_not_called()`. Execution success remains **Unverified** (no test run performed by this reviewer).

---

## 5. Findings

No Critical, High, Moderate, or Minor findings remain.

Resolution of the prior cycle's findings:

- **M1 (producer shutdown/publish-after-close boundary) — Resolved.** `tests/test_kafka_producer.py` now asserts `ingestion_errors_total` in `test_flush_exception_is_reported` (1 → 2 across publish-fail and shutdown-fail), `test_shutdown_and_publish_after_close` (0 → 1 on publish-after-close), and `test_shutdown_failure_can_be_retried` (1, not double-counted on successful retry).
- **M2 (consumer close-failure boundary) — Resolved.** New `test_consumer_close_failure_counted_once` sets `client.close.side_effect = KafkaException(...)` and asserts `kafka_consumer_errors_total == 1` with no double-count on the second `close()`.
- **M3 (lag timeout-exhaustion branch) — Resolved.** New `test_lag_budget_exhaustion_is_counted_and_recoverable` forces budget expiry and asserts `kafka_lag_errors_total == 1`, that `committed()` received the decremented budget, `get_watermark_offsets` was not called, and a subsequent sample recovers without further error increments.

---

## 6. Non-Defect Observations

1. **Committed-offset lag semantics.** Lag reflects the committed next offset, not the fetched position; new groups report `None` (unknown) rather than zero. This is documented and intentional, and is now recorded in `docs/reviews/FOLLOWUPS.md` for the TASK-084 Prometheus gauge design.
2. **Missing-metadata record counts twice.** A record with `None` topic/partition/offset increments both `kafka_events_consumed_total` and `kafka_consumer_errors_total` — consistent with the documented boundaries.
3. **DLQ/standalone diagnostic producer is intentionally unmetered.** `KafkaDeadLetterProducer` exposes no `KafkaMetrics`; this matches documented scope.
4. **Threading.** `sample_lag()` must run on the consumer's owning thread (librdkafka consumers are not thread-safe); documented and consistent with the library contract.

---

## 7. Verdict

**APPROVED** — the implementation is correct, in-scope, well-documented, secret-free, and meets all TASK-011 acceptance criteria. No Critical or High findings exist. The three prior Minor test-coverage gaps (M1–M3) have been fixed by `0c39634`, and the deferred committed-offset-lag observation is now documented in `docs/reviews/FOLLOWUPS.md`. All blocking and non-blocking findings are therefore resolved.

---

WORKFLOW_REVIEW: {"head": "0c39634cd1ea22fda8bdaafa74efeb4ed28c6e27", "verdict": "APPROVED", "blocking_findings": 0}
