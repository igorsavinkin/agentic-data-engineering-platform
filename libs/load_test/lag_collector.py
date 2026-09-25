"""Consumer lag collection and analysis for load-test runs (TASK-112).

Collects time-series lag samples per consumer group, topic, and partition
during load tests.  Provides summary statistics and growth-pattern detection
to identify when consumers cannot keep up with producer throughput.

The collector is independent of the Kafka query mechanism: lag samples are
injected via ``record()`` so that tests can supply deterministic data and
production callers can use any Kafka admin API.
"""

from __future__ import annotations

import statistics
import threading
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class LagSample:
    """A single consumer-lag measurement at a point in time.

    Attributes
    ----------
    elapsed_sec:
        Seconds since the load test started (monotonic clock).
    consumer_group:
        Kafka consumer group identifier.
    topic:
        Kafka topic name.
    partition:
        Partition number.
    lag:
        Number of unconsumed messages (high watermark minus committed offset).
    """

    elapsed_sec: float
    consumer_group: str
    topic: str
    partition: int
    lag: int


@dataclass(frozen=True)
class PartitionLagStats:
    """Summary statistics for a single consumer group / topic / partition."""

    consumer_group: str
    topic: str
    partition: int
    sample_count: int
    min_lag: int
    max_lag: int
    mean_lag: float
    final_lag: int
    growth: str  # "stable", "increasing", "decreasing", "insufficient_data"


@dataclass(frozen=True)
class LagSummary:
    """Aggregate lag analysis for the entire load-test run.

    Attributes
    ----------
    per_partition:
        Per-partition statistics sorted by (consumer_group, topic, partition).
    total_samples:
        Total number of lag samples collected.
    max_observed_lag:
        Highest lag observed across all partitions and samples.
    any_growing:
        True if any partition shows monotonically increasing lag.
    """

    per_partition: list[PartitionLagStats]
    total_samples: int
    max_observed_lag: int
    any_growing: bool


# Thresholds for operational lag assessment (documented in docs/kafka-lag-measurement.md)
LAG_THRESHOLD_WARNING = 1000
LAG_THRESHOLD_CRITICAL = 10000

LagQueryFn = Callable[[float], list[LagSample]]


class LagCollector:
    """Thread-safe collector for consumer-lag time-series data.

    Records lag samples from periodic queries and computes summary
    statistics including per-partition min/max/mean/final lag and
    growth-pattern detection.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._samples: list[LagSample] = []

    def record(self, samples: list[LagSample]) -> None:
        """Record a batch of lag samples from one query cycle."""
        if not samples:
            return
        with self._lock:
            self._samples.extend(samples)

    @property
    def sample_count(self) -> int:
        return len(self._samples)

    def get_time_series(self) -> list[dict]:
        """Return the full time-series as a list of plain dicts."""
        with self._lock:
            return [
                {
                    "elapsed_sec": round(s.elapsed_sec, 3),
                    "consumer_group": s.consumer_group,
                    "topic": s.topic,
                    "partition": s.partition,
                    "lag": s.lag,
                }
                for s in self._samples
            ]

    def get_summary(self) -> LagSummary | None:
        """Compute per-partition lag statistics and growth analysis.

        Returns None if no samples were collected.
        """
        with self._lock:
            samples = list(self._samples)

        if not samples:
            return None

        groups: dict[tuple[str, str, int], list[LagSample]] = {}
        for s in samples:
            key = (s.consumer_group, s.topic, s.partition)
            groups.setdefault(key, []).append(s)

        per_partition: list[PartitionLagStats] = []
        max_lag = 0
        any_growing = False

        for key in sorted(groups):
            group_id, topic, partition = key
            partition_samples = sorted(groups[key], key=lambda s: s.elapsed_sec)
            lags = [s.lag for s in partition_samples]
            partition_max = max(lags)
            growth = _classify_growth(lags)

            if partition_max > max_lag:
                max_lag = partition_max
            if growth == "increasing":
                any_growing = True

            per_partition.append(
                PartitionLagStats(
                    consumer_group=group_id,
                    topic=topic,
                    partition=partition,
                    sample_count=len(lags),
                    min_lag=min(lags),
                    max_lag=partition_max,
                    mean_lag=round(statistics.mean(lags), 1),
                    final_lag=lags[-1],
                    growth=growth,
                )
            )

        return LagSummary(
            per_partition=per_partition,
            total_samples=len(samples),
            max_observed_lag=max_lag,
            any_growing=any_growing,
        )

    def to_report_dict(self) -> dict | None:
        """Produce a JSON-serializable report section, or None if no data."""
        summary = self.get_summary()
        if summary is None:
            return None

        return {
            "total_samples": summary.total_samples,
            "max_observed_lag": summary.max_observed_lag,
            "any_growing_lag": summary.any_growing,
            "per_partition": [
                {
                    "consumer_group": p.consumer_group,
                    "topic": p.topic,
                    "partition": p.partition,
                    "samples": p.sample_count,
                    "min": p.min_lag,
                    "max": p.max_lag,
                    "mean": p.mean_lag,
                    "final": p.final_lag,
                    "growth": p.growth,
                }
                for p in summary.per_partition
            ],
            "thresholds": {
                "warning": LAG_THRESHOLD_WARNING,
                "critical": LAG_THRESHOLD_CRITICAL,
            },
        }


def _classify_growth(lags: list[int]) -> str:
    """Classify the lag trend from a time-ordered sequence.

    Returns one of:
    - ``"stable"``: lag stays within a narrow band (max - min <= 20% of max).
    - ``"increasing"``: the last quarter average is significantly higher than
      the first quarter average (>50% increase).
    - ``"decreasing"``: the last quarter average is significantly lower than
      the first quarter average (>30% decrease, e.g. consumer catching up).
    - ``"insufficient_data"``: fewer than 4 samples.
    """
    n = len(lags)
    if n < 4:
        return "insufficient_data"

    q = max(n // 4, 1)
    first_quarter = lags[:q]
    last_quarter = lags[-q:]

    first_mean = statistics.mean(first_quarter)
    last_mean = statistics.mean(last_quarter)

    all_lags_max = max(lags)
    all_lags_min = min(lags)

    if all_lags_max == 0:
        return "stable"

    spread = (all_lags_max - all_lags_min) / all_lags_max
    if spread <= 0.2:
        return "stable"

    if first_mean > 0 and last_mean > first_mean * 1.5:
        return "increasing"
    if first_mean > 0 and last_mean < first_mean * 0.7:
        return "decreasing"
    if first_mean == 0 and last_mean > 10:
        return "increasing"

    return "stable"
