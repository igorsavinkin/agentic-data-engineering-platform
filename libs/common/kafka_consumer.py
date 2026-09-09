"""Reusable Kafka consumer for canonical product-observation events (TASK-009).

This module provides a consumer that reads from Kafka topics with explicit
consumer-group configuration, deserialization, validation, and offset handling.

Offset commit semantics:
- Offsets are committed ONLY after successful processing of a message via commit_message()
- If processing fails, the offset is NOT committed so the message will be
  redelivered on restart/rebalance
- Deserialization errors are surfaced to the caller with full context; the caller
  routes to an acknowledged DLQ or stops for replay
- On graceful shutdown, the consumer closes without committing unprocessed offsets
- This implements at-least-once delivery; downstream consumers must handle
  duplicates via event_id deduplication
"""

from __future__ import annotations

import logging
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Literal

from confluent_kafka import KafkaError, KafkaException, TopicPartition
from pydantic import ValidationError

from libs.common.config import AppSettings, ConfigurationError
from libs.common.kafka_errors import (
    DeadLetterSink,
    RetryPolicy,
    TransientProcessingError,
    diagnostic_envelope,
)
from libs.event_contracts import ProductObservationEvent, deserialize_event

logger = logging.getLogger(__name__)


class KafkaConsumerSettings(AppSettings):
    """Configuration for Kafka consumer instances.

    Load with load_settings(KafkaConsumerSettings); see docs/kafka-consumer.md.
    """

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_group_id: str = ""
    kafka_auto_offset_reset: str = "earliest"
    kafka_session_timeout_ms: int = 30000
    kafka_heartbeat_interval_ms: int = 10000
    kafka_max_poll_interval_ms: int = 300000
    kafka_enable_auto_commit: Literal[False] = False

    @property
    def consumer_config(self) -> dict[str, object]:
        """Build librdkafka consumer configuration dict."""
        return {
            "bootstrap.servers": self.kafka_bootstrap_servers,
            "group.id": self.kafka_group_id,
            "auto.offset.reset": self.kafka_auto_offset_reset,
            "enable.auto.commit": self.kafka_enable_auto_commit,
            "enable.auto.offset.store": False,
            "allow.auto.create.topics": False,
            "session.timeout.ms": self.kafka_session_timeout_ms,
            "heartbeat.interval.ms": self.kafka_heartbeat_interval_ms,
            "max.poll.interval.ms": self.kafka_max_poll_interval_ms,
        }


@dataclass(frozen=True)
class ConsumerMessage:
    """A successfully deserialized message from Kafka."""

    event: ProductObservationEvent
    topic: str
    partition: int
    offset: int
    raw_value: bytes | None = None


@dataclass(frozen=True)
class DeserializationError:
    """A message that failed deserialization, with metadata for handling."""

    topic: str
    partition: int
    offset: int
    error: Exception
    raw_value: bytes | None = None


class ProcessingError(Exception):
    """Raised when message processing fails irrecoverably."""


class MessageDeserializationError(Exception):
    """The message could not be deserialized into a valid event."""


class KafkaConsumer:
    """Consume canonical events from Kafka with explicit offset management.

    Use process_next() for the TASK-010 failure policy. Low-level poll/commit
    callers must never commit past an unresolved record. See docs/kafka-consumer.md.
    """

    def __init__(self, settings: KafkaConsumerSettings) -> None:
        if not settings.kafka_group_id:
            raise ConfigurationError("kafka_group_id is required for consumer groups")

        self._settings = settings
        self._closed = False
        self._shutdown_requested = False
        self._subscribed_topics: list[str] = []

        try:
            from confluent_kafka import Consumer

            self._consumer = Consumer(settings.consumer_config)
        except (KafkaException, ValueError) as exc:
            raise ConfigurationError("Kafka consumer initialization failed") from exc

        # Register signal handlers for graceful shutdown
        self._register_signal_handlers()

    def subscribe(self, topics: list[str]) -> None:
        """Subscribe to one or more Kafka topics.

        Args:
            topics: List of topic names to consume from.

        Raises:
            RuntimeError: If consumer is closed.
        """
        if self._closed:
            raise RuntimeError("Cannot subscribe: consumer is closed")

        self._consumer.subscribe(topics)
        self._subscribed_topics = topics
        logger.info(
            "kafka_subscribed",
            extra={
                "topics": topics,
                "group_id": self._settings.kafka_group_id,
            },
        )

    def poll(
        self, timeout: float = 1.0
    ) -> tuple[list[ConsumerMessage], list[DeserializationError]]:
        """Poll for new messages and deserialize them.

        Args:
            timeout: Maximum time to wait for messages in seconds.

        Returns:
            Tuple of (successful_messages, deserialization_errors). The caller
            must route failed messages to an acknowledged DLQ or stop for replay.

        Raises:
            RuntimeError: If consumer is closed.
        """
        if self._closed:
            raise RuntimeError("Cannot poll: consumer is closed")

        if self._shutdown_requested:
            return [], []

        messages: list[ConsumerMessage] = []
        errors: list[DeserializationError] = []
        msg = self._consumer.poll(timeout=timeout)

        if msg is None:
            return messages, errors

        error = msg.error()
        if error is not None:
            if error.code() == KafkaError._PARTITION_EOF:
                # End of partition, not an actual error
                return messages, errors
            if error.code() == KafkaError._TRANSPORT:
                logger.warning(
                    "kafka_transport_error",
                    extra={"error_code": error.code(), "error_str": error.str()},
                )
                return messages, errors
            raise KafkaException(error)

        topic = msg.topic()
        partition = msg.partition()
        offset = msg.offset()

        if topic is None or partition is None or offset is None:
            raise RuntimeError("Kafka message missing metadata; stop for replay")

        try:
            value = msg.value()
            if value is None:
                raise MessageDeserializationError("Message value is None")

            event = deserialize_event(value.decode("utf-8"))
            messages.append(
                ConsumerMessage(
                    event=event,
                    topic=topic,
                    partition=partition,
                    offset=offset,
                    raw_value=value,
                )
            )
        except (ValidationError, UnicodeDecodeError, MessageDeserializationError) as exc:
            logger.error(
                "kafka_deserialization_failed",
                extra={
                    "topic": topic,
                    "partition": partition,
                    "offset": offset,
                    "error_type": type(exc).__name__,
                },
            )
            # Surface the error to the caller with full context so they can
            # route to an acknowledged DLQ or stop for replay.
            errors.append(
                DeserializationError(
                    topic=topic,
                    partition=partition,
                    offset=offset,
                    error=exc,
                    raw_value=msg.value(),
                )
            )

        return messages, errors

    def process_next(
        self,
        process: Callable[[ConsumerMessage], None],
        dead_letter: DeadLetterSink,
        *,
        retry: RetryPolicy = RetryPolicy(),
        timeout: float = 1.0,
    ) -> bool:
        """Process one record, committing only success or acknowledged DLQ delivery.

        Any unresolved failure closes this consumer before propagating, so a
        later commit cannot skip the failed record. Restart with the same group.
        The sink must return only after durable acknowledgement, or raise.
        """
        try:
            messages, errors = self.poll(timeout)
            if not messages and not errors:
                return False
            record = errors[0] if errors else messages[0]
            context = {
                "topic": record.topic,
                "partition": record.partition,
                "offset": record.offset,
                "group_id": self._settings.kafka_group_id,
            }
            failure: Exception | None = errors[0].error if errors else None
            attempts = 0
            if messages:
                for attempts in range(1, retry.max_attempts + 1):
                    if self.is_shutdown_requested():
                        self.close()
                        return False
                    try:
                        process(messages[0])
                        failure = None
                        break
                    except TransientProcessingError as exc:
                        failure = exc
                        logger.warning(
                            "kafka_processing_retry", extra={**context, "attempt": attempts}
                        )
                        if attempts < retry.max_attempts:
                            time.sleep(retry.backoff_seconds * attempts)
                    except ProcessingError as exc:
                        failure = exc
                        break
            if self.is_shutdown_requested():
                self.close()
                return False
            if failure is not None:
                dead_letter(
                    diagnostic_envelope(
                        group_id=self._settings.kafka_group_id,
                        topic=record.topic,
                        partition=record.partition,
                        offset=record.offset,
                        raw_value=record.raw_value,
                        error=failure,
                        attempts=attempts,
                    )
                )
                logger.warning("kafka_dead_letter_delivered", extra=context)
            self.commit_offsets([TopicPartition(record.topic, record.partition, record.offset + 1)])
            return True
        except BaseException:
            logger.error(
                "kafka_processing_stopped", extra={"group_id": self._settings.kafka_group_id}
            )
            self.close()
            raise

    def commit_message(self, message: ConsumerMessage) -> None:
        """Commit the offset for a successfully processed message.

        IMPORTANT: Call this ONLY after successful processing. Committing
        before processing completes risks data loss on crash.

        Args:
            message: The message that was successfully processed.

        Raises:
            RuntimeError: If consumer is closed.
            KafkaException: If commit fails.
        """
        if self._closed:
            raise RuntimeError("Cannot commit: consumer is closed")

        topic_partition = TopicPartition(
            message.topic,
            message.partition,
            message.offset + 1,  # Next offset to read
        )

        try:
            self.commit_offsets([topic_partition])
            logger.debug(
                "kafka_offset_committed",
                extra={
                    "topic": message.topic,
                    "partition": message.partition,
                    "offset": message.offset,
                },
            )
        except KafkaException as exc:
            logger.error(
                "kafka_commit_failed",
                extra={
                    "topic": message.topic,
                    "partition": message.partition,
                    "offset": message.offset,
                    "error": str(exc),
                },
            )
            raise

    def commit_offsets(self, offsets: list[TopicPartition]) -> None:
        """Commit explicit offsets (advanced usage).

        Args:
            offsets: List of TopicPartition with desired next offsets.

        Raises:
            RuntimeError: If consumer is closed.
            KafkaException: If commit fails.
        """
        if self._closed:
            raise RuntimeError("Cannot commit: consumer is closed")

        try:
            result = self._consumer.commit(offsets=offsets, asynchronous=False)
            for partition in result or []:
                if partition.error is not None:
                    raise KafkaException(partition.error)
            logger.debug("kafka_offsets_committed", extra={"offset_count": len(offsets)})
        except KafkaException as exc:
            logger.error("kafka_commit_failed", extra={"error": str(exc)})
            raise

    def close(self) -> None:
        """Gracefully shut down the consumer.

        Leaves the consumer group cleanly without committing unprocessed offsets.
        The caller is responsible for explicitly committing offsets via commit_message()
        after successful processing. This ensures at-least-once semantics are preserved:
        if a message was fetched but not successfully processed, its offset remains
        uncommitted and will be redelivered on restart.
        """
        if self._closed:
            return

        try:
            self._consumer.close()
        except KafkaException as exc:
            logger.warning(
                "kafka_close_failed",
                extra={"error": str(exc)},
            )

        self._closed = True
        logger.info("kafka_consumer_closed", extra={"group_id": self._settings.kafka_group_id})

    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested via signal handler."""
        return self._shutdown_requested

    def get_assignment(self) -> list[TopicPartition]:
        """Get current partition assignments.

        Returns:
            List of assigned TopicPartitions, or empty list if not assigned.
        """
        if self._closed:
            return []
        return self._consumer.assignment() or []

    def _register_signal_handlers(self) -> None:
        """Register SIGINT/SIGTERM handlers for graceful shutdown."""

        def handle_signal(signum: int, frame: object) -> None:
            logger.info(
                "kafka_shutdown_signal_received",
                extra={"signal": signum},
            )
            self._shutdown_requested = True

        try:
            signal.signal(signal.SIGINT, handle_signal)
            signal.signal(signal.SIGTERM, handle_signal)
        except (OSError, ValueError):
            # Signal handling may not work in all environments (e.g., non-main thread)
            logger.warning("kafka_signal_handler_registration_failed")

    def __enter__(self) -> KafkaConsumer:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
