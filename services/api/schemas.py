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


class ProductSummaryResponse(BaseModel):
    """Single product row in a paginated list."""

    id: int
    canonical_name: Optional[str] = None
    category: Optional[str] = None
    latest_name: Optional[str] = None
    latest_price: Optional[float] = None
    latest_currency: Optional[str] = None
    latest_availability: Optional[str] = None
    latest_collected_at: Optional[str] = None


class ProductListResponse(BaseModel):
    """Paginated product list envelope."""

    items: list[ProductSummaryResponse]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class ProductDetailResponse(BaseModel):
    """Full product detail response."""

    id: int
    canonical_name: Optional[str] = None
    category: Optional[str] = None
    source_count: int
    latest_name: Optional[str] = None
    latest_price: Optional[float] = None
    latest_currency: Optional[str] = None
    latest_availability: Optional[str] = None
    latest_collected_at: Optional[str] = None
    latest_source: Optional[str] = None
    latest_url: Optional[str] = None


class ObservationResponse(BaseModel):
    """Single historical observation with source traceability."""

    id: int
    name: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    availability: str
    collected_at: str
    source: Optional[str] = None
    url: Optional[str] = None


class ObservationListResponse(BaseModel):
    """Paginated observation list envelope."""

    items: list[ObservationResponse]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
