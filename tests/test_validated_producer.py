"""Unit tests for the validated output producer (TASK-017).

Tests verify that ``KafkaValidatedOutputProducer`` publishes events to
``products.validated.v1`` with synchronous delivery confirmation and
correct error handling.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from libs.common.kafka_producer import KafkaProducerSettings, PublishError
from libs.common.kafka_validated_producer import (
    VALIDATED_TOPIC,
    DeliveryReceipt,
    KafkaValidatedOutputProducer,
)
from libs.event_contracts import (
    Availability,
    ProductObservationEvent,
    ProductObservationPayload,
)


def _make_settings(**overrides: Any) -> KafkaProducerSettings:
    """Create test settings with sensible defaults."""
    defaults: dict[str, Any] = {
        "environment": "development",
        "kafka_bootstrap_servers": "localhost:9092",
        "kafka_client_id": "test-validated",
        "kafka_delivery_timeout_ms": 5000,
    }
    defaults.update(overrides)
    return KafkaProducerSettings(**defaults)


def _make_event(event_id: str = "evt-001") -> ProductObservationEvent:
    """Create a test event."""
    ts = datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc)
    return ProductObservationEvent(
        event_id=event_id,
        event_type="product.observation",
        schema_version=1,
        source="test-source",
        produced_at=ts,
        payload=ProductObservationPayload(
            external_id="prod-123",
            name="Test Product",
            url="https://example.com/product/123",
            price=Decimal("99.99"),
            currency="EUR",
            availability=Availability.IN_STOCK,
            category="electronics",
            collected_at=ts,
        ),
    )


class TestValidatedTopic:
    """The producer must publish to the correct topic."""

    def test_validated_topic_constant(self) -> None:
        """The validated topic is products.validated.v1."""
        assert VALIDATED_TOPIC == "products.validated.v1"


class TestPublishSuccess:
    """Successful publish must return a delivery receipt."""

    @patch("libs.common.kafka_validated_producer.Producer")
    def test_publish_returns_receipt(self, mock_producer_cls: MagicMock) -> None:
        """A successful publish returns a DeliveryReceipt."""
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer

        def fake_produce(topic: str, value: bytes, key: bytes, on_delivery: Any) -> None:
            from confluent_kafka import Message

            msg = MagicMock(spec=Message)
            msg.topic.return_value = topic
            msg.partition.return_value = 0
            msg.offset.return_value = 42
            on_delivery(None, msg)

        mock_producer.produce.side_effect = fake_produce
        mock_producer.flush.return_value = 0

        settings = _make_settings()
        producer = KafkaValidatedOutputProducer(settings)
        event = _make_event()

        receipt = producer.publish(event)

        assert isinstance(receipt, DeliveryReceipt)
        assert receipt.topic == VALIDATED_TOPIC
        assert receipt.partition == 0
        assert receipt.offset == 42
        mock_producer.produce.assert_called_once()

    @patch("libs.common.kafka_validated_producer.Producer")
    def test_publish_uses_correct_topic(self, mock_producer_cls: MagicMock) -> None:
        """Publish sends to products.validated.v1."""
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer

        def fake_produce(topic: str, **kwargs: Any) -> None:
            from confluent_kafka import Message

            msg = MagicMock(spec=Message)
            msg.topic.return_value = topic
            msg.partition.return_value = 0
            msg.offset.return_value = 0
            kwargs["on_delivery"](None, msg)

        mock_producer.produce.side_effect = fake_produce
        mock_producer.flush.return_value = 0

        settings = _make_settings()
        producer = KafkaValidatedOutputProducer(settings)

        producer.publish(_make_event())

        call_args = mock_producer.produce.call_args
        assert call_args[0][0] == VALIDATED_TOPIC


class TestPublishFailure:
    """Publish failures must raise PublishError."""

    @patch("libs.common.kafka_validated_producer.Producer")
    def test_delivery_error_raises(self, mock_producer_cls: MagicMock) -> None:
        """A delivery error raises PublishError."""
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer

        from confluent_kafka import KafkaError

        def fake_produce(topic: str, **kwargs: Any) -> None:
            from confluent_kafka import Message

            error = MagicMock(spec=KafkaError)
            error.code.return_value = -1
            msg = MagicMock(spec=Message)
            kwargs["on_delivery"](error, msg)

        mock_producer.produce.side_effect = fake_produce
        mock_producer.flush.return_value = 0

        settings = _make_settings()
        producer = KafkaValidatedOutputProducer(settings)

        with pytest.raises(PublishError, match="delivery failed"):
            producer.publish(_make_event())

    @patch("libs.common.kafka_validated_producer.Producer")
    def test_unconfirmed_delivery_raises(self, mock_producer_cls: MagicMock) -> None:
        """Unconfirmed delivery raises PublishError."""
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer

        mock_producer.produce.return_value = None
        mock_producer.flush.return_value = 1

        settings = _make_settings()
        producer = KafkaValidatedOutputProducer(settings)

        with pytest.raises(PublishError, match="unconfirmed"):
            producer.publish(_make_event())

    @patch("libs.common.kafka_validated_producer.Producer")
    def test_publish_on_closed_producer_raises(self, mock_producer_cls: MagicMock) -> None:
        """Publishing on a closed producer raises PublishError."""
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer
        mock_producer.flush.return_value = 0

        settings = _make_settings()
        producer = KafkaValidatedOutputProducer(settings)
        producer.close()

        with pytest.raises(PublishError, match="closed"):
            producer.publish(_make_event())


class TestClose:
    """Close must drain pending work."""

    @patch("libs.common.kafka_validated_producer.Producer")
    def test_close_drains(self, mock_producer_cls: MagicMock) -> None:
        """Close flushes pending messages."""
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer
        mock_producer.flush.return_value = 0

        settings = _make_settings()
        producer = KafkaValidatedOutputProducer(settings)
        producer.close()

        mock_producer.flush.assert_called()

    @patch("libs.common.kafka_validated_producer.Producer")
    def test_close_with_pending_raises(self, mock_producer_cls: MagicMock) -> None:
        """Close with unconfirmed deliveries raises PublishError."""
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer
        mock_producer.flush.return_value = 5

        settings = _make_settings()
        producer = KafkaValidatedOutputProducer(settings)

        with pytest.raises(PublishError, match="unconfirmed"):
            producer.close()

    @patch("libs.common.kafka_validated_producer.Producer")
    def test_double_close_is_safe(self, mock_producer_cls: MagicMock) -> None:
        """Calling close twice is safe."""
        mock_producer = MagicMock()
        mock_producer_cls.return_value = mock_producer
        mock_producer.flush.return_value = 0

        settings = _make_settings()
        producer = KafkaValidatedOutputProducer(settings)
        producer.close()
        producer.close()
