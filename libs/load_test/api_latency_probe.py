"""API latency probe for measuring endpoint response times (TASK-114).

Sends HTTP GET requests to configured FastAPI endpoints during load
tests and records per-endpoint latency.  The probe uses the same
factory pattern as ``pg_latency_probe.py`` and ``kafka_lag_probe.py``:
it returns a callable that the runner invokes periodically.

The probe uses ``urllib.request`` to avoid adding an ``httpx`` or
``requests`` dependency.  Each probe cycle hits every configured
endpoint once and records the round-trip latency for each.
"""

from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request
from typing import Callable

from libs.load_test.api_latency_collector import ApiLatencyCollector

logger = logging.getLogger(__name__)

ApiProbeFn = Callable[[], None]

_DEFAULT_TIMEOUT_SEC = 10.0


def create_api_probe_fn(
    collector: ApiLatencyCollector,
    base_url: str,
    endpoints: list[str],
    timeout_sec: float = _DEFAULT_TIMEOUT_SEC,
) -> ApiProbeFn:
    """Create a function that probes API endpoints for latency.

    Parameters
    ----------
    collector:
        Collector that receives latency samples.
    base_url:
        Base URL of the API service (e.g. ``http://localhost:8000``).
    endpoints:
        List of endpoint paths to probe (e.g. ``["/api/v1/health",
        "/api/v1/products"]``).  Each path is appended to ``base_url``.
    timeout_sec:
        HTTP request timeout in seconds.

    Returns
    -------
    Callable
        A nullary function that probes all endpoints once and records
        results in the collector.
    """
    base = base_url.rstrip("/")

    def probe() -> None:
        for endpoint in endpoints:
            url = f"{base}{endpoint}"
            t0 = time.perf_counter()
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                    status_code = resp.status
                    resp.read()
            except urllib.error.HTTPError as exc:
                status_code = exc.code
            except Exception:
                logger.debug("api_probe_failed", extra={"url": url}, exc_info=True)
                continue

            latency_ms = (time.perf_counter() - t0) * 1000.0
            collector.record_sample(
                endpoint=endpoint,
                latency_ms=latency_ms,
                status_code=status_code,
            )

    return probe
