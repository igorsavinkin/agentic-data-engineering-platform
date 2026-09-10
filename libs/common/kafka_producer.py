"""Synchronous canonical-event publication for ingestion (TASK-008)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from threading import Lock
from types import TracebackType

from confluent_kafka import KafkaError, KafkaException, Message, Producer
from pydantic import Field, field_validator

from libs.common.config import AppSettings, ConfigurationError
from libs.event_contracts import ProductObservationEvent, deserialize_event, serialize_event
from libs.observability.kafka_metrics import KafkaMetric, KafkaMetrics

logger = logging.getLogger(__name__)


class KafkaProducerSettings(AppSettings):
    """Load with load_settings(KafkaProducerSettings); see docs/kafka-producer.md."""

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_raw_topic: str = "products.raw.v1"
    kafka_client_id: str = "ingestion"
    kafka_delivery_timeout_ms: int = Field(default=30000, ge=1000, le=300000)

    @field_validator("kafka_bootstrap_servers")
    @classmethod
    def valid_brokers(cls, value: str) -> str:
        # Require explicit host:port entries, including bracketed IPv6. Never
        # echo an invalid value: an accidentally pasted URL may hold credentials.
        for broker in value.split(","):
            match = re.fullmatch(r"(?:[A-Za-z0-9_.-]+|\[[0-9A-Fa-f:]+\]):([0-9]+)", broker)
            if match is None or not 1 <= int(match[1]) <= 65535:
                raise ValueError("expected comma-separated host:port endpoints")
        return value

    @field_validator("kafka_raw_topic", "kafka_client_id")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if value in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9_.-]{1,249}", value):
            raise ValueError("expected 1-249 letters, digits, dots, underscores or hyphens")
        return value


class EventSerializationError(Exception):
    """The event could not be encoded and validated; nothing was enqueued."""


class PublishError(Exception):
    """Delivery failed or was not confirmed. Retain the event for retry."""


@dataclass(frozen=True)
class DeliveryReceipt:
    topic: str
    partition: int
    offset: int


class KafkaEventProducer:
    """Publish one event at a time and wait for its delivery callback.

    The lock serializes calls on this instance, including shutdown. This favors
    simple, observable failure behavior over batching throughput. Client retries
    are idempotent within a producer session; application retries/restarts can
    still duplicate an event and downstream must deduplicate by event_id.
    """

    def __init__(self, settings: KafkaProducerSettings) -> None:
        self._settings = settings
        self._lock = Lock()
        self._closed = False
        self.metrics = KafkaMetrics()
        try:
            self._producer = Producer(
                {
                    "bootstrap.servers": settings.kafka_bootstrap_servers,
                    "client.id": settings.kafka_client_id,
                    "enable.idempotence": True,
                    "acks": "all",
                    "max.in.flight.requests.per.connection": 5,
                    "partitioner": "murmur2_random",
                    "allow.auto.create.topics": False,
                    "delivery.timeout.ms": settings.kafka_delivery_timeout_ms,
                    "request.timeout.ms": min(10000, settings.kafka_delivery_timeout_ms),
                    "linger.ms": 0,
                    # Forward client diagnostics to the application's handlers.
                    "logger": logger,
                }
            )
        except (KafkaException, ValueError) as exc:
            raise ConfigurationError("Kafka producer initialization failed") from exc

    def publish(self, event: ProductObservationEvent) -> DeliveryReceipt:
        with self._lock:
            if self._closed:
                self.metrics.increment(KafkaMetric.PRODUCER_ERRORS)
                raise PublishError("Kafka producer is closed")
            try:
                value = serialize_event(event).encode("utf-8")
                # Models are mutable: validate the exact wire snapshot again so
                # an invalid mutation/model_construct cannot enter the raw topic.
                snapshot = deserialize_event(value.decode("utf-8"))
                key = snapshot.partition_key.encode("utf-8")
            except Exception as exc:
                self.metrics.increment(KafkaMetric.PRODUCER_ERRORS)
                self.metrics.increment(KafkaMetric.INVALID)
                logger.error("event_serialization_failed", extra={"operation": "serialize"})
                raise EventSerializationError("Canonical event serialization failed") from exc

            receipt: DeliveryReceipt | None = None
            failure: KafkaError | None = None
            context = {
                "event_id": snapshot.event_id,
                "source": snapshot.source,
                "operation": "publish",
                "topic": self._settings.kafka_raw_topic,
            }

            def delivered(error: KafkaError | None, message: Message) -> None:
                nonlocal receipt, failure
                if error is not None:
                    failure = error
                    logger.error(
                        "kafka_delivery_failed", extra={**context, "error_code": error.code()}
                    )
                else:
                    topic, partition, offset = (
                        message.topic(),
                        message.partition(),
                        message.offset(),
                    )
                    if topic is None or partition is None or offset is None or offset < 0:
                        return  # Missing broker metadata is an unconfirmed delivery.
                    receipt = DeliveryReceipt(topic, partition, offset)
                    logger.info(
                        "kafka_event_delivered",
                        extra={**context, "partition": receipt.partition, "offset": receipt.offset},
                    )

            try:
                self._producer.produce(
                    self._settings.kafka_raw_topic, value=value, key=key, on_delivery=delivered
                )
                # flush serves callbacks. Its return value alone does NOT prove
                # success: a failed delivery also removes a message from the queue.
                pending = self._producer.flush(self._settings.kafka_delivery_timeout_ms / 1000 + 1)
            except (KafkaException, BufferError) as exc:
                self.metrics.increment(KafkaMetric.PRODUCER_ERRORS)
                logger.error("kafka_publish_failed", extra=context)
                raise PublishError("Kafka publish failed; retain the event for retry") from exc
            if failure is not None:
                self.metrics.increment(KafkaMetric.PRODUCER_ERRORS)
                raise PublishError(
                    f"Kafka delivery failed (code {failure.code()}); retain event for retry"
                )
            if pending or receipt is None:
                self.metrics.increment(KafkaMetric.PRODUCER_ERRORS)
                logger.error("kafka_delivery_unconfirmed", extra=context)
                raise PublishError("Kafka delivery unconfirmed; retry may duplicate the event")
            self.metrics.increment(KafkaMetric.PRODUCED)
            return receipt

    def close(self) -> None:
        """Drain pending work with a bound; raise if shutdown cannot confirm drain."""
        with self._lock:
            if self._closed:
                return
            try:
                pending = self._producer.flush(self._settings.kafka_delivery_timeout_ms / 1000 + 1)
            except KafkaException as exc:
                self.metrics.increment(KafkaMetric.PRODUCER_ERRORS)
                raise PublishError("Kafka shutdown failed") from exc
            if pending:
                self.metrics.increment(KafkaMetric.PRODUCER_ERRORS)
                raise PublishError("Kafka shutdown has unconfirmed deliveries")
            self._closed = True

    def __enter__(self) -> KafkaEventProducer:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            self.close()
        except PublishError:
            if exc is None:
                raise
            # Preserve the original failure while making shutdown failure visible.
            logger.error("kafka_shutdown_failed", extra={"operation": "close"})
