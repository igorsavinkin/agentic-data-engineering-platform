"""Processor metrics: counters, latency, cardinality, and failure isolation (TASK-018)."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from libs.common.kafka_consumer import ConsumerMessage
from libs.event_contracts import ProductObservationEvent
from libs.event_contracts.product_observation import ProductObservationPayload
from libs.observability.processor_metrics import ProcessorMetric, ProcessorMetrics
from services.processor.deduplication import DeduplicationState
from services.processor.pipeline import ProcessorPipeline


def _make_event(event_id: str = "evt-001", source: str = "fake-store") -> ProductObservationEvent:
    return ProductObservationEvent(
        event_id=event_id,
        source=source,
        produced_at=datetime.now(timezone.utc),
        payload=ProductObservationPayload(
            external_id="prod-123",
            name="Test Product",
            url="https://example.com/product/123",
            price=Decimal("99.99"),
            currency="USD",
            availability="in_stock",
            category="electronics",
            collected_at=datetime.now(timezone.utc),
        ),
    )


def _make_message(event_id: str = "evt-001", source: str = "fake-store") -> ConsumerMessage:
    return ConsumerMessage(
        event=_make_event(event_id=event_id, source=source),
        topic="products.raw.v1",
        partition=0,
        offset=0,
    )


# --- ProcessorMetrics unit tests ---


def test_snapshot_is_detached_and_thread_safe() -> None:
    metrics = ProcessorMetrics()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: metrics.increment(ProcessorMetric.EVENTS_PROCESSED), range(1000)))
    snap = metrics.snapshot()
    assert snap[ProcessorMetric.EVENTS_PROCESSED] == 1000
    snap[ProcessorMetric.EVENTS_PROCESSED] = 0
    assert metrics.snapshot()[ProcessorMetric.EVENTS_PROCESSED] == 1000
    assert all(
        v == 0
        for k, v in ProcessorMetrics().snapshot().items()
        if k in {m.value for m in ProcessorMetric}
    )


def test_increment_by_amount() -> None:
    metrics = ProcessorMetrics()
    metrics.increment(ProcessorMetric.BATCH_RECORDS_TOTAL, 42)
    assert metrics.snapshot()[ProcessorMetric.BATCH_RECORDS_TOTAL] == 42
    metrics.increment(ProcessorMetric.BATCH_RECORDS_TOTAL, 8)
    assert metrics.snapshot()[ProcessorMetric.BATCH_RECORDS_TOTAL] == 50


def test_latency_observation() -> None:
    metrics = ProcessorMetrics()
    metrics.observe_latency(0.1)
    metrics.observe_latency(0.3)
    metrics.observe_latency(0.05)
    snap = metrics.snapshot()
    assert snap["processor_processing_seconds_count"] == 3
    assert abs(snap["processor_processing_seconds_sum"] - 0.45) < 1e-9
    assert snap["processor_processing_seconds_min"] == 0.05
    assert snap["processor_processing_seconds_max"] == 0.3


def test_latency_initial_state() -> None:
    metrics = ProcessorMetrics()
    snap = metrics.snapshot()
    assert snap["processor_processing_seconds_count"] == 0
    assert snap["processor_processing_seconds_sum"] == 0.0
    assert snap["processor_processing_seconds_min"] is None
    assert snap["processor_processing_seconds_max"] == 0.0


def test_time_batch_context_manager() -> None:
    metrics = ProcessorMetrics()
    with metrics.time_batch():
        time.sleep(0.01)
    snap = metrics.snapshot()
    assert snap["processor_processing_seconds_count"] == 1
    assert snap["processor_processing_seconds_sum"] >= 0.01


def test_time_batch_records_on_exception() -> None:
    metrics = ProcessorMetrics()
    with pytest.raises(RuntimeError):
        with metrics.time_batch():
            time.sleep(0.01)
            raise RuntimeError("test")
    snap = metrics.snapshot()
    assert snap["processor_processing_seconds_count"] == 1
    assert snap["processor_processing_seconds_sum"] >= 0.01


def test_label_cardinality_guard() -> None:
    """Snapshot keys must be a fixed, bounded set with no high-cardinality labels."""
    metrics = ProcessorMetrics()
    metrics.increment(ProcessorMetric.EVENTS_PROCESSED, 100)
    metrics.observe_latency(0.5)
    snap = metrics.snapshot()
    expected_keys = {
        "processor_events_processed_total",
        "processor_events_valid_total",
        "processor_events_invalid_total",
        "processor_events_duplicate_total",
        "processor_events_failed_total",
        "processor_batches_total",
        "processor_batch_records_total",
        "processor_processing_seconds_count",
        "processor_processing_seconds_sum",
        "processor_processing_seconds_min",
        "processor_processing_seconds_max",
    }
    assert set(snap.keys()) == expected_keys
    for key, value in snap.items():
        assert isinstance(key, str), f"key {key!r} is not a string"
        assert isinstance(value, (int, float, type(None))), f"value for {key} is {type(value)}"


def test_metrics_failure_does_not_raise() -> None:
    """All metric operations must silently swallow exceptions."""
    metrics = ProcessorMetrics()
    metrics.increment(ProcessorMetric.EVENTS_PROCESSED)
    metrics.observe_latency(0.1)
    _ = metrics.snapshot()


# --- Pipeline integration tests ---


def test_pipeline_without_metrics() -> None:
    """Processor must work correctly when no metrics backend is provided."""
    valid_sink = MagicMock()
    invalid_sink = MagicMock()
    pipeline = ProcessorPipeline(valid_sink, invalid_sink)
    msg = _make_message()
    result = pipeline.process_batch([msg])
    assert result.published_valid == 1
    assert result.published_invalid == 0
    valid_sink.assert_called_once()


def test_pipeline_counters_for_valid_events() -> None:
    metrics = ProcessorMetrics()
    pipeline = ProcessorPipeline(MagicMock(), MagicMock(), metrics=metrics)
    messages = [_make_message(event_id=f"evt-{i}") for i in range(3)]
    result = pipeline.process_batch(messages)
    snap = metrics.snapshot()
    assert result.published_valid == 3
    assert snap[ProcessorMetric.EVENTS_PROCESSED] == 3
    assert snap[ProcessorMetric.EVENTS_VALID] == 3
    assert snap[ProcessorMetric.EVENTS_INVALID] == 0
    assert snap[ProcessorMetric.EVENTS_DUPLICATE] == 0
    assert snap[ProcessorMetric.BATCHES_TOTAL] == 1
    assert snap[ProcessorMetric.BATCH_RECORDS_TOTAL] == 3


def test_pipeline_counters_for_invalid_events() -> None:
    metrics = ProcessorMetrics()
    pipeline = ProcessorPipeline(MagicMock(), MagicMock(), metrics=metrics)
    event = _make_event()
    event.payload.price = Decimal("-10.00")
    msg = ConsumerMessage(event=event, topic="products.raw.v1", partition=0, offset=0)
    result = pipeline.process_batch([msg])
    snap = metrics.snapshot()
    assert result.published_invalid == 1
    assert snap[ProcessorMetric.EVENTS_INVALID] == 1
    assert snap[ProcessorMetric.EVENTS_VALID] == 0


def test_pipeline_counters_for_duplicates() -> None:
    metrics = ProcessorMetrics()
    pipeline = ProcessorPipeline(
        MagicMock(), MagicMock(), dedup_state=DeduplicationState(), metrics=metrics
    )
    msg = _make_message(event_id="evt-dup")
    pipeline.process_batch([msg])
    result = pipeline.process_batch([msg])
    snap = metrics.snapshot()
    assert result.duplicates_skipped == 1
    assert snap[ProcessorMetric.EVENTS_DUPLICATE] == 1
    assert snap[ProcessorMetric.EVENTS_PROCESSED] == 2


def test_pipeline_failure_metric() -> None:
    metrics = ProcessorMetrics()
    failing_sink = MagicMock(side_effect=RuntimeError("publish failed"))
    pipeline = ProcessorPipeline(failing_sink, MagicMock(), metrics=metrics)
    msg = _make_message()
    with pytest.raises(RuntimeError, match="publish failed"):
        pipeline.process_batch([msg])
    snap = metrics.snapshot()
    assert snap[ProcessorMetric.EVENTS_FAILED] == 1
    assert snap[ProcessorMetric.EVENTS_PROCESSED] == 0


def test_pipeline_latency_observed() -> None:
    metrics = ProcessorMetrics()
    pipeline = ProcessorPipeline(MagicMock(), MagicMock(), metrics=metrics)
    msg = _make_message()
    pipeline.process_batch([msg])
    snap = metrics.snapshot()
    assert snap["processor_processing_seconds_count"] == 1
    assert snap["processor_processing_seconds_sum"] > 0


def test_pipeline_empty_batch_no_metrics() -> None:
    metrics = ProcessorMetrics()
    pipeline = ProcessorPipeline(MagicMock(), MagicMock(), metrics=metrics)
    result = pipeline.process_batch([])
    assert result.total == 0
    snap = metrics.snapshot()
    assert snap[ProcessorMetric.BATCHES_TOTAL] == 0
    assert snap[ProcessorMetric.EVENTS_PROCESSED] == 0


def test_pipeline_multiple_batches_accumulate() -> None:
    metrics = ProcessorMetrics()
    pipeline = ProcessorPipeline(MagicMock(), MagicMock(), metrics=metrics)
    for i in range(5):
        pipeline.process_batch([_make_message(event_id=f"batch-evt-{i}")])
    snap = metrics.snapshot()
    assert snap[ProcessorMetric.BATCHES_TOTAL] == 5
    assert snap[ProcessorMetric.EVENTS_PROCESSED] == 5
    assert snap[ProcessorMetric.EVENTS_VALID] == 5
    assert snap["processor_processing_seconds_count"] == 5
