"""Dead-letter queue engineering test (TASK-105).

Demonstrates the full failure lifecycle for malformed events:

    Malformed Event -> Detection (deserialization failure) -> DLQ routing
    -> Metric/log -> Main pipeline unaffected -> DLQ queryable

All malformed events in this system fail at the Pydantic deserialization boundary
(``KafkaConsumer.poll`` → ``DeserializationError``).  The consumer's
``process_next(dead_letter=…)`` method routes these via ``diagnostic_envelope``
to the DLQ topic (``products.invalid.v1``).  The pipeline-level
``validation_envelope`` path is defense-in-depth for post-normalization failures
and is not triggered by externally-produced malformed events.

Scenarios:
1. Mixed batch: valid events processed, malformed bytes routed to DLQ.
2. DLQ events are queryable with diagnostic context from products.invalid.v1.
3. Consumer-level metrics (DEAD_LETTERED, INVALID) increment on DLQ routing.
4. Deserialization failures carry error_type and raw_value_base64.
5. DLQ does not block subsequent valid event processing.

Lifecycle per scenario:
    Failure -> Detection -> Metric/log -> Recovery -> No silent data loss

Run with: pytest tests/test_dlq.py -v -m integration
"""

# mypy: disable-error-code="import-untyped,no-untyped-def,import-not-found,no-any-return,attr-defined"
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from confluent_kafka import Producer

from libs.common.kafka_consumer import (
    KafkaConsumer,
    KafkaConsumerSettings,
)
from libs.common.kafka_errors import KafkaDeadLetterProducer
from libs.common.kafka_producer import (
    KafkaEventProducer,
    KafkaProducerSettings,
)
from libs.event_contracts import ProductObservationEvent, deserialize_event
from libs.observability.kafka_metrics import KafkaMetric
from scripts import manage_kafka_topics as manager

INVALID_TOPIC = "products.invalid.v1"
VALIDATED_TOPIC = "products.validated.v1"
RAW_TOPIC = "products.raw.v1"

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.upper().startswith("APP_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("APP_ENVIRONMENT", "development")


@pytest.fixture
def real_broker(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    try:
        probe = subprocess.run(["docker", "info"], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("Docker daemon unavailable")
    if probe.returncode:
        pytest.skip("Docker daemon unavailable")

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    project = f"task105-test-{uuid4().hex[:10]}"
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", project)
    monkeypatch.setenv("PLATFORM_NETWORK_NAME", project)
    monkeypatch.setenv("KAFKA_HOST_PORT", str(port))
    monkeypatch.delenv("KAFKA_BIN_DIR", raising=False)
    monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS", raising=False)

    compose_file = Path(__file__).resolve().parents[1] / "docker-compose.yml"
    compose_cmd = ["docker", "compose", "-f", str(compose_file)]

    try:
        result = subprocess.run(
            [*compose_cmd, "up", "-d", "--wait", "--wait-timeout", "120", "kafka"],
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == 0, f"Failed to start Kafka: {result.stderr}"

        for topic_config in manager.TOPICS:
            assert manager.create_topic(topic_config, "kafka:29092"), (
                f"Failed to create topic {topic_config.name}"
            )

        yield f"localhost:{port}"
    finally:
        subprocess.run(
            [*compose_cmd, "down", "--volumes", "--remove-orphans"],
            capture_output=True,
            check=True,
            timeout=60,
        )


def _make_producer_settings(broker: str, client_id: str) -> KafkaProducerSettings:
    return KafkaProducerSettings(
        environment="development",
        kafka_bootstrap_servers=broker,
        kafka_client_id=client_id,
        kafka_delivery_timeout_ms=5000,
    )


def _make_consumer_settings(broker: str, group_id: str) -> KafkaConsumerSettings:
    return KafkaConsumerSettings(
        environment="development",
        kafka_bootstrap_servers=broker,
        kafka_group_id=group_id,
    )


def _make_valid_event(event_id: str | None = None) -> ProductObservationEvent:
    uid = event_id or f"task105-{uuid4().hex[:12]}"
    return deserialize_event(
        {
            "event_id": uid,
            "source": "task105-test",
            "produced_at": "2026-09-24T12:00:00Z",
            "payload": {
                "external_id": f"product-{uid}",
                "name": "DLQ Test Product",
                "url": f"https://example.com/dlq/{uid}",
                "price": "49.99",
                "currency": "USD",
                "availability": "in_stock",
                "category": "electronics",
                "collected_at": "2026-09-24T11:59:00Z",
            },
        }
    )


def _consume_json(
    broker: str,
    topic: str,
    group_id: str,
    expected: int,
    timeout: float = 15.0,
) -> list[dict]:
    from confluent_kafka import Consumer

    consumer = Consumer(
        {
            "bootstrap.servers": broker,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
        }
    )
    consumer.subscribe([topic])
    results: list[dict] = []
    deadline = time.monotonic() + timeout
    try:
        while len(results) < expected and time.monotonic() < deadline:
            msg = consumer.poll(1.0)
            if msg is None or msg.error() is not None:
                continue
            value = msg.value()
            if value is not None:
                results.append(json.loads(value.decode("utf-8")))
    finally:
        consumer.close()
    return results


@pytest.fixture
def broker_address(real_broker: str) -> str:
    return real_broker


@pytest.fixture
def raw_producer_settings(broker_address: str) -> KafkaProducerSettings:
    return _make_producer_settings(broker_address, "task105-raw-producer")


@pytest.fixture
def validated_producer_settings(broker_address: str) -> KafkaProducerSettings:
    return _make_producer_settings(broker_address, "task105-validated-producer")


@pytest.fixture
def invalid_producer_settings(broker_address: str) -> KafkaProducerSettings:
    return _make_producer_settings(broker_address, "task105-invalid-producer")


@pytest.fixture
def raw_consumer_settings(broker_address: str) -> KafkaConsumerSettings:
    return _make_consumer_settings(broker_address, f"task105-raw-{uuid4().hex[:8]}")


@pytest.fixture
def validated_consumer_settings(broker_address: str) -> KafkaConsumerSettings:
    return _make_consumer_settings(broker_address, f"task105-validated-{uuid4().hex[:8]}")


@pytest.fixture
def invalid_consumer_settings(broker_address: str) -> KafkaConsumerSettings:
    return _make_consumer_settings(broker_address, f"task105-invalid-{uuid4().hex[:8]}")


class TestDlqRoutingMixedBatch:
    """Valid events processed; malformed bytes routed to DLQ via process_next."""

    def test_valid_events_processed_while_malformed_bytes_route_to_dlq(
        self,
        broker_address: str,
        raw_producer_settings: KafkaProducerSettings,
        invalid_producer_settings: KafkaProducerSettings,
        validated_consumer_settings: KafkaConsumerSettings,
        invalid_consumer_settings: KafkaConsumerSettings,
    ) -> None:
        """2 valid events + 1 bad JSON → valid processed, bad → DLQ."""
        valid_event_1 = _make_valid_event()
        valid_event_2 = _make_valid_event()

        with KafkaEventProducer(raw_producer_settings) as raw_producer:
            raw_producer.publish(valid_event_1)
            raw_producer.publish(valid_event_2)

        raw_kafka = Producer({"bootstrap.servers": broker_address})
        try:
            raw_kafka.produce(
                RAW_TOPIC,
                value=b"this is not valid json {{{",
                key=b"bad-key",
            )
            raw_kafka.flush(timeout=5)
        finally:
            raw_kafka.close()

        consumer_settings = _make_consumer_settings(
            broker_address, f"task105-mixed-{uuid4().hex[:8]}"
        )
        consumer = KafkaConsumer(consumer_settings)
        consumer.subscribe([RAW_TOPIC])

        dlq_producer = KafkaDeadLetterProducer(invalid_producer_settings)
        processed_ids: list[str] = []
        dlq_routed = False
        try:
            deadline = time.monotonic() + 25
            while (len(processed_ids) < 2 or not dlq_routed) and time.monotonic() < deadline:
                result = consumer.process_next(
                    process=lambda msg: processed_ids.append(msg.event.event_id),
                    dead_letter=dlq_producer.publish,
                    timeout=2.0,
                )
                if result:
                    dlq_routed = True

            assert len(processed_ids) == 2, (
                f"Expected 2 valid events processed, got {len(processed_ids)}"
            )
            assert valid_event_1.event_id in processed_ids
            assert valid_event_2.event_id in processed_ids
            assert dlq_routed, "Expected DLQ routing for malformed bytes"
        finally:
            dlq_producer.close()
            consumer.close()

        dlq_output = _consume_json(
            broker_address,
            INVALID_TOPIC,
            invalid_consumer_settings.kafka_group_id,
            expected=1,
        )
        assert len(dlq_output) == 1
        assert dlq_output[0]["payload"]["error_type"] == "ValidationError"

        snapshot = consumer.metrics.snapshot()
        assert snapshot[KafkaMetric.PROCESSED.value] >= 2
        assert snapshot[KafkaMetric.DEAD_LETTERED.value] >= 1


class TestDlqQueryable:
    """DLQ events in products.invalid.v1 are queryable with diagnostic context."""

    def test_dlq_events_contain_diagnostic_context(
        self,
        broker_address: str,
        invalid_producer_settings: KafkaProducerSettings,
        invalid_consumer_settings: KafkaConsumerSettings,
    ) -> None:
        """DLQ records contain error_type, topic, partition, offset, raw_value_base64."""
        raw_kafka = Producer({"bootstrap.servers": broker_address})
        try:
            raw_kafka.produce(
                RAW_TOPIC,
                value=b'{"broken": json',
                key=b"dlq-query-key",
            )
            raw_kafka.flush(timeout=5)
        finally:
            raw_kafka.close()

        consumer_settings = _make_consumer_settings(
            broker_address, f"task105-query-{uuid4().hex[:8]}"
        )
        consumer = KafkaConsumer(consumer_settings)
        consumer.subscribe([RAW_TOPIC])

        dlq_producer = KafkaDeadLetterProducer(invalid_producer_settings)
        dlq_called = False
        try:
            deadline = time.monotonic() + 15
            while not dlq_called and time.monotonic() < deadline:
                result = consumer.process_next(
                    process=lambda msg: None,
                    dead_letter=dlq_producer.publish,
                    timeout=2.0,
                )
                if result:
                    dlq_called = True
            assert dlq_called, "Expected DLQ routing for malformed bytes"
        finally:
            dlq_producer.close()
            consumer.close()

        dlq_output = _consume_json(
            broker_address,
            INVALID_TOPIC,
            invalid_consumer_settings.kafka_group_id,
            expected=1,
        )
        assert len(dlq_output) == 1

        dlq_record = dlq_output[0]
        assert dlq_record["event_type"] == "product.invalid"
        payload = dlq_record["payload"]
        assert "error_type" in payload
        assert payload["error_type"] == "ValidationError"
        assert "raw_value_base64" in payload
        assert payload["raw_value_base64"] is not None
        assert "topic" in payload
        assert payload["topic"] == RAW_TOPIC
        assert "partition" in payload
        assert "offset" in payload
        assert "consumer_group" in payload


class TestDlqMetrics:
    """DLQ routing increments consumer-level metrics."""

    def test_consumer_metrics_increment_on_dlq_routing(
        self,
        broker_address: str,
        invalid_producer_settings: KafkaProducerSettings,
    ) -> None:
        """DEAD_LETTERED and INVALID increment for each DLQ-routed message."""
        raw_kafka = Producer({"bootstrap.servers": broker_address})
        try:
            for i in range(3):
                raw_kafka.produce(
                    RAW_TOPIC,
                    value=f"bad-json-{i}".encode(),
                    key=b"metrics-key",
                )
            raw_kafka.flush(timeout=5)
        finally:
            raw_kafka.close()

        consumer_settings = _make_consumer_settings(
            broker_address, f"task105-metrics-{uuid4().hex[:8]}"
        )
        consumer = KafkaConsumer(consumer_settings)
        consumer.subscribe([RAW_TOPIC])

        dlq_producer = KafkaDeadLetterProducer(invalid_producer_settings)
        dlq_count = 0
        try:
            deadline = time.monotonic() + 20
            while dlq_count < 3 and time.monotonic() < deadline:
                result = consumer.process_next(
                    process=lambda msg: None,
                    dead_letter=dlq_producer.publish,
                    timeout=2.0,
                )
                if result:
                    dlq_count += 1
            assert dlq_count == 3, f"Expected 3 DLQ routings, got {dlq_count}"

            snapshot = consumer.metrics.snapshot()
            assert snapshot[KafkaMetric.DEAD_LETTERED.value] == 3
            assert snapshot[KafkaMetric.INVALID.value] == 3
            assert snapshot[KafkaMetric.PROCESSED.value] == 0
        finally:
            dlq_producer.close()
            consumer.close()


class TestConsumerLevelDlq:
    """Consumer-level DLQ: deserialization failures route to DLQ."""

    def test_deserialization_failure_routes_to_dlq(
        self,
        broker_address: str,
        invalid_producer_settings: KafkaProducerSettings,
        invalid_consumer_settings: KafkaConsumerSettings,
    ) -> None:
        """Bad JSON bytes → diagnostic_envelope → DLQ with error_type and raw_value_base64."""
        raw_kafka = Producer({"bootstrap.servers": broker_address})
        try:
            raw_kafka.produce(
                RAW_TOPIC,
                value=b"this is not valid json at all {{{",
                key=b"bad-bytes-key",
            )
            raw_kafka.flush(timeout=5)
        finally:
            raw_kafka.close()

        consumer_settings = _make_consumer_settings(
            broker_address, f"task105-deser-{uuid4().hex[:8]}"
        )
        consumer = KafkaConsumer(consumer_settings)
        consumer.subscribe([RAW_TOPIC])

        dlq_producer = KafkaDeadLetterProducer(invalid_producer_settings)
        try:
            deadline = time.monotonic() + 15
            dlq_called = False
            while not dlq_called and time.monotonic() < deadline:
                result = consumer.process_next(
                    process=lambda msg: None,
                    dead_letter=dlq_producer.publish,
                    timeout=2.0,
                )
                if result:
                    dlq_called = True

            assert dlq_called, "Deserialization error should have been dead-lettered"

            snapshot = consumer.metrics.snapshot()
            assert snapshot[KafkaMetric.DEAD_LETTERED.value] >= 1
            assert snapshot[KafkaMetric.INVALID.value] >= 1
        finally:
            dlq_producer.close()
            consumer.close()

        dlq_output = _consume_json(
            broker_address,
            INVALID_TOPIC,
            invalid_consumer_settings.kafka_group_id,
            expected=1,
        )
        assert len(dlq_output) == 1
        dlq_record = dlq_output[0]
        assert dlq_record["payload"]["error_type"] == "ValidationError"
        assert "raw_value_base64" in dlq_record["payload"]

    def test_dlq_does_not_block_valid_event_processing(
        self,
        broker_address: str,
        raw_producer_settings: KafkaProducerSettings,
        invalid_producer_settings: KafkaProducerSettings,
    ) -> None:
        """Valid events after a DLQ event are processed normally."""
        valid_event = _make_valid_event()
        with KafkaEventProducer(raw_producer_settings) as raw_producer:
            raw_producer.publish(valid_event)

        raw_kafka = Producer({"bootstrap.servers": broker_address})
        try:
            raw_kafka.produce(
                RAW_TOPIC,
                value=b"not-json",
                key=b"blocker-key",
            )
            raw_kafka.flush(timeout=5)
        finally:
            raw_kafka.close()

        consumer_settings = _make_consumer_settings(
            broker_address, f"task105-noblock-{uuid4().hex[:8]}"
        )
        consumer = KafkaConsumer(consumer_settings)
        consumer.subscribe([RAW_TOPIC])

        dlq_producer = KafkaDeadLetterProducer(invalid_producer_settings)
        processed_ids: list[str] = []
        dlq_routed = False
        try:
            deadline = time.monotonic() + 25
            while (len(processed_ids) < 1 or not dlq_routed) and time.monotonic() < deadline:
                result = consumer.process_next(
                    process=lambda msg: processed_ids.append(msg.event.event_id),
                    dead_letter=dlq_producer.publish,
                    timeout=2.0,
                )
                if result:
                    dlq_routed = True

            assert len(processed_ids) >= 1, "Valid event should have been processed"
            assert valid_event.event_id in processed_ids
            assert dlq_routed, "DLQ should have been invoked for bad bytes"
        finally:
            dlq_producer.close()
            consumer.close()
