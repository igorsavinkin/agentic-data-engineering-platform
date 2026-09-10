"""Producer unit tests plus opt-in real Kafka verification (TASK-008)."""

from __future__ import annotations

import os
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from confluent_kafka import Consumer, KafkaError, KafkaException, TopicPartition
from pydantic import ValidationError

from libs.common.config import ConfigurationError, load_settings
from libs.common.kafka_producer import (
    DeliveryReceipt,
    EventSerializationError,
    KafkaEventProducer,
    KafkaProducerSettings,
    PublishError,
)
from libs.event_contracts import ProductObservationEvent, deserialize_event, serialize_event
from scripts import manage_kafka_topics as manager


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.upper().startswith("APP_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("APP_ENVIRONMENT", "development")


@pytest.fixture
def event() -> ProductObservationEvent:
    return deserialize_event(
        {
            "event_id": "test-observation-008",
            "source": "test-source",
            "produced_at": "2026-09-08T12:00:00Z",
            "payload": {
                "external_id": "product-1",
                "name": "Test café",
                "url": "https://example.com/1",
                "price": "19.99",
                "currency": "EUR",
                "availability": "in_stock",
                "category": "test",
                "collected_at": "2026-09-08T11:59:00Z",
            },
        }
    )


@pytest.fixture
def client() -> Iterator[MagicMock]:
    with patch("libs.common.kafka_producer.Producer") as factory:
        mock = factory.return_value
        message = MagicMock()
        message.topic.return_value = "products.raw.v1"
        message.partition.return_value = 2
        message.offset.return_value = 42

        def flush(timeout: float) -> int:
            if mock.produce.called:
                mock.produce.call_args.kwargs["on_delivery"](None, message)
            return 0

        mock.flush.side_effect = flush
        yield mock


def test_publish_preserves_wire_identity_and_key(
    client: MagicMock, event: ProductObservationEvent, caplog: pytest.LogCaptureFixture
) -> None:
    original = serialize_event(event)
    with caplog.at_level("INFO"):
        with KafkaEventProducer(load_settings(KafkaProducerSettings)) as producer:
            assert producer.publish(event) == DeliveryReceipt("products.raw.v1", 2, 42)
            assert producer.publish(event).offset == 42
    for call in client.produce.call_args_list:
        assert call.args == ("products.raw.v1",)
        assert call.kwargs["value"] == original.encode("utf-8")
        assert call.kwargs["key"] == b"test-source:product-1"
        assert deserialize_event(call.kwargs["value"].decode()) == event
    assert serialize_event(event) == original
    assert any(
        r.message == "kafka_event_delivered" and getattr(r, "event_id", None) == event.event_id
        for r in caplog.records
    )


def test_client_reliability_configuration() -> None:
    with patch("libs.common.kafka_producer.Producer") as factory:
        KafkaEventProducer(load_settings(KafkaProducerSettings))
    config = factory.call_args.args[0]
    assert config["enable.idempotence"] is True
    assert config["acks"] == "all"
    assert config["max.in.flight.requests.per.connection"] <= 5
    assert config["allow.auto.create.topics"] is False
    assert config["partitioner"] == "murmur2_random"
    assert config["delivery.timeout.ms"] == 30000


def test_environment_configures_actual_publish(
    client: MagicMock, event: ProductObservationEvent, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_KAFKA_BOOTSTRAP_SERVERS", "broker:19092,[::1]:9092")
    monkeypatch.setenv("APP_KAFKA_RAW_TOPIC", "custom.raw.v1")
    monkeypatch.setenv("APP_KAFKA_CLIENT_ID", "custom-ingestion")
    monkeypatch.setenv("APP_KAFKA_DELIVERY_TIMEOUT_MS", "2000")
    settings = load_settings(KafkaProducerSettings)
    assert settings.kafka_bootstrap_servers == "broker:19092,[::1]:9092"
    assert settings.kafka_client_id == "custom-ingestion"
    KafkaEventProducer(settings).publish(event)
    assert client.produce.call_args.args == ("custom.raw.v1",)
    client.flush.assert_called_once_with(3.0)


@pytest.mark.parametrize(
    "variable,value",
    [
        ("APP_KAFKA_BOOTSTRAP_SERVERS", ""),
        ("APP_KAFKA_BOOTSTRAP_SERVERS", "host:0"),
        ("APP_KAFKA_BOOTSTRAP_SERVERS", "host:65536"),
        ("APP_KAFKA_BOOTSTRAP_SERVERS", "secret@host:9092"),
        ("APP_KAFKA_RAW_TOPIC", ""),
        ("APP_KAFKA_RAW_TOPIC", ".."),
        ("APP_KAFKA_RAW_TOPIC", "bad topic"),
        ("APP_KAFKA_RAW_TOPIC", "a" * 250),
        ("APP_KAFKA_CLIENT_ID", ""),
        ("APP_KAFKA_DELIVERY_TIMEOUT_MS", "0"),
        ("APP_KAFKA_DELIVERY_TIMEOUT_MS", "300001"),
        ("APP_KAFKA_DELIVERY_TIMEOUT_MS", "nan"),
        ("APP_KAFKA_TYPO", "secret"),
    ],
)
def test_invalid_configuration(variable: str, value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(variable, value)
    with pytest.raises(ConfigurationError) as error:
        load_settings(KafkaProducerSettings)
    assert variable in str(error.value)
    assert "secret" not in str(error.value)


def test_settings_are_immutable() -> None:
    settings = load_settings(KafkaProducerSettings)
    with pytest.raises(ValidationError):
        setattr(settings, "kafka_raw_topic", "changed")


def test_serialization_failure_never_enqueues(
    client: MagicMock, event: ProductObservationEvent, caplog: pytest.LogCaptureFixture
) -> None:
    producer = KafkaEventProducer(load_settings(KafkaProducerSettings))
    with patch("libs.common.kafka_producer.serialize_event", side_effect=ValueError("secret")):
        with pytest.raises(EventSerializationError, match="serialization failed"):
            producer.publish(event)
    client.produce.assert_not_called()
    assert "secret" not in caplog.text


def test_mutated_invalid_event_never_enqueues(
    client: MagicMock, event: ProductObservationEvent
) -> None:
    event.schema_version = 99
    with pytest.raises(EventSerializationError):
        KafkaEventProducer(load_settings(KafkaProducerSettings)).publish(event)
    client.produce.assert_not_called()


@pytest.mark.parametrize(
    "failure", [BufferError("queue full"), KafkaException(KafkaError(KafkaError._TRANSPORT))]
)
def test_enqueue_failure_raises(
    client: MagicMock, event: ProductObservationEvent, failure: Exception
) -> None:
    client.produce.side_effect = failure
    with pytest.raises(PublishError, match="publish failed"):
        KafkaEventProducer(load_settings(KafkaProducerSettings)).publish(event)


def test_failed_delivery_is_not_success_even_when_queue_empty(
    client: MagicMock, event: ProductObservationEvent
) -> None:
    def fail(timeout: float) -> int:
        client.produce.call_args.kwargs["on_delivery"](
            KafkaError(KafkaError._MSG_TIMED_OUT), MagicMock()
        )
        return 0

    client.flush.side_effect = fail
    with pytest.raises(PublishError, match="delivery failed"):
        KafkaEventProducer(load_settings(KafkaProducerSettings)).publish(event)


@pytest.mark.parametrize("pending", [0, 1])
def test_missing_callback_is_unconfirmed(
    client: MagicMock, event: ProductObservationEvent, pending: int
) -> None:
    client.flush.side_effect = None
    client.flush.return_value = pending
    with pytest.raises(PublishError, match="unconfirmed"):
        KafkaEventProducer(load_settings(KafkaProducerSettings)).publish(event)


def test_client_initialization_failure() -> None:
    with patch("libs.common.kafka_producer.Producer", side_effect=ValueError("invalid")):
        with pytest.raises(ConfigurationError, match="initialization failed"):
            KafkaEventProducer(load_settings(KafkaProducerSettings))


def test_retry_after_failed_delivery_preserves_event(
    client: MagicMock, event: ProductObservationEvent
) -> None:
    success = client.flush.side_effect

    def fail_once(timeout: float) -> int:
        client.produce.call_args.kwargs["on_delivery"](
            KafkaError(KafkaError._MSG_TIMED_OUT), MagicMock()
        )
        client.flush.side_effect = success
        return 0

    client.flush.side_effect = fail_once
    with KafkaEventProducer(load_settings(KafkaProducerSettings)) as producer:
        with pytest.raises(PublishError):
            producer.publish(event)
        assert producer.publish(event).offset == 42
    calls = client.produce.call_args_list
    assert calls[0].kwargs["value"] == calls[1].kwargs["value"]
    assert calls[0].kwargs["key"] == calls[1].kwargs["key"]


def test_flush_exception_is_reported(client: MagicMock, event: ProductObservationEvent) -> None:
    client.flush.side_effect = KafkaException(KafkaError(KafkaError._TRANSPORT))
    producer = KafkaEventProducer(load_settings(KafkaProducerSettings))
    with pytest.raises(PublishError, match="publish failed"):
        producer.publish(event)
    assert producer.metrics.snapshot()["ingestion_errors_total"] == 1
    with pytest.raises(PublishError, match="shutdown failed"):
        producer.close()
    assert producer.metrics.snapshot()["ingestion_errors_total"] == 2


def test_successful_context_body_still_reports_shutdown_failure(client: MagicMock) -> None:
    client.flush.side_effect = None
    client.flush.return_value = 1
    with pytest.raises(PublishError, match="unconfirmed"):
        with KafkaEventProducer(load_settings(KafkaProducerSettings)):
            pass


def test_shutdown_and_publish_after_close(
    client: MagicMock, event: ProductObservationEvent
) -> None:
    producer = KafkaEventProducer(load_settings(KafkaProducerSettings))
    producer.close()
    producer.close()
    client.flush.assert_called_once()
    assert producer.metrics.snapshot()["ingestion_errors_total"] == 0
    with pytest.raises(PublishError, match="closed"):
        producer.publish(event)
    assert producer.metrics.snapshot()["ingestion_errors_total"] == 1


def test_shutdown_failure_can_be_retried(client: MagicMock) -> None:
    producer = KafkaEventProducer(load_settings(KafkaProducerSettings))
    client.flush.side_effect = [1, 0]
    with pytest.raises(PublishError, match="unconfirmed"):
        producer.close()
    assert producer.metrics.snapshot()["ingestion_errors_total"] == 1
    producer.close()
    assert client.flush.call_count == 2
    assert producer.metrics.snapshot()["ingestion_errors_total"] == 1


def test_shutdown_does_not_mask_original_error(
    client: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    client.flush.side_effect = None
    client.flush.return_value = 1
    with pytest.raises(ValueError, match="original"):
        with KafkaEventProducer(load_settings(KafkaProducerSettings)):
            raise ValueError("original")
    assert "kafka_shutdown_failed" in caplog.text


@pytest.fixture
def real_broker(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Own an isolated Compose project; never touch the developer's stack."""
    try:
        probe = subprocess.run(["docker", "info"], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("Docker daemon unavailable")
    if probe.returncode:
        pytest.skip("Docker daemon unavailable")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    project = "task008-test-" + uuid4().hex[:10]
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", project)
    monkeypatch.setenv("PLATFORM_NETWORK_NAME", project)
    monkeypatch.setenv("KAFKA_HOST_PORT", str(port))
    monkeypatch.delenv("KAFKA_BIN_DIR", raising=False)
    monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS", raising=False)
    compose = [
        "docker",
        "compose",
        "-f",
        str(Path(__file__).resolve().parents[1] / "docker-compose.yml"),
    ]
    try:
        result = subprocess.run(
            [*compose, "up", "-d", "--wait", "--wait-timeout", "120", "kafka"],
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == 0, result.stderr
        assert manager.create_topic(manager.TOPICS[0], "kafka:29092")
        yield f"localhost:{port}"
    finally:
        subprocess.run(
            [*compose, "down", "--volumes", "--remove-orphans"],
            capture_output=True,
            check=True,
            timeout=60,
        )


@pytest.mark.integration
def test_real_publish_and_consume(real_broker: str, event: ProductObservationEvent) -> None:
    settings = KafkaProducerSettings(environment="development", kafka_bootstrap_servers=real_broker)
    with KafkaEventProducer(settings) as producer:
        first = producer.publish(event)
        second = producer.publish(event)
    assert first.topic == "products.raw.v1"
    assert first.partition == second.partition
    assert second.offset == first.offset + 1
    consumer = Consumer(
        {
            "bootstrap.servers": real_broker,
            "group.id": "task008-" + uuid4().hex,
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
        }
    )
    try:
        consumer.assign([TopicPartition(first.topic, first.partition, first.offset)])
        received: list[int | None] = []
        deadline = time.monotonic() + 20
        while len(received) < 2 and time.monotonic() < deadline:
            message = consumer.poll(1)
            if message is None:
                continue
            assert message.error() is None
            assert message.key() == event.partition_key.encode("utf-8")
            assert message.value() == serialize_event(event).encode("utf-8")
            received.append(message.offset())
        assert received == [first.offset, second.offset]
    finally:
        consumer.close()


@pytest.mark.integration
def test_real_kafka_unavailable(event: ProductObservationEvent) -> None:
    # Reserve a TCP port without listening so no other process can become a broker.
    with socket.socket() as unavailable:
        unavailable.bind(("127.0.0.1", 0))
        settings = KafkaProducerSettings(
            environment="development",
            kafka_bootstrap_servers=f"127.0.0.1:{unavailable.getsockname()[1]}",
            kafka_delivery_timeout_ms=1000,
        )
        start = time.monotonic()
        with KafkaEventProducer(settings) as producer:
            with pytest.raises(PublishError, match="delivery failed|unconfirmed"):
                producer.publish(event)
        assert time.monotonic() - start < 8
