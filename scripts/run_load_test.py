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
from typing import Any, Callable

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
        help="Produce exactly this many events (overrides --duration when reached first).",
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
    if args.seed is not None:
        overrides["seed"] = args.seed

    settings = load_settings(LoadTestSettings)
    if overrides:
        settings = settings.model_copy(update=overrides)

    if args.dry_run:
        produce_fn = _build_noop_produce_fn()
        producer = None
    else:
        produce_fn, producer = _build_kafka_produce_fn(settings)

    runner = LoadTestRunner(settings=settings, produce_fn=produce_fn)

    try:
        report = runner.run()
    finally:
        if producer is not None:
            producer.close()

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
