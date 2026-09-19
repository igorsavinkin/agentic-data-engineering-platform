"""Prometheus metrics endpoint for the API service.

Exposes ``/metrics`` returning Prometheus text format. Includes a
``REQUEST_COUNT`` counter and ``REQUEST_LATENCY`` summary that are
incremented by the middleware installed in ``app.py``.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from fastapi import APIRouter, Request, Response
from prometheus_client import Counter, Summary
from prometheus_client.exposition import generate_latest

from libs.observability.prometheus_exporter import create_prometheus_registry

router = APIRouter()

_registry, _collector = create_prometheus_registry(service_name="api")

REQUEST_COUNT = Counter(
    "api_requests_total",
    "Total API HTTP requests.",
    ["method", "endpoint", "status"],
    registry=_registry,
)
REQUEST_LATENCY = Summary(
    "api_request_duration_seconds",
    "API request latency in seconds.",
    ["method", "endpoint"],
    registry=_registry,
)


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Prometheus scrape endpoint."""
    output = generate_latest(_registry)
    return Response(
        content=output,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


async def metrics_middleware(request: Request, call_next: Callable) -> Response:
    """Track request count and latency for Prometheus."""
    start = time.perf_counter()
    response: Response = await call_next(request)
    duration = time.perf_counter() - start

    endpoint = getattr(request.scope.get("route"), "path", request.url.path)
    method = request.method
    status = str(response.status_code)

    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()
    REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)

    return response
