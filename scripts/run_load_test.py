"""Scriptable entry point for the load-test harness (TASK-108).

Usage::

    python scripts/run_load_test.py --rate 100 --duration 30
    python scripts/run_load_test.py --rate 500 --total-events 5000
    python scripts/run_load_test.py --rate 100 --duration 10 --workers 4

Environment variables (APP_ prefix) override defaults.  See
``docs/load-test-harness.md`` for full documentation.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from libs.common.config import load_settings
from libs.event_contracts import ProductObservationEvent
from libs.load_test import LoadTestRunner, LoadTestSettings


def _build_kafka_produce_fn(
    settings: LoadTestSettings,
) -> tuple[Callable[[ProductObservationEvent], str], Any]:
    """Create a produce function backed by the real Kafka producer.

    Returns a callable that accepts one event and returns its event_id.
    Raises on delivery failure so the runner can record errors.
    """
    from libs.common.kafka_producer import KafkaEventProducer, KafkaProducerSettings

    class _KafkaSettings(KafkaProducerSettings):
        kafka_bootstrap_servers: str = settings.kafka_bootstrap_servers
        kafka_raw_topic: str = settings.kafka_raw_topic
        kafka_client_id: str = settings.kafka_client_id

    producer = KafkaEventProducer(_KafkaSettings())

    def produce(event: ProductObservationEvent) -> str:
        producer.publish(event)
        return event.event_id

    return produce, producer


def _build_noop_produce_fn() -> Callable[[ProductObservationEvent], str]:
    """Create a no-op produce function for dry-run / local testing."""

    def produce(event: ProductObservationEvent) -> str:
        return event.event_id

    return produce


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a load test against the AI Data Platform pipeline.",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=None,
        help="Target events per second (default: from APP_TARGET_EVENTS_PER_SEC or 100).",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Test duration in seconds (default: from APP_DURATION_SEC or 30).",
    )
    parser.add_argument(
        "--total-events",
        type=int,
        default=None,
        help="Produce at least this many events (overshoots slightly with multiple workers).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of parallel producer threads (default: 1).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path for the JSON result report (default: load_test_results.json).",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Source label for generated events (default: load-test).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for deterministic generation (default: 42).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without connecting to Kafka; measures generator throughput only.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help="Collect per-iteration timing breakdown (gen, produce, wait, overshoot, total).",
    )
    parser.add_argument(
        "--monitor-group",
        action="append",
        default=None,
        dest="lag_consumer_groups",
        help=(
            "Consumer group ID to monitor for lag (repeatable). "
            "Example: --monitor-group processor --monitor-group raw-writer"
        ),
    )
    parser.add_argument(
        "--lag-interval",
        type=float,
        default=None,
        help="Lag poll interval in seconds (default: 5.0).",
    )
    parser.add_argument(
        "--lag-partitions",
        type=int,
        default=None,
        help="Number of partitions per monitored topic (default: 3).",
    )
    parser.add_argument(
        "--pg-url",
        type=str,
        default=None,
        help=(
            "PostgreSQL URL for end-to-end latency probing. "
            "Example: postgresql://user:pass@localhost:5432/warehouse"
        ),
    )
    parser.add_argument(
        "--latency-interval",
        type=float,
        default=None,
        help="PostgreSQL latency probe interval in seconds (default: 10.0).",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=None,
        help=("Base URL of the API service for latency probing. Example: http://localhost:8000"),
    )
    parser.add_argument(
        "--api-endpoints",
        type=str,
        nargs="+",
        default=None,
        dest="api_endpoints",
        help=(
            "Endpoint paths to probe during load tests. Example: /api/v1/health /api/v1/products"
        ),
    )
    parser.add_argument(
        "--api-latency-interval",
        type=float,
        default=None,
        help="API latency probe interval in seconds (default: 5.0).",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    overrides: dict = {}
    if args.rate is not None:
        overrides["target_events_per_sec"] = args.rate
    if args.duration is not None:
        overrides["duration_sec"] = args.duration
    if args.total_events is not None:
        overrides["total_events"] = args.total_events
    if args.workers is not None:
        overrides["worker_count"] = args.workers
    if args.output is not None:
        overrides["output_path"] = args.output
    if args.source is not None:
        overrides["source_name"] = args.source
        if args.pg_url is not None or not overrides.get("pg_latency_source"):
            overrides.setdefault("pg_latency_source", args.source)
    if args.seed is not None:
        overrides["seed"] = args.seed
    if args.lag_consumer_groups:
        overrides["lag_consumer_groups"] = args.lag_consumer_groups
    if args.lag_interval is not None:
        overrides["lag_poll_interval_sec"] = args.lag_interval
    if args.lag_partitions is not None:
        overrides["lag_partition_count"] = args.lag_partitions
    if args.pg_url is not None:
        overrides["pg_db_url"] = args.pg_url
    if args.latency_interval is not None:
        overrides["pg_latency_poll_interval_sec"] = args.latency_interval
    if args.api_url is not None:
        overrides["api_base_url"] = args.api_url
    if args.api_endpoints is not None:
        overrides["api_endpoints"] = args.api_endpoints
    if args.api_latency_interval is not None:
        overrides["api_latency_poll_interval_sec"] = args.api_latency_interval

    settings = load_settings(LoadTestSettings)
    if overrides:
        settings = LoadTestSettings(**{**settings.model_dump(), **overrides})

    if args.dry_run:
        produce_fn = _build_noop_produce_fn()
        producer = None
    else:
        produce_fn, producer = _build_kafka_produce_fn(settings)

    lag_query_fn = None
    if settings.lag_consumer_groups and not args.dry_run:
        from libs.load_test.kafka_lag_probe import create_lag_query_fn

        lag_query_fn = create_lag_query_fn(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            consumer_groups=settings.lag_consumer_groups,
            topics=settings.lag_topics,
            partition_count=settings.lag_partition_count,
        )
        logging.getLogger(__name__).info(
            "lag_monitoring_enabled",
            extra={
                "consumer_groups": settings.lag_consumer_groups,
                "topics": settings.lag_topics,
                "poll_interval_sec": settings.lag_poll_interval_sec,
            },
        )

    latency_collector = None
    pg_query_fn = None
    if settings.pg_db_url and not args.dry_run:
        from libs.load_test.latency_collector import LatencyCollector
        from libs.load_test.pg_latency_probe import create_pg_probe_fn

        if settings.pg_latency_source != settings.source_name:
            logging.getLogger(__name__).warning(
                "pg_latency_source_mismatch",
                extra={
                    "pg_latency_source": settings.pg_latency_source,
                    "source_name": settings.source_name,
                },
            )

        latency_collector = LatencyCollector()
        pg_query_fn = create_pg_probe_fn(
            db_url=settings.pg_db_url,
            source=settings.pg_latency_source,
        )
        logging.getLogger(__name__).info(
            "pg_latency_probing_enabled",
            extra={
                "poll_interval_sec": settings.pg_latency_poll_interval_sec,
                "source": settings.pg_latency_source,
            },
        )

    api_latency_collector = None
    api_probe = None
    if settings.api_base_url and not args.dry_run:
        from libs.load_test.api_latency_collector import ApiLatencyCollector
        from libs.load_test.api_latency_probe import create_api_probe_fn

        api_latency_collector = ApiLatencyCollector()
        api_probe = create_api_probe_fn(
            collector=api_latency_collector,
            base_url=settings.api_base_url,
            endpoints=settings.api_endpoints,
            timeout_sec=settings.api_latency_timeout_sec,
        )
        logging.getLogger(__name__).info(
            "api_latency_probing_enabled",
            extra={
                "base_url": settings.api_base_url,
                "endpoints": settings.api_endpoints,
                "poll_interval_sec": settings.api_latency_poll_interval_sec,
            },
        )

    runner = LoadTestRunner(
        settings=settings,
        produce_fn=produce_fn,
        diagnostic=args.diagnostic,
        lag_query_fn=lag_query_fn,
        latency_collector=latency_collector,
        pg_query_fn=pg_query_fn,
        api_latency_collector=api_latency_collector,
        api_probe_fn=api_probe,
    )

    try:
        report = runner.run()
    finally:
        if producer is not None:
            producer.close()

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
