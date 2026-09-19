"""Analytics query repository — read-only price analytics access."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from services.api.models import Product, ProductObservation, Source, SourceProduct


@dataclass(frozen=True)
class PriceChangeEntry:
    """Single observation with price delta from previous."""

    observation_id: int
    source_product_id: int
    name: Optional[str]
    price: Optional[Decimal]
    currency: Optional[str]
    collected_at: str
    prev_price: Optional[Decimal]
    price_change_absolute: Optional[Decimal]
    price_change_percent: Optional[Decimal]
    external_id: str
    source_name: str


@dataclass(frozen=True)
class PriceChangeResult:
    """Paginated price change list."""

    items: list[PriceChangeEntry]
    total: int


@dataclass(frozen=True)
class PriceMoverEntry:
    """Product ranked by price change over a period."""

    source_product_id: int
    external_id: str
    source_name: str
    canonical_name: Optional[str]
    currency: Optional[str]
    first_price: Decimal
    last_price: Decimal
    price_change_absolute: Decimal
    price_change_percent: Decimal
    observation_count: int


@dataclass(frozen=True)
class PriceMoverResult:
    """Bounded list of top price movers."""

    items: list[PriceMoverEntry]


@dataclass(frozen=True)
class PriceStatistics:
    """Aggregate price statistics for a single source and currency."""

    source_id: int
    source_name: str
    currency: Optional[str]
    observation_count: int
    listings_with_price: int
    min_price: Optional[Decimal]
    max_price: Optional[Decimal]
    avg_price: Optional[Decimal]


class AnalyticsRepository:
    """Read-only analytical queries backed by SQLAlchemy."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_price_changes(
        self,
        page: int = 1,
        page_size: int = 20,
        source_product_id: Optional[int] = None,
        from_date: Optional[datetime] = None,
    ) -> PriceChangeResult:
        """Return paginated price changes using LAG window function.

        The LAG is partitioned by source_product_id so the "previous price"
        is always from the same source-product listing (and thus the same
        currency).
        """
        prev_price = func.lag(ProductObservation.price).over(
            partition_by=ProductObservation.source_product_id,
            order_by=ProductObservation.collected_at.asc(),
        )

        q = (
            select(
                ProductObservation.id.label("observation_id"),
                ProductObservation.source_product_id,
                ProductObservation.name,
                ProductObservation.price,
                ProductObservation.currency,
                ProductObservation.collected_at,
                prev_price.label("prev_price"),
                SourceProduct.external_id,
                Source.name.label("source_name"),
            )
            .join(SourceProduct, SourceProduct.id == ProductObservation.source_product_id)
            .join(Source, Source.id == SourceProduct.source_id)
        )

        if source_product_id is not None:
            q = q.where(ProductObservation.source_product_id == source_product_id)
        if from_date is not None:
            q = q.where(ProductObservation.collected_at >= from_date)

        q = q.order_by(ProductObservation.collected_at.desc())
        base_subq = q.subquery()

        change_abs = case(
            (
                (base_subq.c.prev_price != None) & (base_subq.c.prev_price > 0),  # noqa: E711
                base_subq.c.price - base_subq.c.prev_price,
            ),
        )
        change_pct = case(
            (
                (base_subq.c.prev_price != None) & (base_subq.c.prev_price > 0),  # noqa: E711
                func.round(
                    (base_subq.c.price - base_subq.c.prev_price) / base_subq.c.prev_price * 100,
                    2,
                ),
            ),
        )

        total = self._session.execute(select(func.count()).select_from(base_subq)).scalar() or 0

        offset = (page - 1) * page_size
        rows = self._session.execute(
            select(
                base_subq.c.observation_id,
                base_subq.c.source_product_id,
                base_subq.c.name,
                base_subq.c.price,
                base_subq.c.currency,
                base_subq.c.collected_at,
                base_subq.c.prev_price,
                base_subq.c.external_id,
                base_subq.c.source_name,
                change_abs.label("price_change_absolute"),
                change_pct.label("price_change_percent"),
            )
            .order_by(base_subq.c.collected_at.desc())
            .offset(offset)
            .limit(page_size)
        ).all()

        items = [
            PriceChangeEntry(
                observation_id=row.observation_id,
                source_product_id=row.source_product_id,
                name=row.name,
                price=row.price,
                currency=row.currency,
                collected_at=row.collected_at.isoformat() if row.collected_at else "",
                prev_price=row.prev_price,
                price_change_absolute=row.price_change_absolute,
                price_change_percent=row.price_change_percent,
                external_id=row.external_id,
                source_name=row.source_name,
            )
            for row in rows
        ]

        return PriceChangeResult(items=items, total=total)

    def list_price_movers(
        self,
        limit: int = 20,
        days_back: int = 30,
        source_id: Optional[int] = None,
        min_observations: int = 2,
    ) -> PriceMoverResult:
        """Return top products ranked by price change percentage.

        First/last prices are taken from the chronologically earliest and
        latest observations per source-product, so price drops are reported
        correctly.  Each source-product is treated as a single currency
        listing; cross-currency aggregation does not occur.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

        agg_q = (
            select(
                ProductObservation.source_product_id,
                func.count().label("obs_count"),
                func.min(ProductObservation.currency).label("currency"),
            )
            .join(SourceProduct, SourceProduct.id == ProductObservation.source_product_id)
            .where(ProductObservation.collected_at >= cutoff)
            .where(ProductObservation.price.is_not(None))
        )
        if source_id is not None:
            agg_q = agg_q.where(SourceProduct.source_id == source_id)

        agg_q = agg_q.group_by(ProductObservation.source_product_id).having(
            func.count() >= min_observations
        )

        agg_rows = self._session.execute(agg_q).all()
        if not agg_rows:
            return PriceMoverResult(items=[])

        sp_data: dict[int, dict] = {}
        for row in agg_rows:
            sp_id = row.source_product_id
            first_obs = self._session.execute(
                select(ProductObservation.price, ProductObservation.currency)
                .where(ProductObservation.source_product_id == sp_id)
                .where(ProductObservation.collected_at >= cutoff)
                .where(ProductObservation.price.is_not(None))
                .order_by(ProductObservation.collected_at.asc())
                .limit(1)
            ).one_or_none()
            last_obs = self._session.execute(
                select(ProductObservation.price)
                .where(ProductObservation.source_product_id == sp_id)
                .where(ProductObservation.collected_at >= cutoff)
                .where(ProductObservation.price.is_not(None))
                .order_by(ProductObservation.collected_at.desc())
                .limit(1)
            ).one_or_none()
            if first_obs and last_obs and first_obs.price and last_obs.price:
                fp: Decimal = first_obs.price
                lp: Decimal = last_obs.price
                abs_change = lp - fp
                pct = float(abs_change / fp * 100) if fp > 0 else 0.0
                sp_data[sp_id] = {
                    "first_price": fp,
                    "last_price": lp,
                    "abs_change": abs_change,
                    "pct": Decimal(str(round(pct, 2))),
                    "obs_count": row.obs_count,
                    "currency": row.currency,
                }

        movers = [
            PriceMoverEntry(
                source_product_id=sp_id,
                external_id="",
                source_name="",
                canonical_name=None,
                currency=d["currency"],
                first_price=d["first_price"],
                last_price=d["last_price"],
                price_change_absolute=d["abs_change"],
                price_change_percent=d["pct"],
                observation_count=d["obs_count"],
            )
            for sp_id, d in sp_data.items()
        ]

        movers.sort(key=lambda m: float(m.price_change_percent), reverse=True)
        movers = movers[:limit]

        sp_ids = [m.source_product_id for m in movers]
        meta_q = (
            select(
                SourceProduct.id,
                SourceProduct.external_id,
                Source.name.label("source_name"),
                Product.canonical_name,
            )
            .join(Source, Source.id == SourceProduct.source_id)
            .join(Product, Product.id == SourceProduct.product_id)
            .where(SourceProduct.id.in_(sp_ids))
        )
        meta = {
            row.id: {
                "external_id": row.external_id,
                "source_name": row.source_name,
                "canonical_name": row.canonical_name,
            }
            for row in self._session.execute(meta_q).all()
        }

        enriched = [
            PriceMoverEntry(
                source_product_id=m.source_product_id,
                external_id=meta.get(m.source_product_id, {}).get("external_id", ""),
                source_name=meta.get(m.source_product_id, {}).get("source_name", ""),
                canonical_name=meta.get(m.source_product_id, {}).get("canonical_name"),
                currency=m.currency,
                first_price=m.first_price,
                last_price=m.last_price,
                price_change_absolute=m.price_change_absolute,
                price_change_percent=m.price_change_percent,
                observation_count=m.observation_count,
            )
            for m in movers
        ]

        return PriceMoverResult(items=enriched)

    def list_price_statistics(
        self,
        days_back: int = 30,
    ) -> list[PriceStatistics]:
        """Return per-source, per-currency aggregate price statistics.

        Groups by both source and currency so that unlike currencies are
        never aggregated together.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

        q = (
            select(
                Source.id.label("source_id"),
                Source.name.label("source_name"),
                ProductObservation.currency,
                func.count(ProductObservation.id).label("obs_count"),
                func.count(ProductObservation.price).label("with_price"),
                func.min(
                    case((ProductObservation.price.is_not(None), ProductObservation.price))
                ).label("min_p"),
                func.max(
                    case((ProductObservation.price.is_not(None), ProductObservation.price))
                ).label("max_p"),
                func.avg(
                    case((ProductObservation.price.is_not(None), ProductObservation.price))
                ).label("avg_p"),
            )
            .join(SourceProduct, SourceProduct.source_id == Source.id)
            .outerjoin(
                ProductObservation,
                (ProductObservation.source_product_id == SourceProduct.id)
                & (ProductObservation.collected_at >= cutoff),
            )
            .group_by(Source.id, Source.name, ProductObservation.currency)
            .order_by(func.count(ProductObservation.id).desc())
        )

        rows = self._session.execute(q).all()

        return [
            PriceStatistics(
                source_id=row.source_id,
                source_name=row.source_name,
                currency=row.currency,
                observation_count=row.obs_count,
                listings_with_price=row.with_price,
                min_price=row.min_p,
                max_price=row.max_p,
                avg_price=row.avg_p,
            )
            for row in rows
        ]
