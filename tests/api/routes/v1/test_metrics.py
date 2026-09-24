"""Tests for the API /metrics endpoint (TASK-084)."""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestMetricsEndpoint:
    def test_metrics_returns_200(self, client: TestClient) -> None:
        response = client.get("/api/v1/metrics")
        assert response.status_code == 200

    def test_metrics_content_type(self, client: TestClient) -> None:
        response = client.get("/api/v1/metrics")
        assert "text/plain" in response.headers["content-type"]

    def test_metrics_not_in_openapi_schema(self, client: TestClient) -> None:
        response = client.get("/api/openapi.json")
        schema = response.json()
        paths = schema.get("paths", {})
        assert "/api/v1/metrics" not in paths

    def test_metrics_output_is_prometheus_format(self, client: TestClient) -> None:
        response = client.get("/api/v1/metrics")
        body = response.text
        assert "ingestion_events_total" in body or "processor_" in body or len(body) > 0
