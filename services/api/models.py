"""Read-only SQLAlchemy ORM models mapping the warehouse schema.

These models are used exclusively by the API service for queries.
Write operations remain in the warehouse loader (raw SQL).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import TIMESTAMP, BigInteger, Float, ForeignKey, Integer, Numeric, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Shared declarative base for read-only warehouse models."""


class Source(Base):
    """Registry of external data sources."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    source_products: Mapped[list[SourceProduct]] = relationship(back_populates="source")


class Product(Base):
    """Canonical product identity independent of source-specific listings."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    canonical_name: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    source_products: Mapped[list[SourceProduct]] = relationship(back_populates="product")


class SourceProduct(Base):
    """Maps source-specific listings to canonical products."""

    __tablename__ = "source_products"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    source: Mapped[Source] = relationship(back_populates="source_products")
    product: Mapped[Product] = relationship(back_populates="source_products")
    observations: Mapped[list[ProductObservation]] = relationship(back_populates="source_product")


class ProductObservation(Base):
    """Historical record of every observed listing state."""

    __tablename__ = "product_observations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("source_products.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[Optional[str]] = mapped_column(Text)
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(precision=12, scale=2))
    currency: Mapped[Optional[str]] = mapped_column(Text)
    availability: Mapped[str] = mapped_column(Text, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    event_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    source_product: Mapped[SourceProduct] = relationship(back_populates="observations")


class PipelineRun(Base):
    """Metadata about each pipeline execution that loads data into the warehouse."""

    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    records_loaded: Mapped[Optional[int]] = mapped_column(BigInteger)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON)


class IngestionHealthResult(Base):
    """Periodic source health assessments from the ingestion_health DAG."""

    __tablename__ = "ingestion_health_results"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    freshness_state: Mapped[str] = mapped_column(Text, nullable=False)
    reasons: Mapped[Optional[dict]] = mapped_column(JSON)
    signals: Mapped[Optional[dict]] = mapped_column(JSON)
    freshness_age_seconds: Mapped[Optional[float]] = mapped_column(Float)
    assessed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    logical_date: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    replay_key: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
