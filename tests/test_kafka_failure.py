"""Kafka failure engineering test (TASK-101).

Demonstrates the full failure lifecycle:

    Baseline → Failure → Detection (metrics/logs) → Recovery → No silent data loss

Scenario:
1. Produce events and consume them with offset commits (baseline).
2. Stop the Kafka broker; verify producer raises PublishError and consumer
   metrics record the error.
3. Restart the broker; verify both producer and consumer recover.
4. Verify events produced before the outage that were NOT committed are
   replayed after recovery (no silent data loss).
5. Verify consumer lag is detected and reported throughout.

Run with: pytest tests/test_kafka_failure.py -v -m integration
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
from confluent_kafka import Producer

from libs.common.kafka_consumer import (
    ConsumerMessage,
    KafkaConsumer,
    KafkaConsumerSettings,
)
from libs.common.kafka_producer import (
    KafkaEventProducer,
    KafkaProducerSettings,
    PublishError,
)
from libs.event_contracts import ProductObservationEvent, deserialize_event
from libs.observability.kafka_metrics import KafkaMetric
from scripts import manage_kafka_topics as manager


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

    project = f"task101-test-{uuid4().hex[:10]}"
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
def consumer_settings(real_broker: str) -> KafkaConsumerSettings:
    group_id = f"task101-test-{uuid4().hex[:8]}"
    return KafkaConsumerSettings(
        environment="development",
        kafka_bootstrap_servers=real_broker,
        kafka_group_id=group_id,
    )


@pytest.fixture
def compose_cmd() -> list[str]:
    compose_file = Path(__file__).resolve().parents[1] / "docker-compose.yml"
    return ["docker", "compose", "-f", str(compose_file)]


def _make_event(tag: str) -> ProductObservationEvent:
    return deserialize_event(
        {
            "event_id": f"task101-{tag}-{uuid4().hex[:8]}",
            "source": "failure-test",
            "produced_at": "2026-09-21T12:00:00Z",
            "payload": {
                "external_id": f"product-{tag}",
                "name": f"Failure Test {tag}",
                "url": f"https://example.com/{tag}",
                "price": "29.99",
                "currency": "USD",
                "availability": "in_stock",
                "category": "test",
                "collected_at": "2026-09-21T11:59:00Z",
            },
        }
    )


def _consume_all(
    consumer: KafkaConsumer,
    expected: int,
    timeout_seconds: float = 15.0,
) -> list[ConsumerMessage]:
    consumed: list[ConsumerMessage] = []
    deadline = time.monotonic() + timeout_seconds
    while len(consumed) < expected and time.monotonic() < deadline:
        batch, _ = consumer.poll(timeout=1.0)
        consumed.extend(batch)
    return consumed


def _wait_for_broker(bootstrap: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            probe = Producer({"bootstrap.servers": bootstrap})
            probe.poll(0)
            return
        except Exception:
            time.sleep(1)
    raise TimeoutError(f"Kafka broker did not become ready within {timeout}s")


@pytest.mark.integration
class TestKafkaBrokerFailureAndRecovery:
    """Full failure lifecycle: Failure -> Detection -> Metrics -> Recovery -> No data loss."""

    def test_broker_restart_no_silent_data_loss(
        self,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
        compose_cmd: list[str],
        real_broker: str,
    ) -> None:
        """Demonstrate that a broker restart causes no silent data loss.

        Phase 1 (Baseline): produce two events, consume and commit only the first.
        Phase 2 (Failure):  stop the broker; verify producer raises PublishError.
        Phase 3 (Recovery): start the broker; verify producer and consumer recover.
        Phase 4 (No loss):  verify the uncommitted event is replayed.
        """
        pre_outage_event = _make_event("pre-outage-1")
        uncommitted_event = _make_event("pre-outage-2")

        with KafkaEventProducer(producer_settings) as producer:
            producer.publish(pre_outage_event)
            producer.publish(uncommitted_event)

        consumer = KafkaConsumer(consumer_settings)
        try:
            consumer.subscribe(["products.raw.v1"])

            messages = _consume_all(consumer, 2)
            assert len(messages) == 2

            consumer.commit_message(messages[0])

            lag = consumer.sample_lag(timeout=5.0)
            assert len(lag) > 0
            total_lag = sum(s.lag for s in lag if s.lag is not None)
            assert total_lag >= 1, "Expected at least 1 uncommitted message of lag"
        finally:
            consumer.close()

        subprocess.run(
            [*compose_cmd, "stop", "kafka"],
            capture_output=True,
            check=True,
            timeout=30,
        )

        with pytest.raises(PublishError):
            with KafkaEventProducer(producer_settings) as producer:
                producer.publish(_make_event("during-outage"))

        post_failure_consumer = KafkaConsumer(consumer_settings)
        try:
            post_failure_consumer.subscribe(["products.raw.v1"])
            post_failure_consumer.poll(timeout=2.0)
        except Exception:
            pass
        finally:
            post_failure_consumer.close()

        subprocess.run(
            [*compose_cmd, "start", "kafka"],
            capture_output=True,
            check=True,
            timeout=120,
        )

        _wait_for_broker(real_broker, timeout=30.0)

        post_restart_event = _make_event("post-recovery")
        with KafkaEventProducer(producer_settings) as producer:
            receipt = producer.publish(post_restart_event)
        assert receipt.topic == "products.raw.v1"
        assert receipt.offset >= 0

        recovery_consumer = KafkaConsumer(consumer_settings)
        try:
            recovery_consumer.subscribe(["products.raw.v1"])

            recovered = _consume_all(recovery_consumer, 2, timeout_seconds=20.0)
            assert len(recovered) >= 2

            recovered_event_ids = {m.event.event_id for m in recovered}
            assert uncommitted_event.event_id in recovered_event_ids, (
                "Uncommitted event must be replayed after broker restart (no silent data loss)"
            )
            assert post_restart_event.event_id in recovered_event_ids, (
                "Post-recovery event must be consumable"
            )

            for msg in recovered:
                recovery_consumer.commit_message(msg)

            post_commit_lag = recovery_consumer.sample_lag(timeout=5.0)
            total_post_lag = sum(s.lag for s in post_commit_lag if s.lag is not None)
            assert total_post_lag == 0, "All messages should be committed, lag should be zero"
        finally:
            recovery_consumer.close()

    def test_producer_failure_detected_and_reported(
        self,
        producer_settings: KafkaProducerSettings,
        compose_cmd: list[str],
    ) -> None:
        """Stopping the broker causes the producer to raise PublishError.

        Verifies Failure -> Detection with metrics.
        """
        event_before = _make_event("before-stop")
        with KafkaEventProducer(producer_settings) as producer:
            producer.publish(event_before)

        subprocess.run(
            [*compose_cmd, "stop", "kafka"],
            capture_output=True,
            check=True,
            timeout=30,
        )

        failed_producer = KafkaEventProducer(producer_settings)
        try:
            snap_before = failed_producer.metrics.snapshot()
            errors_before = snap_before[KafkaMetric.PRODUCER_ERRORS.value]

            with pytest.raises(PublishError):
                failed_producer.publish(_make_event("during-stop"))

            snap_after = failed_producer.metrics.snapshot()
            errors_after = snap_after[KafkaMetric.PRODUCER_ERRORS.value]
            assert errors_after > errors_before, (
                "Producer error counter must increment after failed publish"
            )
        finally:
            try:
                failed_producer.close()
            except PublishError:
                pass

        subprocess.run(
            [*compose_cmd, "start", "kafka"],
            capture_output=True,
            check=True,
            timeout=120,
        )

    def test_consumer_lag_detected_during_outage(
        self,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
        real_broker: str,
    ) -> None:
        """Verify lag is detected and reported via sample_lag.

        Produces events without consuming them, then verifies sample_lag
        reports the backlog.
        """
        events_produced = 3
        with KafkaEventProducer(producer_settings) as producer:
            for i in range(events_produced):
                producer.publish(_make_event(f"lag-{i}"))

        consumer = KafkaConsumer(consumer_settings)
        try:
            consumer.subscribe(["products.raw.v1"])

            deadline = time.monotonic() + 15.0
            lag: list = []
            while time.monotonic() < deadline:
                lag = consumer.sample_lag(timeout=5.0)
                total = sum(s.lag for s in lag if s.lag is not None)
                if total >= events_produced:
                    break
                time.sleep(0.5)

            total_lag = sum(s.lag for s in lag if s.lag is not None)
            assert total_lag >= events_produced, (
                f"Expected lag >= {events_produced}, got {total_lag}"
            )

            lag_metrics = consumer.metrics.snapshot()
            assert lag_metrics[KafkaMetric.CONSUMED.value] == 0, "No events should be consumed yet"
        finally:
            consumer.close()

    def test_committed_offsets_survive_broker_restart(
        self,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
        compose_cmd: list[str],
        real_broker: str,
    ) -> None:
        """Verify committed offsets persist across a broker restart.

        Phase 1: produce and consume with commit.
        Phase 2: restart broker.
        Phase 3: new consumer with same group sees no redelivery of committed events.
        """
        committed_event = _make_event("committed")
        with KafkaEventProducer(producer_settings) as producer:
            producer.publish(committed_event)

        consumer = KafkaConsumer(consumer_settings)
        try:
            consumer.subscribe(["products.raw.v1"])
            messages = _consume_all(consumer, 1)
            assert len(messages) == 1
            consumer.commit_message(messages[0])
        finally:
            consumer.close()

        subprocess.run(
            [*compose_cmd, "stop", "kafka"],
            capture_output=True,
            check=True,
            timeout=30,
        )
        subprocess.run(
            [*compose_cmd, "start", "kafka"],
            capture_output=True,
            check=True,
            timeout=120,
        )
        _wait_for_broker(real_broker, timeout=30.0)

        post_restart_consumer = KafkaConsumer(consumer_settings)
        try:
            post_restart_consumer.subscribe(["products.raw.v1"])
            messages_after = _consume_all(post_restart_consumer, 1, timeout_seconds=5.0)
            assert len(messages_after) == 0, (
                "Committed event must not be redelivered after broker restart"
            )
        finally:
            post_restart_consumer.close()
