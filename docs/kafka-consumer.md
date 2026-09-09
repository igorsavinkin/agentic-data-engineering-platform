# Kafka consumer and failure handling

`KafkaConsumer` provides manual offset management. TASK-010 adds `process_next`
for synchronous, one-record-at-a-time processing and acknowledged DLQ routing.

```python
from libs.common.config import load_settings
from libs.common.kafka_consumer import KafkaConsumer, KafkaConsumerSettings
from libs.common.kafka_errors import KafkaDeadLetterProducer
from libs.common.kafka_producer import KafkaProducerSettings

consumer_settings = load_settings(KafkaConsumerSettings)
dlq = KafkaDeadLetterProducer(load_settings(KafkaProducerSettings))
try:
    with KafkaConsumer(consumer_settings) as consumer:
        consumer.subscribe(["products.raw.v1"])
        while not consumer.is_shutdown_requested():
            consumer.process_next(process, dlq.publish)  # process receives ConsumerMessage
finally:
    dlq.close()
```

Set `APP_KAFKA_GROUP_ID=processor` for the processor. Raw Writer uses `raw-writer`
and Lake Writer uses `lake-writer`. Set `APP_KAFKA_BOOTSTRAP_SERVERS` to
`localhost:9092` on the host or `kafka:29092` inside Compose. Provision topics
through the existing topic-management script (ADR-001); auto-creation is disabled.
The DLQ target is `products.invalid.v1`, with no partition key.

## Failure and offset policy

| Outcome | Action | Commit |
| --- | --- | --- |
| Handler succeeds | Continue | Synchronous offset + 1 |
| Invalid JSON, UTF-8, null payload, invalid/unsupported schema | Publish diagnostic envelope to DLQ | Only after acknowledgement |
| `TransientProcessingError` | Retry same record; default 3 total attempts, delays 0.25 and 0.5 seconds | Only after success or acknowledged DLQ on exhaustion |
| `ProcessingError` | Permanent processing failure; route to DLQ immediately | Only after acknowledgement |
| Unexpected handler exception | Close consumer and propagate; investigate and restart | None |
| DLQ failure, timeout, queue full or missing acknowledgement | Close consumer and propagate | None |
| Commit failure, including per-partition error | Close and propagate | Outcome may be uncertain; replay can duplicate |
| Shutdown during retry/processing | Close, preserving replay | None |

`RetryPolicy` accepts 1?10 attempts and 0?5 seconds of linear backoff.
Only explicitly classified transient failures are retried; handlers must be
idempotent. Callback execution must be bounded by the application. Keep total
processing, backoff and DLQ delivery time below `APP_KAFKA_MAX_POLL_INTERVAL_MS`
(default 300000). A rebalance or commit failure can duplicate side effects.
Librdkafka handles broker reconnects; transport poll errors are logged and the
next bounded poll retries. Fatal poll errors close the managed processing path.
DLQ delivery uses the producer delivery timeout (default 30000 ms); failure stops
consumption rather than endlessly retrying a potentially oversized envelope.

Never catch a failed record and continue polling on the low-level API: committing
a later offset in the same partition would skip it. `process_next` closes on any
unresolved exception and prevents this pattern. Do not mix managed processing
with concurrent or outstanding low-level polls/commits. The library is single-threaded.
Auto-commit cannot be enabled, auto-offset storage is disabled, and close never commits.
The library installs SIGINT/SIGTERM handlers; embedding applications must account
for this existing behavior.

## Diagnostic contract and replay

The version-1 `product.invalid` JSON envelope contains `event_id`, `event_type`,
`schema_version`, `source` (consumer group), `produced_at`, and `payload`.
The payload preserves original topic, partition, offset, consumer group, attempts,
error class, validation error types/locations, and exact input bytes as base64.
A null value remains JSON null, distinct from empty bytes. Original values belong
only in the DLQ; logs omit payloads and arbitrary exception messages. Apply the
same access controls to the DLQ as to the raw topic.

The deterministic DLQ event ID derives from group/topic/partition/offset, so
replays can be deduplicated. Topic deletion/recreation is outside this identity
scope. Publication and offset commit are separate operations: crashing after DLQ
acknowledgement but before commit may publish the envelope again. Likewise,
crashing after handler side effects may repeat them. This is at-least-once,
not end-to-end exactly-once; downstream observation deduplication uses event_id.

Restart with the same consumer group to resume committed offsets. Uncommitted
records replay within Kafka retention (7 days); retention expiry is not recoverable
through this consumer. For deliberate full replay use a new group with
`APP_KAFKA_AUTO_OFFSET_RESET=earliest`. After correcting a failed record, republish
its recovered raw content through the appropriate validated ingestion path.

Structured events `kafka_processing_retry`, `kafka_dead_letter_delivered`,
`kafka_processing_stopped` and `kafka_deserialization_failed` expose the failure
path. Kafka metrics remain TASK-011; processor-specific validation remains TASK-017.

Run `python -m pytest tests/test_kafka_errors.py` and the real-broker test with
`python -m pytest tests/test_kafka_errors.py -m integration -v`. The latter owns
an isolated Compose project and tests DLQ outage, same-group restart, exact raw
payload preservation and the broker's committed offset.
