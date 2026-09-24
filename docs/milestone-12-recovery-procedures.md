# Milestone 12 — Failure Scenarios and Recovery Procedures

This document covers all failure scenarios tested in Milestone 12 (TASK-101 through TASK-106).
Each scenario follows the lifecycle: **Failure → Detection → Metric/log → Recovery → No silent data loss**.

---

## Table of Contents

1. [TASK-101: Kafka Broker Failure](#task-101-kafka-broker-failure)
2. [TASK-102: PostgreSQL Warehouse Failure](#task-102-postgresql-warehouse-failure)
3. [TASK-103: Processor Crash Mid-Batch](#task-103-processor-crash-mid-batch)
4. [TASK-104: Duplicate Events and Kafka Replay](#task-104-duplicate-events-and-kafka-replay)
5. [TASK-105: Dead-Letter Queue Routing](#task-105-dead-letter-queue-routing)
6. [TASK-106: Source Freshness Failure](#task-106-source-freshness-failure)

---

## TASK-101: Kafka Broker Failure

**Test file:** `tests/test_kafka_failure.py`

### Failure

Kafka broker becomes unavailable — producer cannot publish, consumer loses connectivity, or the broker restarts mid-operation.

### Detection

- Producer publish failures raise exceptions caught by the ingestion runner; retry with exponential backoff.
- Consumer poll failures surface as connection errors; the consumer closes and requires restart with the same group ID.
- Consumer lag is tracked via `KafkaMetric` counters and the `kafka_consumer_lag` Prometheus gauge.

### Metric/Log Evidence

| Signal | Type | Description |
|--------|------|-------------|
| `kafka_produce_errors_total` | Counter | Incremented on each publish failure |
| `kafka_consumer_lag` | Gauge | Reports current consumer lag per topic-partition |
| `kafka_processing_stopped` | Log (ERROR) | Emitted when consumer closes due to unrecoverable error |
| `source_fetch_failure_total` | Counter | Incremented when adapter fetch fails due to Kafka unavailability |

### Recovery

1. Kafka broker restarts or reconnects.
2. Producer retries with exponential backoff; events are published once the broker is available.
3. Consumer restarts with the same `group.id`; Kafka delivers from the last committed offset.
4. Uncommitted events are reprocessed (at-least-once semantics).

### No Silent Data Loss

- Events are not acknowledged until processing succeeds or the dead-letter path is taken.
- Consumer offset commits occur only after successful processing.
- After recovery, all uncommitted events are re-delivered and reprocessed.
- Test verifies: events produced before failure are present in the output topic after recovery.

---

## TASK-102: PostgreSQL Warehouse Failure

**Test file:** `tests/warehouse/test_postgresql_failure.py`

### Failure

PostgreSQL becomes unavailable or restarts while the warehouse loader is writing records.

### Detection

- Warehouse loader catches connection/write exceptions and logs `warehouse_write_failed`.
- The loader's retry mechanism detects the failure and backs off before retrying.
- `KafkaMetric.PROCESSED` counter does not increment for failed writes.

### Metric/Log Evidence

| Signal | Type | Description |
|--------|------|-------------|
| `warehouse_write_failed` | Log (ERROR) | Emitted with table name and record details |
| `kafka_processing_stopped` | Log (ERROR) | Consumer closes on unrecoverable write failure |
| Consumer offset not committed | Behavioral | Failed records are not acknowledged |

### Recovery

1. PostgreSQL restarts and accepts connections.
2. Consumer restarts with the same `group.id`; Kafka re-delivers from the last committed offset.
3. Warehouse loader retries idempotently — the `ON CONFLICT DO NOTHING` clause in INSERT statements prevents duplicate records.
4. All records are written exactly once.

### No Silent Data Loss

- Idempotent INSERT with conflict handling ensures no duplicates even after replay.
- Consumer offset is only committed after successful write.
- Test verifies: after PostgreSQL restart, the same events are reprocessed and the final record count matches exactly (no duplicates, no missing records).

---

## TASK-103: Processor Crash Mid-Batch

**Test file:** `tests/test_processor_crash.py`

### Failure

The processor crashes mid-batch — after consuming events from Kafka but before committing offsets.

### Detection

- Process termination is detected by the container orchestrator (Kubernetes/Docker).
- The consumer group coordinator detects the member death via session timeout.
- Uncommitted offsets remain in Kafka; no events are silently acknowledged.

### Metric/Log Evidence

| Signal | Type | Description |
|--------|------|-------------|
| `kafka_processing_stopped` | Log (ERROR) | Emitted on consumer close before commit |
| `kafka_processed_total` | Counter | Only incremented for successfully committed records |
| Consumer group rebalance | Kafka internal | New consumer instance triggers partition reassignment |

### Recovery

1. Processor restarts (new container or process).
2. New consumer instance joins the same `group.id`.
3. Kafka assigns partitions and delivers from the last committed offset.
4. Events processed before the crash but not committed are re-delivered and reprocessed.

### No Silent Data Loss

- At-least-once semantics: events are re-delivered if not committed.
- Idempotent processing (deduplication by `event_id`) prevents duplicate logical records.
- Test verifies: after crash and restart, all events are present in the output exactly once.

---

## TASK-104: Duplicate Events and Kafka Replay

**Test file:** `tests/test_duplicate_replay.py`

### Failure

Duplicate events arrive via Kafka replay (e.g., consumer re-reads a range of offsets, or a producer accidentally publishes the same event twice).

### Detection

- Deduplication is enforced at the processor level via `event_id` tracking.
- The warehouse loader uses `ON CONFLICT DO NOTHING` on the `event_id` unique constraint.
- Duplicate events are detected and silently discarded (not written again).

### Metric/Log Evidence

| Signal | Type | Description |
|--------|------|-------------|
| `kafka_processed_total` | Counter | Incremented per processed event (including duplicates that are deduplicated) |
| `kafka_deduplicated_total` | Counter (if applicable) | Tracks deduplication events |
| Database unique constraint | Behavioral | `ON CONFLICT DO NOTHING` prevents duplicate rows |

### Recovery

- No recovery needed — deduplication is continuous and automatic.
- Replayed events are handled transparently without operator intervention.

### No Silent Data Loss

- Original events are always processed and stored.
- Duplicate events are detected and discarded without affecting the original.
- Test verifies: after replaying the same events, the record count in PostgreSQL and Parquet remains unchanged (no duplicates created).

---

## TASK-105: Dead-Letter Queue Routing

**Test file:** `tests/test_dlq.py`

### Failure

Malformed events arrive on the Kafka topic — invalid JSON, unsupported schema versions, or events that fail Pydantic validation.

### Detection

- `KafkaConsumer.poll()` catches deserialization errors and wraps them as `DeserializationError`.
- `KafkaConsumer.process_next()` routes failures to the DLQ via `diagnostic_envelope()`.
- The DLQ envelope contains diagnostic context: `error_type`, `raw_value_base64`, `topic`, `partition`, `offset`, `consumer_group`, `attempts`.

### Metric/Log Evidence

| Signal | Type | Description |
|--------|------|-------------|
| `KafkaMetric.DEAD_LETTERED` | Counter | Incremented for each event routed to DLQ |
| `KafkaMetric.INVALID` | Counter | Incremented for each invalid event detected |
| `kafka_dead_letter_delivered` | Log (WARNING) | Emitted with topic/partition/offset context |
| `kafka_processing_retry` | Log (WARNING) | Emitted on transient error retry attempts |

### Recovery

1. DLQ events are queryable — the diagnostic envelope provides full context for investigation.
2. The main pipeline continues processing valid events unaffected.
3. After fixing the root cause (e.g., source adapter bug), corrected events are republished to the main topic.
4. DLQ events can be manually inspected and reprocessed if needed.

### No Silent Data Loss

- Malformed events are preserved in the DLQ topic with full diagnostic context.
- Valid events continue flowing through the main pipeline.
- No events are silently dropped — every malformed event is accounted for in the DLQ.
- Test verifies: malformed events appear in the DLQ with correct diagnostic fields; valid events are processed independently.

---

## TASK-106: Source Freshness Failure

**Test file:** `tests/test_observability/test_source_freshness_failure.py`

### Failure

A source adapter stops producing events — the upstream API is down, returns empty results, or the adapter crashes.

### Detection

- `SourceFreshness` tracks the timestamp of the last successful fetch with usable data (`records_emitted > 0`).
- `SourceHealthTracker` compares freshness age against `max_freshness_age_seconds` threshold.
- When freshness age exceeds the threshold, the source transitions to `STALE` state.
- Zero-result fetches do NOT refresh the freshness timestamp (TASK-054 semantics).

### Metric/Log Evidence

| Signal | Type | Description |
|--------|------|-------------|
| `source_freshness_age_seconds` | Prometheus Gauge | Computed at scrape time from last successful fetch |
| `SourceDegradationState.STALE` | Assessment | Health assessor returns STALE when age exceeds threshold |
| `FreshnessState.STALE` | State | Tracker freshness state transitions to STALE |
| `source_stale` alert | Agent tool | `_derive_alerts()` generates medium-severity alert |
| `overall_status: stale` | API | `PipelineStatusRepository` reports source as stale |

### Recovery

1. Source adapter resumes producing events (upstream recovers, adapter restarts).
2. Next successful fetch with `records_emitted > 0` refreshes the freshness timestamp.
3. Freshness age drops below threshold; state transitions back to `FRESH` / `HEALTHY`.
4. Stale alerts clear automatically on the next assessment cycle.

### No Silent Data Loss

- Stale sources are reported as `overall_status: stale`, not `healthy`.
- Downstream consumers see the stale indicator and do not treat old data as current.
- The freshness mechanism ensures that zero-result fetches cannot mask staleness.
- Test verifies: after source stops, STALE is detected and alert is raised; after recovery, HEALTHY is restored and alert clears.

---

## Cross-Cutting Concerns

### At-Least-Once Semantics

All scenarios maintain at-least-once processing guarantees:
- Consumer offsets are committed only after successful processing.
- Uncommitted events are re-delivered after any failure and recovery.
- Idempotent processing (deduplication by `event_id`) prevents duplicate logical records.

### Observability Stack

The monitoring layers work together across all scenarios:

```
Source Adapter → SourceMetrics → SourceHealthTracker → Health Assessment
                                                              ↓
Kafka Consumer → KafkaMetrics → Prometheus Exporter → Grafana Dashboards
                                                              ↓
Processor → ProcessorPipeline → Validation → DLQ (if malformed)
                                                              ↓
Warehouse Loader → PostgreSQL → IngestionHealthEvaluator → API → Agent Alerts
```

### Running the Tests

Each scenario has dedicated integration tests. Run them individually:

```bash
# Kafka failure (requires Docker Compose)
python -m pytest tests/test_kafka_failure.py -m integration -v

# PostgreSQL failure (requires Docker Compose)
python -m pytest tests/warehouse/test_postgresql_failure.py -m integration -v

# Processor crash (requires Docker Compose)
python -m pytest tests/test_processor_crash.py -m integration -v

# Duplicate/replay (requires Docker Compose)
python -m pytest tests/test_duplicate_replay.py -m integration -v

# DLQ routing (requires Docker Compose)
python -m pytest tests/test_dlq.py -m integration -v

# Source freshness (deterministic, no infrastructure required)
python -m pytest tests/test_observability/test_source_freshness_failure.py -v
```

Note: `pyproject.toml` sets `addopts = "-m 'not integration'"`, so a plain `pytest` run deselects integration tests. Use `-m integration` explicitly.
