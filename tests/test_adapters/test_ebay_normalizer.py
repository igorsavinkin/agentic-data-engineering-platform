"""Unit tests for eBay listing/seller normalization (TASK-043).

Tests cover:
* Success paths with complete data
* Malformed/partial input handling
* Deterministic identity mapping
* Condition normalization
* Price/currency edge cases
* URL construction
* Seller normalization with missing data
* Product key assignment via mapper
* Replay idempotency
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from libs.adapters.ebay.models import (
    EbayAvailability,
    EbayImage,
    EbayListingSummary,
    EbayPrice,
)
from libs.adapters.ebay.models import (
    EbaySeller as EbaySellerModel,
)
from libs.adapters.ebay.normalizer import (
    normalize_condition,
    normalize_ebay_seller,
    normalize_listing,
    normalize_listing_url,
    normalize_listing_with_product_key,
    normalize_price,
)
from libs.marketplace.identity import (
    ListingProductMapper,
    build_product_key,
)

# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def full_ebay_summary() -> EbayListingSummary:
    """A complete eBay listing summary with all fields populated."""
    return EbayListingSummary(
        item_id="123456789",
        title="Test Laptop - Brand New",
        price=EbayPrice(value=999.99, currency="USD"),
        condition="Brand New",
        item_web_url="https://www.ebay.com/itm/123456789",
        seller=EbaySellerModel(
            username="test_seller_123",
            feedback_score=1500,
            feedback_percentage=99.5,
        ),
        image=EbayImage(image_url="https://i.ebayimg.com/test.jpg"),
        availability=EbayAvailability(
            ship_to_location_availability=[{"quantity": 5}],
            pickup_at_store_availability=[],
        ),
        category_ids=["1234", "5678", "9012"],
    )


@pytest.fixture
def minimal_ebay_summary() -> EbayListingSummary:
    """A minimal eBay listing summary with only required fields."""
    return EbayListingSummary(
        item_id="987654321",
        title="Minimal Item",
        price=None,
        condition=None,
        item_web_url=None,
        seller=None,
        image=None,
        availability=None,
        category_ids=None,
    )


@pytest.fixture
def partial_ebay_summary() -> EbayListingSummary:
    """An eBay listing with partial data (some fields missing)."""
    return EbayListingSummary(
        item_id="555555555",
        title="Partial Item",
        price=EbayPrice(value=50.0, currency="EUR"),
        condition="Used",
        item_web_url=None,  # Missing URL
        seller=EbaySellerModel(
            username="partial_seller",
            feedback_score=None,  # Missing feedback
            feedback_percentage=None,
        ),
        image=None,
        availability=EbayAvailability(
            ship_to_location_availability=[],  # Empty = out of stock
            pickup_at_store_availability=[],
        ),
        category_ids=["cat1"],
    )


@pytest.fixture
def mapper() -> ListingProductMapper:
    """A fresh product mapper for testing product key assignment."""
    return ListingProductMapper()


# ─── Seller Normalization Tests ──────────────────────────────────────────────


class TestNormalizeEbaySeller:
    """Tests for normalize_ebay_seller()."""

    def test_full_seller_normalized(self) -> None:
        """Complete seller data produces a valid Seller instance."""
        ebay_seller = EbaySellerModel(
            username="top_seller",
            feedback_score=5000,
            feedback_percentage=99.9,
        )
        result = normalize_ebay_seller(ebay_seller)

        assert result is not None
        assert result.seller_id == "ebay:top_seller"
        assert result.source == "ebay"
        assert result.display_name == "top_seller"
        assert result.metadata["feedback_score"] == 5000
        assert result.metadata["feedback_percentage"] == 99.9

    def test_none_input_returns_none(self) -> None:
        """None seller input returns None."""
        assert normalize_ebay_seller(None) is None

    def test_empty_username_returns_none(self) -> None:
        """Seller with empty/whitespace username returns None."""
        ebay_seller = EbaySellerModel(username="   ")
        assert normalize_ebay_seller(ebay_seller) is None

    def test_missing_feedback_preserved_in_metadata(self) -> None:
        """Seller without feedback scores has empty metadata."""
        ebay_seller = EbaySellerModel(username="no_feedback")
        result = normalize_ebay_seller(ebay_seller)

        assert result is not None
        assert result.metadata == {}

    def test_custom_source_override(self) -> None:
        """Custom source parameter changes seller ID prefix."""
        ebay_seller = EbaySellerModel(username="seller_x")
        result = normalize_ebay_seller(ebay_seller, source="custom_source")

        assert result is not None
        assert result.seller_id == "custom_source:seller_x"
        assert result.source == "custom_source"

    def test_deterministic_identity(self) -> None:
        """Same username always produces the same seller_id."""
        ebay_seller = EbaySellerModel(username="consistent_seller")
        result1 = normalize_ebay_seller(ebay_seller)
        result2 = normalize_ebay_seller(ebay_seller)

        assert result1 is not None
        assert result2 is not None
        assert result1.seller_id == result2.seller_id


# ─── Price Normalization Tests ───────────────────────────────────────────────


class TestNormalizePrice:
    """Tests for normalize_price()."""

    def test_valid_price_normalized(self) -> None:
        """Valid price returns Decimal amount and uppercase currency."""
        ebay_price = EbayPrice(value=123.45, currency="usd")
        amount, currency = normalize_price(ebay_price)

        assert amount == Decimal("123.45")
        assert currency == "USD"

    def test_none_price_returns_defaults(self) -> None:
        """None price returns (None, 'USD')."""
        amount, currency = normalize_price(None)
        assert amount is None
        assert currency == "USD"

    def test_negative_price_treated_as_missing(self) -> None:
        """Negative prices are treated as missing."""
        ebay_price = EbayPrice(value=-10.0, currency="USD")
        amount, currency = normalize_price(ebay_price)
        assert amount is None

    def test_zero_price_is_valid(self) -> None:
        """Zero price is valid (free items)."""
        ebay_price = EbayPrice(value=0.0, currency="USD")
        amount, currency = normalize_price(ebay_price)
        assert amount == Decimal("0")
        assert currency == "USD"

    def test_currency_uppercased(self) -> None:
        """Currency codes are uppercased."""
        ebay_price = EbayPrice(value=100.0, currency="eur")
        _, currency = normalize_price(ebay_price)
        assert currency == "EUR"

    def test_missing_currency_defaults_to_usd(self) -> None:
        """Empty currency defaults to USD."""
        ebay_price = EbayPrice(value=100.0, currency="")
        _, currency = normalize_price(ebay_price)
        assert currency == "USD"


# ─── Condition Normalization Tests ───────────────────────────────────────────


class TestNormalizeCondition:
    """Tests for normalize_condition()."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("New", "new"),
            ("brand new", "new"),
            ("BRAND NEW", "new"),
            ("Like New", "like_new"),
            ("excellent", "like_new"),
            ("Very Good", "good"),
            ("Good", "good"),
            ("Acceptable", "acceptable"),
            ("For parts or not working", "for_parts"),
            ("used", "used"),
            ("Unknown Condition", None),
            ("", None),
            (None, None),
        ],
    )
    def test_condition_mapping(self, raw: str | None, expected: str | None) -> None:
        """Various eBay condition strings map to canonical values."""
        assert normalize_condition(raw) == expected


# ─── URL Normalization Tests ─────────────────────────────────────────────────


class TestNormalizeListingUrl:
    """Tests for normalize_listing_url()."""

    def test_api_url_preferred(self) -> None:
        """API-provided URL is used when present."""
        url = normalize_listing_url("123", item_web_url="https://ebay.com/custom/123")
        assert url == "https://ebay.com/custom/123"

    def test_constructed_url_fallback(self) -> None:
        """Constructed URL used when API URL is None."""
        url = normalize_listing_url("456")
        assert url == "https://www.ebay.com/itm/456"

    def test_whitespace_trimmed(self) -> None:
        """URLs are stripped of whitespace."""
        url = normalize_listing_url("789", item_web_url="  https://ebay.com/trimmed  ")
        assert url == "https://ebay.com/trimmed"


# ─── Listing Normalization Tests ─────────────────────────────────────────────


class TestNormalizeListing:
    """Tests for normalize_listing()."""

    def test_full_listing_normalized(self, full_ebay_summary: EbayListingSummary) -> None:
        """Complete listing produces valid MarketplaceListing."""
        listing = normalize_listing(full_ebay_summary)

        assert listing.listing_id == "123456789"  # Raw item_id
        assert listing.qualified_id == "ebay:123456789"  # Source-prefixed
        assert listing.source == "ebay"
        assert listing.title == "Test Laptop - Brand New"
        assert listing.url == "https://www.ebay.com/itm/123456789"
        assert listing.product_key is None  # Not assigned yet

        # Seller should be normalized
        assert listing.seller is not None
        assert listing.seller.seller_id == "ebay:test_seller_123"

        # Metadata should contain diagnostic info
        assert listing.metadata["condition"] == "new"
        assert listing.metadata["availability_raw"] is True
        assert listing.metadata["category_id"] == "9012"

    def test_minimal_listing_handles_missing_fields(
        self, minimal_ebay_summary: EbayListingSummary
    ) -> None:
        """Minimal listing handles all missing optional fields gracefully."""
        listing = normalize_listing(minimal_ebay_summary)

        assert listing.listing_id == "987654321"  # Raw item_id
        assert listing.qualified_id == "ebay:987654321"
        assert listing.source == "ebay"
        assert listing.title == "Minimal Item"
        assert listing.url == "https://www.ebay.com/itm/987654321"  # Constructed
        assert listing.seller is None
        assert listing.product_key is None

        # Metadata should be minimal
        assert "condition" not in listing.metadata
        assert "availability_raw" not in listing.metadata

    def test_partial_listing_handles_partial_data(
        self, partial_ebay_summary: EbayListingSummary
    ) -> None:
        """Partial listing handles some missing fields correctly."""
        listing = normalize_listing(partial_ebay_summary)

        assert listing.listing_id == "555555555"  # Raw item_id
        assert listing.qualified_id == "ebay:555555555"
        assert listing.seller is not None
        assert listing.seller.seller_id == "ebay:partial_seller"
        assert listing.seller.metadata == {}  # No feedback data

        # Out of stock (empty availability lists)
        assert listing.metadata["availability_raw"] is False
        assert listing.metadata["condition"] == "used"

    def test_listing_id_is_deterministic(self, full_ebay_summary: EbayListingSummary) -> None:
        """Same item_id always produces the same listing_id."""
        listing1 = normalize_listing(full_ebay_summary)
        listing2 = normalize_listing(full_ebay_summary)
        assert listing1.listing_id == listing2.listing_id

    def test_custom_source_parameter(self, full_ebay_summary: EbayListingSummary) -> None:
        """Custom source parameter changes listing ID prefix."""
        listing = normalize_listing(full_ebay_summary, source="custom_ebay")
        assert listing.listing_id == "123456789"  # Raw item_id unchanged
        assert listing.qualified_id == "custom_ebay:123456789"
        assert listing.source == "custom_ebay"

    def test_explicit_product_key_assigned(self, full_ebay_summary: EbayListingSummary) -> None:
        """Explicit product key is preserved in listing."""
        listing = normalize_listing(full_ebay_summary, product_key="ebay:laptop-upc-001")
        assert listing.product_key == "ebay:laptop-upc-001"

    def test_distinct_listings_never_collapsed(self, full_ebay_summary: EbayListingSummary) -> None:
        """Different item_ids produce different listing IDs."""
        summary2 = EbayListingSummary(
            item_id="999999999",
            title="Different Item",
            price=None,
            condition=None,
            item_web_url=None,
            seller=None,
            image=None,
            availability=None,
            category_ids=None,
        )
        listing1 = normalize_listing(full_ebay_summary)
        listing2 = normalize_listing(summary2)
        assert listing1.listing_id != listing2.listing_id


# ─── Listing with Product Key Tests ──────────────────────────────────────────


class TestNormalizeListingWithProductKey:
    """Tests for normalize_listing_with_product_key()."""

    def test_mapper_assigns_product_key(
        self, full_ebay_summary: EbayListingSummary, mapper: ListingProductMapper
    ) -> None:
        """Mapper assigns product key to listing."""
        # Use qualified_id (source:item_id) which matches what the listing produces
        qualified_id = "ebay:123456789"  # This is what listing.qualified_id returns
        product_key = build_product_key("ebay", "UPC-LAPTOP-001")
        mapper.assign(qualified_id, product_key)

        listing = normalize_listing_with_product_key(full_ebay_summary, mapper=mapper)
        assert listing.product_key == product_key

    def test_no_mapper_returns_unmapped_listing(
        self, full_ebay_summary: EbayListingSummary
    ) -> None:
        """Without mapper, listing has no product key."""
        listing = normalize_listing_with_product_key(full_ebay_summary)
        assert listing.product_key is None

    def test_unknown_listing_remains_unmapped(
        self, full_ebay_summary: EbayListingSummary, mapper: ListingProductMapper
    ) -> None:
        """Listing not in mapper remains unmapped."""
        listing = normalize_listing_with_product_key(full_ebay_summary, mapper=mapper)
        assert listing.product_key is None


# ─── Replay Idempotency Tests ────────────────────────────────────────────────


class TestReplayIdempotency:
    """Tests ensuring deterministic behavior across replays."""

    def test_same_input_produces_same_listing(self, full_ebay_summary: EbayListingSummary) -> None:
        """Repeated normalization of same input yields identical listing."""
        listing1 = normalize_listing(full_ebay_summary)
        listing2 = normalize_listing(full_ebay_summary)

        assert listing1.listing_id == listing2.listing_id
        assert listing1.title == listing2.title
        assert listing1.url == listing2.url
        if listing1.seller and listing2.seller:
            assert listing1.seller.seller_id == listing2.seller.seller_id

    def test_seller_identity_stable_across_observations(self) -> None:
        """Same seller username produces stable identity."""
        seller1 = EbaySellerModel(username="stable_seller", feedback_score=100)
        seller2 = EbaySellerModel(username="stable_seller", feedback_score=200)

        result1 = normalize_ebay_seller(seller1)
        result2 = normalize_ebay_seller(seller2)

        assert result1 is not None
        assert result2 is not None
        assert result1.seller_id == result2.seller_id
        # Metadata may differ but identity is stable
        assert result1.metadata["feedback_score"] == 100
        assert result2.metadata["feedback_score"] == 200


# ─── Edge Case Tests ─────────────────────────────────────────────────────────


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_whitespace_title_stripped(self) -> None:
        """Titles with leading/trailing whitespace are stripped."""
        summary = EbayListingSummary(
            item_id="ws_test",
            title="  Whitespace Title  ",
            price=None,
            condition=None,
            item_web_url=None,
            seller=None,
            image=None,
            availability=None,
            category_ids=None,
        )
        listing = normalize_listing(summary)
        assert listing.title == "Whitespace Title"

    def test_category_hierarchy_uses_most_specific(self) -> None:
        """Category ID uses last element of hierarchy."""
        summary = EbayListingSummary(
            item_id="cat_test",
            title="Cat Test",
            price=None,
            condition=None,
            item_web_url=None,
            seller=None,
            image=None,
            availability=None,
            category_ids=["root", "mid", "leaf"],
        )
        listing = normalize_listing(summary)
        assert listing.metadata["category_id"] == "leaf"

    def test_empty_category_ids_handled(self) -> None:
        """Empty category list does not add category_id to metadata."""
        summary = EbayListingSummary(
            item_id="empty_cat",
            title="No Cats",
            price=None,
            condition=None,
            item_web_url=None,
            seller=None,
            image=None,
            availability=None,
            category_ids=[],
        )
        listing = normalize_listing(summary)
        assert "category_id" not in listing.metadata
