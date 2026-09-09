# Kafka Consumer — TASK-009 Implementation Guide

## Overview

The `KafkaConsumer` class in `libs/common/kafka_consumer.py` provides a reusable consumer for canonical product-observation events. It implements **at-least-once delivery** with explicit offset management.

## Offset Commit Semantics

### When Offsets Are Committed

Offsets are committed **only after successful processing** of a message via `consumer.commit_message(msg)`. This ensures:

1. **No data loss on crash**: If the process crashes before committing, unprocessed messages will be redelivered
2. **Explicit control**: The application decides when processing is "complete" (e.g., after database write, after Polars transformation, etc.)
3. **Manual commits only**: `enable.auto.commit` is set to `False` to prevent accidental premature commits

### What Happens When Processing Fails

When message processing fails:

1. **Do NOT call `commit_message()`**: The offset remains uncommitted
2. **Log the failure**: Use structured logging with topic/partition/offset context
3. **Optionally route to DLQ**: Send to `products.invalid.v1` if deserialization fails
4. **On restart**: The same message will be redelivered because its offset was never committed

Example pattern:
```python
for msg in messages:
    try:
        process(msg)  # May raise exception
        consumer.commit_message(msg)  # Only on success
    except ProcessingError:
        logger.error("processing_failed", extra={"offset": msg.offset})
        # Do NOT commit - message will be redelivered
```

### Crash After Write But Before Commit

If the process writes data (e.g., to Parquet or PostgreSQL) but crashes before committing the offset:

- **On restart**: The message is redelivered
- **Downstream deduplication required**: Use `event_id` to detect and skip duplicates
- **Idempotent processing essential**: Database upserts, unique constraints on `event_id`

This is the fundamental trade-off of at-least-once delivery: **duplicates are possible, but no data is lost**.

## Failure Behavior Matrix

| Failure Scenario | Offset Committed? | Message Redelivered? | Action Required |
|---|---|---|---|
| Deserialization error | No | Yes | Log, optionally route to DLQ |
| Processing exception | No | Yes | Fix bug, restart consumer |
| Crash before commit | No | Yes | Downstream deduplication |
| Crash after commit | Yes | No | Normal operation |
| Network timeout | No | Yes | Retry automatically on reconnect |
| Broker unavailable | No | Yes | Wait for broker recovery |

## Consumer Group Configuration

Each service uses a dedicated consumer group for independent offset tracking:

```python
# Processor service
settings = KafkaConsumerSettings(
    kafka_group_id="processor",
    kafka_bootstrap_servers="kafka:9092",
)

# Raw Writer service
settings = KafkaConsumerSettings(
    kafka_group_id="raw-writer",
    kafka_bootstrap_servers="kafka:9092",
)
```

Different consumer groups allow:
- Independent scaling per service
- Independent restart without affecting other services
- Different processing speeds without blocking each other

## Graceful Shutdown

The consumer handles SIGINT/SIGTERM signals for clean shutdown:

1. Signal handler sets `_shutdown_requested` flag
2. `poll()` returns empty list when shutdown requested
3. `close()` leaves the consumer group **without committing** unprocessed offsets
4. Context manager (`with` statement) ensures cleanup

Example:
```python
with KafkaConsumer(settings) as consumer:
    consumer.subscribe(["products.raw.v1"])
    while not consumer.is_shutdown_requested():
        messages, errors = consumer.poll(timeout=1.0)
        # Handle deserialization errors
        for err in errors:
            logger.error(
                "deserialization_failed",
                extra={
                    "topic": err.topic,
                    "partition": err.partition,
                    "offset": err.offset,
                    "error": str(err.error),
                },
            )
            # Optionally route to DLQ or skip
        # Process successful messages
        for msg in messages:
            try:
                process(msg)
                consumer.commit_message(msg)  # Only after success
            except ProcessingError:
                logger.error("processing_failed", extra={"offset": msg.offset})
                # Do NOT commit - message will be redelivered
# close() does NOT commit unprocessed offsets; they will be redelivered on restart
```

## At-Least-Once Delivery

The consumer does **not** guarantee exactly-once semantics. Duplicate delivery can occur due to:

- Consumer rebalancing during group membership changes
- Process crash after write but before offset commit
- Manual retry of failed messages
- Replay from earlier offsets for testing/debugging

**Downstream consumers must implement idempotent processing** using `event_id` as the deduplication key.

## Testing

Run consumer tests:
```bash
pytest tests/test_kafka_consumer.py -v
```

Test scenarios covered:
1. ✅ Valid event consumption and deserialization
2. ✅ Malformed JSON handling (returned as `DeserializationError`)
3. ✅ Invalid schema handling (returned as `DeserializationError`)
4. ✅ None value handling (returned as `DeserializationError`)
5. ✅ Offset commit after successful processing
6. ✅ No offset commit on processing failure
7. ✅ Consumer restart with committed offsets
8. ✅ Uncommitted messages redelivered on restart
9. ✅ Duplicate delivery tolerance (same event_id, different offsets)
10. ✅ Graceful shutdown with signal handling
11. ✅ Kafka error handling (EOF, transport errors, unknown topics)

## Integration with Existing Components

The consumer integrates with:
- `libs.event_contracts.ProductObservationEvent`: Canonical event model
- `libs.event_contracts.deserialize_event()`: Validation and deserialization
- `libs.common.config.AppSettings`: Configuration loading

Example usage in processor service:
```python
from libs.common.kafka_consumer import KafkaConsumer, KafkaConsumerSettings
from libs.common.config import load_settings


def run_processor() -> None:
    settings = load_settings(KafkaConsumerSettings)
    with KafkaConsumer(settings) as consumer:
        consumer.subscribe(["products.raw.v1"])
        while not consumer.is_shutdown_requested():
            messages, errors = consumer.poll(timeout=1.0)
            # Handle deserialization errors
            for err in errors:
                logger.error(
                    "deserialization_failed",
                    extra={
                        "topic": err.topic,
                        "partition": err.partition,
                        "offset": err.offset,
                        "error": str(err.error),
                    },
                )
                # Optionally route to DLQ or skip
            # Process successful messages
            for msg in messages:
                try:
                    # Validate and transform
                    validated = validate_and_transform(msg.event)
                    # Publish to products.validated.v1
                    producer.publish(validated)
                    # Commit only after successful publish
                    consumer.commit_message(msg)
                except Exception as exc:
                    logger.error(
                        "processing_failed",
                        extra={
                            "event_id": msg.event.event_id,
                            "error": str(exc),
                        },
                    )
                    # Do NOT commit - will be redelivered
```
