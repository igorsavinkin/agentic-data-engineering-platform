"""Dead-letter queue engineering test (TASK-105).

Demonstrates the full failure lifecycle for malformed events:

    Malformed Event -> Detection (validation/deserialization) -> DLQ routing
    -> Metric/log -> Main pipeline unaffected -> DLQ queryable

Scenarios:
1. Mixed batch: invalid events route to DLQ, valid events reach validated topic.
2. DLQ events are queryable with diagnostic context from products.invalid.v1.
3. Processor metrics (EVENTS_INVALID) increment on DLQ routing.
4. Consumer-level DLQ: deserialization failures route to DLQ via process_next.
5. DLQ monitoring: KafkaMetric.DEAD_LETTERED increments on consumer-level DLQ.

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
    ConsumerMessage,
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
from libs.observability.processor_metrics import ProcessorMetric, ProcessorMetrics
from scripts import manage_kafka_topics as manager
from services.processor.deduplication import DeduplicationState
from services.processor.pipeline import ProcessorPipeline

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


def _make_invalid_raw_event() -> dict:
    return {
        "event_id": f"task105-bad-{uuid4().hex[:8]}",
        "event_type": "product.observation",
        "schema_version": 999,
        "source": "task105-test",
        "produced_at": "2026-09-24T12:00:00Z",
        "payload": {
            "external_id": "bad-product",
            "name": "Invalid Product",
            "url": "https://example.com/bad",
            "price": "10.00",
            "currency": "USD",
            "availability": "in_stock",
            "category": "test",
            "collected_at": "2026-09-24T11:59:00Z",
        },
    }


def _consume_raw_messages(
    consumer: KafkaConsumer,
    expected: int,
    timeout: float = 15.0,
) -> list[ConsumerMessage]:
    messages: list[ConsumerMessage] = []
    deadline = time.monotonic() + timeout
    while len(messages) < expected and time.monotonic() < deadline:
        batch, errors = consumer.poll(timeout=1.0)
        messages.extend(batch)
        if errors:
            pass
    return messages


def _consume_raw_json(
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


def _build_pipeline(
    validated_settings: KafkaProducerSettings,
    invalid_settings: KafkaProducerSettings,
    dedup_state: DeduplicationState | None = None,
    metrics: ProcessorMetrics | None = None,
) -> tuple[ProcessorPipeline, object, KafkaDeadLetterProducer]:
    from libs.common.kafka_validated_producer import KafkaValidatedOutputProducer

    validated_producer = KafkaValidatedOutputProducer(validated_settings)
    invalid_producer = KafkaDeadLetterProducer(invalid_settings)
    pipeline = ProcessorPipeline(
        validated_sink=validated_producer.publish,
        invalid_sink=invalid_producer.publish,
        dedup_state=dedup_state,
        metrics=metrics,
    )
    return pipeline, validated_producer, invalid_producer


class TestDlqRoutingMixedBatch:
    """Malformed events route to DLQ; valid events reach validated topic."""

    def test_invalid_events_route_to_dlq_valid_events_unaffected(
        self,
        broker_address: str,
        raw_producer_settings: KafkaProducerSettings,
        raw_consumer_settings: KafkaConsumerSettings,
        validated_producer_settings: KafkaProducerSettings,
        invalid_producer_settings: KafkaProducerSettings,
        validated_consumer_settings: KafkaConsumerSettings,
        invalid_consumer_settings: KafkaConsumerSettings,
    ) -> None:
        """A mixed batch: 2 valid + 1 invalid → valid to validated, invalid to DLQ."""
        valid_event_1 = _make_valid_event()
        valid_event_2 = _make_valid_event()

        with KafkaEventProducer(raw_producer_settings) as raw_producer:
            raw_producer.publish(valid_event_1)
            raw_producer.publish(valid_event_2)

        bad_event = _make_invalid_raw_event()
        raw_kafka = Producer({"bootstrap.servers": broker_address})
        try:
            raw_kafka.produce(
                RAW_TOPIC,
                value=json.dumps(bad_event).encode("utf-8"),
                key=b"test-key",
            )
            raw_kafka.flush(timeout=5)
        finally:
            raw_kafka.close()

        raw_consumer = KafkaConsumer(raw_consumer_settings)
        try:
            raw_consumer.subscribe([RAW_TOPIC])
            messages = _consume_raw_messages(raw_consumer, expected=2, timeout=20.0)
            assert len(messages) == 2

            metrics = ProcessorMetrics()
            pipeline, vp, ip = _build_pipeline(
                validated_producer_settings,
                invalid_producer_settings,
                metrics=metrics,
            )
            try:
                result = pipeline.process_batch(messages)
                assert result.published_valid == 2
                assert result.published_invalid == 0
                assert result.duplicates_skipped == 0
            finally:
                vp.close()
                ip.close()

            errors: list = []
            deadline = time.monotonic() + 10
            while not errors and time.monotonic() < deadline:
                _, batch_errors = raw_consumer.poll(timeout=1.0)
                errors.extend(batch_errors)
            assert len(errors) == 1

            pipeline2, vp2, ip2 = _build_pipeline(
                validated_producer_settings,
                invalid_producer_settings,
                metrics=metrics,
            )
            try:
                result2 = pipeline2.process_batch(errors)
                assert result2.published_invalid == 1
                assert result2.published_valid == 0
            finally:
                vp2.close()
                ip2.close()
        finally:
            raw_consumer.close()

        validated_output = _consume_raw_json(
            broker_address,
            VALIDATED_TOPIC,
            validated_consumer_settings.kafka_group_id,
            expected=2,
        )
        assert len(validated_output) == 2
        validated_ids = {o["event_id"] for o in validated_output}
        assert valid_event_1.event_id in validated_ids
        assert valid_event_2.event_id in validated_ids

        dlq_output = _consume_raw_json(
            broker_address,
            INVALID_TOPIC,
            invalid_consumer_settings.kafka_group_id,
            expected=1,
        )
        assert len(dlq_output) == 1
        assert dlq_output[0]["payload"]["reason"] == "validation_failure"

        snapshot = metrics.snapshot()
        assert snapshot[ProcessorMetric.EVENTS_INVALID.value] == 1
        assert snapshot[ProcessorMetric.EVENTS_VALID.value] == 2


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


class TestDlqQueryable:
    """DLQ events in products.invalid.v1 are queryable with diagnostic context."""

    def test_dlq_events_contain_diagnostic_context(
        self,
        broker_address: str,
        raw_consumer_settings: KafkaConsumerSettings,
        validated_producer_settings: KafkaProducerSettings,
        invalid_producer_settings: KafkaProducerSettings,
        invalid_consumer_settings: KafkaConsumerSettings,
    ) -> None:
        """Invalid events in DLQ contain validation error details."""
        bad_event = _make_invalid_raw_event()
        raw_kafka = Producer({"bootstrap.servers": broker_address})
        try:
            raw_kafka.produce(
                RAW_TOPIC,
                value=json.dumps(bad_event).encode("utf-8"),
                key=b"dlq-query-key",
            )
            raw_kafka.flush(timeout=5)
        finally:
            raw_kafka.close()

        raw_consumer = KafkaConsumer(raw_consumer_settings)
        try:
            errors: list = []
            deadline = time.monotonic() + 15
            while not errors and time.monotonic() < deadline:
                _, batch_errors = raw_consumer.poll(timeout=1.0)
                errors.extend(batch_errors)
            assert len(errors) == 1

            pipeline, vp, ip = _build_pipeline(
                validated_producer_settings,
                invalid_producer_settings,
            )
            try:
                result = pipeline.process_batch(errors)
                assert result.published_invalid == 1
            finally:
                vp.close()
                ip.close()
        finally:
            raw_consumer.close()

        dlq_output = _consume_raw_json(
            broker_address,
            INVALID_TOPIC,
            invalid_consumer_settings.kafka_group_id,
            expected=1,
        )
        assert len(dlq_output) == 1

        dlq_record = dlq_output[0]
        assert "event_id" in dlq_record
        assert dlq_record["event_type"] == "product.invalid"
        assert dlq_record["payload"]["reason"] == "validation_failure"
        assert "validation_errors" in dlq_record["payload"]
        assert "external_id" in dlq_record["payload"]


class TestDlqMetrics:
    """DLQ routing increments processor and consumer metrics."""

    def test_processor_metrics_increment_on_dlq_routing(
        self,
        broker_address: str,
        raw_consumer_settings: KafkaConsumerSettings,
        validated_producer_settings: KafkaProducerSettings,
        invalid_producer_settings: KafkaProducerSettings,
    ) -> None:
        """EVENTS_INVALID increments when invalid events route to DLQ."""
        bad_events = [_make_invalid_raw_event() for _ in range(3)]
        raw_kafka = Producer({"bootstrap.servers": broker_address})
        try:
            for bad_event in bad_events:
                raw_kafka.produce(
                    RAW_TOPIC,
                    value=json.dumps(bad_event).encode("utf-8"),
                    key=b"metrics-key",
                )
            raw_kafka.flush(timeout=5)
        finally:
            raw_kafka.close()

        raw_consumer = KafkaConsumer(raw_consumer_settings)
        try:
            errors: list = []
            deadline = time.monotonic() + 15
            while len(errors) < 3 and time.monotonic() < deadline:
                _, batch_errors = raw_consumer.poll(timeout=1.0)
                errors.extend(batch_errors)
            assert len(errors) == 3

            metrics = ProcessorMetrics()
            pipeline, vp, ip = _build_pipeline(
                validated_producer_settings,
                invalid_producer_settings,
                metrics=metrics,
            )
            try:
                result = pipeline.process_batch(errors)
                assert result.published_invalid == 3
                assert result.published_valid == 0
            finally:
                vp.close()
                ip.close()

            snapshot = metrics.snapshot()
            assert snapshot[ProcessorMetric.EVENTS_INVALID.value] == 3
            assert snapshot[ProcessorMetric.EVENTS_PROCESSED.value] == 3
            assert snapshot[ProcessorMetric.EVENTS_VALID.value] == 0
        finally:
            raw_consumer.close()


class TestConsumerLevelDlq:
    """Consumer-level DLQ: deserialization failures route to DLQ."""

    def test_deserialization_failure_routes_to_dlq(
        self,
        broker_address: str,
        raw_producer_settings: KafkaProducerSettings,
        invalid_producer_settings: KafkaProducerSettings,
        invalid_consumer_settings: KafkaConsumerSettings,
    ) -> None:
        """Bad JSON bytes produce a deserialization error routed to DLQ."""
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

        dlq_output = _consume_raw_json(
            broker_address,
            INVALID_TOPIC,
            invalid_consumer_settings.kafka_group_id,
            expected=1,
        )
        assert len(dlq_output) == 1
        dlq_record = dlq_output[0]
        assert dlq_record["payload"]["reason"] == "deserialization_failure"
        assert "raw_value_base64" in dlq_record["payload"]

    def test_dlq_does_not_block_valid_event_processing(
        self,
        broker_address: str,
        raw_producer_settings: KafkaProducerSettings,
        validated_producer_settings: KafkaProducerSettings,
        invalid_producer_settings: KafkaProducerSettings,
        validated_consumer_settings: KafkaConsumerSettings,
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
        processed_valid_ids: list[str] = []
        try:
            deadline = time.monotonic() + 20
            valid_processed = False
            dlq_processed = False
            while not (valid_processed and dlq_processed) and time.monotonic() < deadline:
                result = consumer.process_next(
                    process=lambda msg: processed_valid_ids.append(msg.event.event_id),
                    dead_letter=dlq_producer.publish,
                    timeout=2.0,
                )
                if result and processed_valid_ids:
                    valid_processed = True
                if result and not processed_valid_ids:
                    dlq_processed = True
        finally:
            dlq_producer.close()
            consumer.close()

        assert len(processed_valid_ids) >= 1
        assert valid_event.event_id in processed_valid_ids
