"""Tests for health and readiness endpoints."""

from __future__ import annotations

from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from services.api.app import create_app
from services.api.config import DatabaseSettings
from services.api.dependencies import get_db


class TestHealth:
    def test_health_returns_200(self, client: TestClient) -> None:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["service"] == "api"
        assert body["version"] == "0.1.0"

    def test_health_response_model(self, client: TestClient) -> None:
        response = client.get("/api/v1/health")
        body = response.json()
        assert set(body.keys()) == {"status", "service", "version"}


class TestReadiness:
    def test_readiness_with_db(self, client: TestClient) -> None:
        response = client.get("/api/v1/ready")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert body["database"] == "connected"

    def test_readiness_without_db(self) -> None:
        from unittest.mock import MagicMock

        app = create_app(db_settings=DatabaseSettings(url="sqlite://"))

        failing_session = MagicMock()
        failing_session.execute.side_effect = Exception("connection refused")

        def _failing_db() -> Generator[Session, None, None]:
            yield failing_session

        app.dependency_overrides[get_db] = _failing_db
        client = TestClient(app)

        response = client.get("/api/v1/ready")
        assert response.status_code == 503
        body = response.json()
        assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
