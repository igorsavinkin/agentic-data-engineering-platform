"""Product query repository — read-only data access for product endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from services.api.models import Product, ProductObservation, Source, SourceProduct


@dataclass(frozen=True)
class ProductSummary:
    """Lightweight product row for list endpoints."""

    id: int
    canonical_name: Optional[str]
    category: Optional[str]
    latest_name: Optional[str]
    latest_price: Optional[Decimal]
    latest_currency: Optional[str]
    latest_availability: Optional[str]
    latest_collected_at: Optional[str]


@dataclass(frozen=True)
class ProductDetail:
    """Full product detail including latest observation and source info."""

    id: int
    canonical_name: Optional[str]
    category: Optional[str]
    source_count: int
    latest_name: Optional[str]
    latest_price: Optional[Decimal]
    latest_currency: Optional[str]
    latest_availability: Optional[str]
    latest_collected_at: Optional[str]
    latest_source: Optional[str]
    latest_url: Optional[str]


@dataclass(frozen=True)
class ProductListResult:
    """Paginated product list with total count."""

    items: list[ProductSummary]
    total: int


class ProductRepository:
    """Read-only product queries backed by SQLAlchemy."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_products(
        self,
        page: int = 1,
        page_size: int = 20,
        category: Optional[str] = None,
        source: Optional[str] = None,
    ) -> ProductListResult:
        """Return a paginated list of products with their latest observation."""
        filtered_products = select(Product.id).distinct()
        if category is not None:
            filtered_products = filtered_products.where(Product.category == category)
        if source is not None:
            filtered_products = (
                filtered_products.join(SourceProduct, SourceProduct.product_id == Product.id)
                .join(Source, Source.id == SourceProduct.source_id)
                .where(Source.name == source)
            )
        fp_subq = filtered_products.subquery("fp")

        latest_obs_subq = (
            select(
                SourceProduct.product_id,
                func.max(ProductObservation.collected_at).label("max_collected"),
            )
            .join(ProductObservation)
            .group_by(SourceProduct.product_id)
            .subquery()
        )

        data_q = (
            select(
                Product.id,
                Product.canonical_name,
                Product.category,
                ProductObservation.name.label("latest_name"),
                ProductObservation.price.label("latest_price"),
                ProductObservation.currency.label("latest_currency"),
                ProductObservation.availability.label("latest_availability"),
                ProductObservation.collected_at.label("latest_collected_at"),
            )
            .join(fp_subq, fp_subq.c.id == Product.id)
            .join(
                latest_obs_subq,
                latest_obs_subq.c.product_id == Product.id,
            )
            .join(
                ProductObservation,
                (ProductObservation.collected_at == latest_obs_subq.c.max_collected)
                & (
                    ProductObservation.source_product_id.in_(
                        select(SourceProduct.id).where(SourceProduct.product_id == Product.id)
                    )
                ),
            )
            .order_by(Product.id)
        )

        total = self._session.execute(select(func.count()).select_from(fp_subq)).scalar() or 0

        offset = (page - 1) * page_size
        rows = self._session.execute(data_q.offset(offset).limit(page_size)).all()

        items = [
            ProductSummary(
                id=row.id,
                canonical_name=row.canonical_name,
                category=row.category,
                latest_name=row.latest_name,
                latest_price=row.latest_price,
                latest_currency=row.latest_currency,
                latest_availability=row.latest_availability,
                latest_collected_at=(
                    row.latest_collected_at.isoformat() if row.latest_collected_at else None
                ),
            )
            for row in rows
        ]

        return ProductListResult(items=items, total=total)

    def get_product(self, product_id: int) -> Optional[ProductDetail]:
        """Return full detail for a single product, or None if not found."""
        latest_obs_subq = (
            select(
                SourceProduct.product_id,
                func.max(ProductObservation.collected_at).label("max_collected"),
            )
            .join(ProductObservation)
            .group_by(SourceProduct.product_id)
            .subquery()
        )

        source_count_subq = (
            select(
                SourceProduct.product_id,
                func.count().label("source_count"),
            )
            .group_by(SourceProduct.product_id)
            .subquery()
        )

        q = (
            select(
                Product.id,
                Product.canonical_name,
                Product.category,
                source_count_subq.c.source_count,
                ProductObservation.name.label("latest_name"),
                ProductObservation.price.label("latest_price"),
                ProductObservation.currency.label("latest_currency"),
                ProductObservation.availability.label("latest_availability"),
                ProductObservation.collected_at.label("latest_collected_at"),
                Source.name.label("latest_source"),
                SourceProduct.url.label("latest_url"),
            )
            .join(SourceProduct, SourceProduct.product_id == Product.id)
            .join(
                latest_obs_subq,
                latest_obs_subq.c.product_id == Product.id,
            )
            .join(
                ProductObservation,
                (ProductObservation.source_product_id == SourceProduct.id)
                & (ProductObservation.collected_at == latest_obs_subq.c.max_collected),
            )
            .join(Source, Source.id == SourceProduct.source_id)
            .join(
                source_count_subq,
                source_count_subq.c.product_id == Product.id,
            )
            .where(Product.id == product_id)
            .order_by(ProductObservation.collected_at.desc())
            .limit(1)
        )

        row = self._session.execute(q).one_or_none()
        if row is None:
            return None

        return ProductDetail(
            id=row.id,
            canonical_name=row.canonical_name,
            category=row.category,
            source_count=row.source_count,
            latest_name=row.latest_name,
            latest_price=row.latest_price,
            latest_currency=row.latest_currency,
            latest_availability=row.latest_availability,
            latest_collected_at=(
                row.latest_collected_at.isoformat() if row.latest_collected_at else None
            ),
            latest_source=row.latest_source,
            latest_url=row.latest_url,
        )
