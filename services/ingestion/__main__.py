"""Ingestion service entrypoint (TASK-037).

Wires Fake Store and Best Buy adapters to Kafka, then runs the continuous
fetch-publish loop. Can be invoked via:

    python -m services.ingestion

Environment variables:
    BESTBUY_API_KEY       Best Buy API key (required for Best Buy adapter)
    KAFKA_BOOTSTRAP_SERVERS  Kafka broker address (default: localhost:9092)
    INGESTION_INTERVAL_SECONDS  Fetch cycle interval (default: 60)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any

# Ensure the project root is on sys.path when running as a module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from libs.adapters.best_buy.adapter import BestBuyAdapter
from libs.adapters.fake_store.adapter import FakeStoreAdapter
from libs.common.kafka_producer import KafkaEventProducer, KafkaProducerSettings
from libs.observability.metrics_http_server import MetricsHTTPServer
from libs.observability.prometheus_exporter import create_prometheus_registry
from services.ingestion.runner import IngestionRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ingestion")


def _build_adapters() -> list[Any]:
    """Instantiate configured source adapters.

    Returns
    -------
    list[SourceAdapterProtocol]
        List of adapter instances ready for fetching.
    """
    adapters: list[Any] = []

    # Fake Store adapter — no API key required
    fake_store = FakeStoreAdapter(limit=10)
    adapters.append(fake_store)
    logger.info("adapter_configured", extra={"source": "fake_store", "limit": 10})

    # Best Buy adapter — requires API key
    api_key = os.environ.get("BESTBUY_API_KEY")
    if api_key:
        best_buy = BestBuyAdapter(api_key=api_key, page_size=10)
        adapters.append(best_buy)
        logger.info("adapter_configured", extra={"source": "best_buy", "page_size": 10})
    else:
        logger.warning(
            "best_buy_api_key_missing",
            extra={"hint": "Set BESTBUY_API_KEY environment variable to enable Best Buy ingestion"},
        )

    if not adapters:
        raise RuntimeError("No adapters configured — at least one source is required")

    return adapters


async def main() -> None:
    """Main entrypoint: wire adapters + producer, run continuous loop."""
    # Load configuration
    interval = float(os.environ.get("INGESTION_INTERVAL_SECONDS", "60"))
    settings = KafkaProducerSettings()

    logger.info(
        "ingestion_service_initializing",
        extra={
            "kafka_brokers": settings.kafka_bootstrap_servers,
            "kafka_topic": settings.kafka_raw_topic,
            "interval_seconds": interval,
        },
    )

    # Build adapters
    adapters = _build_adapters()

    # Create Kafka producer
    with KafkaEventProducer(settings) as producer:
        logger.info("kafka_producer_ready", extra={"brokers": settings.kafka_bootstrap_servers})

        # Create and run ingestion runner
        runner = IngestionRunner(
            adapters=adapters,
            producer=producer,
            interval_seconds=interval,
            max_retries=3,
        )

        # Wire Prometheus metrics
        registry, collector = create_prometheus_registry(service_name="ingestion")
        collector.register_kafka(producer.metrics)
        for src_metrics in runner.source_metrics.values():
            collector.register_source(src_metrics)
        metrics_server = MetricsHTTPServer(registry=registry, port=9100)
        metrics_server.start()
        logger.info("prometheus_metrics_server_started", extra={"port": 9100})

        try:
            await runner.run_continuous()
        except KeyboardInterrupt:
            logger.info("ingestion_shutdown_requested")
            runner.stop()
        finally:
            metrics_server.stop()
            # Close adapters
            for adapter in adapters:
                if hasattr(adapter, "close"):
                    await adapter.close()

            # Print final stats
            stats = runner.stats
            logger.info(
                "ingestion_final_stats",
                extra={
                    "total_published": stats.total_events_published,
                    "total_malformed": stats.total_malformed,
                    "total_errors": stats.total_errors,
                },
            )


if __name__ == "__main__":
    asyncio.run(main())
