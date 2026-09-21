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

_SAME_KEY_EXTERNAL_ID = "lag-same-product"


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
def fast_producer_settings(real_broker: str) -> KafkaProducerSettings:
    return KafkaProducerSettings(
        environment="development",
        kafka_bootstrap_servers=real_broker,
        kafka_raw_topic="products.raw.v1",
        kafka_delivery_timeout_ms=1000,
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


def _make_event(tag: str, external_id: str | None = None) -> ProductObservationEvent:
    return deserialize_event(
        {
            "event_id": f"task101-{tag}-{uuid4().hex[:8]}",
            "source": "failure-test",
            "produced_at": "2026-09-21T12:00:00Z",
            "payload": {
                "external_id": external_id or f"product-{tag}",
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


def _wait_for_broker(bootstrap: str, timeout: float = 60.0) -> None:
    from confluent_kafka.admin import AdminClient

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            admin = AdminClient({"bootstrap.servers": bootstrap})
            admin.list_topics(timeout=5)
            return
        except Exception:
            time.sleep(2)
    raise TimeoutError(f"Kafka broker did not become ready within {timeout}s")


@pytest.mark.integration
class TestKafkaBrokerFailureAndRecovery:
    """Full failure lifecycle: Failure -> Detection -> Metrics -> Recovery -> No data loss."""

    def test_broker_restart_no_silent_data_loss(
        self,
        producer_settings: KafkaProducerSettings,
        fast_producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
        compose_cmd: list[str],
        real_broker: str,
    ) -> None:
        """Demonstrate that a broker restart causes no silent data loss.

        Phase 1 (Baseline): produce two events with the same partition key,
            consume both, commit only the first.
        Phase 2 (Failure):  stop the broker; verify producer raises PublishError
            and consumer error metrics increment.
        Phase 3 (Recovery): start the broker; verify producer and consumer recover.
        Phase 4 (No loss):  verify the uncommitted event is replayed.
        """
        pre_outage_event = _make_event("pre-outage-1", _SAME_KEY_EXTERNAL_ID)
        uncommitted_event = _make_event("pre-outage-2", _SAME_KEY_EXTERNAL_ID)

        with KafkaEventProducer(producer_settings) as producer:
            producer.publish(pre_outage_event)
            producer.publish(uncommitted_event)

        consumer = KafkaConsumer(consumer_settings)
        try:
            consumer.subscribe(["products.raw.v1"])

            messages = _consume_all(consumer, 2)
            assert len(messages) == 2

            consumer.commit_message(messages[0])
        finally:
            consumer.close()

        subprocess.run(
            [*compose_cmd, "stop", "kafka"],
            capture_output=True,
            check=True,
            timeout=30,
        )

        with pytest.raises(PublishError):
            with KafkaEventProducer(fast_producer_settings) as producer:
                producer.publish(_make_event("during-outage"))

        outage_consumer = KafkaConsumer(consumer_settings)
        try:
            outage_consumer.subscribe(["products.raw.v1"])
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                try:
                    outage_consumer.poll(timeout=2.0)
                except Exception:
                    pass
                if outage_consumer.metrics.snapshot()[KafkaMetric.CONSUMER_ERRORS.value] > 0:
                    break
            errors_during_outage = outage_consumer.metrics.snapshot()[
                KafkaMetric.CONSUMER_ERRORS.value
            ]
        finally:
            outage_consumer.close()

        assert errors_during_outage > 0, (
            "Consumer error counter must increment during broker outage"
        )

        subprocess.run(
            [*compose_cmd, "start", "kafka"],
            capture_output=True,
            check=True,
            timeout=120,
        )

        _wait_for_broker(real_broker, timeout=60.0)

        post_restart_event = _make_event("post-recovery", _SAME_KEY_EXTERNAL_ID)
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
        finally:
            recovery_consumer.close()

    def test_producer_failure_detected_and_reported(
        self,
        fast_producer_settings: KafkaProducerSettings,
        compose_cmd: list[str],
    ) -> None:
        """Stopping the broker causes the producer to raise PublishError.

        Verifies Failure -> Detection with metrics.
        """
        event_before = _make_event("before-stop")
        with KafkaEventProducer(fast_producer_settings) as producer:
            producer.publish(event_before)

        subprocess.run(
            [*compose_cmd, "stop", "kafka"],
            capture_output=True,
            check=True,
            timeout=30,
        )

        failed_producer = KafkaEventProducer(fast_producer_settings)
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

    def test_consumer_lag_detected_after_partial_commit(
        self,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
    ) -> None:
        """Verify lag is detected and reported via sample_lag.

        Produces events with the same partition key, consumes and commits
        only the first, then verifies sample_lag reports the remaining
        backlog on that partition.
        """
        events_produced = 3
        with KafkaEventProducer(producer_settings) as producer:
            for i in range(events_produced):
                producer.publish(
                    _make_event(f"lag-{i}", _SAME_KEY_EXTERNAL_ID),
                )

        consumer = KafkaConsumer(consumer_settings)
        try:
            consumer.subscribe(["products.raw.v1"])

            messages = _consume_all(consumer, events_produced)
            assert len(messages) == events_produced

            consumer.commit_message(messages[0])

            deadline = time.monotonic() + 15.0
            lag: list = []
            while time.monotonic() < deadline:
                lag = consumer.sample_lag(timeout=5.0)
                committed_lag = [s for s in lag if s.lag is not None and s.lag > 0]
                if committed_lag:
                    break
                time.sleep(0.5)

            committed_lag = [s for s in lag if s.lag is not None and s.lag > 0]
            assert len(committed_lag) > 0, (
                "Expected lag > 0 on at least one partition after partial commit"
            )
            total_lag = sum(s.lag for s in committed_lag if s.lag is not None)
            assert total_lag >= events_produced - 1, (
                f"Expected lag >= {events_produced - 1}, got {total_lag}"
            )
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
        _wait_for_broker(real_broker, timeout=60.0)

        post_restart_consumer = KafkaConsumer(consumer_settings)
        try:
            post_restart_consumer.subscribe(["products.raw.v1"])
            messages_after = _consume_all(post_restart_consumer, 1, timeout_seconds=5.0)
            assert len(messages_after) == 0, (
                "Committed event must not be redelivered after broker restart"
            )
        finally:
            post_restart_consumer.close()
