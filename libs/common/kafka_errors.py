"""Initial, synchronous Kafka failure path (TASK-010)."""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from confluent_kafka import KafkaError, KafkaException, Message, Producer

from libs.common.kafka_producer import KafkaProducerSettings, PublishError

logger = logging.getLogger(__name__)


class TransientProcessingError(Exception):
    """Explicit opt-in to bounded retries of an idempotent handler."""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_seconds: float = 0.25

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")
        if not 0 <= self.backoff_seconds <= 5:
            raise ValueError("backoff_seconds must be between 0 and 5")


class KafkaDeadLetterProducer:
    """Publish lossless diagnostic envelopes; return only after broker acknowledgement.

    Single-threaded, like the consumer. Client retries are bounded by delivery
    timeout. Application-level failure stops consumption for restart/replay.
    """

    topic = "products.invalid.v1"

    def __init__(self, settings: KafkaProducerSettings) -> None:
        self._timeout = settings.kafka_delivery_timeout_ms / 1000 + 1
        self._producer = Producer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "client.id": settings.kafka_client_id,
                "enable.idempotence": True,
                "acks": "all",
                "allow.auto.create.topics": False,
                "delivery.timeout.ms": settings.kafka_delivery_timeout_ms,
                "request.timeout.ms": min(10000, settings.kafka_delivery_timeout_ms),
            }
        )

    def publish(self, envelope: dict[str, object]) -> None:
        acknowledged = False
        failure: KafkaError | None = None

        def delivered(error: KafkaError | None, message: Message) -> None:
            nonlocal acknowledged, failure
            failure = error
            offset = message.offset()
            acknowledged = error is None and offset is not None and offset >= 0

        try:
            self._producer.produce(
                self.topic,
                value=json.dumps(envelope).encode("utf-8"),
                on_delivery=delivered,
            )
            pending = self._producer.flush(self._timeout)
        except (KafkaException, BufferError) as exc:
            raise PublishError("DLQ publication failed; restart for replay") from exc
        if pending or failure is not None or not acknowledged:
            raise PublishError("DLQ delivery unconfirmed; restart for replay")

    def close(self) -> None:
        if self._producer.flush(self._timeout):
            raise PublishError("DLQ shutdown has unconfirmed deliveries")


DeadLetterSink = Callable[[dict[str, object]], None]


def diagnostic_envelope(
    *,
    group_id: str,
    topic: str,
    partition: int,
    offset: int,
    raw_value: bytes | None,
    error: Exception,
    attempts: int,
) -> dict[str, object]:
    """Preserve bytes in the DLQ, never in logs or exception messages.

    Error type and validation locations diagnose failures without persisting
    arbitrary exception strings that may contain credentials.
    """
    from pydantic import ValidationError

    details = (
        [{"type": item["type"], "loc": item["loc"]} for item in error.errors()]
        if isinstance(error, ValidationError)
        else []
    )
    identity = json.dumps([group_id, topic, partition, offset])
    return {
        "event_id": str(uuid5(NAMESPACE_URL, identity)),
        "event_type": "product.invalid",
        "schema_version": 1,
        "source": group_id,
        "produced_at": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "topic": topic,
            "partition": partition,
            "offset": offset,
            "consumer_group": group_id,
            "raw_value_base64": (
                base64.b64encode(raw_value).decode("ascii") if raw_value is not None else None
            ),
            "error_type": type(error).__name__,
            "validation_errors": details,
            "attempts": attempts,
        },
    }
