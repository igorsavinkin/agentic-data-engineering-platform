"""Tests for Pydantic response schemas."""

from __future__ import annotations

from services.api.schemas import (
    APIResponse,
    ErrorDetail,
    ErrorResponse,
    HealthStatus,
    ReadinessStatus,
)


def test_api_response_default_status() -> None:
    r = APIResponse()
    assert r.status == "ok"


def test_error_response_serialization() -> None:
    r = ErrorResponse(error=ErrorDetail(code="NOT_FOUND", message="gone"))
    data = r.model_dump()
    assert data["error"]["code"] == "NOT_FOUND"
    assert data["error"]["detail"] is None


def test_error_response_with_detail() -> None:
    r = ErrorResponse(
        error=ErrorDetail(code="BAD_REQUEST", message="invalid", detail={"field": "x"})
    )
    data = r.model_dump()
    assert data["error"]["detail"] == {"field": "x"}


def test_health_status_fields() -> None:
    h = HealthStatus(status="healthy", service="api", version="0.1.0")
    assert h.status == "healthy"
    assert h.service == "api"


def test_readiness_status_fields() -> None:
    r = ReadinessStatus(status="ready", service="api", version="0.1.0", database="connected")
    assert r.database == "connected"
