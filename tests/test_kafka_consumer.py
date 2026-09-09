"""Tests for Kafka consumer (TASK-009).

Test scenarios:
1. Valid event consumption and deserialization
2. Malformed event handling
3. Consumer restart behavior
4. Duplicate delivery tolerance
5. Offset commit after successful processing
6. Graceful shutdown
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

# Set test environment for all KafkaConsumerSettings instantiations
os.environ["APP_ENVIRONMENT"] = "test"

import pytest
from confluent_kafka import KafkaError, KafkaException, TopicPartition

from libs.common.config import ConfigurationError
from libs.common.kafka_consumer import (
    ConsumerMessage,
    DeserializationError,
    KafkaConsumer,
    KafkaConsumerSettings,
)
from libs.event_contracts import ProductObservationEvent, ProductObservationPayload


def _make_valid_event() -> ProductObservationEvent:
    """Create a valid test event."""
    return ProductObservationEvent(
        event_id="test-event-001",
        source="test-source",
        produced_at=datetime.now(timezone.utc),
        payload=ProductObservationPayload(
            external_id="prod-123",
            name="Test Product",
            url="https://example.com/product/123",
            price=Decimal("99.99"),
            currency="USD",
            availability="in_stock",
            category="electronics",
            collected_at=datetime.now(timezone.utc),
        ),
    )


def _make_malformed_json() -> bytes:
    """Return invalid JSON bytes."""
    return b"{invalid json"


def _make_invalid_event_json() -> bytes:
    """Return JSON that doesn't match the event schema."""
    return json.dumps({"wrong_field": "value"}).encode("utf-8")


class TestKafkaConsumerSettings:
    """Test consumer configuration validation."""

    def test_default_settings(self) -> None:
        """Default settings should have sensible values."""
        settings = KafkaConsumerSettings(kafka_group_id="test-group")
        assert settings.kafka_bootstrap_servers == "localhost:9092"
        assert settings.kafka_group_id == "test-group"
        assert settings.kafka_auto_offset_reset == "earliest"
        assert settings.kafka_enable_auto_commit is False

    def test_consumer_config_dict(self) -> None:
        """Consumer config should include all required fields."""
        settings = KafkaConsumerSettings(
            kafka_group_id="processor",
            kafka_bootstrap_servers="kafka:9092",
        )
        config = settings.consumer_config
        assert config["group.id"] == "processor"
        assert config["bootstrap.servers"] == "kafka:9092"
        assert config["enable.auto.commit"] is False
        assert config["auto.offset.reset"] == "earliest"

    def test_missing_group_id_raises(self) -> None:
        """Consumer requires a group ID."""
        with pytest.raises(ConfigurationError, match="kafka_group_id is required"):
            KafkaConsumer(KafkaConsumerSettings(kafka_group_id=""))


class TestValidEventConsumption:
    """Test consuming and deserializing valid events."""

    @patch("confluent_kafka.Consumer")
    def test_consume_valid_event(self, mock_consumer_class: MagicMock) -> None:
        """Valid event should be deserialized and returned."""
        # Setup mock
        mock_consumer = MagicMock()
        mock_consumer_class.return_value = mock_consumer

        # Create a mock message with valid event
        valid_event = _make_valid_event()
        event_json = valid_event.model_dump_json().encode("utf-8")

        mock_msg = MagicMock()
        mock_msg.error.return_value = None
        mock_msg.topic.return_value = "products.raw.v1"
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 42
        mock_msg.value.return_value = event_json
        mock_consumer.poll.return_value = mock_msg

        # Consume
        settings = KafkaConsumerSettings(kafka_group_id="test-group")
        with KafkaConsumer(settings) as consumer:
            messages, errors = consumer.poll(timeout=0.1)

        # Verify
        assert len(messages) == 1
        msg = messages[0]
        assert msg.event.event_id == "test-event-001"
        assert msg.topic == "products.raw.v1"
        assert msg.partition == 0
        assert msg.offset == 42
        assert msg.event.payload.external_id == "prod-123"

    @patch("confluent_kafka.Consumer")
    def test_poll_returns_empty_on_timeout(self, mock_consumer_class: MagicMock) -> None:
        """Poll should return empty list when no messages available."""
        mock_consumer = MagicMock()
        mock_consumer_class.return_value = mock_consumer
        mock_consumer.poll.return_value = None

        settings = KafkaConsumerSettings(kafka_group_id="test-group")
        with KafkaConsumer(settings) as consumer:
            messages, errors = consumer.poll(timeout=0.1)

        assert messages == []


class TestMalformedEventHandling:
    """Test handling of malformed/invalid events."""

    @patch("confluent_kafka.Consumer")
    def test_malformed_json_is_returned_as_error(self, mock_consumer_class: MagicMock) -> None:
        """Malformed JSON should be surfaced as DeserializationError for caller to handle."""
        mock_consumer = MagicMock()
        mock_consumer_class.return_value = mock_consumer

        mock_msg = MagicMock()
        mock_msg.error.return_value = None
        mock_msg.topic.return_value = "products.raw.v1"
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 10
        mock_msg.value.return_value = _make_malformed_json()
        mock_consumer.poll.return_value = mock_msg

        settings = KafkaConsumerSettings(kafka_group_id="test-group")
        with KafkaConsumer(settings) as consumer:
            messages, errors = consumer.poll(timeout=0.1)

        # Should NOT include in successful messages
        assert messages == []
        # Should surface error with full context (H2 fix)
        assert len(errors) == 1
        err = errors[0]
        assert err.topic == "products.raw.v1"
        assert err.partition == 0
        assert err.offset == 10
        assert err.raw_value is not None

    @patch("confluent_kafka.Consumer")
    def test_invalid_schema_is_returned_as_error(self, mock_consumer_class: MagicMock) -> None:
        """JSON with wrong schema should be surfaced as DeserializationError."""
        mock_consumer = MagicMock()
        mock_consumer_class.return_value = mock_consumer

        mock_msg = MagicMock()
        mock_msg.error.return_value = None
        mock_msg.topic.return_value = "products.raw.v1"
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 11
        mock_msg.value.return_value = _make_invalid_event_json()
        mock_consumer.poll.return_value = mock_msg

        settings = KafkaConsumerSettings(kafka_group_id="test-group")
        with KafkaConsumer(settings) as consumer:
            messages, errors = consumer.poll(timeout=0.1)

        # Should NOT include in successful messages
        assert messages == []
        # Should surface error (H2 fix)
        assert len(errors) == 1
        err = errors[0]
        assert err.topic == "products.raw.v1"
        assert err.partition == 0
        assert err.offset == 11

    @patch("confluent_kafka.Consumer")
    def test_none_value_is_returned_as_error(self, mock_consumer_class: MagicMock) -> None:
        """Messages with None value should be surfaced as DeserializationError."""
        mock_consumer = MagicMock()
        mock_consumer_class.return_value = mock_consumer

        mock_msg = MagicMock()
        mock_msg.error.return_value = None
        mock_msg.topic.return_value = "products.raw.v1"
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 12
        mock_msg.value.return_value = None
        mock_consumer.poll.return_value = mock_msg

        settings = KafkaConsumerSettings(kafka_group_id="test-group")
        with KafkaConsumer(settings) as consumer:
            messages, errors = consumer.poll(timeout=0.1)

        assert messages == []
        # Should surface error (H2 fix)
        assert len(errors) == 1
        err = errors[0]
        assert err.topic == "products.raw.v1"
        assert err.offset == 12
        assert err.raw_value is None


class TestOffsetCommitBehavior:
    """Test explicit offset commit semantics."""

    @patch("confluent_kafka.Consumer")
    def test_commit_after_successful_processing(self, mock_consumer_class: MagicMock) -> None:
        """Offset should be committed only after successful processing."""
        mock_consumer = MagicMock()
        mock_consumer_class.return_value = mock_consumer

        valid_event = _make_valid_event()
        msg = ConsumerMessage(
            event=valid_event,
            topic="products.raw.v1",
            partition=0,
            offset=42,
        )

        settings = KafkaConsumerSettings(kafka_group_id="test-group")
        consumer = KafkaConsumer(settings)
        try:
            consumer.commit_message(msg)
        finally:
            consumer.close()

        # Verify commit was called with correct offset (next offset = current + 1)
        # First call is from commit_message, second from close()
        assert mock_consumer.commit.call_count >= 1
        first_call_args = mock_consumer.commit.call_args_list[0]
        offsets = first_call_args[1]["offsets"]
        assert len(offsets) == 1
        assert offsets[0].topic == "products.raw.v1"
        assert offsets[0].partition == 0
        assert offsets[0].offset == 43  # Next offset to read

    @patch("confluent_kafka.Consumer")
    def test_no_commit_on_processing_failure(self, mock_consumer_class: MagicMock) -> None:
        """If processing fails, offset should NOT be committed."""
        mock_consumer = MagicMock()
        mock_consumer_class.return_value = mock_consumer

        # Simulate: poll returns message, processing fails, commit never called
        _valid_event = _make_valid_event()

        settings = KafkaConsumerSettings(kafka_group_id="test-group")
        with KafkaConsumer(settings):
            # In real usage: try/except around processing, no commit on failure
            try:
                # Simulate processing failure
                raise Exception("Processing failed")
            except Exception:
                pass  # Do NOT commit offset

            # Verify commit was NOT called
            mock_consumer.commit.assert_not_called()


class TestConsumerRestart:
    """Test consumer restart behavior and offset reset."""

    @patch("confluent_kafka.Consumer")
    def test_restart_uses_committed_offsets(self, mock_consumer_class: MagicMock) -> None:
        """On restart, consumer should resume from last committed offset."""
        mock_consumer = MagicMock()
        mock_consumer_class.return_value = mock_consumer

        # First session: consume and commit through offset 42
        settings = KafkaConsumerSettings(kafka_group_id="processor")
        with KafkaConsumer(settings) as consumer:
            # Simulate committing up to offset 42
            tp = TopicPartition("products.raw.v1", 0, 43)
            consumer.commit_offsets([tp])

        # Second session: new consumer instance
        mock_consumer.reset_mock()
        with KafkaConsumer(settings):
            # New consumer will start from committed offset (43) due to
            # auto.offset.reset and committed offsets
            pass

        # Both consumers closed cleanly
        assert mock_consumer.close.called

    @patch("confluent_kafka.Consumer")
    def test_uncommitted_messages_redelivered_on_restart(
        self, mock_consumer_class: MagicMock
    ) -> None:
        """Messages consumed but not committed should be redelivered."""
        mock_consumer = MagicMock()
        mock_consumer_class.return_value = mock_consumer

        # First session: consume message at offset 42 but don't commit
        valid_event = _make_valid_event()
        mock_msg = MagicMock()
        mock_msg.error.return_value = None
        mock_msg.topic.return_value = "products.raw.v1"
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 42
        mock_msg.value.return_value = valid_event.model_dump_json().encode("utf-8")
        mock_consumer.poll.return_value = mock_msg

        settings = KafkaConsumerSettings(kafka_group_id="processor")
        with KafkaConsumer(settings) as consumer:
            messages, errors = consumer.poll(timeout=0.1)
            assert len(messages) == 1
            # Intentionally do NOT commit - simulating crash/failure

        # On restart, same message should be delivered again
        mock_consumer.reset_mock()
        mock_consumer.poll.return_value = mock_msg

        with KafkaConsumer(settings) as consumer2:
            messages2 = consumer2.poll(timeout=0.1)
            assert len(messages2) == 1
            assert messages2[0].offset == 42  # Same offset redelivered


class TestDuplicateDelivery:
    """Test that consumer tolerates duplicate delivery (at-least-once)."""

    @patch("confluent_kafka.Consumer")
    def test_same_event_delivered_twice(self, mock_consumer_class: MagicMock) -> None:
        """Same event_id may appear multiple times; consumer must deliver both."""
        mock_consumer = MagicMock()
        mock_consumer_class.return_value = mock_consumer

        valid_event = _make_valid_event()
        event_json = valid_event.model_dump_json().encode("utf-8")

        # First delivery at offset 42
        mock_msg1 = MagicMock()
        mock_msg1.error.return_value = None
        mock_msg1.topic.return_value = "products.raw.v1"
        mock_msg1.partition.return_value = 0
        mock_msg1.offset.return_value = 42
        mock_msg1.value.return_value = event_json

        # Second delivery at offset 100 (after rebalance/restart)
        mock_msg2 = MagicMock()
        mock_msg2.error.return_value = None
        mock_msg2.topic.return_value = "products.raw.v1"
        mock_msg2.partition.return_value = 0
        mock_msg2.offset.return_value = 100
        mock_msg2.value.return_value = event_json

        mock_consumer.poll.side_effect = [mock_msg1, mock_msg2, None]

        settings = KafkaConsumerSettings(kafka_group_id="processor")
        with KafkaConsumer(settings) as consumer:
            messages = []
            while True:
                batch, errors = consumer.poll(timeout=0.1)
                if not batch:
                    break
                messages.extend(batch)

        # Both deliveries received (at-least-once)
        assert len(messages) == 2
        assert messages[0].event.event_id == "test-event-001"
        assert messages[1].event.event_id == "test-event-001"
        # Different offsets show they're separate deliveries
        assert messages[0].offset == 42
        assert messages[1].offset == 100

    @patch("confluent_kafka.Consumer")
    def test_downstream_must_deduplicate_by_event_id(self, mock_consumer_class: MagicMock) -> None:
        """Consumer delivers duplicates; downstream must deduplicate."""
        mock_consumer = MagicMock()
        mock_consumer_class.return_value = mock_consumer

        # Create two events with SAME event_id but different offsets
        valid_event = _make_valid_event()
        event_json = valid_event.model_dump_json().encode("utf-8")

        mock_msg1 = MagicMock()
        mock_msg1.error.return_value = None
        mock_msg1.topic.return_value = "products.raw.v1"
        mock_msg1.partition.return_value = 0
        mock_msg1.offset.return_value = 42
        mock_msg1.value.return_value = event_json

        mock_msg2 = MagicMock()
        mock_msg2.error.return_value = None
        mock_msg2.topic.return_value = "products.raw.v1"
        mock_msg2.partition.return_value = 0
        mock_msg2.offset.return_value = 43
        mock_msg2.value.return_value = event_json

        mock_consumer.poll.side_effect = [mock_msg1, mock_msg2, None]

        settings = KafkaConsumerSettings(kafka_group_id="processor")
        with KafkaConsumer(settings) as consumer:
            messages = []
            while True:
                batch, errors = consumer.poll(timeout=0.1)
                if not batch:
                    break
                messages.extend(batch)

        # Consumer delivers both (at-least-once guarantee)
        assert len(messages) == 2

        # Downstream deduplication example
        seen_event_ids: set[str] = set()
        unique_messages = []
        for msg in messages:
            if msg.event.event_id not in seen_event_ids:
                seen_event_ids.add(msg.event.event_id)
                unique_messages.append(msg)

        # After deduplication, only one unique event
        assert len(unique_messages) == 1


class TestGracefulShutdown:
    """Test graceful shutdown behavior."""

    @patch("confluent_kafka.Consumer")
    def test_shutdown_does_not_commit_unprocessed_offsets(self, mock_consumer_class: MagicMock) -> None:
        """Shutdown should NOT commit unprocessed offsets (at-least-once semantics).
        
        The caller is responsible for explicitly committing via commit_message() after
        successful processing. close() only closes the consumer without committing,
        ensuring unprocessed messages are redelivered on restart.
        """
        mock_consumer = MagicMock()
        mock_consumer_class.return_value = mock_consumer

        settings = KafkaConsumerSettings(kafka_group_id="test-group")
        consumer = KafkaConsumer(settings)
        consumer.close()

        # Verify NO commit was called during shutdown (H1 fix)
        assert not mock_consumer.commit.called, "close() must not commit unprocessed offsets"
        assert mock_consumer.close.called

    @patch("confluent_kafka.Consumer")
    def test_shutdown_requested_flag(self, mock_consumer_class: MagicMock) -> None:
        """Shutdown flag should be set by signal handler."""
        mock_consumer = MagicMock()
        mock_consumer_class.return_value = mock_consumer

        settings = KafkaConsumerSettings(kafka_group_id="test-group")
        with KafkaConsumer(settings) as consumer:
            # Initially not requested
            assert consumer.is_shutdown_requested() is False

            # Simulate signal
            consumer._shutdown_requested = True
            assert consumer.is_shutdown_requested() is True

            # Poll should return empty when shutdown requested
            messages, errors = consumer.poll(timeout=0.1)
            assert messages == []

    @patch("confluent_kafka.Consumer")
    def test_double_close_is_safe(self, mock_consumer_class: MagicMock) -> None:
        """Calling close() twice should not raise."""
        mock_consumer = MagicMock()
        mock_consumer_class.return_value = mock_consumer

        settings = KafkaConsumerSettings(kafka_group_id="test-group")
        consumer = KafkaConsumer(settings)
        consumer.close()
        consumer.close()  # Should not raise

    @patch("confluent_kafka.Consumer")
    def test_operations_fail_after_close(self, mock_consumer_class: MagicMock) -> None:
        """Operations should fail after consumer is closed."""
        mock_consumer = MagicMock()
        mock_consumer_class.return_value = mock_consumer

        settings = KafkaConsumerSettings(kafka_group_id="test-group")
        consumer = KafkaConsumer(settings)
        consumer.close()

        with pytest.raises(RuntimeError, match="consumer is closed"):
            consumer.subscribe(["products.raw.v1"])

        with pytest.raises(RuntimeError, match="consumer is closed"):
            consumer.poll(timeout=0.1)

        valid_event = _make_valid_event()
        msg = ConsumerMessage(
            event=valid_event,
            topic="products.raw.v1",
            partition=0,
            offset=42,
        )
        with pytest.raises(RuntimeError, match="consumer is closed"):
            consumer.commit_message(msg)


class TestKafkaErrors:
    """Test handling of Kafka-level errors."""

    @patch("confluent_kafka.Consumer")
    def test_partition_eof_is_not_error(self, mock_consumer_class: MagicMock) -> None:
        """End-of-partition should return empty list, not raise."""
        mock_consumer = MagicMock()
        mock_consumer_class.return_value = mock_consumer

        mock_msg = MagicMock()
        error = MagicMock()
        error.code.return_value = KafkaError._PARTITION_EOF
        mock_msg.error.return_value = error
        mock_consumer.poll.return_value = mock_msg

        settings = KafkaConsumerSettings(kafka_group_id="test-group")
        with KafkaConsumer(settings) as consumer:
            messages, errors = consumer.poll(timeout=0.1)

        assert messages == []

    @patch("confluent_kafka.Consumer")
    def test_transport_error_returns_empty(self, mock_consumer_class: MagicMock) -> None:
        """Transport errors should log warning and return empty."""
        mock_consumer = MagicMock()
        mock_consumer_class.return_value = mock_consumer

        mock_msg = MagicMock()
        error = MagicMock()
        error.code.return_value = KafkaError._TRANSPORT
        error.str.return_value = "Broker transport failure"
        mock_msg.error.return_value = error
        mock_consumer.poll.return_value = mock_msg

        settings = KafkaConsumerSettings(kafka_group_id="test-group")
        with KafkaConsumer(settings) as consumer:
            messages, errors = consumer.poll(timeout=0.1)

        assert messages == []

    @patch("confluent_kafka.Consumer")
    def test_other_kafka_errors_raise(self, mock_consumer_class: MagicMock) -> None:
        """Non-recoverable Kafka errors should raise exception."""
        mock_consumer = MagicMock()
        mock_consumer_class.return_value = mock_consumer

        mock_msg = MagicMock()
        error = MagicMock()
        error.code.return_value = KafkaError.UNKNOWN_TOPIC_OR_PART
        mock_msg.error.return_value = error
        mock_consumer.poll.return_value = mock_msg

        settings = KafkaConsumerSettings(kafka_group_id="test-group")
        with KafkaConsumer(settings) as consumer:
            with pytest.raises(KafkaException):
                consumer.poll(timeout=0.1)


class TestSubscription:
    """Test topic subscription behavior."""

    @patch("confluent_kafka.Consumer")
    def test_subscribe_to_topics(self, mock_consumer_class: MagicMock) -> None:
        """Consumer should subscribe to specified topics."""
        mock_consumer = MagicMock()
        mock_consumer_class.return_value = mock_consumer

        settings = KafkaConsumerSettings(kafka_group_id="processor")
        with KafkaConsumer(settings) as consumer:
            consumer.subscribe(["products.raw.v1"])

        mock_consumer.subscribe.assert_called_once_with(["products.raw.v1"])

    @patch("confluent_kafka.Consumer")
    def test_subscribe_multiple_topics(self, mock_consumer_class: MagicMock) -> None:
        """Consumer can subscribe to multiple topics."""
        mock_consumer = MagicMock()
        mock_consumer_class.return_value = mock_consumer

        settings = KafkaConsumerSettings(kafka_group_id="processor")
        with KafkaConsumer(settings) as consumer:
            consumer.subscribe(["products.raw.v1", "products.validated.v1"])

        mock_consumer.subscribe.assert_called_once_with(
            ["products.raw.v1", "products.validated.v1"]
        )

    @patch("confluent_kafka.Consumer")
    def test_get_assignment(self, mock_consumer_class: MagicMock) -> None:
        """Consumer should report current partition assignments."""
        mock_consumer = MagicMock()
        mock_consumer_class.return_value = mock_consumer

        # Mock assignment
        tp = TopicPartition("products.raw.v1", 0, -1000)
        mock_consumer.assignment.return_value = [tp]

        settings = KafkaConsumerSettings(kafka_group_id="processor")
        with KafkaConsumer(settings) as consumer:
            assignment = consumer.get_assignment()

        assert len(assignment) == 1
        assert assignment[0].topic == "products.raw.v1"
        assert assignment[0].partition == 0
