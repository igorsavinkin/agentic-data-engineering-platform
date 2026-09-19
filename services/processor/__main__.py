"""Processor service entrypoint (TASK-072).

Wires Kafka consumer to the processor pipeline, consuming raw events from
products.raw.v1, validating and normalizing them, applying deduplication,
and publishing valid records to products.validated.v1. Invalid records are
routed to products.invalid.v1 with diagnostic context.

Offset semantics: offsets are committed ONLY after successful processing
and output publication, implementing at-least-once delivery.

Environment variables:
    APP_ENVIRONMENT              Environment name (required)
    APP_KAFKA_BOOTSTRAP_SERVERS  Kafka broker address (default: localhost:9092)
    APP_KAFKA_GROUP_ID           Consumer group ID (required)
    APP_KAFKA_AUTO_OFFSET_RESET  Offset reset policy (default: earliest)
"""

from __future__ import annotations

import logging
from typing import Any

from libs.common.config import load_settings
from libs.common.kafka_consumer import ConsumerMessage, KafkaConsumer, KafkaConsumerSettings
from libs.common.kafka_errors import DeadLetterSink, PublishError, RetryPolicy
from libs.common.kafka_producer import KafkaEventProducer, KafkaProducerSettings
from libs.event_contracts import ProductObservationEvent
from services.processor.pipeline import ProcessorPipeline

logger = logging.getLogger(__name__)

RAW_TOPIC = "products.raw.v1"
VALIDATED_TOPIC = "products.validated.v1"
INVALID_TOPIC = "products.invalid.v1"


def _build_validated_sink(producer: KafkaEventProducer) -> callable:
    """Return a sink that publishes valid events to the validated topic."""

    def sink(event: ProductObservationEvent) -> None:
        try:
            producer.publish(event, topic=VALIDATED_TOPIC)
        except Exception as exc:
            raise PublishError(f"failed to publish to {VALIDATED_TOPIC}: {exc}") from exc

    return sink


def _build_invalid_sink(producer: KafkaEventProducer) -> DeadLetterSink:
    """Return a sink that publishes invalid envelopes to the invalid topic."""

    def sink(envelope: dict[str, Any]) -> None:
        # Envelopes are dicts; publish as raw dict (will be serialized)
        try:
            producer._producer.produce(
                INVALID_TOPIC,
                value=str(envelope).encode("utf-8"),
            )
            producer._producer.flush()
        except Exception as exc:
            raise PublishError(f"failed to publish to {INVALID_TOPIC}: {exc}") from exc

    return sink


def process_batch(
    messages: list[ConsumerMessage],
    pipeline: ProcessorPipeline,
) -> None:
    """Process a batch of messages through the pipeline.

    Raises PublishError if any output publication fails, so the caller
    does NOT commit the offset.
    """
    result = pipeline.process_batch(messages)
    logger.info(
        "processor_batch_complete",
        extra={
            "valid": result.published_valid,
            "invalid": result.published_invalid,
            "duplicates": result.duplicates_skipped,
            "conflicts": result.conflicts,
        },
    )


def run_consumer() -> None:
    """Main entry point: initialize components and start consuming."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    consumer_settings = load_settings(KafkaConsumerSettings)
    producer_settings = load_settings(KafkaProducerSettings)

    consumer = KafkaConsumer(consumer_settings)
    producer = KafkaEventProducer(producer_settings)

    validated_sink = _build_validated_sink(producer)
    invalid_sink = _build_invalid_sink(producer)
    pipeline = ProcessorPipeline(validated_sink=validated_sink, invalid_sink=invalid_sink)

    consumer.subscribe([RAW_TOPIC])
    logger.info(
        "processor_started",
        extra={
            "topic": RAW_TOPIC,
            "group_id": consumer_settings.kafka_group_id,
        },
    )

    try:
        while not consumer.is_shutdown_requested():
            processed = consumer.process_next(
                process=lambda msg: process_batch([msg], pipeline),
                dead_letter=invalid_sink,
                retry=RetryPolicy(max_attempts=3, backoff_seconds=1),
            )
            if not processed:
                import time

                time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info("processor_interrupted")
    finally:
        consumer.close()
        producer.close()
        logger.info("processor_stopped")


if __name__ == "__main__":
    run_consumer()
