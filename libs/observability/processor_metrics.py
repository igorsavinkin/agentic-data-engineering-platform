"""Instance-local, bounded processor counters and latency observations.

Follows the TASK-011 ``KafkaMetrics`` conventions: thread-safe, instance-local,
no payload/exception/config labels, no exporter in the data path. Snapshots are
detached copies. Counters reset on instance restart.

TASK-018 requirement: metrics failure must not alter processing semantics.
All metric operations are wrapped so that exceptions cannot propagate into
the processor pipeline.
"""

from __future__ import annotations

import time
from enum import StrEnum
from threading import Lock


class ProcessorMetric(StrEnum):
    EVENTS_PROCESSED = "processor_events_processed_total"
    EVENTS_VALID = "processor_events_valid_total"
    EVENTS_INVALID = "processor_events_invalid_total"
    EVENTS_DUPLICATE = "processor_events_duplicate_total"
    EVENTS_FAILED = "processor_events_failed_total"
    BATCHES_TOTAL = "processor_batches_total"
    BATCH_RECORDS_TOTAL = "processor_batch_records_total"


class _LatencySummary:
    """Thread-safe latency tracker: count, sum, min, max.

    Sufficient for Prometheus Summary rate and average computation.
    No buckets or quantiles — those belong to a later observability milestone.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._count: int = 0
        self._sum_seconds: float = 0.0
        self._min_seconds: float | None = None
        self._max_seconds: float = 0.0

    def observe(self, duration_seconds: float) -> None:
        with self._lock:
            self._count += 1
            self._sum_seconds += duration_seconds
            if self._min_seconds is None or duration_seconds < self._min_seconds:
                self._min_seconds = duration_seconds
            if duration_seconds > self._max_seconds:
                self._max_seconds = duration_seconds

    def snapshot(self) -> dict[str, float | int | None]:
        with self._lock:
            return {
                "processor_processing_seconds_count": self._count,
                "processor_processing_seconds_sum": self._sum_seconds,
                "processor_processing_seconds_min": self._min_seconds,
                "processor_processing_seconds_max": self._max_seconds,
            }


class ProcessorMetrics:
    """Thread-safe processor counters and latency with no high-cardinality labels.

    Labels are intentionally absent: source, event_id, product_id, URL, and
    raw error messages are excluded to bound cardinality. The only dimensions
    are the fixed metric names defined in ``ProcessorMetric``.

    All public methods catch exceptions internally so that metrics failures
    cannot alter processor pipeline semantics (TASK-018 requirement 6).
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._counts = dict.fromkeys(ProcessorMetric, 0)
        self._latency = _LatencySummary()

    def increment(self, metric: ProcessorMetric, amount: int = 1) -> None:
        try:
            with self._lock:
                self._counts[metric] += amount
        except Exception:
            pass

    def observe_latency(self, duration_seconds: float) -> None:
        try:
            self._latency.observe(duration_seconds)
        except Exception:
            pass

    def snapshot(self) -> dict[str, int | float | None]:
        with self._lock:
            counts: dict[str, int | float | None] = {
                metric.value: count for metric, count in self._counts.items()
            }
        counts.update(self._latency.snapshot())
        return counts

    def time_batch(self) -> _BatchTimer:
        """Context manager that measures batch processing duration.

        Usage::

            with metrics.time_batch():
                process(messages)

        The observed duration is recorded even if the block raises.
        """
        return _BatchTimer(self)


class _BatchTimer:
    """Minimal context-manager timer for ``ProcessorMetrics.time_batch()``."""

    def __init__(self, metrics: ProcessorMetrics) -> None:
        self._metrics = metrics
        self._start: float = 0.0

    def __enter__(self) -> _BatchTimer:
        self._start = time.monotonic()
        return self

    def __exit__(self, *exc: object) -> None:
        duration = time.monotonic() - self._start
        self._metrics.observe_latency(duration)
