"""Prometheus metrics endpoint for the API service.

Exposes ``/metrics`` returning Prometheus text format. The API service
does not run Kafka or processing pipelines, so this endpoint serves
process-level metrics and acts as a template for future API-specific
counters (request counts, latency, etc.).
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client.exposition import generate_latest

from libs.observability.prometheus_exporter import create_prometheus_registry

router = APIRouter()

_registry, _collector = create_prometheus_registry(service_name="api")


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Prometheus scrape endpoint.

    Returns metrics in Prometheus text exposition format. Not included
    in OpenAPI schema because it is consumed by Prometheus, not clients.
    """
    output = generate_latest(_registry)
    return Response(
        content=output,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
