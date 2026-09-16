"""Tests for the generic MarketplaceListing model (TASK-042)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from libs.marketplace.listing import MarketplaceListing
from libs.marketplace.seller import Seller


def _make_seller(seller_id: str = "s-001", source: str = "ebay") -> Seller:
    return Seller(seller_id=seller_id, source=source)


# ---------------------------------------------------------------------------
# Construction and field validation
# ---------------------------------------------------------------------------


def test_listing_minimal_construction() -> None:
    """A listing requires listing_id, source, title, and url."""
    listing = MarketplaceListing(
        listing_id="L-001",
        source="ebay",
        title="Widget",
        url="https://ebay.com/itm/L-001",
    )
    assert listing.listing_id == "L-001"
    assert listing.source == "ebay"
    assert listing.seller is None
    assert listing.product_key is None
    assert listing.metadata == {}


def test_listing_full_construction() -> None:
    """All optional fields can be provided."""
    seller = _make_seller()
    listing = MarketplaceListing(
        listing_id="L-001",
        source="ebay",
        seller=seller,
        product_key="ebay:UPC-0001",
        title="Widget",
        url="https://ebay.com/itm/L-001",
        metadata={"condition": "new"},
    )
    assert listing.seller == seller
    assert listing.product_key == "ebay:UPC-0001"
    assert listing.metadata["condition"] == "new"


def test_listing_empty_listing_id_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        MarketplaceListing(
            listing_id="",
            source="ebay",
            title="Widget",
            url="https://ebay.com/itm/L-001",
        )
    assert "listing_id" in str(exc_info.value)


def test_listing_empty_source_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        MarketplaceListing(
            listing_id="L-001",
            source="",
            title="Widget",
            url="https://ebay.com/itm/L-001",
        )
    assert "source" in str(exc_info.value)


def test_listing_empty_title_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        MarketplaceListing(
            listing_id="L-001",
            source="ebay",
            title="",
            url="https://ebay.com/itm/L-001",
        )
    assert "title" in str(exc_info.value)


def test_listing_empty_url_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        MarketplaceListing(
            listing_id="L-001",
            source="ebay",
            title="Widget",
            url="",
        )
    assert "url" in str(exc_info.value)


def test_listing_strips_whitespace() -> None:
    listing = MarketplaceListing(
        listing_id="  L-001  ",
        source="  ebay  ",
        title="  Widget  ",
        url="  https://ebay.com/itm/L-001  ",
    )
    assert listing.listing_id == "L-001"
    assert listing.source == "ebay"
    assert listing.title == "Widget"
    assert listing.url == "https://ebay.com/itm/L-001"


def test_listing_is_frozen() -> None:
    listing = MarketplaceListing(
        listing_id="L-001",
        source="ebay",
        title="Widget",
        url="https://ebay.com/itm/L-001",
    )
    with pytest.raises(ValidationError):
        listing.listing_id = "L-002"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Qualified ID
# ---------------------------------------------------------------------------


def test_qualified_id() -> None:
    listing = MarketplaceListing(
        listing_id="L-001",
        source="ebay",
        title="Widget",
        url="https://ebay.com/itm/L-001",
    )
    assert listing.qualified_id == "ebay:L-001"


# ---------------------------------------------------------------------------
# Multiple listings for same product
# ---------------------------------------------------------------------------


def test_multiple_listings_share_product_key() -> None:
    """Two sellers can list the same logical product."""
    product_key = "ebay:UPC-0001"
    listing_a = MarketplaceListing(
        listing_id="L-001",
        source="ebay",
        seller=_make_seller("seller-a"),
        product_key=product_key,
        title="Widget (Seller A)",
        url="https://ebay.com/itm/L-001",
    )
    listing_b = MarketplaceListing(
        listing_id="L-002",
        source="ebay",
        seller=_make_seller("seller-b"),
        product_key=product_key,
        title="Widget (Seller B)",
        url="https://ebay.com/itm/L-002",
    )
    assert listing_a.product_key == listing_b.product_key
    assert listing_a.listing_id != listing_b.listing_id
    assert listing_a.seller != listing_b.seller


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_listing_serialization_round_trip() -> None:
    seller = _make_seller()
    listing = MarketplaceListing(
        listing_id="L-001",
        source="ebay",
        seller=seller,
        product_key="ebay:UPC-0001",
        title="Widget",
        url="https://ebay.com/itm/L-001",
        metadata={"condition": "new"},
    )
    data = listing.model_dump()
    restored = MarketplaceListing.model_validate(data)
    assert restored == listing


def test_listing_json_round_trip() -> None:
    listing = MarketplaceListing(
        listing_id="L-001",
        source="ebay",
        title="Widget",
        url="https://ebay.com/itm/L-001",
    )
    json_str = listing.model_dump_json()
    restored = MarketplaceListing.model_validate_json(json_str)
    assert restored == listing
