"""Tests for event contract backward compatibility with marketplace fields (TASK-042).

These tests verify that:
1. Existing events without listing_id / seller_id continue to work (backward
   compatibility).
2. New events can carry optional marketplace fields.
3. Malformed marketplace field values are rejected.
4. Serialisation round-trips preserve marketplace fields.
5. The partition key and event-id helpers remain stable.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from libs.event_contracts import (
    ProductObservationEvent,
    ProductObservationPayload,
    deserialize_event,
    serialize_event,
)


def _base_payload_kwargs() -> dict[str, object]:
    return {
        "external_id": "sku-12345",
        "name": "Wireless Headphones",
        "url": "https://example.com/products/sku-12345",
        "price": Decimal("149.99"),
        "currency": "EUR",
        "availability": "in_stock",
        "category": "electronics",
        "collected_at": datetime(2026, 9, 3, 7, 59, 30, tzinfo=timezone.utc),
    }


def _base_event_kwargs() -> dict[str, object]:
    return {
        "event_id": "evt-001",
        "event_type": "product.observation",
        "schema_version": 1,
        "source": "example-source",
        "produced_at": datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc),
        "payload": _base_payload_kwargs(),
    }


# ---------------------------------------------------------------------------
# Backward compatibility — existing events without marketplace fields
# ---------------------------------------------------------------------------


def test_payload_without_marketplace_fields() -> None:
    """Non-marketplace sources must continue to work unchanged."""
    payload = ProductObservationPayload(**_base_payload_kwargs())
    assert payload.listing_id is None
    assert payload.seller_id is None


def test_event_without_marketplace_fields() -> None:
    """Full event construction works without marketplace fields."""
    event = ProductObservationEvent(**_base_event_kwargs())
    assert event.payload.listing_id is None
    assert event.payload.seller_id is None


def test_serialization_without_marketplace_fields() -> None:
    """Serialized events without marketplace fields round-trip correctly."""
    event = ProductObservationEvent(**_base_event_kwargs())
    serialized = serialize_event(event)
    deserialized = deserialize_event(serialized)
    assert deserialized == event
    assert deserialized.payload.listing_id is None
    assert deserialized.payload.seller_id is None


def test_existing_json_without_marketplace_fields_still_valid() -> None:
    """A JSON event produced before the marketplace fields existed is still valid.

    This simulates replay of legacy events from Kafka / Bronze Parquet.
    """
    legacy_json = json.dumps(
        {
            "event_id": "evt-legacy",
            "event_type": "product.observation",
            "schema_version": 1,
            "source": "fake_store",
            "produced_at": "2026-09-03T08:00:00+00:00",
            "payload": {
                "external_id": "1",
                "name": "Legacy Product",
                "url": "https://example.com/1",
                "price": "9.99",
                "currency": "USD",
                "availability": "in_stock",
                "category": "test",
                "collected_at": "2026-09-03T07:59:30+00:00",
            },
        }
    )
    event = deserialize_event(legacy_json)
    assert event.payload.listing_id is None
    assert event.payload.seller_id is None
    assert event.payload.external_id == "1"


# ---------------------------------------------------------------------------
# New marketplace fields
# ---------------------------------------------------------------------------


def test_payload_with_listing_id() -> None:
    payload = ProductObservationPayload(**{**_base_payload_kwargs(), "listing_id": "L-001"})
    assert payload.listing_id == "L-001"
    assert payload.seller_id is None


def test_payload_with_seller_id() -> None:
    payload = ProductObservationPayload(**{**_base_payload_kwargs(), "seller_id": "S-001"})
    assert payload.listing_id is None
    assert payload.seller_id == "S-001"


def test_payload_with_both_marketplace_fields() -> None:
    payload = ProductObservationPayload(
        **{
            **_base_payload_kwargs(),
            "listing_id": "L-001",
            "seller_id": "S-001",
        }
    )
    assert payload.listing_id == "L-001"
    assert payload.seller_id == "S-001"


def test_event_with_marketplace_fields() -> None:
    payload_dict = {
        **_base_payload_kwargs(),
        "listing_id": "ebay:12345",
        "seller_id": "ebay:top-seller",
    }
    event = ProductObservationEvent(**{**_base_event_kwargs(), "payload": payload_dict})
    assert event.payload.listing_id == "ebay:12345"
    assert event.payload.seller_id == "ebay:top-seller"


# ---------------------------------------------------------------------------
# Malformed marketplace fields
# ---------------------------------------------------------------------------


def test_empty_listing_id_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ProductObservationPayload(**{**_base_payload_kwargs(), "listing_id": ""})
    assert "listing_id" in str(exc_info.value)


def test_empty_seller_id_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ProductObservationPayload(**{**_base_payload_kwargs(), "seller_id": ""})
    assert "seller_id" in str(exc_info.value)


def test_whitespace_only_listing_id_rejected() -> None:
    """str_strip_whitespace turns "   " into "" which violates min_length."""
    with pytest.raises(ValidationError):
        ProductObservationPayload(**{**_base_payload_kwargs(), "listing_id": "   "})


def test_whitespace_only_seller_id_rejected() -> None:
    with pytest.raises(ValidationError):
        ProductObservationPayload(**{**_base_payload_kwargs(), "seller_id": "   "})


# ---------------------------------------------------------------------------
# Serialization round-trip with marketplace fields
# ---------------------------------------------------------------------------


def test_marketplace_fields_survive_serialization() -> None:
    payload_dict = {
        **_base_payload_kwargs(),
        "listing_id": "ebay:12345",
        "seller_id": "ebay:seller-42",
    }
    event = ProductObservationEvent(
        **{**_base_event_kwargs(), "payload": payload_dict, "source": "ebay"}
    )
    serialized = serialize_event(event)
    deserialized = deserialize_event(serialized)

    assert deserialized.payload.listing_id == "ebay:12345"
    assert deserialized.payload.seller_id == "ebay:seller-42"
    assert deserialized == event


def test_marketplace_fields_in_json() -> None:
    """Verify marketplace fields appear in the serialized JSON."""
    payload_dict = {
        **_base_payload_kwargs(),
        "listing_id": "L-001",
        "seller_id": "S-001",
    }
    event = ProductObservationEvent(**{**_base_event_kwargs(), "payload": payload_dict})
    parsed = json.loads(serialize_event(event))
    assert parsed["payload"]["listing_id"] == "L-001"
    assert parsed["payload"]["seller_id"] == "S-001"


def test_null_marketplace_fields_in_json() -> None:
    """When marketplace fields are None, they serialise as null."""
    event = ProductObservationEvent(**_base_event_kwargs())
    parsed = json.loads(serialize_event(event))
    assert parsed["payload"]["listing_id"] is None
    assert parsed["payload"]["seller_id"] is None


# ---------------------------------------------------------------------------
# Partition key and event ID stability
# ---------------------------------------------------------------------------


def test_partition_key_unchanged_with_marketplace_fields() -> None:
    """Adding marketplace fields does not change the partition key.

    The partition key is source + external_id, which preserves per-source
    ordering.  Marketplace fields are additional metadata, not part of
    the partitioning strategy.
    """
    event_without = ProductObservationEvent(**_base_event_kwargs())

    payload_with = {
        **_base_payload_kwargs(),
        "listing_id": "L-001",
        "seller_id": "S-001",
    }
    event_with = ProductObservationEvent(**{**_base_event_kwargs(), "payload": payload_with})

    assert event_without.partition_key == event_with.partition_key


def test_schema_version_still_one() -> None:
    """Adding optional nullable fields is a compatible change; version stays 1."""
    event = ProductObservationEvent(**_base_event_kwargs())
    assert event.schema_version == 1
