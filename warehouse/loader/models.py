"""Data models for mapping Silver Parquet rows to warehouse database records.

This module defines typed dataclasses that represent the transformation from
Silver Parquet event data into the relational warehouse schema (sources,
products, source_products, product_observations).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class SourceRecord:
    """Represents a source to be upserted into the sources table."""

    name: str
    description: str | None = None


@dataclass(frozen=True)
class ProductRecord:
    """Represents a canonical product to be upserted into the products table."""

    canonical_name: str | None = None
    category: str | None = None


@dataclass(frozen=True)
class SourceProductRecord:
    """Maps a source-specific listing to a canonical product."""

    source_id: int
    product_id: int
    external_id: str
    url: str | None = None


@dataclass(frozen=True)
class ObservationRecord:
    """A single product observation (historical record)."""

    source_product_id: int
    availability: str
    collected_at: datetime
    event_id: str
    name: str | None = None
    price: Decimal | None = None
    currency: str | None = None


@dataclass
class MappedRow:
    """Complete mapping of one Silver Parquet row into warehouse entities.

    Contains all four entity types that may need to be created/updated for
    a single input row. Some fields may be None if the entity already exists
    or if the row doesn't require creating that entity.
    """

    source: SourceRecord | None = None
    product: ProductRecord | None = None
    source_product: SourceProductRecord | None = None
    observation: ObservationRecord | None = None
