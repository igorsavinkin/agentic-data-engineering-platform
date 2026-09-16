"""Tests for marketplace identity mapping utilities (TASK-042)."""

from __future__ import annotations

import pytest

from libs.marketplace.identity import (
    ListingProductMapper,
    build_listing_id,
    build_product_key,
    build_seller_id,
    derive_product_key_from_listing,
    extract_product_identifier_from_metadata,
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


# ---------------------------------------------------------------------------
# extract_product_identifier_from_metadata (TASK-044)
# ---------------------------------------------------------------------------


def test_extract_upc_valid() -> None:
    """Valid UPC-A (12 digits) is extracted."""
    metadata = {"upc": "012345678905"}
    result = extract_product_identifier_from_metadata(metadata)
    assert result == ("upc", "012345678905")


def test_extract_ean_valid() -> None:
    """Valid EAN-13 (13 digits) is extracted."""
    metadata = {"ean": "5901234123457"}
    result = extract_product_identifier_from_metadata(metadata)
    assert result == ("ean", "5901234123457")


def test_extract_asin_valid() -> None:
    """Valid ASIN (10 alphanumeric) is extracted."""
    metadata = {"asin": "B08N5WRWNW"}
    result = extract_product_identifier_from_metadata(metadata)
    assert result == ("asin", "B08N5WRWNW")


def test_extract_isbn_valid() -> None:
    """Valid ISBN-13 is extracted."""
    metadata = {"isbn": "9780306406157"}
    result = extract_product_identifier_from_metadata(metadata)
    assert result == ("isbn", "9780306406157")


def test_extract_gtin_preferred_over_upc() -> None:
    """GTIN takes precedence when both GTIN and UPC are present."""
    metadata = {"gtin": "0012345678905", "upc": "012345678905"}
    result = extract_product_identifier_from_metadata(metadata)
    assert result == ("gtin", "0012345678905")


def test_extract_invalid_upc_rejected() -> None:
    """Invalid UPC format (wrong length) returns None."""
    metadata = {"upc": "12345"}  # Too short
    result = extract_product_identifier_from_metadata(metadata)
    assert result is None


def test_extract_invalid_asin_rejected() -> None:
    """Invalid ASIN format (wrong length) returns None."""
    metadata = {"asin": "B08N5"}  # Too short
    result = extract_product_identifier_from_metadata(metadata)
    assert result is None


def test_extract_empty_metadata_returns_none() -> None:
    """Empty metadata dict returns None."""
    result = extract_product_identifier_from_metadata({})
    assert result is None


def test_extract_non_dict_metadata_returns_none() -> None:
    """Non-dict metadata returns None."""
    result = extract_product_identifier_from_metadata(None)  # type: ignore[arg-type]
    assert result is None
    result = extract_product_identifier_from_metadata("not a dict")  # type: ignore[arg-type]
    assert result is None


def test_extract_whitespace_value_rejected() -> None:
    """Whitespace-only identifier value is rejected."""
    metadata = {"upc": "   "}
    result = extract_product_identifier_from_metadata(metadata)
    assert result is None


def test_extract_numeric_upc_converted_to_string() -> None:
    """Numeric UPC values are converted to strings for validation."""
    metadata = {"upc": 12345678905}
    result = extract_product_identifier_from_metadata(metadata)
    # int(12345678905) -> str "12345678905" which is 11 digits, not valid UPC-A
    assert result is None


def test_extract_mpn_valid() -> None:
    """Valid MPN (alphanumeric with hyphens) is extracted."""
    metadata = {"mpn": "ABC-123-XYZ"}
    result = extract_product_identifier_from_metadata(metadata)
    assert result == ("mpn", "ABC-123-XYZ")


def test_extract_mpn_too_short_rejected() -> None:
    """MPN shorter than 4 characters is rejected."""
    metadata = {"mpn": "AB"}
    result = extract_product_identifier_from_metadata(metadata)
    assert result is None


def test_extract_priority_order_gtin_first() -> None:
    """Identifier extraction follows priority order: GTIN > UPC > EAN > ..."""
    # When multiple identifiers exist, the first in priority order wins
    metadata = {
        "mpn": "MFR-123",
        "upc": "012345678905",
        "ean": "5901234123457",
    }
    result = extract_product_identifier_from_metadata(metadata)
    # GTIN not present, so UPC is next in priority
    assert result == ("upc", "012345678905")


def test_extract_gtin_valid_8_digits() -> None:
    """Valid GTIN-8 (8 digits) is extracted."""
    metadata = {"gtin": "12345678"}
    result = extract_product_identifier_from_metadata(metadata)
    assert result == ("gtin", "12345678")


def test_extract_gtin_valid_12_digits() -> None:
    """Valid GTIN-12 (same as UPC-A) is extracted."""
    metadata = {"gtin": "012345678905"}
    result = extract_product_identifier_from_metadata(metadata)
    assert result == ("gtin", "012345678905")


def test_extract_gtin_valid_13_digits() -> None:
    """Valid GTIN-13 (same as EAN-13) is extracted."""
    metadata = {"gtin": "5901234123457"}
    result = extract_product_identifier_from_metadata(metadata)
    assert result == ("gtin", "5901234123457")


def test_extract_gtin_valid_14_digits() -> None:
    """Valid GTIN-14 (14 digits) is extracted."""
    metadata = {"gtin": "00123456789050"}
    result = extract_product_identifier_from_metadata(metadata)
    assert result == ("gtin", "00123456789050")


def test_extract_invalid_gtin_rejected() -> None:
    """Invalid GTIN format (non-numeric or wrong length) returns None."""
    metadata = {"gtin": "not-a-real-gtin"}
    result = extract_product_identifier_from_metadata(metadata)
    assert result is None


def test_extract_invalid_gtin_too_short_rejected() -> None:
    """GTIN shorter than 8 digits is rejected."""
    metadata = {"gtin": "1234567"}  # 7 digits
    result = extract_product_identifier_from_metadata(metadata)
    assert result is None


def test_extract_invalid_gtin_too_long_rejected() -> None:
    """GTIN longer than 14 digits is rejected."""
    metadata = {"gtin": "12345678901234567"}  # 17 digits
    result = extract_product_identifier_from_metadata(metadata)
    assert result is None


def test_extract_gtin_shadows_upc_when_both_present() -> None:
    """Valid GTIN takes precedence over valid UPC when both exist."""
    metadata = {"gtin": "00123456789050", "upc": "012345678905"}
    result = extract_product_identifier_from_metadata(metadata)
    assert result == ("gtin", "00123456789050")


def test_extract_invalid_gtin_allows_fallback_to_upc() -> None:
    """Invalid GTIN is skipped, allowing valid UPC to be used."""
    metadata = {"gtin": "junk", "upc": "012345678905"}
    result = extract_product_identifier_from_metadata(metadata)
    assert result == ("upc", "012345678905")


# ---------------------------------------------------------------------------
# derive_product_key_from_listing (TASK-044)
# ---------------------------------------------------------------------------


def test_derive_product_key_with_upc() -> None:
    """Product key is derived from UPC in metadata."""
    metadata = {"upc": "012345678905"}
    result = derive_product_key_from_listing("ebay", "ebay:12345", metadata)
    assert result == "ebay:012345678905"


def test_derive_product_key_with_asin() -> None:
    """Product key is derived from ASIN in metadata."""
    metadata = {"asin": "B08N5WRWNW"}
    result = derive_product_key_from_listing("amazon", "amazon:B08N5WRWNW-1", metadata)
    assert result == "amazon:B08N5WRWNW"


def test_derive_product_key_no_identifier_returns_none() -> None:
    """When no explicit identifier exists, listing remains unmapped."""
    metadata = {"title": "Widget Pro", "condition": "new"}
    result = derive_product_key_from_listing("ebay", "ebay:12345", metadata)
    assert result is None


def test_derive_product_key_deterministic() -> None:
    """Same input always produces same product key (replay-safe)."""
    metadata = {"upc": "012345678905"}
    key1 = derive_product_key_from_listing("ebay", "ebay:12345", metadata)
    key2 = derive_product_key_from_listing("ebay", "ebay:12345", metadata)
    assert key1 == key2


def test_derive_product_key_different_listings_same_product() -> None:
    """Different listings with same UPC map to same product key."""
    metadata1 = {"upc": "012345678905"}
    metadata2 = {"upc": "012345678905"}
    key1 = derive_product_key_from_listing("ebay", "ebay:12345", metadata1)
    key2 = derive_product_key_from_listing("ebay", "ebay:67890", metadata2)
    assert key1 == key2 == "ebay:012345678905"


def test_derive_product_key_different_sources_same_upc() -> None:
    """Same UPC from different sources produces source-prefixed keys."""
    metadata = {"upc": "012345678905"}
    key_ebay = derive_product_key_from_listing("ebay", "ebay:12345", metadata)
    key_amazon = derive_product_key_from_listing("amazon", "amazon:B08N5WRWNW", metadata)
    assert key_ebay == "ebay:012345678905"
    assert key_amazon == "amazon:012345678905"
    assert key_ebay != key_amazon  # Source prefix ensures isolation


def test_derive_product_key_invalid_upc_returns_none() -> None:
    """Invalid UPC format results in None (listing stays unmapped)."""
    metadata = {"upc": "invalid-upc"}
    result = derive_product_key_from_listing("ebay", "ebay:12345", metadata)
    assert result is None


def test_derive_product_key_preserves_listing_separation() -> None:
    """Listings without identifiers remain separate (not merged)."""
    metadata1 = {"title": "Widget A"}
    metadata2 = {"title": "Widget B"}
    key1 = derive_product_key_from_listing("ebay", "ebay:1", metadata1)
    key2 = derive_product_key_from_listing("ebay", "ebay:2", metadata2)
    # Both should be None - they stay as separate unmapped listings
    assert key1 is None
    assert key2 is None


# ---------------------------------------------------------------------------
# Integration: ListingProductMapper + derive_product_key (TASK-044)
# ---------------------------------------------------------------------------


def test_mapper_integration_assign_derived_key() -> None:
    """Full flow: derive product key from metadata, then assign to mapper."""
    mapper = ListingProductMapper()
    metadata = {"upc": "012345678905"}
    product_key = derive_product_key_from_listing("ebay", "ebay:12345", metadata)

    assert product_key is not None
    mapper.assign("ebay:12345", product_key)

    assert mapper.get_product_key("ebay:12345") == "ebay:012345678905"
    assert mapper.has_listing("ebay:12345")
    assert mapper.has_product("ebay:012345678905")


def test_mapper_integration_multiple_listings_one_product() -> None:
    """Multiple listings with same UPC map to single product."""
    mapper = ListingProductMapper()

    # Two eBay listings for the same product (same UPC)
    metadata1 = {"upc": "012345678905", "seller": "seller1"}
    metadata2 = {"upc": "012345678905", "seller": "seller2"}

    key1 = derive_product_key_from_listing("ebay", "ebay:L1", metadata1)
    key2 = derive_product_key_from_listing("ebay", "ebay:L2", metadata2)

    assert key1 == key2 == "ebay:012345678905"  # Same product key, narrowed to str
    mapper.assign("ebay:L1", key1)
    mapper.assign("ebay:L2", key2)

    assert mapper.get_listing_ids("ebay:012345678905") == {"ebay:L1", "ebay:L2"}
    assert mapper.product_count == 1
    assert mapper.listing_count == 2


def test_mapper_integration_ambiguous_listings_stay_separate() -> None:
    """Listings without explicit identifiers remain unmapped and separate."""
    mapper = ListingProductMapper()

    # Two listings with only titles (no UPC/ASIN/etc.)
    metadata1 = {"title": "iPhone 13 Pro"}
    metadata2 = {"title": "iPhone 13 Pro Max"}

    key1 = derive_product_key_from_listing("ebay", "ebay:L1", metadata1)
    key2 = derive_product_key_from_listing("ebay", "ebay:L2", metadata2)

    # Both should be None - no assignment happens
    assert key1 is None
    assert key2 is None

    # Mapper has no mappings
    assert mapper.listing_count == 0
    assert mapper.product_count == 0


def test_mapper_integration_replay_idempotency() -> None:
    """Replaying the same listing produces identical mapping (idempotent)."""
    mapper = ListingProductMapper()
    metadata = {"upc": "012345678905"}
    product_key = derive_product_key_from_listing("ebay", "ebay:12345", metadata)

    assert product_key is not None

    # First observation
    mapper.assign("ebay:12345", product_key)
    assert mapper.listing_count == 1

    # Replay: same listing, same product key
    mapper.assign("ebay:12345", product_key)
    assert mapper.listing_count == 1  # No duplicate
    assert mapper.product_count == 1


def test_mapper_integration_cross_source_product_grouping() -> None:
    """Different sources can reference same logical product via shared identifier."""
    mapper = ListingProductMapper()

    # Same physical product sold on eBay and Amazon (same UPC)
    ebay_metadata = {"upc": "012345678905"}
    amazon_metadata = {"upc": "012345678905"}

    ebay_key = derive_product_key_from_listing("ebay", "ebay:12345", ebay_metadata)
    amazon_key = derive_product_key_from_listing("amazon", "amazon:B08N5WRWNW", amazon_metadata)

    # Keys are source-prefixed but point to same UPC
    assert ebay_key == "ebay:012345678905"
    assert amazon_key == "amazon:012345678905"

    # Each source maintains its own namespace
    mapper.assign("ebay:12345", ebay_key)
    mapper.assign("amazon:B08N5WRWNW", amazon_key)

    # Different product keys (source-isolated)
    assert mapper.product_count == 2
    assert mapper.listing_count == 2
