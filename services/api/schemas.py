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


class PriceChangeResponse(BaseModel):
    """Single price change entry with delta from previous observation."""

    observation_id: int
    source_product_id: int
    name: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    collected_at: str
    prev_price: Optional[float] = None
    prev_currency: Optional[str] = None
    price_change_absolute: Optional[float] = None
    price_change_percent: Optional[float] = None
    external_id: str
    source_name: str


class PriceChangeListResponse(BaseModel):
    """Paginated price change list envelope."""

    items: list[PriceChangeResponse]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class PriceMoverResponse(BaseModel):
    """Single product ranked by price change over a period."""

    source_product_id: int
    external_id: str
    source_name: str
    canonical_name: Optional[str] = None
    currency: Optional[str] = None
    first_price: float
    last_price: float
    price_change_absolute: float
    price_change_percent: float
    observation_count: int


class PriceMoverListResponse(BaseModel):
    """Bounded list of top price movers."""

    items: list[PriceMoverResponse]


class PriceStatisticsItemResponse(BaseModel):
    """Aggregate price statistics for a single source and currency."""

    source_id: int
    source_name: str
    currency: Optional[str] = None
    observation_count: int
    observations_with_price: int
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    avg_price: Optional[float] = None


class PriceStatisticsResponse(BaseModel):
    """Per-source price statistics."""

    items: list[PriceStatisticsItemResponse]


class PipelineRunResponse(BaseModel):
    """Single pipeline run with derived overall status."""

    id: int
    run_type: str
    status: str
    overall_status: str
    started_at: str
    finished_at: Optional[str] = None
    records_loaded: Optional[int] = None
    error_message: Optional[str] = None


class PipelineRunListResponse(BaseModel):
    """Paginated pipeline run list envelope."""

    items: list[PipelineRunResponse]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class SourceHealthResponse(BaseModel):
    """Latest health assessment for a single source."""

    source_name: str
    overall_status: str
    degradation_state: str
    freshness_state: str
    freshness_age_seconds: Optional[float] = None
    assessed_at: str
    reasons: Optional[dict[str, Any]] = None


class SourceHealthListResponse(BaseModel):
    """Source health overview."""

    items: list[SourceHealthResponse]


class QualityCheckResponse(BaseModel):
    """Single data quality check result."""

    id: int
    check_name: str
    severity: str
    passed: bool
    message: Optional[str] = None
    checked_at: str
    records_checked: int
    failed_records: int
    pipeline_run_id: Optional[int] = None
    observation_id: Optional[int] = None
    details: Optional[dict[str, Any]] = None


class QualityCheckListResponse(BaseModel):
    """Paginated quality check list envelope."""

    items: list[QualityCheckResponse]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class QualitySummaryResponse(BaseModel):
    """Aggregate quality summary per check name."""

    check_name: str
    total_runs: int
    passed_runs: int
    failed_runs: int
    last_checked_at: str
    severity: str


class QualitySummaryListResponse(BaseModel):
    """Quality summary list."""

    items: list[QualitySummaryResponse]
