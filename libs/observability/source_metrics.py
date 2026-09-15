"""Instance-local, bounded source-adapter counters and freshness tracking.

Follows the TASK-011 ``KafkaMetrics`` conventions: thread-safe, instance-local,
no payload/exception/config labels, no exporter in the data path. Snapshots are
detached copies. Counters reset on instance restart.

TASK-040 requirement: metrics failure must not alter ingestion semantics.
All metric operations are wrapped so that exceptions cannot propagate into
the adapter pipeline.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from enum import StrEnum
from threading import Lock


class SourceMetric(StrEnum):
    FETCH_ATTEMPTS = "source_fetch_attempts_total"
    FETCH_SUCCESS = "source_fetch_success_total"
    FETCH_FAILURE = "source_fetch_failure_total"
    RECORDS_COLLECTED = "source_records_collected_total"
    RECORDS_EMITTED = "source_records_emitted_total"
    ZERO_RECORD_FETCHES = "source_zero_record_fetches_total"


class _LatencyTracker:
    """Thread-safe latency tracker for fetch operations.

    Tracks count, sum, min, max for computing rate and average via Prometheus.
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
                "source_fetch_latency_seconds_count": self._count,
                "source_fetch_latency_seconds_sum": self._sum_seconds,
                "source_fetch_latency_seconds_min": self._min_seconds,
                "source_fetch_latency_seconds_max": self._max_seconds,
            }


class SourceFreshness:
    """Thread-safe freshness tracker per source.

    Records the last successful fetch timestamp and provides staleness
    calculation. This is intentionally separate from counters because
    freshness is a gauge-like value, not a counter.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._last_successful_fetch: datetime | None = None

    def record_success(self, timestamp: datetime | None = None) -> None:
        """Record a successful fetch at the given timestamp (or now)."""
        try:
            ts = timestamp or datetime.now(timezone.utc)
            with self._lock:
                self._last_successful_fetch = ts
        except Exception:
            pass

    def get_last_successful_fetch(self) -> datetime | None:
        """Return the timestamp of the last successful fetch, or None."""
        with self._lock:
            return self._last_successful_fetch

    def calculate_freshness_age_seconds(self, reference: datetime | None = None) -> float | None:
        """Calculate age in seconds since last successful fetch.

        Returns None if no successful fetch has occurred yet.
        """
        try:
            ref = reference or datetime.now(timezone.utc)
            with self._lock:
                if self._last_successful_fetch is None:
                    return None
                return (ref - self._last_successful_fetch).total_seconds()
        except Exception:
            return None

    def snapshot(self) -> dict[str, str | None]:
        """Return a detached snapshot of freshness state."""
        with self._lock:
            last_fetch = self._last_successful_fetch
        return {
            "source_last_successful_fetch": last_fetch.isoformat() if last_fetch else None,
        }


class SourceMetrics:
    """Thread-safe source-adapter counters and freshness with low-cardinality labels.

    Labels are intentionally limited to source name only. Event IDs, product IDs,
    URLs, and raw error messages are excluded to bound cardinality.

    All public methods catch exceptions internally so that metrics failures
    cannot alter adapter pipeline semantics (TASK-040 requirement).
    """

    def __init__(self, source_name: str) -> None:
        self._source_name = source_name
        self._lock = Lock()
        self._counts = dict.fromkeys(SourceMetric, 0)
        self._latency = _LatencyTracker()
        self._freshness = SourceFreshness()

    @property
    def source_name(self) -> str:
        """Return the source identifier these metrics track."""
        return self._source_name

    def increment(self, metric: SourceMetric, amount: int = 1) -> None:
        """Increment a counter metric safely."""
        try:
            with self._lock:
                self._counts[metric] += amount
        except Exception:
            pass

    def observe_latency(self, duration_seconds: float) -> None:
        """Record a fetch latency observation."""
        try:
            self._latency.observe(duration_seconds)
        except Exception:
            pass

    def record_fetch_success(self, records_collected: int, records_emitted: int) -> None:
        """Record a successful fetch with record counts.

        Parameters
        ----------
        records_collected:
            Total records received from the source (including malformed).
        records_emitted:
            Valid canonical events ready for publication.
        """
        try:
            self.increment(SourceMetric.FETCH_SUCCESS)
            self.increment(SourceMetric.RECORDS_COLLECTED, records_collected)
            self.increment(SourceMetric.RECORDS_EMITTED, records_emitted)
            self._freshness.record_success()

            # Track zero-record fetches separately
            if records_collected == 0:
                self.increment(SourceMetric.ZERO_RECORD_FETCHES)
        except Exception:
            pass

    def record_fetch_failure(self) -> None:
        """Record a failed fetch attempt."""
        try:
            self.increment(SourceMetric.FETCH_FAILURE)
        except Exception:
            pass

    def get_freshness_age_seconds(self) -> float | None:
        """Get age in seconds since last successful fetch."""
        return self._freshness.calculate_freshness_age_seconds()

    def get_last_successful_fetch(self) -> datetime | None:
        """Get timestamp of last successful fetch."""
        return self._freshness.get_last_successful_fetch()

    def snapshot(self) -> dict[str, int | float | str | None]:
        """Return a detached snapshot of all metrics and freshness state."""
        with self._lock:
            counts: dict[str, int | float | str | None] = {
                metric.value: count for metric, count in self._counts.items()
            }
        counts.update(self._latency.snapshot())
        counts.update(self._freshness.snapshot())
        counts["source"] = self._source_name
        return counts

    def time_fetch(self) -> _FetchTimer:
        """Context manager that measures fetch duration.

        Usage::

            with metrics.time_fetch():
                result = await adapter.fetch()

        The observed duration is recorded even if the block raises.
        """
        return _FetchTimer(self)


class _FetchTimer:
    """Minimal context-manager timer for ``SourceMetrics.time_fetch()``."""

    def __init__(self, metrics: SourceMetrics) -> None:
        self._metrics = metrics
        self._start: float = 0.0

    def __enter__(self) -> _FetchTimer:
        self._start = time.monotonic()
        return self

    def __exit__(self, *exc: object) -> None:
        duration = time.monotonic() - self._start
        self._metrics.observe_latency(duration)
