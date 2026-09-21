"""Processor crash engineering test (TASK-103).

Demonstrates the full failure lifecycle when the processor crashes mid-batch:

    Baseline -> Crash (exception) -> Detection (metric/log) -> Recovery -> No silent data loss

Scenario:
1. Produce events to Kafka with the same partition key (baseline).
2. Start a consumer; process the first event successfully (offset committed).
3. Simulate a crash on the second event (unexpected Exception from process callback).
4. Verify the consumer closes, the offset is NOT committed, PROCESSING_ERRORS
   counter increments, and kafka_processing_stopped is logged (detection).
5. Start a new consumer with the same group; verify the uncommitted event is
   redelivered (at-least-once semantics, no silent data loss).
6. Verify all events are eventually processed after recovery.

Run with: pytest tests/test_processor_crash.py -v -m integration
"""

# mypy: disable-error-code="import-untyped,no-untyped-def,import-not-found,no-any-return"
from __future__ import annotations

import logging
import os
import socket
import subprocess
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from uuid import uuid4

import pytest

from libs.common.kafka_consumer import (
    ConsumerMessage,
    KafkaConsumer,
    KafkaConsumerSettings,
)
from libs.common.kafka_producer import (
    KafkaEventProducer,
    KafkaProducerSettings,
)
from libs.event_contracts import ProductObservationEvent, deserialize_event
from libs.observability.kafka_metrics import KafkaMetric
from scripts import manage_kafka_topics as manager

pytestmark = pytest.mark.integration

_SAME_EXTERNAL_ID = "crash-test-product"


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

    project = f"task103-test-{uuid4().hex[:10]}"
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


@pytest.fixture
def producer_settings(real_broker: str) -> KafkaProducerSettings:
    return KafkaProducerSettings(
        environment="development",
        kafka_bootstrap_servers=real_broker,
        kafka_raw_topic="products.raw.v1",
    )


@pytest.fixture
def group_id() -> str:
    return f"task103-crash-{uuid4().hex[:8]}"


@pytest.fixture
def consumer_settings(real_broker: str, group_id: str) -> KafkaConsumerSettings:
    return KafkaConsumerSettings(
        environment="development",
        kafka_bootstrap_servers=real_broker,
        kafka_group_id=group_id,
    )


def _make_event(tag: str) -> ProductObservationEvent:
    return deserialize_event(
        {
            "event_id": f"task103-{tag}-{uuid4().hex[:8]}",
            "source": "crash-test",
            "produced_at": "2026-09-21T12:00:00Z",
            "payload": {
                "external_id": _SAME_EXTERNAL_ID,
                "name": f"Crash Test {tag}",
                "url": f"https://example.com/{tag}",
                "price": "29.99",
                "currency": "USD",
                "availability": "in_stock",
                "category": "test",
                "collected_at": "2026-09-21T11:59:00Z",
            },
        }
    )


def _process_one(
    consumer: KafkaConsumer,
    callback: Callable[[ConsumerMessage], None],
    dead_letter: Callable[[dict], None],
    timeout_seconds: float = 15.0,
) -> bool:
    """Call process_next in a loop until it processes one message or times out."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = consumer.process_next(
            process=callback,
            dead_letter=dead_letter,
            timeout=2.0,
        )
        if result:
            return True
    return False


def _noop_dead_letter(envelope: dict) -> None:
    pass


class TestProcessorCrashMidBatch:
    """Demonstrates at-least-once semantics when the processor crashes."""

    def test_crash_uncommitted_event_redelivered(
        self,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A crash before commit causes the event to be redelivered on restart.

        Lifecycle:
        1. Produce 3 events (same partition key for deterministic ordering).
        2. Consumer 1: process event 1 (commit), crash on event 2 (no commit).
        3. Consumer 2 (same group): re-consume from last committed offset,
           verify event 2 is redelivered (no silent data loss).
        """
        produced_event_ids: list[str] = []
        with KafkaEventProducer(producer_settings) as producer:
            for tag in ["evt-a", "evt-b", "evt-c"]:
                evt = _make_event(tag)
                produced_event_ids.append(evt.event_id)
                producer.publish(evt)

        processed_event_ids: list[str] = []

        consumer1 = KafkaConsumer(consumer_settings)
        consumer1.subscribe(["products.raw.v1"])

        assert _process_one(
            consumer1,
            callback=lambda msg: processed_event_ids.append(msg.event.event_id),
            dead_letter=_noop_dead_letter,
        ), "Should process first event"

        def crash_on_process(msg: ConsumerMessage) -> None:
            raise RuntimeError("Simulated processor crash")

        with caplog.at_level(logging.ERROR, logger="libs.common.kafka_consumer"):
            with pytest.raises(RuntimeError, match="Simulated processor crash"):
                _process_one(
                    consumer1,
                    callback=crash_on_process,
                    dead_letter=_noop_dead_letter,
                )

        assert consumer1.metrics.snapshot()[KafkaMetric.PROCESSING_ERRORS.value] > 0, (
            "PROCESSING_ERRORS must increment on crash"
        )
        assert any("kafka_processing_stopped" in record.message for record in caplog.records), (
            "kafka_processing_stopped must be logged on crash"
        )

        consumer2 = KafkaConsumer(consumer_settings)
        try:
            consumer2.subscribe(["products.raw.v1"])

            assert _process_one(
                consumer2,
                callback=lambda msg: processed_event_ids.append(msg.event.event_id),
                dead_letter=_noop_dead_letter,
                timeout_seconds=20.0,
            ), "Consumer2 should re-process the uncommitted event"

            assert _process_one(
                consumer2,
                callback=lambda msg: processed_event_ids.append(msg.event.event_id),
                dead_letter=_noop_dead_letter,
                timeout_seconds=10.0,
            ), "Consumer2 should process the third event"
        finally:
            consumer2.close()

        assert processed_event_ids == produced_event_ids, (
            "Exact events must be processed once, in order — no loss, no duplicates"
        )

    def test_successful_processing_commits_offset(
        self,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
    ) -> None:
        """Normal processing commits offsets; a second consumer sees no redelivery."""
        with KafkaEventProducer(producer_settings) as producer:
            for tag in ["normal-1", "normal-2"]:
                producer.publish(_make_event(tag))

        processed: list[str] = []

        consumer1 = KafkaConsumer(consumer_settings)
        try:
            consumer1.subscribe(["products.raw.v1"])

            for _ in range(2):
                assert _process_one(
                    consumer1,
                    callback=lambda msg: processed.append(msg.event.event_id),
                    dead_letter=_noop_dead_letter,
                ), "Should process event successfully"
        finally:
            consumer1.close()

        assert len(processed) == 2

        consumer2 = KafkaConsumer(consumer_settings)
        try:
            consumer2.subscribe(["products.raw.v1"])
            result = consumer2.process_next(
                process=lambda msg: processed.append(msg.event.event_id),
                dead_letter=_noop_dead_letter,
                timeout=5.0,
            )
            assert result is False, "No events should be redelivered after successful commit"
        finally:
            consumer2.close()

    def test_processing_error_metric_on_crash(
        self,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A crash increments PROCESSING_ERRORS and logs kafka_processing_stopped."""
        with KafkaEventProducer(producer_settings) as producer:
            producer.publish(_make_event("metric-check"))

        consumer = KafkaConsumer(consumer_settings)
        consumer.subscribe(["products.raw.v1"])

        def crashing_process(msg: ConsumerMessage) -> None:
            raise RuntimeError("Processor exploded")

        with caplog.at_level(logging.ERROR, logger="libs.common.kafka_consumer"):
            with pytest.raises(RuntimeError, match="Processor exploded"):
                _process_one(
                    consumer,
                    callback=crashing_process,
                    dead_letter=_noop_dead_letter,
                )

        snapshot = consumer.metrics.snapshot()
        assert snapshot[KafkaMetric.PROCESSING_ERRORS.value] >= 1, (
            "PROCESSING_ERRORS must be >= 1 after crash"
        )
        assert snapshot[KafkaMetric.PROCESSED.value] == 0, (
            "PROCESSED must be 0 — the event was never successfully processed"
        )
        assert any("kafka_processing_stopped" in record.message for record in caplog.records), (
            "kafka_processing_stopped must be logged on crash"
        )

        consumer.close()
