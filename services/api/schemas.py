"""Pydantic response schemas for the API service.

All responses use typed models — no raw dicts at the boundary.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class APIResponse(BaseModel):
    """Base envelope for all API responses."""

    status: str = "ok"


class ErrorDetail(BaseModel):
    """Single error entry in an error response."""

    code: str
    message: str
    detail: Optional[dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """Structured error response body."""

    error: ErrorDetail


class PaginatedResponse(APIResponse):
    """Typed paginated response envelope."""

    items: list[Any]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class HealthStatus(BaseModel):
    """Liveness probe response."""

    status: str
    service: str
    version: str


class ReadinessStatus(BaseModel):
    """Readiness probe response with dependency checks."""

    status: str
    service: str
    version: str
    database: str
