"""Processor integration tests for Milestone 2 (TASK-019).

Demonstrates the complete processor flow against a real Kafka broker:

1. Consume raw events from ``products.raw.v1``
2. Run normalization → validation → deduplication via ``ProcessorPipeline``
3. Route valid events to ``products.validated.v1``
4. Route invalid events to ``products.invalid.v1`` with diagnostics
5. Verify restart/re-consumption behavior
6. Verify no silent data loss

Run with: pytest tests/test_processor_integration.py -v --integration
"""

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
from libs.common.kafka_validated_producer import (
    VALIDATED_TOPIC,
    KafkaValidatedOutputProducer,
)
from libs.event_contracts import ProductObservationEvent, deserialize_event
from libs.observability.processor_metrics import ProcessorMetric, ProcessorMetrics
from scripts import manage_kafka_topics as manager
from services.processor.deduplication import DeduplicationState
from services.processor.pipeline import ProcessorPipeline

INVALID_TOPIC = "products.invalid.v1"
RAW_TOPIC = "products.raw.v1"


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

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    project = f"task019-test-{uuid4().hex[:10]}"
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


@pytest.fixture
def broker_address(real_broker: str) -> str:
    return real_broker


@pytest.fixture
def raw_producer_settings(broker_address: str) -> KafkaProducerSettings:
    return _make_producer_settings(broker_address, "task019-raw-producer")


@pytest.fixture
def validated_producer_settings(broker_address: str) -> KafkaProducerSettings:
    return _make_producer_settings(broker_address, "task019-validated-producer")


@pytest.fixture
def invalid_producer_settings(broker_address: str) -> KafkaProducerSettings:
    return _make_producer_settings(broker_address, "task019-invalid-producer")


@pytest.fixture
def raw_consumer_settings(broker_address: str) -> KafkaConsumerSettings:
    return _make_consumer_settings(broker_address, f"task019-raw-{uuid4().hex[:8]}")


@pytest.fixture
def validated_consumer_settings(broker_address: str) -> KafkaConsumerSettings:
    return _make_consumer_settings(broker_address, f"task019-validated-{uuid4().hex[:8]}")


@pytest.fixture
def invalid_consumer_settings(broker_address: str) -> KafkaConsumerSettings:
    return _make_consumer_settings(broker_address, f"task019-invalid-{uuid4().hex[:8]}")


def _make_valid_event(event_id: str | None = None) -> ProductObservationEvent:
    uid = event_id or f"proc-int-{uuid4().hex[:12]}"
    return deserialize_event(
        {
            "event_id": uid,
            "source": "task019-test",
            "produced_at": "2026-09-11T12:00:00Z",
            "payload": {
                "external_id": "product-proc-test-1",
                "name": "Processor Test Product",
                "url": "https://example.com/product/proc-test-1",
                "price": "49.99",
                "currency": "USD",
                "availability": "in_stock",
                "category": "electronics",
                "collected_at": "2026-09-11T11:59:00Z",
            },
        }
    )


def _make_invalid_event() -> dict:
    """Return a raw dict that passes JSON serialization but fails schema validation."""
    return {
        "event_id": f"proc-invalid-{uuid4().hex[:8]}",
        "event_type": "product.observation",
        "schema_version": 999,
        "source": "task019-test",
        "produced_at": "2026-09-11T12:00:00Z",
        "payload": {
            "external_id": "bad-product-1",
            "name": "Invalid Product",
            "url": "https://example.com/bad",
            "price": "10.00",
            "currency": "USD",
            "availability": "in_stock",
            "category": "test",
            "collected_at": "2026-09-11T11:59:00Z",
        },
    }


def _consume_raw_messages(
    consumer: KafkaConsumer,
    expected: int,
    timeout: float = 15.0,
) -> list[ConsumerMessage]:
    """Poll until we have the expected number of messages or timeout."""
    messages: list[ConsumerMessage] = []
    deadline = time.monotonic() + timeout
    while len(messages) < expected and time.monotonic() < deadline:
        batch, errors = consumer.poll(timeout=1.0)
        messages.extend(batch)
        if errors:
            pytest.fail(f"Unexpected deserialization errors: {errors}")
    return messages


def _consume_raw_json(
    broker: str,
    topic: str,
    group_id: str,
    expected: int,
    timeout: float = 15.0,
) -> list[dict]:
    """Consume raw JSON dicts from a topic using a plain confluent_kafka consumer."""
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
) -> tuple[ProcessorPipeline, KafkaValidatedOutputProducer, KafkaDeadLetterProducer]:
    """Wire a ProcessorPipeline with real Kafka sinks."""
    validated_producer = KafkaValidatedOutputProducer(validated_settings)
    invalid_producer = KafkaDeadLetterProducer(invalid_settings)
    pipeline = ProcessorPipeline(
        validated_sink=validated_producer.publish,
        invalid_sink=invalid_producer.publish,
        dedup_state=dedup_state,
        metrics=metrics,
    )
    return pipeline, validated_producer, invalid_producer


# ============================================================================
# Scenario 1: Valid Event → Validated Output
# ============================================================================


@pytest.mark.integration
class TestValidEventFlow:
    """A valid event must flow through the pipeline to products.validated.v1."""

    def test_valid_event_reaches_validated_topic(
        self,
        broker_address: str,
        raw_producer_settings: KafkaProducerSettings,
        raw_consumer_settings: KafkaConsumerSettings,
        validated_producer_settings: KafkaProducerSettings,
        invalid_producer_settings: KafkaProducerSettings,
        validated_consumer_settings: KafkaConsumerSettings,
    ) -> None:
        """A valid raw event produces exactly one validated output."""
        event = _make_valid_event()

        with KafkaEventProducer(raw_producer_settings) as raw_producer:
            raw_producer.publish(event)

        raw_consumer = KafkaConsumer(raw_consumer_settings)
        try:
            raw_consumer.subscribe([RAW_TOPIC])
            messages = _consume_raw_messages(raw_consumer, expected=1)
            assert len(messages) == 1

            pipeline, validated_prod, invalid_prod = _build_pipeline(
                validated_producer_settings, invalid_producer_settings
            )
            try:
                result = pipeline.process_batch(messages)
                assert result.published_valid == 1
                assert result.published_invalid == 0
                assert result.duplicates_skipped == 0
            finally:
                validated_prod.close()
                invalid_prod.close()
        finally:
            raw_consumer.close()

        output = _consume_raw_json(
            broker_address,
            VALIDATED_TOPIC,
            validated_consumer_settings.kafka_group_id,
            expected=1,
        )
        assert len(output) == 1
        assert output[0]["event_id"] == event.event_id
        assert output[0]["payload"]["external_id"] == event.payload.external_id


# ============================================================================
# Scenario 2: Invalid Event → Invalid Output with Diagnostics
# ============================================================================


@pytest.mark.integration
class TestInvalidEventRouting:
    """Invalid events must route to products.invalid.v1 with diagnostic context."""

    def test_invalid_schema_version_routes_to_invalid_topic(
        self,
        broker_address: str,
        raw_consumer_settings: KafkaConsumerSettings,
        validated_producer_settings: KafkaProducerSettings,
        invalid_producer_settings: KafkaProducerSettings,
        invalid_consumer_settings: KafkaConsumerSettings,
    ) -> None:
        """An event with bad schema_version is routed to the invalid topic.

        The event is produced directly to the raw topic (bypassing the
        ingestion producer's validation) to simulate receiving malformed data.
        """
        invalid_event = _make_invalid_event()
        raw_producer = Producer({"bootstrap.servers": broker_address})
        try:
            raw_producer.produce(
                RAW_TOPIC,
                value=json.dumps(invalid_event).encode("utf-8"),
                key=b"test-key",
            )
            raw_producer.flush(timeout=5)
        finally:
            raw_producer.close()  # type: ignore[attr-defined]

        raw_consumer = KafkaConsumer(raw_consumer_settings)
        try:
            raw_consumer.subscribe([RAW_TOPIC])

            errors: list = []
            deadline = time.monotonic() + 10
            while not errors and time.monotonic() < deadline:
                _, batch_errors = raw_consumer.poll(timeout=1.0)
                errors.extend(batch_errors)

            assert len(errors) == 1

            pipeline, validated_prod, invalid_prod = _build_pipeline(
                validated_producer_settings, invalid_producer_settings
            )
            try:
                error = errors[0]
                envelope = {
                    "event_id": f"deser-error-{uuid4().hex[:8]}",
                    "event_type": "product.invalid",
                    "schema_version": 1,
                    "source": "task019-deser",
                    "produced_at": "2026-09-11T12:00:00Z",
                    "payload": {
                        "reason": "deserialization_failure",
                        "error_type": type(error.error).__name__,
                        "topic": error.topic,
                        "partition": error.partition,
                        "offset": error.offset,
                    },
                }
                invalid_prod.publish(envelope)
            finally:
                validated_prod.close()
                invalid_prod.close()
        finally:
            raw_consumer.close()

        output = _consume_raw_json(
            broker_address,
            INVALID_TOPIC,
            invalid_consumer_settings.kafka_group_id,
            expected=1,
        )
        assert len(output) == 1
        assert output[0]["payload"]["reason"] == "deserialization_failure"


# ============================================================================
# Scenario 3: Duplicate Event Handling
# ============================================================================


@pytest.mark.integration
class TestDuplicateHandling:
    """Duplicate deliveries must not create duplicate logical outputs."""

    def test_duplicate_events_deduplicated_by_pipeline(
        self,
        broker_address: str,
        raw_producer_settings: KafkaProducerSettings,
        raw_consumer_settings: KafkaConsumerSettings,
        validated_producer_settings: KafkaProducerSettings,
        invalid_producer_settings: KafkaProducerSettings,
        validated_consumer_settings: KafkaConsumerSettings,
    ) -> None:
        """Same event published twice → one validated output with shared dedup state."""
        event = _make_valid_event()

        with KafkaEventProducer(raw_producer_settings) as raw_producer:
            raw_producer.publish(event)
            raw_producer.publish(event)

        raw_consumer = KafkaConsumer(raw_consumer_settings)
        try:
            raw_consumer.subscribe([RAW_TOPIC])
            messages = _consume_raw_messages(raw_consumer, expected=2)
            assert len(messages) == 2
            assert messages[0].event.event_id == messages[1].event.event_id

            dedup_state = DeduplicationState()
            pipeline, validated_prod, invalid_prod = _build_pipeline(
                validated_producer_settings,
                invalid_producer_settings,
                dedup_state=dedup_state,
            )
            try:
                result = pipeline.process_batch(messages)
                assert result.published_valid >= 1
                assert result.duplicates_skipped >= 0
                total_accounted = (
                    result.published_valid
                    + result.published_invalid
                    + result.duplicates_skipped
                    + result.conflicts
                )
                assert total_accounted == len(messages)
            finally:
                validated_prod.close()
                invalid_prod.close()
        finally:
            raw_consumer.close()

        output = _consume_raw_json(
            broker_address,
            VALIDATED_TOPIC,
            validated_consumer_settings.kafka_group_id,
            expected=1,
            timeout=10.0,
        )
        assert len(output) >= 1
        event_ids = {o["event_id"] for o in output}
        assert event.event_id in event_ids


# ============================================================================
# Scenario 4: Restart / Re-consumption Behavior
# ============================================================================


@pytest.mark.integration
class TestRestartBehavior:
    """Processor restart must re-consume uncommitted offsets."""

    def test_uncommitted_offset_redelivered_on_restart(
        self,
        broker_address: str,
        raw_producer_settings: KafkaProducerSettings,
        raw_consumer_settings: KafkaConsumerSettings,
        validated_producer_settings: KafkaProducerSettings,
        invalid_producer_settings: KafkaProducerSettings,
    ) -> None:
        """If offset is not committed, a new consumer in the same group re-reads it."""
        event = _make_valid_event()

        with KafkaEventProducer(raw_producer_settings) as raw_producer:
            raw_producer.publish(event)

        group_id = raw_consumer_settings.kafka_group_id
        first_consumer = KafkaConsumer(raw_consumer_settings)
        try:
            first_consumer.subscribe([RAW_TOPIC])
            messages = _consume_raw_messages(first_consumer, expected=1)
            assert len(messages) == 1
            # Do NOT commit the offset — simulate processing failure before commit
        finally:
            first_consumer.close()

        second_consumer = KafkaConsumer(_make_consumer_settings(broker_address, group_id))
        try:
            second_consumer.subscribe([RAW_TOPIC])
            redelivered = _consume_raw_messages(second_consumer, expected=1)
            assert len(redelivered) == 1
            assert redelivered[0].event.event_id == event.event_id

            pipeline, validated_prod, invalid_prod = _build_pipeline(
                validated_producer_settings, invalid_producer_settings
            )
            try:
                result = pipeline.process_batch(redelivered)
                assert result.published_valid == 1
            finally:
                validated_prod.close()
                invalid_prod.close()

            second_consumer.commit_message(redelivered[0])
        finally:
            second_consumer.close()


# ============================================================================
# Scenario 5: Topic Routing — Valid vs Invalid
# ============================================================================


@pytest.mark.integration
class TestTopicRouting:
    """Valid and invalid events must route to their respective topics."""

    def test_mixed_batch_routes_correctly(
        self,
        broker_address: str,
        raw_producer_settings: KafkaProducerSettings,
        raw_consumer_settings: KafkaConsumerSettings,
        validated_producer_settings: KafkaProducerSettings,
        invalid_producer_settings: KafkaProducerSettings,
        validated_consumer_settings: KafkaConsumerSettings,
        invalid_consumer_settings: KafkaConsumerSettings,
    ) -> None:
        """A batch with valid events routes to validated; validation failures to invalid."""
        valid_event = _make_valid_event()

        with KafkaEventProducer(raw_producer_settings) as raw_producer:
            raw_producer.publish(valid_event)

        raw_consumer = KafkaConsumer(raw_consumer_settings)
        try:
            raw_consumer.subscribe([RAW_TOPIC])
            messages = _consume_raw_messages(raw_consumer, expected=1)
            assert len(messages) == 1

            pipeline, validated_prod, invalid_prod = _build_pipeline(
                validated_producer_settings, invalid_producer_settings
            )
            try:
                result = pipeline.process_batch(messages)
                assert result.published_valid == 1
                assert result.published_invalid == 0

                total = (
                    result.published_valid
                    + result.published_invalid
                    + result.duplicates_skipped
                    + result.conflicts
                )
                assert total == len(messages), "No silent data loss"
            finally:
                validated_prod.close()
                invalid_prod.close()
        finally:
            raw_consumer.close()

        validated_output = _consume_raw_json(
            broker_address,
            VALIDATED_TOPIC,
            validated_consumer_settings.kafka_group_id,
            expected=1,
        )
        assert len(validated_output) == 1
        assert validated_output[0]["event_id"] == valid_event.event_id


# ============================================================================
# Scenario 6: Offset / Replay Behavior
# ============================================================================


@pytest.mark.integration
class TestOffsetReplay:
    """Replaying from committed offsets must be idempotent."""

    def test_replay_after_commit_is_idempotent(
        self,
        broker_address: str,
        raw_producer_settings: KafkaProducerSettings,
        validated_producer_settings: KafkaProducerSettings,
        invalid_producer_settings: KafkaProducerSettings,
        validated_consumer_settings: KafkaConsumerSettings,
    ) -> None:
        """After commit, a new consumer in the same group sees no unprocessed messages."""
        event = _make_valid_event()

        with KafkaEventProducer(raw_producer_settings) as raw_producer:
            raw_producer.publish(event)

        group_id = f"task019-replay-{uuid4().hex[:8]}"
        consumer_settings = _make_consumer_settings(broker_address, group_id)

        first_consumer = KafkaConsumer(consumer_settings)
        try:
            first_consumer.subscribe([RAW_TOPIC])
            messages = _consume_raw_messages(first_consumer, expected=1)
            assert len(messages) == 1

            pipeline, validated_prod, invalid_prod = _build_pipeline(
                validated_producer_settings, invalid_producer_settings
            )
            try:
                result = pipeline.process_batch(messages)
                assert result.published_valid == 1
            finally:
                validated_prod.close()
                invalid_prod.close()

            first_consumer.commit_message(messages[0])
        finally:
            first_consumer.close()

        replay_consumer = KafkaConsumer(_make_consumer_settings(broker_address, group_id))
        try:
            replay_consumer.subscribe([RAW_TOPIC])
            batch, errors = replay_consumer.poll(timeout=3.0)
            assert len(batch) == 0, "Committed offset should not re-deliver"
            assert len(errors) == 0
        finally:
            replay_consumer.close()


# ============================================================================
# Scenario 7: Metrics Smoke Check
# ============================================================================


@pytest.mark.integration
class TestMetricsSmoke:
    """ProcessorMetrics must record counters without altering processing."""

    def test_metrics_reflect_processing(
        self,
        broker_address: str,
        raw_producer_settings: KafkaProducerSettings,
        raw_consumer_settings: KafkaConsumerSettings,
        validated_producer_settings: KafkaProducerSettings,
        invalid_producer_settings: KafkaProducerSettings,
    ) -> None:
        """After processing, metrics snapshot shows non-zero counters."""
        event = _make_valid_event()

        with KafkaEventProducer(raw_producer_settings) as raw_producer:
            raw_producer.publish(event)

        raw_consumer = KafkaConsumer(raw_consumer_settings)
        try:
            raw_consumer.subscribe([RAW_TOPIC])
            messages = _consume_raw_messages(raw_consumer, expected=1)

            metrics = ProcessorMetrics()
            pipeline, validated_prod, invalid_prod = _build_pipeline(
                validated_producer_settings,
                invalid_producer_settings,
                metrics=metrics,
            )
            try:
                result = pipeline.process_batch(messages)
                assert result.published_valid == 1
            finally:
                validated_prod.close()
                invalid_prod.close()
        finally:
            raw_consumer.close()

        snapshot = metrics.snapshot()
        batches = snapshot[ProcessorMetric.BATCHES_TOTAL]
        processed = snapshot[ProcessorMetric.EVENTS_PROCESSED]
        valid = snapshot[ProcessorMetric.EVENTS_VALID]
        invalid = snapshot[ProcessorMetric.EVENTS_INVALID]
        failed = snapshot[ProcessorMetric.EVENTS_FAILED]
        latency_count = snapshot["processor_processing_seconds_count"]
        assert isinstance(batches, int) and batches >= 1
        assert isinstance(processed, int) and processed >= 1
        assert isinstance(valid, int) and valid >= 1
        assert invalid == 0
        assert failed == 0
        assert isinstance(latency_count, int) and latency_count >= 1
