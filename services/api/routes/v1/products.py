"""Product list and detail endpoints."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from services.api.dependencies import get_db
from services.api.errors import APIError
from services.api.repositories.product import ProductRepository, ProductSummary
from services.api.schemas import (
    ProductDetailResponse,
    ProductListResponse,
    ProductSummaryResponse,
)

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=ProductListResponse)
def list_products(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page (max 100)"),
    category: Optional[str] = Query(default=None, description="Filter by product category"),
    source: Optional[str] = Query(default=None, description="Filter by source name"),
    db: Session = Depends(get_db),
) -> ProductListResponse:
    """Return a paginated list of products with their latest observation."""
    repo = ProductRepository(db)
    result = repo.list_products(page=page, page_size=page_size, category=category, source=source)
    return ProductListResponse(
        items=[_summary_to_response(item) for item in result.items],
        total=result.total,
        page=page,
        page_size=page_size,
    )


@router.get("/{product_id}", response_model=ProductDetailResponse)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
) -> ProductDetailResponse:
    """Return full detail for a single product."""
    repo = ProductRepository(db)
    detail = repo.get_product(product_id)
    if detail is None:
        raise APIError(
            status_code=404,
            error_code="PRODUCT_NOT_FOUND",
            message=f"Product {product_id} not found",
        )
    return ProductDetailResponse(
        id=detail.id,
        canonical_name=detail.canonical_name,
        category=detail.category,
        source_count=detail.source_count,
        latest_name=detail.latest_name,
        latest_price=_decimal_to_float(detail.latest_price),
        latest_currency=detail.latest_currency,
        latest_availability=detail.latest_availability,
        latest_collected_at=detail.latest_collected_at,
        latest_source=detail.latest_source,
        latest_url=detail.latest_url,
    )


def _summary_to_response(item: ProductSummary) -> ProductSummaryResponse:
    return ProductSummaryResponse(
        id=item.id,
        canonical_name=item.canonical_name,
        category=item.category,
        latest_name=item.latest_name,
        latest_price=_decimal_to_float(item.latest_price),
        latest_currency=item.latest_currency,
        latest_availability=item.latest_availability,
        latest_collected_at=item.latest_collected_at,
    )


def _decimal_to_float(value: Optional[Decimal]) -> Optional[float]:
    if value is None:
        return None
    return float(value)
