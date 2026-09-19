"""Price analytics endpoints."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from services.api.dependencies import get_db
from services.api.repositories.analytics import AnalyticsRepository
from services.api.schemas import (
    PriceChangeListResponse,
    PriceChangeResponse,
    PriceMoverListResponse,
    PriceMoverResponse,
    PriceStatisticsItemResponse,
    PriceStatisticsResponse,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/price-changes", response_model=PriceChangeListResponse)
def list_price_changes(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page (max 100)"),
    source_product_id: Optional[int] = Query(
        default=None, description="Filter by source-product listing"
    ),
    from_date: Optional[datetime] = Query(
        default=None, description="Filter observations collected on or after this ISO timestamp"
    ),
    db: Session = Depends(get_db),
) -> PriceChangeListResponse:
    """Return paginated price changes with deltas from previous observations."""
    repo = AnalyticsRepository(db)
    result = repo.list_price_changes(
        page=page,
        page_size=page_size,
        source_product_id=source_product_id,
        from_date=from_date,
    )
    return PriceChangeListResponse(
        items=[
            PriceChangeResponse(
                observation_id=item.observation_id,
                source_product_id=item.source_product_id,
                name=item.name,
                price=_decimal_to_float(item.price),
                currency=item.currency,
                collected_at=item.collected_at,
                prev_price=_decimal_to_float(item.prev_price),
                price_change_absolute=_decimal_to_float(item.price_change_absolute),
                price_change_percent=_decimal_to_float(item.price_change_percent),
                external_id=item.external_id,
                source_name=item.source_name,
            )
            for item in result.items
        ],
        total=result.total,
        page=page,
        page_size=page_size,
    )


@router.get("/price-movers", response_model=PriceMoverListResponse)
def list_price_movers(
    limit: int = Query(default=20, ge=1, le=100, description="Max results (default 20)"),
    days_back: int = Query(default=30, ge=1, le=365, description="Time window in days"),
    source_id: Optional[int] = Query(default=None, description="Filter by source ID"),
    min_observations: int = Query(
        default=2, ge=2, le=100, description="Minimum observations required"
    ),
    db: Session = Depends(get_db),
) -> PriceMoverListResponse:
    """Return top products ranked by price change percentage."""
    repo = AnalyticsRepository(db)
    result = repo.list_price_movers(
        limit=limit,
        days_back=days_back,
        source_id=source_id,
        min_observations=min_observations,
    )
    return PriceMoverListResponse(
        items=[
            PriceMoverResponse(
                source_product_id=item.source_product_id,
                external_id=item.external_id,
                source_name=item.source_name,
                canonical_name=item.canonical_name,
                first_price=float(item.first_price),
                last_price=float(item.last_price),
                price_change_absolute=float(item.price_change_absolute),
                price_change_percent=float(item.price_change_percent),
                observation_count=item.observation_count,
            )
            for item in result.items
        ]
    )


@router.get("/price-statistics", response_model=PriceStatisticsResponse)
def list_price_statistics(
    days_back: int = Query(default=30, ge=1, le=365, description="Time window in days"),
    db: Session = Depends(get_db),
) -> PriceStatisticsResponse:
    """Return per-source aggregate price statistics."""
    repo = AnalyticsRepository(db)
    stats = repo.list_price_statistics(days_back=days_back)
    return PriceStatisticsResponse(
        items=[
            PriceStatisticsItemResponse(
                source_id=s.source_id,
                source_name=s.source_name,
                observation_count=s.observation_count,
                listings_with_price=s.listings_with_price,
                min_price=_decimal_to_float(s.min_price),
                max_price=_decimal_to_float(s.max_price),
                avg_price=_decimal_to_float(s.avg_price),
            )
            for s in stats
        ]
    )


def _decimal_to_float(value: Optional[Decimal]) -> Optional[float]:
    if value is None:
        return None
    return float(value)
