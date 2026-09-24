"""Metrics collection for load-test runs (TASK-108).

Tracks per-event latencies, throughput counters, and process-level resource
usage.  All measurements are recorded in-memory and can be summarized into
a structured report at the end of a run.

Hot-path design: ``record_latency`` and ``record_error`` avoid acquiring a
lock by relying on CPython's GIL guaranteeing atomic bytecode-level
operations for ``list.append``.  Counts are derived from ``len()`` on
append-only lists, which is atomic under the GIL.  This removes the
primary serialization bottleneck at high throughput (1000+ eps with many
workers).  ``get_summary`` is only called after all workers have joined,
so the collected data is consistent by construction.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class LatencySample:
    """A single produce-to-ack latency measurement."""

    event_id: str
    latency_ms: float
    timestamp: float


@dataclass
class ResourceSnapshot:
    """A point-in-time snapshot of process resource usage."""

    timestamp: float
    rss_mb: float
    user_cpu_sec: float
    system_cpu_sec: float

    @property
    def total_cpu_sec(self) -> float:
        return self.user_cpu_sec + self.system_cpu_sec


class MetricsCollector:
    """Thread-safe collector for load-test metrics.

    Records per-event latencies, error counts, and periodic resource
    snapshots.  The hot path (``record_latency``, ``record_error``) is
    lock-free: CPython's GIL makes ``list.append`` atomic at the bytecode
    level.  Counts are derived from ``len()`` on append-only lists rather
    than maintained as separate integer counters, because ``int += 1``
    compiles to multiple bytecodes and is NOT atomic under the GIL.

    Resource snapshots and lifecycle markers (``mark_start``/``mark_end``)
    still use a lock because they are called infrequently (1 Hz or once
    per run) and touch shared mutable state that must be consistent.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latencies: list[LatencySample] = []
        self._errors: list[float] = []
        self._resource_snapshots: list[ResourceSnapshot] = []
        self._start_time: float | None = None
        self._end_time: float | None = None

    def record_latency(self, event_id: str, latency_ms: float) -> None:
        """Record a successful produce-to-ack latency (lock-free)."""
        sample = LatencySample(
            event_id=event_id,
            latency_ms=latency_ms,
            timestamp=time.monotonic(),
        )
        self._latencies.append(sample)

    def record_error(self) -> None:
        """Record a produce error (lock-free)."""
        self._errors.append(time.monotonic())

    def record_resource_snapshot(self) -> None:
        """Capture a point-in-time resource usage snapshot."""
        ru = os.times()
        try:
            with open(f"/proc/{os.getpid()}/status") as f:
                rss_kb = 0
                for line in f:
                    if line.startswith("VmRSS:"):
                        rss_kb = int(line.split()[1])
                        break
            rss_mb = rss_kb / 1024.0
        except (FileNotFoundError, OSError):
            rss_mb = 0.0

        snapshot = ResourceSnapshot(
            timestamp=time.monotonic(),
            rss_mb=rss_mb,
            user_cpu_sec=ru.user,
            system_cpu_sec=ru.system,
        )
        with self._lock:
            self._resource_snapshots.append(snapshot)

    def mark_start(self) -> None:
        with self._lock:
            self._start_time = time.monotonic()

    def mark_end(self) -> None:
        with self._lock:
            self._end_time = time.monotonic()

    @property
    def produced_count(self) -> int:
        return len(self._latencies)

    @property
    def error_count(self) -> int:
        return len(self._errors)

    def get_summary(self) -> dict:
        """Compute a summary of collected metrics.

        Returns a dict with throughput, latency percentiles, resource usage,
        and error counts.  Safe to call after ``mark_end()`` and after all
        worker threads have joined.
        """
        with self._lock:
            latencies = sorted(s.latency_ms for s in self._latencies)
            produced = len(self._latencies)
            errors = len(self._errors)
            snapshots = list(self._resource_snapshots)
            start = self._start_time
            end = self._end_time

        duration_sec = (end - start) if (start and end) else 0.0
        throughput = produced / duration_sec if duration_sec > 0 else 0.0

        latency_stats = _compute_percentiles(latencies)

        peak_rss_mb = max((s.rss_mb for s in snapshots), default=0.0)
        total_cpu_sec = (
            snapshots[-1].total_cpu_sec - snapshots[0].total_cpu_sec if len(snapshots) >= 2 else 0.0
        )

        return {
            "duration_sec": round(duration_sec, 3),
            "produced_count": produced,
            "error_count": errors,
            "throughput_events_per_sec": round(throughput, 2),
            "latency_ms": latency_stats,
            "resource": {
                "peak_rss_mb": round(peak_rss_mb, 1),
                "total_cpu_sec": round(total_cpu_sec, 3),
            },
        }


def _compute_percentiles(values: list[float]) -> dict:
    """Compute latency percentiles from a sorted list of values."""
    if not values:
        return {
            "min": 0.0,
            "p50": 0.0,
            "p90": 0.0,
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
        "p90": round(_percentile(90), 3),
        "p95": round(_percentile(95), 3),
        "p99": round(_percentile(99), 3),
        "max": round(values[-1], 3),
        "mean": round(mean, 3),
    }
