# Kafka operational metrics

TASK-011 exposes `producer.metrics.snapshot()` and `consumer.metrics.snapshot()`
as detached dictionaries of cumulative integer counters. Each wrapper owns its
own thread-safe registry; counters start at zero and reset when the instance is
recreated. No metrics server or Prometheus dependency is required yet.

| Counter | Increment boundary |
| --- | --- |
| `ingestion_events_total` | Canonical `publish()` returns a confirmed delivery receipt. |
| `ingestion_errors_total` | Each failed canonical publish or shutdown call, including invalid serialization, enqueue failure, failed/unconfirmed delivery, and publishing after close. |
| `kafka_events_consumed_total` | Each non-error Kafka record fetched by `poll()`, including invalid records and redeliveries. |
| `kafka_events_processed_total` | `process_next()` completes a valid handler and successfully commits its offset. DLQ records are excluded. |
| `events_invalid_total` | A producer rejects serialization/validation, or a consumer rejects a fetched record's decoding/validation (including tombstones). |
| `kafka_consumer_errors_total` | Kafka poll, commit, or close errors, or missing record metadata. Partition EOF and empty polls are excluded. |
| `kafka_processing_errors_total` | Each failed handler attempt, including retryable, permanent, and unexpected exceptions. |
| `kafka_dead_letter_events_total` | The `process_next()` sink returns an acknowledgement, before the source offset commit. |
| `kafka_lag_errors_total` | A lag query fails or exhausts its time budget. |

These are operational counts, not unique observations. Retrying or replaying an
event can increment them again. A publish timeout can mean Kafka accepted a record
even though this process could not confirm it; that call counts as an error, not
a confirmed production. A late callback does not retrospectively change this
count. Low-level `poll()`/`commit_message()` callers do not increment the processed
counter because the library cannot observe their business handler. Construction
failures have no usable instance registry and retain their existing exceptions.
The canonical producer counter excludes standalone diagnostic/DLQ publishers.

## Consumer lag

Call `consumer.sample_lag(timeout=5.0)` periodically on the consumer's owning
thread. It returns fresh `ConsumerLag(topic, partition, lag)` records for current
assignments. It does not poll, seek, commit, or cache previous assignments. An
unassigned consumer returns an empty list. Calling it after close raises.

Lag is the broker high watermark (next append offset) minus the group's committed
next offset. Fetching a record does not reduce it; committing successful work
does. It is an offset distance, not an exact count of business records (compaction
or transactional records can create gaps). No commit, a negative watermark, or a
commit outside the retained log range produces `None`, meaning **unknown**, not
zero. This also makes new groups and retention/truncation conditions visible.

Broker queries share one finite positive timeout budget. Kafka errors and budget
expiry increment `kafka_lag_errors_total` and raise; callers must treat that sample
as unavailable, never reuse it as a current zero. Assignment and broker offsets
can change around sampling, so results are point-in-time estimates, not an atomic
cluster snapshot. Sampling only covers this instance's assignments, not inactive
groups or the entire cluster. Schedule it sparingly: network queries block the
owning thread and count toward the consumer's max-poll interval.

## Later Prometheus integration

A collector can read counter snapshots without executing exporter callbacks in
the publish/consume path. Map their existing `_total` names to cumulative counter
samples; do not add the entire snapshot to a Prometheus counter on every scrape.
Keep instance identity distinct to avoid merging independent counter resets.

Publish successful lag samples as `kafka_consumer_lag` gauges with controlled
topic/partition labels; represent `None` as unavailable and remove revoked
partitions. A service should sample on its consumer thread and hand a timestamped
copy to the collector. Track sample age and omit expired samples. An exporter and
background sampling lifecycle belong to the later observability milestone.

Counters contain only fixed metric names and numbers. Lag samples contain topic,
partition, and offset distance. Neither API includes payloads, event IDs, source
URLs, broker endpoints, group IDs, configuration values, or exception text.

## Verification

Run `scripts/task_check.ps1` and:

```powershell
python -m pytest tests/test_kafka_metrics.py tests/test_kafka_producer.py tests/test_kafka_errors.py -m integration -v
```

The metrics integration test uses an isolated Compose broker to verify duplicate
publication counts, fetched counts, unknown initial lag, and lag reduction only
after explicit commits. Unit tests cover failure/invalid boundaries, retries,
thread-safe snapshots, unavailable lag, and assignment loss.
