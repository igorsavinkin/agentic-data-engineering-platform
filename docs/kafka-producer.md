# Canonical Kafka producer (TASK-008)

`libs.common.kafka_producer.KafkaEventProducer` publishes canonical observations
to the configured raw topic. Install `requirements-dev.txt` for development or
`requirements.txt` for runtime use. The client is `confluent-kafka` (librdkafka).

## Configuration and use

Load `KafkaProducerSettings` with the existing `load_settings` helper. It inherits
`AppSettings`, including required `APP_ENVIRONMENT`, `.env` loading, environment
precedence, immutable settings, and rejection of unknown `APP_` variables.

| Variable | Default | Accepted values |
| --- | --- | --- |
| `APP_KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Comma-separated `host:port` entries; bracketed IPv6 supported; ports 1–65535 |
| `APP_KAFKA_RAW_TOPIC` | `products.raw.v1` | 1–249 letters, digits, dots, underscores or hyphens; excludes `.` and `..` |
| `APP_KAFKA_CLIENT_ID` | `ingestion` | Same character constraints as topic |
| `APP_KAFKA_DELIVERY_TIMEOUT_MS` | `30000` | Integer, 1000–300000 milliseconds |

Host processes use `localhost:9092`; containers on the Compose network use
`kafka:29092`. If changing `KAFKA_HOST_PORT`, set the application bootstrap port
to match. These application variables are separate from the topic-management
script's `KAFKA_BOOTSTRAP_SERVERS`. This task targets the local PLAINTEXT stack;
authenticated/TLS deployments require a later explicit configuration extension.

Create the topics using TASK-007 before publishing:

```powershell
docker compose up -d --wait kafka
python scripts/manage_kafka_topics.py create
```

Given an existing `ProductObservationEvent` named `event`:

```python
from libs.common.config import load_settings
from libs.common.kafka_producer import KafkaEventProducer, KafkaProducerSettings

settings = load_settings(KafkaProducerSettings)
with KafkaEventProducer(settings) as producer:
    receipt = producer.publish(event)
    print(receipt.topic, receipt.partition, receipt.offset)
```

`publish` returns a `DeliveryReceipt` only after a successful delivery callback
with broker metadata. It serializes the event to UTF-8 JSON through TASK-006's
serializer and validates that wire snapshot before enqueueing. It retains the
event ID, observation timestamp, publication timestamp, and payload. The caller
sets `produced_at` when preparing the event for its initial publication; retries
reuse that same event. The UTF-8 key is `source:external_id` per ADR-001. The
explicit `murmur2_random` partitioner provides Java-compatible keyed partitioning;
future producers must use the same key encoding and partitioning algorithm.

## Delivery and failure behavior

Each call serializes sends on the instance and flushes with a finite timeout
(`delivery.timeout.ms` plus one second for callback servicing). `acks=all` and
`enable.idempotence=true` let librdkafka retry transient failures within the
delivery deadline while preserving session ordering. The client supplies its
default retry/backoff policy; this wrapper adds no unbounded retry loop.
Synchronous publication trades batching throughput for a simple acknowledgment
boundary. There is no global ordering across partitions, producers, or threads
competing to acquire the instance lock.

- `EventSerializationError`: encoding or validation failed before enqueueing.
  Correct the input; no event was sent by this call.
- `PublishError`: enqueueing failed, Kafka reported failure, or delivery could not
  be confirmed before the wait expired. Do not discard the event. Retain it and
  retry using the same `event_id`; an uncertain delivery may already be in Kafka.
- `ConfigurationError`: invalid environment settings or client initialization
  failure. Construction does not establish broker readiness; a successful
  publish is the delivery check.
- `close()` drains with the same finite timeout and rejects future publication
  after a successful close. Failure to drain raises and can be retried. The
  context manager closes automatically, preserving an original exception if
  shutdown also fails and logging the shutdown failure.

A timeout does not cancel a queued record. Later callback servicing, including
`close()`, can deliver it. A late callback does not retroactively make the original
failed call successful; the caller must retain its failed-event state. Explicit
application retries can append duplicate records even with producer idempotence.
After a crash, an in-memory queue is not a durable outbox: ingestion must retain
or recollect observations and replay with stable IDs. This is compatible with
at-least-once processing, not an end-to-end exactly-once guarantee. Consumers own
deduplication and committing offsets after successful processing. A failed
publish is not automatically sent to a DLQ through the same unavailable broker.
Consumer/DLQ implementation belongs to subsequent tasks.

Structured Python log records expose operation, event ID, source, topic, and
delivery partition/offset or numeric Kafka error code. Serialization failures
omit untrusted payloads. Applications configure log handlers and formatting;
logs do not include event payloads or configuration values from this wrapper.
Do not log chained exception details that may include invalid input. Kafka's own
client diagnostics are forwarded to the logger. Metrics are scoped to TASK-011.
Local replication factor one still provides no broker-failure redundancy.

## Verification

```powershell
python -m pytest tests/test_kafka_producer.py
python -m pytest tests/test_kafka_producer.py -m integration -v
./scripts/task_check.ps1
```

Unit tests cover identity/key preservation, settings, serialization and invalid
mutation, enqueue failures, failed callbacks despite an empty queue, absent
callbacks, bounded shutdown, and closed-producer behavior. The integration test
creates an isolated Compose project with a temporary host port, creates and
validates `products.raw.v1` via TASK-007, publishes the same observation twice,
then reads both offsets through a real consumer and checks exact bytes and keys.
It removes only its own containers/network/volumes. It skips if Docker is
unavailable; once Docker is available, startup or publication errors fail the
test. A separate integration test verifies bounded failure against a reserved
non-listening port. No production consumer service is introduced.

TASK-008 implementation validation on Windows with Python 3.14.0,
confluent-kafka 2.15.0 and the Compose Apache Kafka 4.3.1 image:

- `scripts/task_check.ps1`: Ruff format/lint, mypy, 112 unit tests, and repository
  structure validation passed.
- `pytest tests/test_kafka_producer.py -m integration -v`: both real publish/consume
  and unavailable-broker tests passed (45.41 seconds including stack lifecycle).
- Git hooks were installed; no shared development stack was removed.

Client reference: [Confluent Python API](https://docs.confluent.io/platform/current/clients/confluent-kafka-python/html/index.html).
