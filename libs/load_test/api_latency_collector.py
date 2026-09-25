"""API latency collection and analysis for load tests (TASK-114).

Measures HTTP response latency for key FastAPI endpoints while the
pipeline is under load.  A probe function sends requests to configured
endpoints and records per-endpoint latency distributions (p50, p95,
p99).  The collector is independent of the HTTP mechanism: probe
results are injected via ``record_sample()`` so that tests can supply
deterministic data and production callers can use any HTTP client.

Latency is measured client-side in milliseconds using
``time.perf_counter()`` around each HTTP request.  The distribution
identifies which endpoints degrade under pipeline stress.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class ApiLatencySample:
    """A single API latency measurement.

    Attributes
    ----------
    endpoint:
        Normalized endpoint path (e.g. ``/api/v1/products``).
    latency_ms:
        Round-trip HTTP latency in milliseconds.
    status_code:
        HTTP status code returned by the server.
    """

    endpoint: str
    latency_ms: float
    status_code: int


class ApiLatencyCollector:
    """Thread-safe collector for API latency measurements.

    The probe calls ``record_sample()`` after each HTTP request.
    The collector groups samples by endpoint and computes per-endpoint
    percentile distributions for the load-test report.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._samples: list[ApiLatencySample] = []

    def record_sample(self, endpoint: str, latency_ms: float, status_code: int) -> None:
        """Record a single API latency measurement."""
        with self._lock:
            self._samples.append(
                ApiLatencySample(
                    endpoint=endpoint,
                    latency_ms=latency_ms,
                    status_code=status_code,
                )
            )

    @property
    def sample_count(self) -> int:
        with self._lock:
            return len(self._samples)

    def get_samples(self) -> list[ApiLatencySample]:
        """Return a copy of all recorded samples."""
        with self._lock:
            return list(self._samples)

    def to_report_dict(self) -> dict | None:
        """Produce a JSON-serializable latency report, or None if unused."""
        with self._lock:
            samples = list(self._samples)

        if not samples:
            return None

        by_endpoint: dict[str, list[ApiLatencySample]] = {}
        for s in samples:
            by_endpoint.setdefault(s.endpoint, []).append(s)

        endpoints: dict[str, dict] = {}
        for ep, ep_samples in sorted(by_endpoint.items()):
            latencies = sorted(s.latency_ms for s in ep_samples)
            status_counts: dict[str, int] = {}
            for s in ep_samples:
                key = str(s.status_code)
                status_counts[key] = status_counts.get(key, 0) + 1

            endpoints[ep] = {
                "sample_count": len(ep_samples),
                "latency_ms": _compute_percentiles(latencies),
                "status_codes": status_counts,
            }

        all_latencies = sorted(s.latency_ms for s in samples)
        return {
            "total_samples": len(samples),
            "endpoint_count": len(endpoints),
            "overall_latency_ms": _compute_percentiles(all_latencies),
            "endpoints": endpoints,
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
