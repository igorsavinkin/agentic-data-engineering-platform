"""Raw Writer consumer loop — consume ``products.raw.v1`` and persist to Bronze (TASK-021).

This module provides the runtime entry point for the Raw Writer service.
It creates a Kafka consumer, subscribes to the raw-events topic, and routes
each message through the ``BronzeWriter``.  Offset commits happen ONLY after
successful Parquet persistence, implementing at-least-once delivery with
idempotent processing.

Failure handling
----------------
* Transient storage errors cause the offset to NOT be committed; the record
  will be redelivered on restart.
* Deserialization errors are routed to the dead-letter sink.
* The consumer registers SIGINT/SIGTERM handlers for graceful shutdown.
"""

from __future__ import annotations

import logging
from typing import Any

from libs.common.config import load_settings
from libs.common.kafka_consumer import ConsumerMessage, KafkaConsumer, KafkaConsumerSettings
from libs.common.kafka_errors import DeadLetterSink, RetryPolicy
from libs.common.minio_storage import MinIOSettings, MinIOStorage, StorageError
from libs.raw_writer import BronzeWriter

logger = logging.getLogger(__name__)

RAW_TOPIC = "products.raw.v1"


def _build_dead_letter_sink() -> DeadLetterSink:
    """Return a no-op DLQ sink for local development.

    In production this would publish to a Kafka DLQ topic or write to a
    persistent error log.  For TASK-021 scope we log and continue.
    """

    def sink(envelope: dict[str, Any]) -> None:
        logger.error(
            "raw_writer_dlq",
            extra={"envelope": envelope},
        )

    return sink


def process_message(
    message: ConsumerMessage,
    writer: BronzeWriter,
) -> None:
    """Process a single Kafka message: add to batch and flush if needed.

    Raises ``StorageError`` on write failure so the caller does NOT commit
    the offset.
    """
    event = message.event
    should_flush = writer.add_event(event)
    if should_flush:
        writer.flush_batch()


def run_consumer() -> None:
    """Main entry point: initialise components and start consuming."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    settings = load_settings(KafkaConsumerSettings)
    minio_settings = load_settings(MinIOSettings)

    # Ensure Bronze bucket exists
    storage = MinIOStorage(minio_settings)
    storage.ensure_bucket(minio_settings.minio_bucket_bronze)

    writer = BronzeWriter(storage=storage, bucket=minio_settings.minio_bucket_bronze)
    consumer = KafkaConsumer(settings)
    dlq = _build_dead_letter_sink()

    consumer.subscribe([RAW_TOPIC])
    logger.info("raw_writer_started", extra={"topic": RAW_TOPIC})

    try:
        while not consumer.is_shutdown_requested():
            processed = consumer.process_next(
                process=lambda msg: process_message(msg, writer),
                dead_letter=dlq,
                retry=RetryPolicy(max_attempts=3, backoff_seconds=1),
            )
            if not processed:
                # No messages available; brief sleep to avoid busy-loop
                import time

                time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info("raw_writer_interrupted")
    finally:
        # Flush any remaining events in the batch
        try:
            writer.flush_batch()
        except StorageError as exc:
            logger.error("raw_writer_final_flush_failed", extra={"error": str(exc)})
        consumer.close()
        storage.close()
        logger.info("raw_writer_stopped")


if __name__ == "__main__":
    run_consumer()
