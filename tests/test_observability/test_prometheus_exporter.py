"""Tests for the Prometheus metrics exporter bridge (TASK-084)."""

from __future__ import annotations

from prometheus_client import CollectorRegistry
from prometheus_client.exposition import generate_latest

from libs.observability.kafka_metrics import KafkaMetric, KafkaMetrics
from libs.observability.processor_metrics import ProcessorMetric, ProcessorMetrics
from libs.observability.prometheus_exporter import (
    PlatformMetricsCollector,
    create_prometheus_registry,
)
from libs.observability.source_metrics import SourceMetric, SourceMetrics


def _find_by_sample_name(metrics: list, sample_name: str) -> list:
    """Find metric families whose samples carry *sample_name*.

    ``CounterMetricFamily`` strips ``_total`` from ``.name`` but sample
    names keep the full suffix, so we match on samples instead.
    """
    return [m for m in metrics if any(s.name == sample_name for s in m.samples)]


class TestPlatformMetricsCollector:
    def test_empty_collector_produces_no_samples(self) -> None:
        collector = PlatformMetricsCollector(service_name="test")
        metrics = collector.collect()
        for family in metrics:
            assert len(family.samples) == 0

    def test_describe_returns_empty(self) -> None:
        collector = PlatformMetricsCollector(service_name="test")
        assert collector.describe() == []

    def test_kafka_counters_appear_in_collection(self) -> None:
        collector = PlatformMetricsCollector(service_name="test-svc")
        kafka = KafkaMetrics()
        kafka.increment(KafkaMetric.PRODUCED)
        kafka.increment(KafkaMetric.PRODUCED)
        kafka.increment(KafkaMetric.CONSUMED)
        collector.register_kafka(kafka)

        metrics = collector.collect()
        kafka_families = _find_by_sample_name(metrics, "ingestion_events_total")
        assert len(kafka_families) == 1
        samples = kafka_families[0].samples
        assert len(samples) == 1
        assert samples[0].value == 2
        assert samples[0].labels["service"] == "test-svc"

    def test_processor_counters_appear(self) -> None:
        collector = PlatformMetricsCollector(service_name="proc")
        proc = ProcessorMetrics()
        proc.increment(ProcessorMetric.EVENTS_VALID, 5)
        proc.increment(ProcessorMetric.EVENTS_INVALID, 2)
        collector.register_processor(proc)

        metrics = collector.collect()
        valid_families = _find_by_sample_name(metrics, "processor_events_valid_total")
        assert len(valid_families) == 1
        assert valid_families[0].samples[0].value == 5

    def test_processor_latency_summary(self) -> None:
        collector = PlatformMetricsCollector(service_name="proc")
        proc = ProcessorMetrics()
        proc.observe_latency(0.1)
        proc.observe_latency(0.3)
        collector.register_processor(proc)

        metrics = collector.collect()
        latency_families = [m for m in metrics if m.name == "processor_processing_seconds"]
        assert len(latency_families) == 1
        sample = latency_families[0].samples[0]
        assert sample.labels["service"] == "proc"

    def test_source_counters_include_source_label(self) -> None:
        collector = PlatformMetricsCollector(service_name="ingest")
        src = SourceMetrics(source_name="fake-store")
        src.increment(SourceMetric.FETCH_SUCCESS)
        src.increment(SourceMetric.RECORDS_COLLECTED, 10)
        collector.register_source(src)

        metrics = collector.collect()
        fetch_families = _find_by_sample_name(metrics, "source_fetch_success_total")
        assert len(fetch_families) == 1
        sample = fetch_families[0].samples[0]
        assert sample.value == 1
        assert sample.labels["source"] == "fake-store"
        assert sample.labels["service"] == "ingest"

    def test_source_freshness_gauge(self) -> None:
        from datetime import datetime, timedelta, timezone

        collector = PlatformMetricsCollector(service_name="ingest")
        now = datetime.now(timezone.utc)
        src = SourceMetrics(source_name="best-buy")
        src._freshness.record_success(now - timedelta(seconds=60))
        collector.register_source(src)

        metrics = collector.collect()
        freshness = [m for m in metrics if m.name == "source_freshness_age_seconds"]
        assert len(freshness) == 1
        assert freshness[0].samples[0].labels["source"] == "best-buy"
        assert freshness[0].samples[0].value >= 59

    def test_multiple_sources_produce_separate_samples(self) -> None:
        collector = PlatformMetricsCollector(service_name="ingest")
        src1 = SourceMetrics(source_name="fake-store")
        src1.increment(SourceMetric.FETCH_SUCCESS, 3)
        src2 = SourceMetrics(source_name="best-buy")
        src2.increment(SourceMetric.FETCH_SUCCESS, 7)
        collector.register_source(src1)
        collector.register_source(src2)

        metrics = collector.collect()
        fetch_families = _find_by_sample_name(metrics, "source_fetch_success_total")
        assert len(fetch_families) == 1
        assert len(fetch_families[0].samples) == 2
        values = {s.labels["source"]: s.value for s in fetch_families[0].samples}
        assert values["fake-store"] == 3
        assert values["best-buy"] == 7


class TestCreatePrometheusRegistry:
    def test_creates_isolated_registry(self) -> None:
        registry, collector = create_prometheus_registry(service_name="test")
        assert isinstance(registry, CollectorRegistry)
        assert isinstance(collector, PlatformMetricsCollector)

    def test_registered_collector_generates_output(self) -> None:
        registry, collector = create_prometheus_registry(service_name="test")
        kafka = KafkaMetrics()
        for _ in range(42):
            kafka.increment(KafkaMetric.PRODUCED)
        collector.register_kafka(kafka)

        output = generate_latest(registry).decode("utf-8")
        assert "ingestion_events_total" in output
        assert "42.0" in output

    def test_multiple_registries_are_independent(self) -> None:
        reg1, col1 = create_prometheus_registry(service_name="svc1")
        reg2, col2 = create_prometheus_registry(service_name="svc2")
        kafka1 = KafkaMetrics()
        for _ in range(10):
            kafka1.increment(KafkaMetric.PRODUCED)
        col1.register_kafka(kafka1)

        output1 = generate_latest(reg1).decode("utf-8")
        output2 = generate_latest(reg2).decode("utf-8")
        assert "10.0" in output1
        assert "svc1" in output1
        assert "svc2" not in output1
        assert "10.0" not in output2
