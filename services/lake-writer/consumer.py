"""Lake Writer consumer loop — consume ``products.validated.v1`` and persist to Silver (TASK-022).

This module provides the runtime entry point for the Lake Writer service.
It creates a Kafka consumer, subscribes to the validated-events topic, and routes
each message through the ``SilverWriter``.  Offset commits happen ONLY after
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
from libs.common.minio_storage import MinIOSettings, MinIOStorage
from libs.lake_writer import SilverWriter
from libs.observability.kafka_metrics import KafkaMetric, LagSample
from libs.observability.metrics_http_server import MetricsHTTPServer
from libs.observability.prometheus_exporter import create_prometheus_registry

logger = logging.getLogger(__name__)

VALIDATED_TOPIC = "products.validated.v1"


def _build_dead_letter_sink() -> DeadLetterSink:
    """Return a DLQ sink that fails closed.

    When a message cannot be deserialized or processed, this sink logs the
    failure and raises ``RuntimeError`` so the caller does NOT commit the
    offset.  The record will be redelivered on restart for manual inspection.

    In production this would publish to a Kafka DLQ topic; here we fail
    closed to avoid silently acknowledging discarded records.
    """

    def sink(envelope: dict[str, Any]) -> None:
        logger.error(
            "lake_writer_dlq_failed",
            extra={"envelope": str(envelope)},
        )
        raise RuntimeError(
            f"dead-letter delivery failed — refusing to commit offset for envelope: {envelope}"
        )

    return sink


def _sample_lag(consumer: KafkaConsumer) -> None:
    """Sample consumer lag and update metrics."""
    try:
        lag_records = consumer.sample_lag(timeout=2.0)
        samples = [
            LagSample(topic=r.topic, partition=r.partition, lag=r.lag)
            for r in lag_records
            if r.lag is not None
        ]
        consumer.metrics.update_lag(samples)
    except Exception:
        consumer.metrics.increment(KafkaMetric.LAG_ERRORS)
        logger.debug("lag_sample_failed", exc_info=True)


def process_message(
    message: ConsumerMessage,
    writer: SilverWriter,
) -> None:
    """Process a single Kafka message: persist to Silver immediately.

    Each event is written individually so that the offset is committed ONLY
    after successful persistence.  This implements at-least-once delivery
    with no risk of losing committed-but-unwritten records.

    Raises ``StorageError`` on write failure so the caller does NOT commit
    the offset.
    """
    writer.write_event(message.event)


def run_consumer() -> None:
    """Main entry point: initialise components and start consuming."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    settings = load_settings(KafkaConsumerSettings)
    minio_settings = load_settings(MinIOSettings)

    # Ensure Silver bucket exists
    storage = MinIOStorage(minio_settings)
    storage.ensure_bucket(minio_settings.minio_bucket_silver)

    writer = SilverWriter(storage=storage, bucket=minio_settings.minio_bucket_silver)
    consumer = KafkaConsumer(settings)
    dlq = _build_dead_letter_sink()

    consumer.subscribe([VALIDATED_TOPIC])
    logger.info("lake_writer_started", extra={"topic": VALIDATED_TOPIC})

    registry, collector = create_prometheus_registry(service_name="lake-writer")
    collector.register_kafka(consumer.metrics)
    metrics_server = MetricsHTTPServer(registry=registry, port=9100)
    metrics_server.start()
    logger.info("prometheus_metrics_server_started", extra={"port": 9100})

    try:
        iteration = 0
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
            iteration += 1
            if iteration % 50 == 0:
                _sample_lag(consumer)
    except KeyboardInterrupt:
        logger.info("lake_writer_interrupted")
    finally:
        metrics_server.stop()
        consumer.close()
        storage.close()
        logger.info("lake_writer_stopped")


if __name__ == "__main__":
    run_consumer()
