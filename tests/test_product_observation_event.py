"""Tests for the canonical product-observation event contract (TASK-006)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from libs.event_contracts import (
    Availability,
    ProductObservationEvent,
    ProductObservationPayload,
    deserialize_event,
    make_event_id,
    serialize_event,
    utc_now,
)


def _valid_payload_dict() -> dict[str, object]:
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


def _valid_event_dict() -> dict[str, object]:
    return {
        "event_id": "evt-001",
        "event_type": "product.observation",
        "schema_version": 1,
        "source": "example-source",
        "produced_at": datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc),
        "payload": _valid_payload_dict(),
    }


def test_valid_event_creation() -> None:
    event = ProductObservationEvent(**_valid_event_dict())

    assert event.event_id == "evt-001"
    assert event.event_type == "product.observation"
    assert event.schema_version == 1
    assert event.source == "example-source"
    assert event.produced_at == datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc)
    assert event.payload.external_id == "sku-12345"
    assert event.payload.name == "Wireless Headphones"
    assert event.payload.price == Decimal("149.99")
    assert event.payload.currency == "EUR"
    assert event.payload.availability == Availability.IN_STOCK
    assert event.payload.category == "electronics"
    assert event.payload.collected_at == datetime(2026, 9, 3, 7, 59, 30, tzinfo=timezone.utc)


def test_deterministic_serialization_and_deserialization() -> None:
    event = ProductObservationEvent(**_valid_event_dict())

    serialized_a = serialize_event(event)
    serialized_b = serialize_event(event)
    assert serialized_a == serialized_b

    deserialized = deserialize_event(serialized_a)
    assert deserialized == event

    # JSON structure contains the expected contract fields.
    parsed = json.loads(serialized_a)
    assert parsed["event_id"] == "evt-001"
    assert parsed["payload"]["external_id"] == "sku-12345"
    assert Decimal(parsed["payload"]["price"]) == Decimal("149.99")
    assert parsed["payload"]["currency"] == "EUR"


def test_missing_required_envelope_field() -> None:
    data = _valid_event_dict()
    del data["source"]

    with pytest.raises(ValidationError) as exc_info:
        ProductObservationEvent(**data)

    assert "source" in str(exc_info.value)


def test_missing_required_payload_field() -> None:
    data = _valid_event_dict()
    payload = dict(_valid_payload_dict())
    del payload["name"]
    data["payload"] = payload

    with pytest.raises(ValidationError) as exc_info:
        ProductObservationEvent(**data)

    assert "name" in str(exc_info.value)


def test_invalid_produced_at_naive() -> None:
    data = _valid_event_dict()
    data["produced_at"] = datetime(2026, 9, 3, 8, 0, 0)

    with pytest.raises(ValidationError) as exc_info:
        ProductObservationEvent(**data)

    assert "produced_at" in str(exc_info.value)
    assert "timezone-aware" in str(exc_info.value)


def test_invalid_collected_at_naive() -> None:
    data = _valid_event_dict()
    data["payload"] = {
        **_valid_payload_dict(),
        "collected_at": datetime(2026, 9, 3, 7, 59, 30),
    }

    with pytest.raises(ValidationError) as exc_info:
        ProductObservationEvent(**data)

    assert "collected_at" in str(exc_info.value)
    assert "timezone-aware" in str(exc_info.value)


def test_negative_price() -> None:
    data = _valid_event_dict()
    data["payload"] = {**_valid_payload_dict(), "price": Decimal("-0.01")}

    with pytest.raises(ValidationError) as exc_info:
        ProductObservationEvent(**data)

    assert "price" in str(exc_info.value)
    assert "non-negative" in str(exc_info.value)


def test_null_price() -> None:
    data = _valid_event_dict()
    data["payload"] = {**_valid_payload_dict(), "price": None}

    event = ProductObservationEvent(**data)
    assert event.payload.price is None

    deserialized = deserialize_event(serialize_event(event))
    assert deserialized.payload.price is None


def test_invalid_price_type() -> None:
    data = _valid_event_dict()
    data["payload"] = {**_valid_payload_dict(), "price": "not-a-number"}

    with pytest.raises(ValidationError) as exc_info:
        ProductObservationEvent(**data)

    assert "price" in str(exc_info.value)


def test_invalid_availability_enum_value() -> None:
    data = _valid_event_dict()
    data["payload"] = {**_valid_payload_dict(), "availability": "back_soon"}

    with pytest.raises(ValidationError) as exc_info:
        ProductObservationEvent(**data)

    assert "availability" in str(exc_info.value)


def test_invalid_currency() -> None:
    data = _valid_event_dict()
    data["payload"] = {**_valid_payload_dict(), "currency": "euro"}

    with pytest.raises(ValidationError) as exc_info:
        ProductObservationEvent(**data)

    assert "currency" in str(exc_info.value)


def test_unsupported_schema_version() -> None:
    data = _valid_event_dict()
    data["schema_version"] = 99

    with pytest.raises(ValidationError) as exc_info:
        ProductObservationEvent(**data)

    assert "schema_version" in str(exc_info.value)
    assert "unsupported schema version" in str(exc_info.value)


def test_duplicate_event_id_is_stable() -> None:
    event_a = ProductObservationEvent(**_valid_event_dict())
    event_b = ProductObservationEvent(**_valid_event_dict())

    assert event_a.event_id == event_b.event_id
    assert serialize_event(event_a) == serialize_event(event_b)
    assert event_a == event_b


def test_external_id_is_distinct_from_product_id() -> None:
    event = ProductObservationEvent(**_valid_event_dict())

    assert event.payload.external_id == "sku-12345"
    assert "product_id" not in ProductObservationPayload.model_fields
    assert "product_id" not in ProductObservationEvent.model_fields


def test_event_type_defaults_to_product_observation() -> None:
    data = _valid_event_dict()
    del data["event_type"]

    event = ProductObservationEvent(**data)
    assert event.event_type == "product.observation"


def test_partition_key_is_source_and_external_id() -> None:
    event = ProductObservationEvent(**_valid_event_dict())
    assert event.partition_key == "example-source:sku-12345"


def test_make_event_id_is_deterministic() -> None:
    collected_at = utc_now()
    event_id = make_event_id("example-source", "sku-12345", collected_at)
    assert event_id == f"example-source:sku-12345:{collected_at.isoformat()}"


def test_collected_at_and_produced_at_are_distinct() -> None:
    collected_at = datetime(2026, 9, 3, 7, 59, 30, tzinfo=timezone.utc)
    produced_at = collected_at + timedelta(seconds=30)
    data = _valid_event_dict()
    data["produced_at"] = produced_at
    data["payload"] = {**_valid_payload_dict(), "collected_at": collected_at}

    event = ProductObservationEvent(**data)
    assert event.produced_at == produced_at
    assert event.payload.collected_at == collected_at
    assert event.produced_at != event.payload.collected_at


def test_empty_external_id_is_rejected() -> None:
    data = _valid_event_dict()
    data["payload"] = {**_valid_payload_dict(), "external_id": ""}

    with pytest.raises(ValidationError) as exc_info:
        ProductObservationEvent(**data)

    assert "external_id" in str(exc_info.value)
