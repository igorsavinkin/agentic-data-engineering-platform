"""End-to-end processing latency collection and analysis (TASK-113).

Tracks per-event produce timestamps during load tests and computes
end-to-end latency when events appear in PostgreSQL.  The collector
is independent of the database query mechanism: arrival notifications
are injected via ``record_pg_arrivals()`` so that tests can supply
deterministic data and production callers can use any DB API.

Latency = query_time - produce_time for each event, measured in
milliseconds.  The distribution (p50, p95, p99) identifies where
time is spent across the full pipeline: ingestion, Kafka transport,
processor validation, lake persistence, warehouse batch loading,
and PostgreSQL insert.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Callable


@dataclass(frozen=True)
class ProduceRecord:
    """Wall-clock timestamp recorded when an event is produced to Kafka."""

    event_id: str
    produce_time: datetime


@dataclass(frozen=True)
class EndToEndSample:
    """A single end-to-end latency measurement.

    Attributes
    ----------
    event_id:
        Unique event identifier that flows through the entire pipeline.
    latency_ms:
        Milliseconds between Kafka produce and PostgreSQL availability.
    produce_time:
        Wall-clock UTC time when the event was produced to Kafka.
    arrival_time:
        Wall-clock UTC time when the event was first observed in PostgreSQL.
    """

    event_id: str
    latency_ms: float
    produce_time: datetime
    arrival_time: datetime


PgQueryFn = Callable[[list[str]], list[str]]


class LatencyCollector:
    """Thread-safe collector for end-to-end processing latency.

    Workers call ``record_produce()`` for each event.  A background probe
    calls ``record_pg_arrivals()`` with event IDs found in PostgreSQL.
    The collector computes per-event latency as ``query_time - produce_time``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._produce_records: dict[str, datetime] = {}
        self._samples: list[EndToEndSample] = []
        self._resolved_ids: set[str] = set()

    def record_produce(self, event_id: str, produce_time: datetime) -> None:
        """Record the wall-clock time an event was produced to Kafka."""
        with self._lock:
            self._produce_records[event_id] = produce_time

    def record_pg_arrivals(
        self, found_event_ids: list[str], query_time: datetime
    ) -> list[EndToEndSample]:
        """Record that these event IDs are now visible in PostgreSQL.

        Returns the newly computed latency samples (events not previously
        resolved).  Events without a matching produce record are silently
        ignored.
        """
        new_samples: list[EndToEndSample] = []
        with self._lock:
            for eid in found_event_ids:
                if eid in self._resolved_ids:
                    continue
                produce_time = self._produce_records.get(eid)
                if produce_time is None:
                    continue
                latency_ms = (query_time - produce_time).total_seconds() * 1000.0
                sample = EndToEndSample(
                    event_id=eid,
                    latency_ms=latency_ms,
                    produce_time=produce_time,
                    arrival_time=query_time,
                )
                self._samples.append(sample)
                self._resolved_ids.add(eid)
                new_samples.append(sample)
        return new_samples

    @property
    def produced_count(self) -> int:
        with self._lock:
            return len(self._produce_records)

    @property
    def resolved_count(self) -> int:
        with self._lock:
            return len(self._resolved_ids)

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._produce_records) - len(self._resolved_ids)

    def get_pending_event_ids(self) -> list[str]:
        """Return event IDs that have been produced but not yet found in PG."""
        with self._lock:
            return [eid for eid in self._produce_records if eid not in self._resolved_ids]

    def get_samples(self) -> list[EndToEndSample]:
        """Return a copy of all resolved latency samples."""
        with self._lock:
            return list(self._samples)

    def to_report_dict(self) -> dict | None:
        """Produce a JSON-serializable latency report, or None if no data."""
        with self._lock:
            samples = list(self._samples)
            total_produced = len(self._produce_records)
            total_resolved = len(self._resolved_ids)

        if not samples:
            return None

        latencies = sorted(s.latency_ms for s in samples)
        stats = _compute_percentiles(latencies)

        return {
            "total_produced": total_produced,
            "total_resolved": total_resolved,
            "unresolved": total_produced - total_resolved,
            "sample_count": len(samples),
            "latency_ms": stats,
        }


def _compute_percentiles(values: list[float]) -> dict:
    """Compute latency percentiles from a sorted list of values."""
    if not values:
        return {
            "min": 0.0,
            "p50": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "max": 0.0,
            "mean": 0.0,
        }

    n = len(values)
    mean = sum(values) / n

    def _percentile(p: float) -> float:
        k = (n - 1) * p / 100.0
        f = int(k)
        c = f + 1 if f + 1 < n else f
        d = k - f
        return values[f] + d * (values[c] - values[f])

    return {
        "min": round(values[0], 3),
        "p50": round(_percentile(50), 3),
        "p95": round(_percentile(95), 3),
        "p99": round(_percentile(99), 3),
        "max": round(values[-1], 3),
        "mean": round(mean, 3),
    }
