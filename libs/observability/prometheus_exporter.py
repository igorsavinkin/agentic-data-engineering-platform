"""Prometheus exporter bridging snapshot-based metrics to Prometheus collectors.

Implements a custom ``prometheus_client`` Collector that reads ``.snapshot()``
dicts from ``KafkaMetrics``, ``ProcessorMetrics``, and ``SourceMetrics`` on
each Prometheus scrape. No callbacks execute in the data path — Prometheus
pulls fresh values at scrape time.

Counters are exposed as ``CounterMetricFamily`` so Prometheus can compute
rates and detect process-restart resets. Latency summaries use
``SummaryMetricFamily``. Freshness ages use ``GaugeMetricFamily``.

Instance identity is preserved via a ``service`` label.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from prometheus_client import CollectorRegistry
from prometheus_client.core import (
    CounterMetricFamily,
    GaugeMetricFamily,
    SummaryMetricFamily,
)

if TYPE_CHECKING:
    from libs.observability.kafka_metrics import KafkaMetrics
    from libs.observability.processor_metrics import ProcessorMetrics
    from libs.observability.source_metrics import SourceMetrics

_KAFKA_COUNTERS: list[tuple[str, str]] = [
    ("ingestion_events_total", "Canonical publish confirmations."),
    ("ingestion_errors_total", "Failed canonical publish or shutdown calls."),
    ("kafka_events_consumed_total", "Non-error Kafka records fetched by poll()."),
    ("kafka_events_processed_total", "Successfully processed and committed records."),
    ("events_invalid_total", "Records rejected by serialization or validation."),
    ("kafka_consumer_errors_total", "Kafka poll, commit, or close errors."),
    ("kafka_processing_errors_total", "Failed handler attempts."),
    ("kafka_dead_letter_events_total", "Records sent to the dead-letter sink."),
    ("kafka_lag_errors_total", "Failed consumer lag queries."),
]

_PROCESSOR_COUNTERS: list[tuple[str, str]] = [
    ("processor_events_processed_total", "Records completing the processing chain."),
    ("processor_events_valid_total", "Records published to products.validated.v1."),
    ("processor_events_invalid_total", "Records published to products.invalid.v1."),
    ("processor_events_duplicate_total", "Exact duplicates skipped."),
    ("processor_events_failed_total", "Records where the processing chain raised."),
    ("processor_batches_total", "Non-empty batches entering the pipeline."),
    ("processor_batch_records_total", "Cumulative record count across batches."),
]

_SOURCE_COUNTERS: list[tuple[str, str]] = [
    ("source_fetch_attempts_total", "Source fetch attempts."),
    ("source_fetch_success_total", "Successful source fetches."),
    ("source_fetch_failure_total", "Failed source fetches."),
    ("source_records_collected_total", "Total records collected from sources."),
    ("source_records_emitted_total", "Valid canonical events emitted."),
    ("source_zero_record_fetches_total", "Fetches returning zero records."),
    ("source_pages_fetched_total", "Pages fetched during paginated collection."),
    ("source_retry_attempts_total", "Retry attempts within fetch operations."),
    ("source_malformed_records_total", "Malformed or unparseable records."),
    ("source_partial_failures_total", "Partial collection failures."),
]


class PlatformMetricsCollector:
    """Custom Prometheus Collector that reads platform metric snapshots.

    Registers with a ``CollectorRegistry`` and yields Prometheus metric
    families on each scrape. Snapshot sources are registered dynamically
    via ``register_kafka()``, ``register_processor()``, and
    ``register_source()``.

    Parameters
    ----------
    service_name:
        Value for the ``service`` label identifying this process.
    """

    def __init__(self, service_name: str = "platform") -> None:
        self._service = service_name
        self._kafka_sources: list[Callable[[], dict[str, int]]] = []
        self._kafka_lag_sources: list[Callable[[], list]] = []
        self._processor_sources: list[Callable[[], dict]] = []
        self._source_sources: list[Callable[[], dict]] = []

    def describe(self) -> list:
        return []

    def collect(self) -> list:
        metrics: list = []
        metrics.extend(self._collect_kafka_counters())
        metrics.extend(self._collect_processor_counters())
        metrics.extend(self._collect_processor_latency())
        metrics.extend(self._collect_source_counters())
        metrics.extend(self._collect_source_latency())
        metrics.extend(self._collect_source_freshness())
        metrics.extend(self._collect_kafka_lag())
        return metrics

    def register_kafka(self, kafka_metrics: KafkaMetrics) -> None:
        self._kafka_sources.append(kafka_metrics.snapshot)
        self._kafka_lag_sources.append(kafka_metrics.lag_snapshot)

    def register_processor(self, processor_metrics: ProcessorMetrics) -> None:
        self._processor_sources.append(processor_metrics.snapshot)

    def register_source(self, source_metrics: SourceMetrics) -> None:
        self._source_sources.append(source_metrics.snapshot)

    def _collect_kafka_counters(self) -> list[CounterMetricFamily]:
        families: dict[str, CounterMetricFamily] = {}
        for name, help_text in _KAFKA_COUNTERS:
            families[name] = CounterMetricFamily(name, help_text, labels=["service"])
        for snapshot_fn in self._kafka_sources:
            snap = snapshot_fn()
            for name, value in snap.items():
                if name in families:
                    families[name].add_metric([self._service], value)
        return list(families.values())

    def _collect_processor_counters(self) -> list[CounterMetricFamily]:
        families: dict[str, CounterMetricFamily] = {}
        for name, help_text in _PROCESSOR_COUNTERS:
            families[name] = CounterMetricFamily(name, help_text, labels=["service"])
        for snapshot_fn in self._processor_sources:
            snap = snapshot_fn()
            for name, value in snap.items():
                if name in families and isinstance(value, (int, float)):
                    families[name].add_metric([self._service], value)
        return list(families.values())

    def _collect_processor_latency(self) -> list[SummaryMetricFamily]:
        family = SummaryMetricFamily(
            "processor_processing_seconds",
            "Processor batch processing duration in seconds.",
            labels=["service"],
        )
        for snapshot_fn in self._processor_sources:
            snap = snapshot_fn()
            count = snap.get("processor_processing_seconds_count", 0)
            total = snap.get("processor_processing_seconds_sum", 0.0)
            if count:
                family.add_metric(
                    [self._service],
                    count_value=int(count),
                    sum_value=float(total),
                )
        return [family]

    def _collect_source_counters(self) -> list[CounterMetricFamily]:
        families: dict[str, CounterMetricFamily] = {}
        for name, help_text in _SOURCE_COUNTERS:
            families[name] = CounterMetricFamily(name, help_text, labels=["service", "source"])
        for snapshot_fn in self._source_sources:
            snap = snapshot_fn()
            source = snap.get("source", "unknown")
            for name, value in snap.items():
                if name in families and isinstance(value, (int, float)):
                    families[name].add_metric([self._service, source], value)
        return list(families.values())

    def _collect_source_latency(self) -> list[SummaryMetricFamily]:
        family = SummaryMetricFamily(
            "source_fetch_latency_seconds",
            "Source fetch latency in seconds.",
            labels=["service", "source"],
        )
        for snapshot_fn in self._source_sources:
            snap = snapshot_fn()
            source = snap.get("source", "unknown")
            count = snap.get("source_fetch_latency_seconds_count", 0)
            total = snap.get("source_fetch_latency_seconds_sum", 0.0)
            if count:
                family.add_metric(
                    [self._service, source],
                    count_value=int(count),
                    sum_value=float(total),
                )
        return [family]

    def _collect_source_freshness(self) -> list[GaugeMetricFamily]:
        family = GaugeMetricFamily(
            "source_freshness_age_seconds",
            "Seconds since last successful source fetch.",
            labels=["service", "source"],
        )
        for snapshot_fn in self._source_sources:
            snap = snapshot_fn()
            source = snap.get("source", "unknown")
            last_fetch_iso = snap.get("source_last_successful_fetch")
            if last_fetch_iso:
                from datetime import datetime, timezone

                last_fetch = datetime.fromisoformat(last_fetch_iso)
                age = (datetime.now(timezone.utc) - last_fetch).total_seconds()
                family.add_metric([self._service, source], max(age, 0.0))
        return [family]

    def _collect_kafka_lag(self) -> list[GaugeMetricFamily]:
        family = GaugeMetricFamily(
            "kafka_consumer_lag",
            "Consumer group lag by topic and partition.",
            labels=["service", "topic", "partition"],
        )
        for lag_fn in self._kafka_lag_sources:
            samples = lag_fn()
            for sample in samples:
                family.add_metric(
                    [self._service, sample.topic, str(sample.partition)],
                    sample.lag,
                )
        return [family]


def create_prometheus_registry(
    service_name: str,
) -> tuple[CollectorRegistry, PlatformMetricsCollector]:
    """Create an isolated Prometheus registry with the platform collector.

    Returns the registry and collector so callers can register metric
    sources after creation.
    """
    registry = CollectorRegistry()
    collector = PlatformMetricsCollector(service_name=service_name)
    registry.register(collector)
    return registry, collector
