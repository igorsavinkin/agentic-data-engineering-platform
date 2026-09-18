"""Tests for the application factory and OpenAPI endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_openapi_schema_available(client: TestClient) -> None:
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "AI Data Platform API"
    assert "paths" in schema


def test_docs_ui_available(client: TestClient) -> None:
    response = client.get("/api/docs")
    assert response.status_code == 200


def test_v1_routes_registered(client: TestClient) -> None:
    response = client.get("/api/openapi.json")
    paths = response.json()["paths"]
    assert "/api/v1/health" in paths
    assert "/api/v1/ready" in paths
