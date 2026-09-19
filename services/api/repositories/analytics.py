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
    prev_currency: Optional[str]
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
    observations_with_price: int
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

        LAG is computed over the full observation history per source-product,
        then ``from_date`` is applied as an outer filter so the first in-window
        observation retains its correct predecessor delta.  Deltas are only
        computed when the current and previous currencies match.
        """
        prev_price = func.lag(ProductObservation.price).over(
            partition_by=ProductObservation.source_product_id,
            order_by=ProductObservation.collected_at.asc(),
        )
        prev_currency = func.lag(ProductObservation.currency).over(
            partition_by=ProductObservation.source_product_id,
            order_by=ProductObservation.collected_at.asc(),
        )

        base_q = (
            select(
                ProductObservation.id.label("observation_id"),
                ProductObservation.source_product_id,
                ProductObservation.name,
                ProductObservation.price,
                ProductObservation.currency,
                ProductObservation.collected_at,
                prev_price.label("prev_price"),
                prev_currency.label("prev_currency"),
                SourceProduct.external_id,
                Source.name.label("source_name"),
            )
            .join(SourceProduct, SourceProduct.id == ProductObservation.source_product_id)
            .join(Source, Source.id == SourceProduct.source_id)
        )

        if source_product_id is not None:
            base_q = base_q.where(ProductObservation.source_product_id == source_product_id)

        base_subq = base_q.subquery()

        same_currency = (base_subq.c.prev_currency != None) & (  # noqa: E711
            base_subq.c.currency == base_subq.c.prev_currency
        )
        change_abs = case(
            (
                (base_subq.c.prev_price != None) & same_currency,  # noqa: E711
                base_subq.c.price - base_subq.c.prev_price,
            ),
        )
        change_pct = case(
            (
                (base_subq.c.prev_price != None) & (base_subq.c.prev_price > 0) & same_currency,  # noqa: E711
                func.round(
                    (base_subq.c.price - base_subq.c.prev_price) / base_subq.c.prev_price * 100,
                    2,
                ),
            ),
        )

        enriched_q = select(
            base_subq,
            change_abs.label("price_change_absolute"),
            change_pct.label("price_change_percent"),
        )
        enriched_subq = enriched_q.subquery()

        filtered = select(enriched_subq)
        if from_date is not None:
            filtered = filtered.where(enriched_subq.c.collected_at >= from_date)
        filtered_subq = filtered.subquery()

        total = self._session.execute(select(func.count()).select_from(filtered_subq)).scalar() or 0

        offset = (page - 1) * page_size
        rows = self._session.execute(
            select(filtered_subq)
            .order_by(filtered_subq.c.collected_at.desc())
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
                collected_at=row.collected_at.isoformat(),
                prev_price=row.prev_price,
                prev_currency=row.prev_currency,
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

        Uses a two-phase approach: an aggregate query identifies candidate
        source-products, then two batched queries fetch chronological
        first/last prices.  Only source-products where the first and last
        observations share the same currency are included.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

        agg_q = (
            select(
                ProductObservation.source_product_id,
                func.count().label("obs_count"),
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

        counts = {row.source_product_id: row.obs_count for row in agg_rows}
        sp_ids = list(counts.keys())

        first_q = (
            select(
                ProductObservation.source_product_id,
                ProductObservation.price,
                ProductObservation.currency,
            )
            .where(ProductObservation.source_product_id.in_(sp_ids))
            .where(ProductObservation.collected_at >= cutoff)
            .where(ProductObservation.price.is_not(None))
            .order_by(ProductObservation.source_product_id, ProductObservation.collected_at.asc())
        )
        first_prices: dict[int, tuple[Decimal, str]] = {}
        for row in self._session.execute(first_q).all():
            if row.source_product_id not in first_prices:
                first_prices[row.source_product_id] = (row.price, row.currency)

        last_q = (
            select(
                ProductObservation.source_product_id,
                ProductObservation.price,
                ProductObservation.currency,
            )
            .where(ProductObservation.source_product_id.in_(sp_ids))
            .where(ProductObservation.collected_at >= cutoff)
            .where(ProductObservation.price.is_not(None))
            .order_by(ProductObservation.source_product_id, ProductObservation.collected_at.desc())
        )
        last_prices: dict[int, tuple[Decimal, str]] = {}
        for row in self._session.execute(last_q).all():
            if row.source_product_id not in last_prices:
                last_prices[row.source_product_id] = (row.price, row.currency)

        movers: list[PriceMoverEntry] = []
        for sp_id in sp_ids:
            if sp_id not in first_prices or sp_id not in last_prices:
                continue
            fp, fc = first_prices[sp_id]
            lp, lc = last_prices[sp_id]
            if fc != lc:
                continue
            abs_change = lp - fp
            pct = float(abs_change / fp * 100) if fp > 0 else 0.0
            movers.append(
                PriceMoverEntry(
                    source_product_id=sp_id,
                    external_id="",
                    source_name="",
                    canonical_name=None,
                    currency=fc,
                    first_price=fp,
                    last_price=lp,
                    price_change_absolute=abs_change,
                    price_change_percent=Decimal(str(round(pct, 2))),
                    observation_count=counts[sp_id],
                )
            )

        movers.sort(key=lambda m: float(m.price_change_percent), reverse=True)
        movers = movers[:limit]

        if not movers:
            return PriceMoverResult(items=[])

        sp_ids_top = [m.source_product_id for m in movers]
        meta_q = (
            select(
                SourceProduct.id,
                SourceProduct.external_id,
                Source.name.label("source_name"),
                Product.canonical_name,
            )
            .join(Source, Source.id == SourceProduct.source_id)
            .join(Product, Product.id == SourceProduct.product_id)
            .where(SourceProduct.id.in_(sp_ids_top))
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
                observations_with_price=row.with_price,
                min_price=row.min_p,
                max_price=row.max_p,
                avg_price=row.avg_p,
            )
            for row in rows
        ]
