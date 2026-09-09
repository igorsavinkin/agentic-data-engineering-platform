"""Failure handling boundaries, including real-broker restart after failure."""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Iterator
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from confluent_kafka import Consumer, KafkaError, KafkaException, Producer, TopicPartition
from pydantic import ValidationError
from test_kafka_consumer import _make_valid_event
from test_kafka_producer import real_broker  # noqa: F401, F811

from libs.common.kafka_consumer import KafkaConsumer, KafkaConsumerSettings, ProcessingError
from libs.common.kafka_errors import KafkaDeadLetterProducer, RetryPolicy, TransientProcessingError
from libs.common.kafka_producer import KafkaProducerSettings, PublishError
from scripts import manage_kafka_topics as manager


@pytest.fixture
def client() -> Iterator[MagicMock]:
    with patch("confluent_kafka.Consumer") as factory:
        client = factory.return_value
        client.commit.return_value = []
        msg = MagicMock()
        msg.error.return_value = None
        msg.topic.return_value = "products.raw.v1"
        msg.partition.return_value = 0
        msg.offset.return_value = 7
        msg.value.return_value = _make_valid_event().model_dump_json().encode()
        client.poll.return_value = msg
        yield client


def consumer() -> KafkaConsumer:
    return KafkaConsumer(
        KafkaConsumerSettings(environment="development", kafka_group_id="processor")
    )


@pytest.mark.parametrize("raw", [b"{broken", b"\xff", None, b'{"schema_version":999}'])
def test_invalid_ack_before_commit(
    client: MagicMock, raw: bytes | None, caplog: pytest.LogCaptureFixture
) -> None:
    client.poll.return_value.value.return_value = raw
    sink = MagicMock()
    sink.side_effect = lambda envelope: client.commit.assert_not_called()
    c = consumer()
    assert c.process_next(MagicMock(), sink)
    payload = sink.call_args.args[0]["payload"]
    assert payload["raw_value_base64"] == (
        base64.b64encode(raw).decode() if raw is not None else None
    )
    assert payload["offset"] == 7
    assert client.commit.call_args.kwargs["offsets"][0].offset == 8
    assert "kafka_dead_letter_delivered" in caplog.text
    c.close()


def test_retry_success(client: MagicMock) -> None:
    handler = MagicMock(side_effect=[TransientProcessingError(), None])
    sink = MagicMock()
    with patch("libs.common.kafka_consumer.time.sleep") as sleep:
        with consumer() as c:
            assert c.process_next(handler, sink)
    assert handler.call_count == 2
    sleep.assert_called_once_with(0.25)
    sink.assert_not_called()
    client.commit.assert_called_once()


@pytest.mark.parametrize(
    "error,attempts", [(TransientProcessingError(), 3), (ProcessingError(), 1)]
)
def test_exhausted_or_permanent_routes_to_dlq(
    client: MagicMock, error: Exception, attempts: int
) -> None:
    handler = MagicMock(side_effect=error)
    sink = MagicMock()
    with consumer() as c:
        c.process_next(handler, sink, retry=RetryPolicy(backoff_seconds=0))
    assert handler.call_count == attempts
    assert sink.call_args.args[0]["payload"]["attempts"] == attempts
    client.commit.assert_called_once()


@pytest.mark.parametrize("where", ["handler", "dlq", "commit", "partition_commit"])
def test_unresolved_failure_closes_without_later_poll(client: MagicMock, where: str) -> None:
    handler = MagicMock()
    sink = MagicMock()
    if where == "handler":
        handler.side_effect = RuntimeError("bug")
    elif where == "dlq":
        client.poll.return_value.value.return_value = b"bad"
        sink.side_effect = PublishError("offline")
    elif where == "commit":
        client.commit.side_effect = KafkaException(KafkaError(KafkaError._TRANSPORT))
    else:
        client.commit.return_value = [MagicMock(error=KafkaError(KafkaError._TRANSPORT))]
    c = consumer()
    with pytest.raises(Exception):
        c.process_next(handler, sink)
    client.close.assert_called_once()
    with pytest.raises(RuntimeError, match="closed"):
        c.poll()
    if where in {"handler", "dlq"}:
        client.commit.assert_not_called()


def test_logs_do_not_expose_input(client: MagicMock, caplog: pytest.LogCaptureFixture) -> None:
    client.poll.return_value.value.return_value = b'{"password":"secret-canary"}'
    with consumer() as c:
        c.process_next(MagicMock(), MagicMock())
    assert "secret-canary" not in caplog.text
    assert all("secret-canary" not in str(r.__dict__) for r in caplog.records)


def test_auto_commit_rejected() -> None:
    with pytest.raises(ValidationError):
        KafkaConsumerSettings(environment="development", kafka_enable_auto_commit=True)


@pytest.mark.parametrize("mode", ["success", "failed", "missing", "pending", "queue"])
def test_dlq_requires_callback_ack(mode: str) -> None:
    with patch("libs.common.kafka_errors.Producer") as factory:
        client = factory.return_value

        def flush(timeout: float) -> int:
            if mode not in {"missing", "pending"}:
                msg = MagicMock()
                msg.offset.return_value = 2
                client.produce.call_args.kwargs["on_delivery"](
                    KafkaError(KafkaError._TRANSPORT) if mode == "failed" else None, msg
                )
            return int(mode == "pending")

        client.flush.side_effect = flush
        if mode == "queue":
            client.produce.side_effect = BufferError()
        producer = KafkaDeadLetterProducer(KafkaProducerSettings(environment="development"))
        if mode == "success":
            producer.publish({"event_id": "test"})
        else:
            with pytest.raises(PublishError):
                producer.publish({"event_id": "test"})


@pytest.mark.integration
def test_real_dlq_failure_restart_and_offset(real_broker: str) -> None:  # noqa: F811
    assert manager.create_topic(manager.TOPICS[2], "kafka:29092")
    producer = Producer({"bootstrap.servers": real_broker})
    raw = b'{"schema_version":999,"diagnostic":"original"}'
    producer.produce("products.raw.v1", partition=0, value=raw)
    assert producer.flush(10) == 0
    group = "task010-" + uuid4().hex
    settings = KafkaConsumerSettings(
        environment="development", kafka_group_id=group, kafka_bootstrap_servers=real_broker
    )
    sink = MagicMock(side_effect=PublishError("simulated DLQ outage"))
    with KafkaConsumer(settings) as c:
        c.subscribe(["products.raw.v1"])
        deadline = time.monotonic() + 30
        with pytest.raises(PublishError):
            while time.monotonic() < deadline:
                c.process_next(MagicMock(), sink)
    envelope = sink.call_args.args[0]
    dlq = KafkaDeadLetterProducer(
        KafkaProducerSettings(environment="development", kafka_bootstrap_servers=real_broker)
    )
    try:
        with KafkaConsumer(settings) as c:
            c.subscribe(["products.raw.v1"])
            deadline = time.monotonic() + 30
            done = False
            while not done and time.monotonic() < deadline:
                done = c.process_next(MagicMock(), dlq.publish)
            assert done
        reader = Consumer(
            {"bootstrap.servers": real_broker, "group.id": group, "enable.auto.commit": False}
        )
        try:
            committed = reader.committed([TopicPartition("products.raw.v1", 0)], timeout=10)
            assert committed[0].offset == envelope["payload"]["offset"] + 1
            reader.assign([TopicPartition("products.invalid.v1", 0, 0)])
            deadline = time.monotonic() + 20
            record = None
            while record is None and time.monotonic() < deadline:
                record = reader.poll(1)
            assert record is not None and record.error() is None
            value = record.value()
            assert value is not None
            delivered = json.loads(value)
            assert delivered["event_id"] == envelope["event_id"]
            assert base64.b64decode(delivered["payload"]["raw_value_base64"]) == raw
        finally:
            reader.close()
    finally:
        dlq.close()


def test_supported_shape_with_unsupported_version(client: MagicMock) -> None:
    raw = json.loads(_make_valid_event().model_dump_json())
    raw["schema_version"] = 999
    client.poll.return_value.value.return_value = json.dumps(raw).encode()
    sink = MagicMock()
    with consumer() as c:
        c.process_next(MagicMock(), sink)
    details = sink.call_args.args[0]["payload"]["validation_errors"]
    assert details == [{"type": "value_error", "loc": ("schema_version",)}]


def test_shutdown_during_retry_leaves_uncommitted(client: MagicMock) -> None:
    c = consumer()

    def stop(message: object) -> None:
        c._shutdown_requested = True
        raise TransientProcessingError()

    sink = MagicMock()
    assert not c.process_next(stop, sink, retry=RetryPolicy(backoff_seconds=0))
    sink.assert_not_called()
    client.commit.assert_not_called()
    client.close.assert_called_once()


@pytest.mark.parametrize("attempts,delay", [(0, 0), (11, 0), (3, -1), (3, float("nan")), (3, 6)])
def test_retry_policy_rejects_unbounded_values(attempts: int, delay: float) -> None:
    with pytest.raises(ValueError):
        RetryPolicy(attempts, delay)
