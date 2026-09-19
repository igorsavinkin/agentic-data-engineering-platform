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
import time

from libs.common.config import load_settings
from libs.common.kafka_consumer import ConsumerMessage, KafkaConsumer, KafkaConsumerSettings
from libs.common.kafka_errors import KafkaDeadLetterProducer, RetryPolicy
from libs.common.kafka_producer import KafkaProducerSettings
from libs.common.kafka_validated_producer import KafkaValidatedOutputProducer
from libs.observability.kafka_metrics import LagSample
from libs.observability.logging_config import setup_logging
from libs.observability.metrics_http_server import MetricsHTTPServer
from libs.observability.otel_config import (
    OTelSettings,
    extract_trace_context,
    get_current_trace_id,
    get_tracer,
    safe_attributes,
    setup_opentelemetry,
)
from libs.observability.processor_metrics import ProcessorMetrics
from libs.observability.prometheus_exporter import create_prometheus_registry
from services.processor.pipeline import ProcessorPipeline

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

RAW_TOPIC = "products.raw.v1"


def _sample_lag(consumer: KafkaConsumer) -> None:
    """Sample consumer lag and update metrics, clearing stale samples."""
    try:
        lag_records = consumer.sample_lag(timeout=2.0)
        samples = [
            LagSample(topic=r.topic, partition=r.partition, lag=r.lag)
            for r in lag_records
            if r.lag is not None
        ]
        consumer.metrics.update_lag(samples)
    except Exception:
        logger.debug("lag_sample_failed", exc_info=True)
    consumer.metrics.clear_stale_lag(max_age_seconds=60.0)


def process_batch(
    messages: list[ConsumerMessage],
    pipeline: ProcessorPipeline,
) -> None:
    """Process a batch of messages through the pipeline.

    Raises PublishError if any output publication fails, so the caller
    does NOT commit the offset.
    """
    parent_ctx = None
    if messages and messages[0].headers:
        parent_ctx = extract_trace_context(messages[0].headers)

    with tracer.start_as_current_span("processor.process_batch", context=parent_ctx) as span:
        span.set_attributes(
            safe_attributes(
                {
                    "message_count": len(messages),
                    "topic": messages[0].topic if messages else "",
                }
            )
        )
        trace_id = get_current_trace_id()
        if trace_id:
            from libs.observability.logging_config import set_correlation_id

            set_correlation_id(trace_id)

        result = pipeline.process_batch(messages)
        logger.info(
            "processor_batch_complete",
            extra={
                "valid": result.published_valid,
                "invalid": result.published_invalid,
                "duplicates": result.duplicates_skipped,
                "conflicts": result.conflicts,
                "trace_id": trace_id,
            },
        )


def run_consumer() -> None:
    """Main entry point: initialize components and start consuming."""
    setup_logging(service_name="processor")
    setup_opentelemetry(OTelSettings(service_name="processor"))

    consumer_settings = load_settings(KafkaConsumerSettings)
    producer_settings = load_settings(KafkaProducerSettings)

    consumer = KafkaConsumer(consumer_settings)
    validated_producer = KafkaValidatedOutputProducer(producer_settings)
    invalid_producer = KafkaDeadLetterProducer(producer_settings)

    proc_metrics = ProcessorMetrics()
    pipeline = ProcessorPipeline(
        validated_sink=validated_producer.publish,
        invalid_sink=invalid_producer.publish,
        metrics=proc_metrics,
    )

    registry, collector = create_prometheus_registry(service_name="processor")
    collector.register_processor(proc_metrics)
    collector.register_kafka(consumer.metrics)
    metrics_server = MetricsHTTPServer(registry=registry, port=9100)
    metrics_server.start()
    logger.info("prometheus_metrics_server_started", extra={"port": 9100})

    consumer.subscribe([RAW_TOPIC])
    logger.info(
        "processor_started",
        extra={
            "topic": RAW_TOPIC,
            "group_id": consumer_settings.kafka_group_id,
        },
    )

    try:
        iteration = 0
        while not consumer.is_shutdown_requested():
            processed = consumer.process_next(
                process=lambda msg: process_batch([msg], pipeline),
                dead_letter=invalid_producer.publish,
                retry=RetryPolicy(max_attempts=3, backoff_seconds=1),
            )
            if not processed:
                time.sleep(0.1)
            iteration += 1
            if iteration % 50 == 0:
                _sample_lag(consumer)
    except KeyboardInterrupt:
        logger.info("processor_interrupted")
    finally:
        metrics_server.stop()
        consumer.close()
        validated_producer.close()
        invalid_producer.close()
        logger.info("processor_stopped")


if __name__ == "__main__":
    run_consumer()
