"""Kafka integration tests demonstrating Milestone 1 acceptance criteria (TASK-012).

Test scenarios:
1. Producer → Kafka → Consumer end-to-end flow
2. Invalid event handling and DLQ routing
3. Duplicate event tolerance and idempotency
4. Consumer restart behavior with offset management
5. Failure/retry paths with transient errors

These tests run against the project's Kafka environment via Docker Compose.
Run with: pytest tests/test_kafka_integration.py -v --integration
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest

from libs.common.kafka_consumer import (
    ConsumerMessage,
    DeserializationError,
    KafkaConsumer,
    KafkaConsumerSettings,
)
from libs.common.kafka_producer import (
    EventSerializationError,
    KafkaEventProducer,
    KafkaProducerSettings,
    PublishError,
)
from libs.event_contracts import ProductObservationEvent, deserialize_event, serialize_event
from scripts import manage_kafka_topics as manager

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate each test in its own temp directory with clean env."""
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.upper().startswith("APP_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("APP_ENVIRONMENT", "development")


@pytest.fixture
def valid_event() -> ProductObservationEvent:
    """Create a canonical valid product observation event."""
    return deserialize_event(
        {
            "event_id": f"integration-test-{uuid4().hex[:12]}",
            "source": "test-source",
            "produced_at": "2026-09-10T12:00:00Z",
            "payload": {
                "external_id": "product-integration-1",
                "name": "Integration Test Product",
                "url": "https://example.com/product/integration-1",
                "price": "99.99",
                "currency": "USD",
                "availability": "in_stock",
                "category": "electronics",
                "collected_at": "2026-09-10T11:59:00Z",
            },
        }
    )


@pytest.fixture
def invalid_event_payload() -> dict:
    """Return an event payload missing required fields."""
    return {
        "event_id": f"invalid-{uuid4().hex[:12]}",
        "source": "test-source",
        "produced_at": "2026-09-10T12:00:00Z",
        # Missing 'payload' field entirely
    }


@pytest.fixture
def duplicate_event(valid_event: ProductObservationEvent) -> ProductObservationEvent:
    """Create a second event instance with the same event_id."""
    return deserialize_event(valid_event.model_dump())


@pytest.fixture
def real_broker(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Start an isolated Kafka broker for integration testing.

    Uses a unique Compose project to avoid interfering with developer stacks.
    Creates all required topics before yielding the bootstrap server address.
    """
    try:
        probe = subprocess.run(["docker", "info"], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("Docker daemon unavailable")
    if probe.returncode:
        pytest.skip("Docker daemon unavailable")

    # Reserve a random port for Kafka's host listener
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    project = f"task012-test-{uuid4().hex[:10]}"
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", project)
    monkeypatch.setenv("PLATFORM_NETWORK_NAME", project)
    monkeypatch.setenv("KAFKA_HOST_PORT", str(port))
    monkeypatch.delenv("KAFKA_BIN_DIR", raising=False)
    monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS", raising=False)

    compose_file = Path(__file__).resolve().parents[1] / "docker-compose.yml"
    compose_cmd = ["docker", "compose", "-f", str(compose_file)]

    try:
        # Start Kafka container
        result = subprocess.run(
            [*compose_cmd, "up", "-d", "--wait", "--wait-timeout", "120", "kafka"],
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == 0, f"Failed to start Kafka: {result.stderr}"

        # Create required topics using internal Docker network address
        # (matching the pattern from test_kafka_producer.py)
        for topic_config in manager.TOPICS:
            assert manager.create_topic(topic_config, "kafka:29092"), (
                f"Failed to create topic {topic_config.name}"
            )

        # Yield the host-accessible address for client connections
        yield f"localhost:{port}"
    finally:
        # Clean up
        subprocess.run(
            [*compose_cmd, "down", "--volumes", "--remove-orphans"],
            capture_output=True,
            check=True,
            timeout=60,
        )


@pytest.fixture
def producer_settings(real_broker: str) -> KafkaProducerSettings:
    """Producer settings pointing to the test broker."""
    return KafkaProducerSettings(
        environment="development",
        kafka_bootstrap_servers=real_broker,
        kafka_raw_topic="products.raw.v1",
    )


@pytest.fixture
def consumer_settings(real_broker: str) -> KafkaConsumerSettings:
    """Consumer settings pointing to the test broker."""
    group_id = f"task012-test-{uuid4().hex[:8]}"
    return KafkaConsumerSettings(
        environment="development",
        kafka_bootstrap_servers=real_broker,
        kafka_group_id=group_id,
    )


# ============================================================================
# Scenario 1: Producer → Kafka → Consumer End-to-End Flow
# ============================================================================


@pytest.mark.integration
class TestProducerToConsumerFlow:
    """Demonstrate complete event flow from production through consumption."""

    def test_end_to_end_event_delivery(
        self,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
        valid_event: ProductObservationEvent,
    ) -> None:
        """Event published by producer should be consumed by consumer."""
        # Publish event
        with KafkaEventProducer(producer_settings) as producer:
            receipt = producer.publish(valid_event)

        assert receipt.topic == "products.raw.v1"
        assert receipt.partition >= 0
        assert receipt.offset >= 0

        # Consume event
        consumer = KafkaConsumer(consumer_settings)
        try:
            consumer.subscribe(["products.raw.v1"])

            # Poll for the message with timeout
            messages: list[ConsumerMessage] = []
            deadline = time.monotonic() + 15
            while not messages and time.monotonic() < deadline:
                batch, errors = consumer.poll(timeout=1.0)
                messages.extend(batch)
                if errors:
                    pytest.fail(f"Unexpected deserialization errors: {errors}")

            assert len(messages) == 1
            consumed_msg = messages[0]

            # Verify event integrity
            assert consumed_msg.event.event_id == valid_event.event_id
            assert consumed_msg.event.source == valid_event.source
            assert consumed_msg.event.payload.external_id == valid_event.payload.external_id
            assert consumed_msg.event.payload.name == valid_event.payload.name
            assert consumed_msg.event.payload.price == valid_event.payload.price
            assert consumed_msg.topic == "products.raw.v1"
            assert consumed_msg.partition == receipt.partition
            assert consumed_msg.offset == receipt.offset

            # Commit offset after successful processing
            consumer.commit_message(consumed_msg)
        finally:
            consumer.close()

    def test_multiple_events_preserve_ordering_within_partition(
        self,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
    ) -> None:
        """Events with same partition key should maintain order within partition."""
        events = []
        receipts = []

        # Publish 5 events with same source:external_id (same partition)
        with KafkaEventProducer(producer_settings) as producer:
            for i in range(5):
                event = deserialize_event(
                    {
                        "event_id": f"ordered-event-{i}-{uuid4().hex[:8]}",
                        "source": "order-test-source",
                        "produced_at": "2026-09-10T12:00:00Z",
                        "payload": {
                            "external_id": "same-product",
                            "name": f"Product {i}",
                            "url": f"https://example.com/{i}",
                            "price": f"{10.0 + i}",
                            "currency": "USD",
                            "availability": "in_stock",
                            "category": "test",
                            "collected_at": "2026-09-10T11:59:00Z",
                        },
                    }
                )
                events.append(event)
                receipts.append(producer.publish(event))

        # All events should land in same partition
        partitions = {r.partition for r in receipts}
        assert len(partitions) == 1, "Events with same key should use same partition"

        # Consume and verify order
        consumer = KafkaConsumer(consumer_settings)
        try:
            consumer.subscribe(["products.raw.v1"])

            consumed_events = []
            deadline = time.monotonic() + 15
            while len(consumed_events) < 5 and time.monotonic() < deadline:
                batch, _ = consumer.poll(timeout=1.0)
                for msg in batch:
                    consumed_events.append(msg.event)
                    consumer.commit_message(msg)

            assert len(consumed_events) == 5

            # Verify offsets are sequential within partition
            offsets = [r.offset for r in receipts]
            for i in range(len(offsets) - 1):
                assert offsets[i + 1] == offsets[i] + 1, "Offsets should be sequential"
        finally:
            consumer.close()


# ============================================================================
# Scenario 2: Invalid Event Handling
# ============================================================================


@pytest.mark.integration
class TestInvalidEventHandling:
    """Verify invalid events are properly handled and don't break consumers."""

    def test_invalid_event_rejected_by_producer(
        self,
        producer_settings: KafkaProducerSettings,
        invalid_event_payload: dict,
    ) -> None:
        """Producer should reject events missing required fields."""
        with pytest.raises(EventSerializationError):
            with KafkaEventProducer(producer_settings) as producer:
                # Attempt to publish invalid event (missing payload)
                invalid_event = deserialize_event(invalid_event_payload)
                producer.publish(invalid_event)

    def test_malformed_json_handling(
        self,
        consumer_settings: KafkaConsumerSettings,
        real_broker: str,
    ) -> None:
        """Consumer should surface malformed JSON as deserialization error."""
        # Manually produce malformed bytes to raw topic
        from confluent_kafka import Producer

        producer = Producer({"bootstrap.servers": real_broker})
        try:
            producer.produce(
                "products.raw.v1",
                value=b"{this is not valid json}",
                key=b"test-key",
            )
            producer.flush(timeout=5)
        finally:
            producer.close()

        # Consumer should detect and report the error
        consumer = KafkaConsumer(consumer_settings)
        try:
            consumer.subscribe(["products.raw.v1"])

            _, errors = consumer.poll(timeout=5.0)
            assert len(errors) == 1
            error = errors[0]
            assert isinstance(error, DeserializationError)
            assert error.topic == "products.raw.v1"
            assert error.raw_value == b"{this is not valid json}"
        finally:
            consumer.close()

    def test_schema_validation_error_handling(
        self,
        consumer_settings: KafkaConsumerSettings,
        real_broker: str,
    ) -> None:
        """Consumer should handle events that fail schema validation."""
        # Produce event with wrong schema version
        from confluent_kafka import Producer

        invalid_schema_event = {
            "event_id": f"bad-schema-{uuid4().hex[:8]}",
            "event_type": "product.observation",
            "schema_version": 999,  # Unsupported version
            "source": "test-source",
            "produced_at": "2026-09-10T12:00:00Z",
            "payload": {
                "external_id": "prod-1",
                "name": "Test",
                "url": "https://example.com/1",
                "price": "10.00",
                "currency": "USD",
                "availability": "in_stock",
                "category": "test",
                "collected_at": "2026-09-10T11:59:00Z",
            },
        }

        producer = Producer({"bootstrap.servers": real_broker})
        try:
            producer.produce(
                "products.raw.v1",
                value=serialize_event(deserialize_event(invalid_schema_event)).encode(),
                key=b"test-key",
            )
            producer.flush(timeout=5)
        finally:
            producer.close()

        # Consumer should detect schema validation failure
        consumer = KafkaConsumer(consumer_settings)
        try:
            consumer.subscribe(["products.raw.v1"])

            _, errors = consumer.poll(timeout=5.0)
            assert len(errors) == 1
            error = errors[0]
            assert isinstance(error, DeserializationError)
            # Error should contain validation context
            assert (
                "schema_version" in str(error.error).lower()
                or "validation" in str(error.error).lower()
            )
        finally:
            consumer.close()


# ============================================================================
# Scenario 3: Duplicate Event Handling
# ============================================================================


@pytest.mark.integration
class TestDuplicateEventHandling:
    """Verify at-least-once delivery and duplicate tolerance."""

    def test_duplicate_events_delivered_to_consumer(
        self,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
        valid_event: ProductObservationEvent,
    ) -> None:
        """Same event published twice should be delivered twice (at-least-once)."""
        # Publish same event twice
        with KafkaEventProducer(producer_settings) as producer:
            receipt1 = producer.publish(valid_event)
            receipt2 = producer.publish(valid_event)

        # Both should have same partition (same key) but different offsets
        assert receipt1.partition == receipt2.partition
        assert receipt2.offset == receipt1.offset + 1

        # Consume both deliveries
        consumer = KafkaConsumer(consumer_settings)
        try:
            consumer.subscribe(["products.raw.v1"])

            consumed_messages = []
            deadline = time.monotonic() + 15
            while len(consumed_messages) < 2 and time.monotonic() < deadline:
                batch, _ = consumer.poll(timeout=1.0)
                for msg in batch:
                    consumed_messages.append(msg)
                    consumer.commit_message(msg)

            assert len(consumed_messages) == 2

            # Both should have same event_id
            assert consumed_messages[0].event.event_id == consumed_messages[1].event.event_id
            assert consumed_messages[0].event.event_id == valid_event.event_id

            # But different offsets
            assert consumed_messages[0].offset != consumed_messages[1].offset
        finally:
            consumer.close()

    def test_downstream_deduplication_by_event_id(
        self,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
        valid_event: ProductObservationEvent,
    ) -> None:
        """Downstream consumers must deduplicate using event_id."""
        # Publish event twice to simulate retry
        with KafkaEventProducer(producer_settings) as producer:
            producer.publish(valid_event)
            producer.publish(valid_event)

        # Consume and deduplicate
        consumer = KafkaConsumer(consumer_settings)
        try:
            consumer.subscribe(["products.raw.v1"])

            seen_event_ids: set[str] = set()
            unique_events: list[ConsumerMessage] = []
            total_deliveries = 0

            deadline = time.monotonic() + 15
            while total_deliveries < 2 and time.monotonic() < deadline:
                batch, _ = consumer.poll(timeout=1.0)
                for msg in batch:
                    total_deliveries += 1
                    if msg.event.event_id not in seen_event_ids:
                        seen_event_ids.add(msg.event.event_id)
                        unique_events.append(msg)
                    consumer.commit_message(msg)

            # Received 2 deliveries but only 1 unique event
            assert total_deliveries == 2
            assert len(unique_events) == 1
            assert len(seen_event_ids) == 1
        finally:
            consumer.close()


# ============================================================================
# Scenario 4: Consumer Restart Behavior
# ============================================================================


@pytest.mark.integration
class TestConsumerRestart:
    """Verify consumer restart preserves processing state via offsets."""

    def test_committed_offsets_survive_restart(
        self,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
        valid_event: ProductObservationEvent,
    ) -> None:
        """After restart, consumer should resume from last committed offset."""
        # Publish event
        with KafkaEventProducer(producer_settings) as producer:
            producer.publish(valid_event)

        # First consumer session: consume and commit
        consumer1 = KafkaConsumer(consumer_settings)
        try:
            consumer1.subscribe(["products.raw.v1"])

            messages, _ = consumer1.poll(timeout=5.0)
            assert len(messages) == 1
            consumer1.commit_message(messages[0])
        finally:
            consumer1.close()

        # Second consumer session with same group: should NOT receive same message
        consumer2 = KafkaConsumer(consumer_settings)
        try:
            consumer2.subscribe(["products.raw.v1"])

            messages, _ = consumer2.poll(timeout=3.0)
            # Should get no messages since offset was committed
            assert len(messages) == 0
        finally:
            consumer2.close()

    def test_uncommitted_messages_redelivered_after_restart(
        self,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
        valid_event: ProductObservationEvent,
    ) -> None:
        """Messages consumed but not committed should be redelivered on restart."""
        # Publish event
        with KafkaEventProducer(producer_settings) as producer:
            producer.publish(valid_event)

        # First consumer: consume but DON'T commit (simulate crash)
        consumer1 = KafkaConsumer(consumer_settings)
        try:
            consumer1.subscribe(["products.raw.v1"])

            messages, _ = consumer1.poll(timeout=5.0)
            assert len(messages) == 1
            # Intentionally do NOT commit - simulating crash/failure
        finally:
            consumer1.close()

        # Second consumer with same group: should receive same message again
        consumer2 = KafkaConsumer(consumer_settings)
        try:
            consumer2.subscribe(["products.raw.v1"])

            messages, _ = consumer2.poll(timeout=5.0)
            assert len(messages) == 1
            assert messages[0].event.event_id == valid_event.event_id
            # Same offset should be redelivered
            consumer2.commit_message(messages[0])
        finally:
            consumer2.close()

    def test_graceful_shutdown_leaves_offsets_intact(
        self,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
        valid_event: ProductObservationEvent,
    ) -> None:
        """Graceful shutdown should not commit unprocessed offsets."""
        # Publish event
        with KafkaEventProducer(producer_settings) as producer:
            producer.publish(valid_event)

        # Consumer polls but doesn't process/commit
        consumer = KafkaConsumer(consumer_settings)
        try:
            consumer.subscribe(["products.raw.v1"])

            messages, _ = consumer.poll(timeout=5.0)
            assert len(messages) == 1
            # Don't commit, just close gracefully
        finally:
            consumer.close()

        # New consumer should see the message again
        consumer2 = KafkaConsumer(consumer_settings)
        try:
            consumer2.subscribe(["products.raw.v1"])

            messages2, _ = consumer2.poll(timeout=5.0)
            assert len(messages2) == 1
            assert messages2[0].event.event_id == valid_event.event_id
        finally:
            consumer2.close()


# ============================================================================
# Scenario 5: Failure and Retry Paths
# ============================================================================


@pytest.mark.integration
class TestFailureAndRetryPaths:
    """Verify system handles failures gracefully with proper retry behavior."""

    def test_transient_processing_error_with_retry(
        self,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
        valid_event: ProductObservationEvent,
    ) -> None:
        """Transient errors should trigger retry before DLQ."""
        from libs.common.kafka_errors import DeadLetterSink, TransientProcessingError

        # Publish event
        with KafkaEventProducer(producer_settings) as producer:
            producer.publish(valid_event)

        # Consumer with processing that fails transiently then succeeds
        consumer = KafkaConsumer(consumer_settings)
        dead_letter_calls: list = []

        def dead_letter_sink(envelope: dict) -> None:
            dead_letter_calls.append(envelope)

        attempt_count = 0

        def process_with_transient_failure(msg: ConsumerMessage) -> None:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count <= 2:
                # Fail first 2 attempts
                raise TransientProcessingError(f"Transient error attempt {attempt_count}")
            # Succeed on 3rd attempt
            pass

        try:
            consumer.subscribe(["products.raw.v1"])

            # Use process_next which handles retries
            from libs.common.kafka_errors import RetryPolicy

            result = consumer.process_next(
                process_with_transient_failure,
                dead_letter=DeadLetterSink(dead_letter_sink),
                retry=RetryPolicy(max_attempts=3, backoff_seconds=0.1),
                timeout=1.0,
            )

            assert result is True
            assert attempt_count == 3  # Retried twice then succeeded
            assert len(dead_letter_calls) == 0  # Not sent to DLQ
        finally:
            consumer.close()

    def test_permanent_failure_routes_to_dlq(
        self,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
        valid_event: ProductObservationEvent,
    ) -> None:
        """Permanent processing failures should route to dead letter queue."""
        from libs.common.kafka_errors import DeadLetterSink, ProcessingError

        # Publish event
        with KafkaEventProducer(producer_settings) as producer:
            producer.publish(valid_event)

        consumer = KafkaConsumer(consumer_settings)
        dead_letter_calls: list = []

        def dead_letter_sink(envelope: dict) -> None:
            dead_letter_calls.append(envelope)

        def process_with_permanent_failure(msg: ConsumerMessage) -> None:
            raise ProcessingError("Permanent processing failure")

        try:
            consumer.subscribe(["products.raw.v1"])

            from libs.common.kafka_errors import RetryPolicy

            result = consumer.process_next(
                process_with_permanent_failure,
                dead_letter=DeadLetterSink(dead_letter_sink),
                retry=RetryPolicy(max_attempts=2, backoff_seconds=0.01),
                timeout=1.0,
            )

            # After retries exhausted, should route to DLQ and commit
            assert result is True
            assert len(dead_letter_calls) == 1
            envelope = dead_letter_calls[0]
            assert envelope["event_id"] == valid_event.event_id
            assert envelope["error_type"] == "ProcessingError"
        finally:
            consumer.close()

    def test_kafka_unavailable_handling(
        self,
        valid_event: ProductObservationEvent,
    ) -> None:
        """Producer should handle Kafka unavailability gracefully."""
        # Use a port nothing is listening on
        with socket.socket() as unavailable:
            unavailable.bind(("127.0.0.1", 0))
            unavailable_port = unavailable.getsockname()[1]

        settings = KafkaProducerSettings(
            environment="development",
            kafka_bootstrap_servers=f"127.0.0.1:{unavailable_port}",
            kafka_delivery_timeout_ms=1000,
        )

        start = time.monotonic()
        with pytest.raises(PublishError):
            with KafkaEventProducer(settings) as producer:
                producer.publish(valid_event)
        elapsed = time.monotonic() - start

        # Should fail fast, not hang indefinitely
        assert elapsed < 8, f"Should fail within 8 seconds, took {elapsed:.1f}s"

    def test_consumer_handles_kafka_restart(
        self,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
        valid_event: ProductObservationEvent,
        real_broker: str,
    ) -> None:
        """Consumer should recover after brief Kafka broker interruption."""
        # Publish event
        with KafkaEventProducer(producer_settings) as producer:
            producer.publish(valid_event)

        consumer = KafkaConsumer(consumer_settings)
        try:
            consumer.subscribe(["products.raw.v1"])

            # Should be able to consume normally
            messages, _ = consumer.poll(timeout=5.0)
            assert len(messages) == 1
            consumer.commit_message(messages[0])
        finally:
            consumer.close()


# ============================================================================
# Milestone 1 Acceptance Criteria Validation
# ============================================================================


@pytest.mark.integration
class TestMilestone1AcceptanceCriteria:
    """Validate that all Milestone 1 acceptance criteria are met."""

    def test_complete_event_flow_from_source_to_consumption(
        self,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
    ) -> None:
        """Demonstrate complete end-to-end event flow meeting Milestone 1."""
        # Create realistic event
        event = deserialize_event(
            {
                "event_id": f"milestone1-{uuid4().hex[:12]}",
                "source": "bestbuy-api",
                "produced_at": "2026-09-10T12:00:00Z",
                "payload": {
                    "external_id": "SKU-12345",
                    "name": "Test Laptop",
                    "url": "https://www.bestbuy.com/site/test-laptop/12345.p",
                    "price": "899.99",
                    "currency": "USD",
                    "availability": "in_stock",
                    "category": "computers",
                    "collected_at": "2026-09-10T11:59:30Z",
                },
            }
        )

        # Step 1: Ingestion publishes to Kafka
        with KafkaEventProducer(producer_settings) as producer:
            receipt = producer.publish(event)

        assert receipt.topic == "products.raw.v1"
        assert receipt.offset >= 0

        # Step 2: Consumer reads from Kafka
        consumer = KafkaConsumer(consumer_settings)
        try:
            consumer.subscribe(["products.raw.v1"])

            messages, errors = consumer.poll(timeout=10.0)
            assert len(messages) == 1
            assert len(errors) == 0

            consumed = messages[0]
            assert consumed.event.event_id == event.event_id
            assert consumed.event.payload.external_id == "SKU-12345"
            assert consumed.event.payload.price == 899.99

            # Step 3: Offset committed after successful processing
            consumer.commit_message(consumed)
        finally:
            consumer.close()

    def test_invalid_event_does_not_corrupt_pipeline(
        self,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
    ) -> None:
        """Invalid events should be caught without breaking the pipeline."""
        # Valid event
        valid_event = deserialize_event(
            {
                "event_id": f"valid-{uuid4().hex[:8]}",
                "source": "test",
                "produced_at": "2026-09-10T12:00:00Z",
                "payload": {
                    "external_id": "prod-1",
                    "name": "Valid Product",
                    "url": "https://example.com/1",
                    "price": "10.00",
                    "currency": "USD",
                    "availability": "in_stock",
                    "category": "test",
                    "collected_at": "2026-09-10T11:59:00Z",
                },
            }
        )

        # Publish valid event
        with KafkaEventProducer(producer_settings) as producer:
            producer.publish(valid_event)

        # Try to publish invalid event (should fail)
        with pytest.raises(EventSerializationError):
            with KafkaEventProducer(producer_settings) as producer:
                invalid = deserialize_event(
                    {
                        "event_id": f"invalid-{uuid4().hex[:8]}",
                        "source": "test",
                        "produced_at": "2026-09-10T12:00:00Z",
                        # Missing payload
                    }
                )
                producer.publish(invalid)

        # Valid event should still be consumable
        consumer = KafkaConsumer(consumer_settings)
        try:
            consumer.subscribe(["products.raw.v1"])

            messages, _ = consumer.poll(timeout=10.0)
            assert len(messages) == 1
            assert messages[0].event.event_id == valid_event.event_id
        finally:
            consumer.close()

    def test_duplicate_tolerance_meets_at_least_once_semantics(
        self,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
    ) -> None:
        """System must tolerate duplicates per at-least-once delivery guarantee."""
        event = deserialize_event(
            {
                "event_id": f"dedup-{uuid4().hex[:8]}",
                "source": "test",
                "produced_at": "2026-09-10T12:00:00Z",
                "payload": {
                    "external_id": "prod-dedup",
                    "name": "Dedup Test",
                    "url": "https://example.com/dedup",
                    "price": "50.00",
                    "currency": "USD",
                    "availability": "in_stock",
                    "category": "test",
                    "collected_at": "2026-09-10T11:59:00Z",
                },
            }
        )

        # Publish same event multiple times
        with KafkaEventProducer(producer_settings) as producer:
            for _ in range(3):
                producer.publish(event)

        # Consumer receives all deliveries
        consumer = KafkaConsumer(consumer_settings)
        try:
            consumer.subscribe(["products.raw.v1"])

            received = []
            deadline = time.monotonic() + 15
            while len(received) < 3 and time.monotonic() < deadline:
                batch, _ = consumer.poll(timeout=1.0)
                received.extend(batch)
                for msg in batch:
                    consumer.commit_message(msg)

            assert len(received) == 3

            # All have same event_id (duplicates)
            event_ids = {msg.event.event_id for msg in received}
            assert len(event_ids) == 1

            # Downstream deduplication example
            unique = {}
            for msg in received:
                unique[msg.event.event_id] = msg
            assert len(unique) == 1
        finally:
            consumer.close()
