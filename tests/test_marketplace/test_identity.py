"""Tests for marketplace identity mapping utilities (TASK-042)."""

from __future__ import annotations

import pytest

from libs.marketplace.identity import (
    ListingProductMapper,
    build_listing_id,
    build_product_key,
    build_seller_id,
    listing_id_to_external_id,
)

# ---------------------------------------------------------------------------
# build_listing_id
# ---------------------------------------------------------------------------


def test_build_listing_id_basic() -> None:
    assert build_listing_id("ebay", "12345") == "ebay:12345"


def test_build_listing_id_deterministic() -> None:
    a = build_listing_id("ebay", "12345")
    b = build_listing_id("ebay", "12345")
    assert a == b


def test_build_listing_id_different_sources() -> None:
    assert build_listing_id("ebay", "12345") != build_listing_id("other", "12345")


def test_build_listing_id_empty_source_rejected() -> None:
    with pytest.raises(ValueError, match="source must be non-empty"):
        build_listing_id("", "12345")


def test_build_listing_id_empty_id_rejected() -> None:
    with pytest.raises(ValueError, match="raw_listing_id must be non-empty"):
        build_listing_id("ebay", "")


# ---------------------------------------------------------------------------
# build_seller_id
# ---------------------------------------------------------------------------


def test_build_seller_id_basic() -> None:
    assert build_seller_id("ebay", "top-seller") == "ebay:top-seller"


def test_build_seller_id_deterministic() -> None:
    assert build_seller_id("ebay", "s1") == build_seller_id("ebay", "s1")


def test_build_seller_id_empty_source_rejected() -> None:
    with pytest.raises(ValueError, match="source must be non-empty"):
        build_seller_id("", "s1")


def test_build_seller_id_empty_id_rejected() -> None:
    with pytest.raises(ValueError, match="raw_seller_id must be non-empty"):
        build_seller_id("ebay", "")


# ---------------------------------------------------------------------------
# build_product_key
# ---------------------------------------------------------------------------


def test_build_product_key_basic() -> None:
    assert build_product_key("ebay", "UPC-0001") == "ebay:UPC-0001"


def test_build_product_key_deterministic() -> None:
    assert build_product_key("ebay", "p1") == build_product_key("ebay", "p1")


def test_build_product_key_empty_source_rejected() -> None:
    with pytest.raises(ValueError, match="source must be non-empty"):
        build_product_key("", "p1")


def test_build_product_key_empty_id_rejected() -> None:
    with pytest.raises(ValueError, match="product_identifier must be non-empty"):
        build_product_key("ebay", "")


# ---------------------------------------------------------------------------
# listing_id_to_external_id (decomposition)
# ---------------------------------------------------------------------------


def test_listing_id_to_external_id_basic() -> None:
    source, raw = listing_id_to_external_id("ebay:12345")
    assert source == "ebay"
    assert raw == "12345"


def test_listing_id_to_external_id_with_colon_in_raw_id() -> None:
    """Raw IDs containing colons are preserved (split on first colon only)."""
    source, raw = listing_id_to_external_id("ebay:abc:def:123")
    assert source == "ebay"
    assert raw == "abc:def:123"


def test_listing_id_to_external_id_invalid_no_colon() -> None:
    with pytest.raises(ValueError, match="invalid qualified listing id"):
        listing_id_to_external_id("nocolon")


def test_listing_id_to_external_id_invalid_empty_source() -> None:
    with pytest.raises(ValueError, match="invalid qualified listing id"):
        listing_id_to_external_id(":12345")


def test_listing_id_to_external_id_invalid_empty_id() -> None:
    with pytest.raises(ValueError, match="invalid qualified listing id"):
        listing_id_to_external_id("ebay:")


def test_listing_id_round_trip() -> None:
    """build_listing_id -> listing_id_to_external_id is lossless."""
    qualified = build_listing_id("ebay", "12345")
    source, raw = listing_id_to_external_id(qualified)
    assert source == "ebay"
    assert raw == "12345"
    assert build_listing_id(source, raw) == qualified


# ---------------------------------------------------------------------------
# ListingProductMapper
# ---------------------------------------------------------------------------


def test_mapper_assign_and_get() -> None:
    mapper = ListingProductMapper()
    mapper.assign("ebay:L-001", "ebay:UPC-0001")
    assert mapper.get_product_key("ebay:L-001") == "ebay:UPC-0001"


def test_mapper_get_unmapped_returns_none() -> None:
    mapper = ListingProductMapper()
    assert mapper.get_product_key("ebay:unknown") is None


def test_mapper_multiple_listings_same_product() -> None:
    mapper = ListingProductMapper()
    mapper.assign("ebay:L-001", "ebay:UPC-0001")
    mapper.assign("ebay:L-002", "ebay:UPC-0001")

    assert mapper.get_product_key("ebay:L-001") == "ebay:UPC-0001"
    assert mapper.get_product_key("ebay:L-002") == "ebay:UPC-0001"
    assert mapper.get_listing_ids("ebay:UPC-0001") == {"ebay:L-001", "ebay:L-002"}
    assert mapper.product_count == 1
    assert mapper.listing_count == 2


def test_mapper_reassign_listing_to_new_product() -> None:
    """Re-assigning a listing moves it from the old product."""
    mapper = ListingProductMapper()
    mapper.assign("ebay:L-001", "ebay:PROD-A")
    mapper.assign("ebay:L-001", "ebay:PROD-B")

    assert mapper.get_product_key("ebay:L-001") == "ebay:PROD-B"
    assert mapper.get_listing_ids("ebay:PROD-A") == set()
    assert mapper.get_listing_ids("ebay:PROD-B") == {"ebay:L-001"}
    assert mapper.listing_count == 1


def test_mapper_reassign_same_product_is_noop() -> None:
    mapper = ListingProductMapper()
    mapper.assign("ebay:L-001", "ebay:PROD-A")
    mapper.assign("ebay:L-001", "ebay:PROD-A")
    assert mapper.listing_count == 1
    assert mapper.product_count == 1


def test_mapper_get_listing_ids_unknown_product() -> None:
    mapper = ListingProductMapper()
    assert mapper.get_listing_ids("ebay:unknown") == set()


def test_mapper_has_listing() -> None:
    mapper = ListingProductMapper()
    mapper.assign("ebay:L-001", "ebay:P1")
    assert mapper.has_listing("ebay:L-001") is True
    assert mapper.has_listing("ebay:L-999") is False


def test_mapper_has_product() -> None:
    mapper = ListingProductMapper()
    mapper.assign("ebay:L-001", "ebay:P1")
    assert mapper.has_product("ebay:P1") is True
    assert mapper.has_product("ebay:P999") is False


def test_mapper_counts() -> None:
    mapper = ListingProductMapper()
    assert mapper.listing_count == 0
    assert mapper.product_count == 0

    mapper.assign("ebay:L-001", "ebay:P1")
    mapper.assign("ebay:L-002", "ebay:P1")
    mapper.assign("ebay:L-003", "ebay:P2")
    assert mapper.listing_count == 3
    assert mapper.product_count == 2


def test_mapper_clear() -> None:
    mapper = ListingProductMapper()
    mapper.assign("ebay:L-001", "ebay:P1")
    mapper.clear()
    assert mapper.listing_count == 0
    assert mapper.product_count == 0
    assert mapper.get_product_key("ebay:L-001") is None


def test_mapper_empty_listing_id_rejected() -> None:
    mapper = ListingProductMapper()
    with pytest.raises(ValueError, match="qualified_listing_id must be non-empty"):
        mapper.assign("", "ebay:P1")


def test_mapper_empty_product_key_rejected() -> None:
    mapper = ListingProductMapper()
    with pytest.raises(ValueError, match="product_key must be non-empty"):
        mapper.assign("ebay:L-001", "")


def test_mapper_idempotent_assign() -> None:
    """Assigning the same mapping twice is idempotent (important for replay)."""
    mapper = ListingProductMapper()
    mapper.assign("ebay:L-001", "ebay:P1")
    mapper.assign("ebay:L-001", "ebay:P1")
    assert mapper.listing_count == 1
    assert mapper.product_count == 1
    assert mapper.get_listing_ids("ebay:P1") == {"ebay:L-001"}


# ---------------------------------------------------------------------------
# Cross-source isolation
# ---------------------------------------------------------------------------


def test_different_sources_same_raw_id_are_distinct() -> None:
    """Two sources using the same raw listing ID produce different identities."""
    listing_a = build_listing_id("ebay", "12345")
    listing_b = build_listing_id("other", "12345")
    assert listing_a != listing_b

    mapper = ListingProductMapper()
    mapper.assign(listing_a, build_product_key("ebay", "P1"))
    mapper.assign(listing_b, build_product_key("other", "P1"))

    assert mapper.get_product_key(listing_a) == "ebay:P1"
    assert mapper.get_product_key(listing_b) == "other:P1"
    assert mapper.listing_count == 2
    assert mapper.product_count == 2
