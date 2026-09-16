"""Tests for SourceAdapterProtocol._build_event with marketplace fields (TASK-042).

Verifies that the protocol helper correctly passes optional listing_id and
seller_id through to the canonical event, and that omitting them preserves
backward compatibility.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from libs.adapters.protocol import FetchResult, SourceAdapterProtocol
from libs.event_contracts import ProductObservationEvent


class _TestableAdapter(SourceAdapterProtocol):
    """Minimal concrete adapter for testing the _build_event helper."""

    @property
    def source_name(self) -> str:
        return "test_source"

    async def fetch(self) -> FetchResult[Any]:
        raise NotImplementedError


def test_build_event_without_marketplace_fields() -> None:
    """Non-marketplace sources: listing_id and seller_id default to None."""
    event = _TestableAdapter._build_event(
        source="fake_store",
        external_id="123",
        name="Widget",
        url="https://example.com/123",
        price=9.99,
        currency="usd",
        availability="in_stock",
        category="gadgets",
        collected_at=datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc),
    )
    assert isinstance(event, ProductObservationEvent)
    assert event.payload.listing_id is None
    assert event.payload.seller_id is None
    assert event.payload.external_id == "123"
    assert event.source == "fake_store"


def test_build_event_with_marketplace_fields() -> None:
    """Marketplace sources can pass listing_id and seller_id."""
    event = _TestableAdapter._build_event(
        source="ebay",
        external_id="12345",
        name="Widget Listing",
        url="https://ebay.com/itm/12345",
        price=19.99,
        currency="USD",
        availability="in_stock",
        category="gadgets",
        collected_at=datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc),
        listing_id="ebay:12345",
        seller_id="ebay:top-seller",
    )
    assert event.payload.listing_id == "ebay:12345"
    assert event.payload.seller_id == "ebay:top-seller"
    assert event.source == "ebay"


def test_build_event_with_only_listing_id() -> None:
    """listing_id without seller_id is valid."""
    event = _TestableAdapter._build_event(
        source="ebay",
        external_id="12345",
        name="Widget",
        url="https://ebay.com/itm/12345",
        price=19.99,
        currency="USD",
        availability="in_stock",
        category="gadgets",
        collected_at=datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc),
        listing_id="ebay:12345",
    )
    assert event.payload.listing_id == "ebay:12345"
    assert event.payload.seller_id is None


def test_build_event_with_only_seller_id() -> None:
    """seller_id without listing_id is valid."""
    event = _TestableAdapter._build_event(
        source="ebay",
        external_id="12345",
        name="Widget",
        url="https://ebay.com/itm/12345",
        price=19.99,
        currency="USD",
        availability="in_stock",
        category="gadgets",
        collected_at=datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc),
        seller_id="ebay:seller-42",
    )
    assert event.payload.listing_id is None
    assert event.payload.seller_id == "ebay:seller-42"


def test_build_event_null_price_with_marketplace_fields() -> None:
    """Marketplace events with null price still work."""
    event = _TestableAdapter._build_event(
        source="ebay",
        external_id="12345",
        name="Widget",
        url="https://ebay.com/itm/12345",
        price=None,
        currency="USD",
        availability="unknown",
        category="gadgets",
        collected_at=datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc),
        listing_id="ebay:12345",
        seller_id="ebay:seller-42",
    )
    assert event.payload.price is None
    assert event.payload.listing_id == "ebay:12345"
