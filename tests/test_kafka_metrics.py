"""Operational counter boundaries and committed-offset lag (TASK-011)."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from confluent_kafka import KafkaError, KafkaException, TopicPartition
from test_kafka_consumer import _make_valid_event
from test_kafka_errors import client, consumer  # noqa: F401
from test_kafka_producer import real_broker  # noqa: F401

from libs.common.kafka_consumer import (
    ConsumerLag,
    ConsumerMessage,
    KafkaConsumer,
    KafkaConsumerSettings,
)
from libs.common.kafka_errors import RetryPolicy, TransientProcessingError
from libs.common.kafka_producer import (
    EventSerializationError,
    KafkaEventProducer,
    KafkaProducerSettings,
    PublishError,
)
from libs.observability.kafka_metrics import KafkaMetric, KafkaMetrics


def test_snapshot_is_detached_thread_safe_and_instance_local() -> None:
    metrics = KafkaMetrics()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: metrics.increment(KafkaMetric.CONSUMED), range(1000)))
    snapshot = metrics.snapshot()
    assert snapshot[KafkaMetric.CONSUMED] == 1000
    snapshot[KafkaMetric.CONSUMED] = 0
    assert metrics.snapshot()[KafkaMetric.CONSUMED] == 1000
    assert all(value == 0 for value in KafkaMetrics().snapshot().values())


@pytest.mark.parametrize("mode", ["success", "queue", "failed", "missing", "metadata", "invalid"])
def test_producer_metrics(mode: str) -> None:
    event = _make_valid_event()
    with patch("libs.common.kafka_producer.Producer") as factory:
        raw = factory.return_value

        def flush(timeout: float) -> int:
            message = MagicMock()
            message.topic.return_value = "products.raw.v1"
            message.partition.return_value = 0
            message.offset.return_value = None if mode == "metadata" else 0
            if mode != "missing":
                raw.produce.call_args.kwargs["on_delivery"](
                    KafkaError(KafkaError._TRANSPORT) if mode == "failed" else None, message
                )
            return 0

        raw.flush.side_effect = flush
        if mode == "queue":
            raw.produce.side_effect = BufferError("secret-canary")
        if mode == "invalid":
            event.schema_version = 999
        producer = KafkaEventProducer(KafkaProducerSettings(environment="development"))
        if mode == "success":
            producer.publish(event)
            producer.publish(event)
        else:
            with pytest.raises((PublishError, EventSerializationError)):
                producer.publish(event)
        counts = producer.metrics.snapshot()
        assert counts[KafkaMetric.PRODUCED] == (2 if mode == "success" else 0)
        assert counts[KafkaMetric.PRODUCER_ERRORS] == int(mode != "success")
        assert counts[KafkaMetric.INVALID] == int(mode == "invalid")
        assert "secret-canary" not in str(counts)


def test_consumption_retries_and_commits_are_distinct(client: MagicMock) -> None:  # noqa: F811
    with consumer() as c:
        handler = MagicMock(side_effect=[TransientProcessingError("secret-canary"), None])
        c.process_next(handler, MagicMock(), retry=RetryPolicy(backoff_seconds=0))
        counts = c.metrics.snapshot()
        assert counts[KafkaMetric.CONSUMED] == 1
        assert counts[KafkaMetric.PROCESSING_ERRORS] == 1
        assert counts[KafkaMetric.PROCESSED] == 1
        assert counts[KafkaMetric.INVALID] == 0
        assert "secret-canary" not in str(counts)


@pytest.mark.parametrize("value", [b'{"password":"secret-canary"}', b"\xff", None])
def test_invalid_counted_once_and_dlq_not_processed(
    client: MagicMock,  # noqa: F811
    value: bytes | None,
) -> None:
    client.poll.return_value.value.return_value = value
    with consumer() as c:
        c.process_next(MagicMock(), MagicMock())
        counts = c.metrics.snapshot()
        assert counts[KafkaMetric.CONSUMED] == 1
        assert counts[KafkaMetric.INVALID] == 1
        assert counts[KafkaMetric.DEAD_LETTERED] == 1
        assert counts[KafkaMetric.PROCESSED] == 0
        assert "secret-canary" not in str(counts)


def test_failed_commit_not_processed_or_double_counted(client: MagicMock) -> None:  # noqa: F811
    client.commit.side_effect = KafkaException(KafkaError(KafkaError._TRANSPORT))
    with consumer() as c:
        with pytest.raises(KafkaException):
            c.process_next(MagicMock(), MagicMock())
        assert c.metrics.snapshot()[KafkaMetric.CONSUMER_ERRORS] == 1
        assert c.metrics.snapshot()[KafkaMetric.PROCESSED] == 0


@pytest.mark.parametrize("mode", ["idle", "eof", "transport", "exception"])
def test_poll_outcomes(client: MagicMock, mode: str) -> None:  # noqa: F811
    if mode == "idle":
        client.poll.return_value = None
    elif mode == "exception":
        client.poll.side_effect = KafkaException(KafkaError(KafkaError._TRANSPORT))
    else:
        client.poll.return_value.error.return_value = KafkaError(
            KafkaError._PARTITION_EOF if mode == "eof" else KafkaError._TRANSPORT
        )
    with consumer() as c:
        if mode == "exception":
            with pytest.raises(KafkaException):
                c.poll()
        else:
            assert c.poll() == ([], [])
        counts = c.metrics.snapshot()
        assert counts[KafkaMetric.CONSUMED] == 0
        assert counts[KafkaMetric.CONSUMER_ERRORS] == int(mode in {"transport", "exception"})


@pytest.mark.parametrize("offset,expected", [(7, 3), (10, 0), (-1001, None), (11, None), (1, None)])
def test_lag_uses_committed_next_offset(
    client: MagicMock,  # noqa: F811
    offset: int,
    expected: int | None,
) -> None:
    client.assignment.return_value = [TopicPartition("products.raw.v1", 0)]
    client.committed.return_value = [TopicPartition("products.raw.v1", 0, offset)]
    client.get_watermark_offsets.return_value = (2, 10)
    with consumer() as c:
        assert c.sample_lag() == [ConsumerLag("products.raw.v1", 0, expected)]
    assert client.get_watermark_offsets.call_args.kwargs["cached"] is False
    client.poll.assert_not_called()
    client.commit.assert_not_called()


def test_lag_assignment_and_failures_do_not_leave_stale_samples(client: MagicMock) -> None:  # noqa: F811
    client.assignment.return_value = [TopicPartition("products.raw.v1", 0)]
    client.committed.return_value = [TopicPartition("products.raw.v1", 0, 2)]
    client.get_watermark_offsets.return_value = (0, 3)
    with consumer() as c:
        assert c.sample_lag()[0].lag == 1
        client.committed.side_effect = KafkaException(KafkaError(KafkaError._TRANSPORT))
        with pytest.raises(KafkaException):
            c.sample_lag()
        assert c.metrics.snapshot()[KafkaMetric.LAG_ERRORS] == 1
        client.assignment.return_value = []
        assert c.sample_lag() == []
    with pytest.raises(RuntimeError, match="closed"):
        c.sample_lag()


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_lag_requires_bounded_timeout(client: MagicMock, timeout: float) -> None:  # noqa: F811
    with consumer() as c:
        with pytest.raises(ValueError):
            c.sample_lag(timeout)
    client.committed.assert_not_called()


@pytest.mark.integration
def test_real_counters_and_lag_follow_commit(real_broker: str) -> None:  # noqa: F811
    with patch("libs.common.kafka_consumer.signal.signal"):
        with KafkaConsumer(
            KafkaConsumerSettings(
                environment="development",
                kafka_group_id="task011-" + uuid4().hex,
                kafka_bootstrap_servers=real_broker,
            )
        ) as c:
            with KafkaEventProducer(
                KafkaProducerSettings(
                    environment="development", kafka_bootstrap_servers=real_broker
                )
            ) as producer:
                first = producer.publish(_make_valid_event())
                producer.publish(_make_valid_event())
                assert producer.metrics.snapshot()[KafkaMetric.PRODUCED] == 2
            c.subscribe([first.topic])
            deadline = time.monotonic() + 30
            messages: list[ConsumerMessage] = []
            while len(messages) < 2 and time.monotonic() < deadline:
                batch, errors = c.poll(1)
                assert not errors
                messages.extend(batch)
            assert len(messages) == 2
            assert c.metrics.snapshot()[KafkaMetric.CONSUMED] == 2
            assert all(sample.lag is None for sample in c.sample_lag())
            c.commit_message(messages[0])
            samples = {sample.partition: sample.lag for sample in c.sample_lag()}
            assert samples[first.partition] == 1
            c.commit_message(messages[1])
            samples = {sample.partition: sample.lag for sample in c.sample_lag()}
            assert samples[first.partition] == 0
