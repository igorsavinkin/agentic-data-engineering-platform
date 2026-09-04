"""Canonical product-observation event contract.

This module defines the versioned envelope and payload for product
observation events published to Kafka by ingestion adapters and consumed
by the processor and raw writer.

The contract follows ``ai/SPECIFICATION.md`` §7 (Event Contract) and
§9 (Delivery Semantics): events are at-least-once, so consumers must
tolerate duplicate ``event_id`` values. The event model preserves the
stable identifiers required for downstream idempotent processing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

SUPPORTED_SCHEMA_VERSIONS: frozenset[int] = frozenset({1})
CURRENT_SCHEMA_VERSION: int = 1


class Availability(str, Enum):
    """Allowed availability values for product observations."""

    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    PREORDER = "preorder"
    UNKNOWN = "unknown"


class ProductObservationPayload(BaseModel):
    """Canonical payload for a product observation.

    ``external_id`` is the source-provided product/listing identifier and
    must not be confused with the platform-assigned ``products.id`` used in
    the warehouse.
    """

    model_config = {"str_strip_whitespace": True}

    external_id: str = Field(
        ...,
        min_length=1,
        description="Source-provided product/listing identifier.",
    )
    name: str = Field(..., min_length=1, description="Product name.")
    url: str = Field(..., min_length=1, description="Canonical product URL.")
    price: Decimal | None = Field(
        ...,
        description="Observed price; null when the source does not provide a usable price.",
    )
    currency: str = Field(
        ...,
        pattern=r"^[A-Z]{3}$",
        description="ISO-4217 currency code (three uppercase letters).",
    )
    availability: Availability = Field(
        ...,
        description="Availability state at observation time.",
    )
    category: str = Field(..., min_length=1, description="Product category.")
    collected_at: datetime = Field(
        ...,
        description="Timestamp when the observation was collected from the source.",
    )

    @field_validator("price", mode="after")
    @classmethod
    def _validate_price_non_negative(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return value
        if value < 0:
            raise ValueError("price must be non-negative when provided")
        return value

    @field_validator("collected_at", mode="after")
    @classmethod
    def _validate_collected_at_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("collected_at must be timezone-aware")
        return value


class ProductObservationEvent(BaseModel):
    """Canonical envelope for product-observation events.

    ``produced_at`` records event publication time and must not be used as a
    substitute for ``payload.collected_at``.
    """

    model_config = {"str_strip_whitespace": True}

    event_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for this observation event.",
    )
    event_type: Literal["product.observation"] = "product.observation"
    schema_version: int = Field(
        default=CURRENT_SCHEMA_VERSION,
        ge=1,
        description="Event schema version; unsupported versions are rejected.",
    )
    source: str = Field(
        ...,
        min_length=1,
        description="Source adapter that produced the event.",
    )
    produced_at: datetime = Field(
        ...,
        description="Timestamp when the event was published to Kafka.",
    )
    payload: ProductObservationPayload = Field(
        ...,
        description="Canonical product observation payload.",
    )

    @field_validator("schema_version", mode="after")
    @classmethod
    def _validate_schema_version(cls, value: int) -> int:
        if value not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(
                f"unsupported schema version {value}; "
                f"supported versions: {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
            )
        return value

    @field_validator("produced_at", mode="after")
    @classmethod
    def _validate_produced_at_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("produced_at must be timezone-aware")
        return value

    @property
    def partition_key(self) -> str:
        """Deterministic Kafka partition key preserving source/product order."""
        return f"{self.source}:{self.payload.external_id}"


def serialize_event(event: ProductObservationEvent) -> str:
    """Serialize a validated event to a deterministic JSON string."""
    return event.model_dump_json()


def deserialize_event(data: str | dict[str, Any]) -> ProductObservationEvent:
    """Deserialize and validate a JSON string or dict into an event.

    Raises:
        pydantic.ValidationError: when the data violates the contract.
    """
    if isinstance(data, str):
        return ProductObservationEvent.model_validate_json(data)
    return ProductObservationEvent.model_validate(data)


def make_event_id(source: str, external_id: str, collected_at: datetime) -> str:
    """Build a deterministic event id from stable observation identifiers.

    This helper is optional; producers may generate event ids with any
    scheme as long as they are unique per observation event. The
    deterministic form is useful for tests and replay scenarios.
    """
    return f"{source}:{external_id}:{collected_at.isoformat()}"


def utc_now() -> datetime:
    """Return the current UTC timestamp for use in event timestamps."""
    return datetime.now(timezone.utc)
