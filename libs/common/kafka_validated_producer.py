"""Synchronous publisher for validated product-observation events (TASK-017).

Publishes ``ProductObservationEvent`` objects to ``products.validated.v1``
with the same synchronous delivery confirmation used by the ingestion
producer. A successful return means the broker acknowledged the write;
any failure raises ``PublishError`` so the caller must not commit the
input offset.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from threading import Lock
from types import TracebackType

from confluent_kafka import KafkaError, KafkaException, Message, Producer

from libs.common.config import ConfigurationError
from libs.common.kafka_producer import KafkaProducerSettings, PublishError
from libs.event_contracts import ProductObservationEvent, serialize_event
from libs.observability.kafka_metrics import KafkaMetric, KafkaMetrics

logger = logging.getLogger(__name__)

VALIDATED_TOPIC = "products.validated.v1"


@dataclass(frozen=True)
class DeliveryReceipt:
    topic: str
    partition: int
    offset: int


class KafkaValidatedOutputProducer:
    """Publish validated events to ``products.validated.v1``.

    Serializes one event at a time and waits for broker acknowledgement.
    Raises ``PublishError`` on any delivery failure so the caller can
    preserve at-least-once semantics by not committing the input offset.
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
                }
            )
        except (KafkaException, ValueError) as exc:
            raise ConfigurationError(
                "Kafka validated output producer initialization failed"
            ) from exc

    def publish(self, event: ProductObservationEvent) -> DeliveryReceipt:
        with self._lock:
            if self._closed:
                self.metrics.increment(KafkaMetric.PRODUCER_ERRORS)
                raise PublishError("Validated output producer is closed")

            try:
                value = serialize_event(event).encode("utf-8")
                key = event.partition_key.encode("utf-8")
            except Exception as exc:
                self.metrics.increment(KafkaMetric.PRODUCER_ERRORS)
                raise PublishError("Validated event serialization failed") from exc

            receipt: DeliveryReceipt | None = None
            failure: KafkaError | None = None
            context = {
                "event_id": event.event_id,
                "source": event.source,
                "topic": VALIDATED_TOPIC,
            }

            def delivered(error: KafkaError | None, message: Message) -> None:
                nonlocal receipt, failure
                if error is not None:
                    failure = error
                    logger.error(
                        "kafka_validated_delivery_failed",
                        extra={**context, "error_code": error.code()},
                    )
                else:
                    topic = message.topic()
                    partition = message.partition()
                    offset = message.offset()
                    if topic is None or partition is None or offset is None or offset < 0:
                        return
                    receipt = DeliveryReceipt(topic, partition, offset)

            try:
                self._producer.produce(VALIDATED_TOPIC, value=value, key=key, on_delivery=delivered)
                pending = self._producer.flush(self._settings.kafka_delivery_timeout_ms / 1000 + 1)
            except (KafkaException, BufferError) as exc:
                self.metrics.increment(KafkaMetric.PRODUCER_ERRORS)
                raise PublishError("Validated output publish failed; retain for retry") from exc

            if failure is not None:
                self.metrics.increment(KafkaMetric.PRODUCER_ERRORS)
                raise PublishError(
                    f"Validated delivery failed (code {failure.code()}); retain for retry"
                )
            if pending or receipt is None:
                self.metrics.increment(KafkaMetric.PRODUCER_ERRORS)
                raise PublishError("Validated delivery unconfirmed; retry may duplicate")
            self.metrics.increment(KafkaMetric.PROCESSED)
            return receipt

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                pending = self._producer.flush(self._settings.kafka_delivery_timeout_ms / 1000 + 1)
            except KafkaException as exc:
                self.metrics.increment(KafkaMetric.PRODUCER_ERRORS)
                raise PublishError("Validated producer shutdown failed") from exc
            if pending:
                self.metrics.increment(KafkaMetric.PRODUCER_ERRORS)
                raise PublishError("Validated producer shutdown has unconfirmed deliveries")
            self._closed = True

    def __enter__(self) -> KafkaValidatedOutputProducer:
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
            logger.error("kafka_validated_shutdown_failed", extra={"operation": "close"})
