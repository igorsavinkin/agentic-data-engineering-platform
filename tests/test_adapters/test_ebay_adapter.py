"""Tests for the eBay Browse API adapter.

Covers:
- representative listing mapping
- multiple records
- nullable fields (price, availability)
- malformed upstream record
- HTTP timeout/error
- rate-limit handling
- auth failure
- empty source response
- canonical event compatibility
- seller identity preservation
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from libs.adapters import FetchResult, SourceFetchError
from libs.adapters.ebay import EbayAdapter, EbayClient
from libs.adapters.ebay.models import (
    EbayAvailability,
    EbayListingSummary,
    EbaySearchResponse,
)
from libs.event_contracts.product_observation import (
    ProductObservationPayload,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_listing_dict() -> dict[str, Any]:
    """Representative eBay listing summary response."""
    return {
        "itemId": "123456789012",
        "title": "Apple iPhone 14 Pro Max 256GB Deep Purple Unlocked",
        "price": {"value": 899.99, "currency": "USD"},
        "condition": "New",
        "itemWebUrl": "https://www.ebay.com/itm/123456789012",
        "seller": {
            "username": "top_seller_123",
            "feedbackScore": 9850,
            "positiveFeedbackPercent": 99.5,
        },
        "image": {"imageUrl": "https://i.ebayimg.com/image/i/123456789012.jpg"},
        "availability": {
            "shipToLocationAvailability": [{"quantity": 5}],
            "pickupAtStoreAvailability": [],
        },
        "categoryIds": ["9355", "58058"],
    }


@pytest.fixture
def sample_listing(sample_listing_dict: dict[str, Any]) -> EbayListingSummary:
    """Typed EbayListingSummary from dict."""
    return EbayListingSummary.model_validate(sample_listing_dict)


@pytest.fixture
def multiple_listings() -> list[dict[str, Any]]:
    """Multiple listings for batch testing."""
    return [
        {
            "itemId": "111111111111",
            "title": "Product One",
            "price": {"value": 10.0, "currency": "USD"},
            "condition": "New",
            "itemWebUrl": "https://www.ebay.com/itm/111111111111",
            "seller": {"username": "seller_one"},
            "availability": {"shipToLocationAvailability": [{"quantity": 1}]},
            "categoryIds": ["9355"],
        },
        {
            "itemId": "222222222222",
            "title": "Product Two",
            "price": {"value": 20.50, "currency": "EUR"},
            "condition": "Used",
            "itemWebUrl": "https://www.ebay.com/itm/222222222222",
            "seller": {"username": "seller_two", "feedbackScore": 500},
            "availability": {"shipToLocationAvailability": []},
            "categoryIds": ["58058", "9355"],
        },
        {
            "itemId": "333333333333",
            "title": "Product Three",
            "price": None,
            "condition": "New",
            "itemWebUrl": None,
            "seller": None,
            "availability": None,
            "categoryIds": None,
        },
    ]


@pytest.fixture
def malformed_listing_dict() -> dict[str, Any]:
    """Listing missing required fields to trigger validation failure."""
    return {
        "itemId": "999999999999",
        # Missing title - should fail validation
    }


# ---------------------------------------------------------------------------
# 1. Representative listing mapping
# ---------------------------------------------------------------------------


class TestListingMapping:
    """Test single listing mapping to canonical events."""

    @pytest.mark.asyncio
    async def test_map_single_listing(self, sample_listing: EbayListingSummary) -> None:
        """A single EbayListingSummary maps to a valid canonical event."""
        search_response = EbaySearchResponse(total=1, item_summaries=[sample_listing])

        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.return_value = (search_response, [])

            adapter = EbayAdapter()
            result = await adapter.fetch()

            assert len(result.events) == 1
            event = result.events[0]
            payload = event.payload

            assert isinstance(payload, ProductObservationPayload)
            assert payload.external_id == "123456789012"
            assert payload.name == sample_listing.title
            assert float(payload.price) == 899.99 if payload.price else False
            assert payload.currency == "USD"
            assert payload.availability == "in_stock"
            assert payload.category == "ebay_category_58058"
            assert "ebay.com/itm/123456789012" in payload.url

    @pytest.mark.asyncio
    async def test_external_id_is_string(self, sample_listing: EbayListingSummary) -> None:
        """external_id must be a string even though source uses string IDs."""
        search_response = EbaySearchResponse(total=1, item_summaries=[sample_listing])

        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.return_value = (search_response, [])

            adapter = EbayAdapter()
            result = await adapter.fetch()

            assert len(result.events) == 1
            payload = result.events[0].payload
            assert isinstance(payload.external_id, str)
            assert payload.external_id == "123456789012"


# ---------------------------------------------------------------------------
# 2. Multiple records
# ---------------------------------------------------------------------------


class TestMultipleRecords:
    """Test fetching and mapping multiple listings."""

    @pytest.mark.asyncio
    async def test_fetch_multiple_listings(self, multiple_listings: list[dict[str, Any]]) -> None:
        """Adapter fetches and maps multiple listings correctly."""
        typed_listings = [EbayListingSummary.model_validate(p) for p in multiple_listings]
        search_response = EbaySearchResponse(total=3, item_summaries=typed_listings)

        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.return_value = (search_response, [])

            adapter = EbayAdapter(limit=10)
            result = await adapter.fetch()

            assert len(result.events) == 3
            assert result.total_records == 3
            assert all(e.source == "ebay" for e in result.events)
            assert result.events[0].payload.external_id == "111111111111"
            assert result.events[1].payload.external_id == "222222222222"
            assert result.events[2].payload.external_id == "333333333333"

    @pytest.mark.asyncio
    async def test_fetch_with_query_filter(self) -> None:
        """Adapter passes query parameter to client."""
        search_response = EbaySearchResponse(total=0, item_summaries=[])

        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.return_value = (search_response, [])

            adapter = EbayAdapter(query="laptop", limit=50)
            await adapter.fetch()

            mock_search.assert_called_once()
            call_kwargs = mock_search.call_args
            assert call_kwargs.kwargs.get("query") == "laptop"
            assert call_kwargs.kwargs.get("limit") == 50

    @pytest.mark.asyncio
    async def test_fetch_with_category_ids(self) -> None:
        """Adapter passes category_ids to client."""
        search_response = EbaySearchResponse(total=0, item_summaries=[])

        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.return_value = (search_response, [])

            adapter = EbayAdapter(category_ids=["9355", "58058"])
            await adapter.fetch()

            mock_search.assert_called_once()
            call_kwargs = mock_search.call_args
            assert call_kwargs.kwargs.get("category_ids") == ["9355", "58058"]


# ---------------------------------------------------------------------------
# 3. Nullable fields
# ---------------------------------------------------------------------------


class TestNullableFields:
    """Test handling of nullable/optional fields."""

    @pytest.mark.asyncio
    async def test_null_price_field(self) -> None:
        """Listing with null price still maps correctly with null price."""
        listing = EbayListingSummary(
            item_id="123",
            title="No Price Item",
            price=None,
            condition="New",
            item_web_url="https://www.ebay.com/itm/123",
            seller=None,
            image=None,
            availability=None,
            category_ids=None,
        )
        search_response = EbaySearchResponse(total=1, item_summaries=[listing])

        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.return_value = (search_response, [])

            adapter = EbayAdapter()
            result = await adapter.fetch()

            assert len(result.events) == 1
            payload = result.events[0].payload
            assert payload.external_id == "123"
            assert payload.price is None

    @pytest.mark.asyncio
    async def test_null_availability_defaults_to_unknown(self) -> None:
        """Listing with no availability info defaults to 'unknown'."""
        listing = EbayListingSummary(
            item_id="456",
            title="Unknown Availability",
            price={"value": 50.0, "currency": "USD"},
            condition="New",
            item_web_url="https://www.ebay.com/itm/456",
            seller=None,
            image=None,
            availability=None,
            category_ids=None,
        )
        search_response = EbaySearchResponse(total=1, item_summaries=[listing])

        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.return_value = (search_response, [])

            adapter = EbayAdapter()
            result = await adapter.fetch()

            assert len(result.events) == 1
            payload = result.events[0].payload
            assert payload.availability == "unknown"

    @pytest.mark.asyncio
    async def test_empty_availability_means_out_of_stock(self) -> None:
        """Listing with empty availability arrays means out of stock."""
        listing = EbayListingSummary(
            item_id="789",
            title="Out of Stock",
            price={"value": 100.0, "currency": "USD"},
            condition="New",
            item_web_url="https://www.ebay.com/itm/789",
            seller=None,
            image=None,
            availability=EbayAvailability(
                ship_to_location_availability=[],
                pickup_at_store_availability=[],
            ),
            category_ids=None,
        )
        search_response = EbaySearchResponse(total=1, item_summaries=[listing])

        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.return_value = (search_response, [])

            adapter = EbayAdapter()
            result = await adapter.fetch()

            assert len(result.events) == 1
            payload = result.events[0].payload
            assert payload.availability == "out_of_stock"

    @pytest.mark.asyncio
    async def test_null_item_web_url_constructs_fallback_url(self) -> None:
        """When item_web_url is null, URL is constructed from item_id."""
        listing = EbayListingSummary(
            item_id="abc123",
            title="No URL Item",
            price={"value": 25.0, "currency": "USD"},
            condition="New",
            item_web_url=None,
            seller=None,
            image=None,
            availability=None,
            category_ids=None,
        )
        search_response = EbaySearchResponse(total=1, item_summaries=[listing])

        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.return_value = (search_response, [])

            adapter = EbayAdapter()
            result = await adapter.fetch()

            assert len(result.events) == 1
            payload = result.events[0].payload
            assert payload.url == "https://www.ebay.com/itm/abc123"

    @pytest.mark.asyncio
    async def test_null_category_ids_defaults_to_uncategorized(self) -> None:
        """Listing with no category_ids defaults to 'uncategorized'."""
        listing = EbayListingSummary(
            item_id="cat_test",
            title="Uncategorized Item",
            price={"value": 15.0, "currency": "USD"},
            condition="New",
            item_web_url="https://www.ebay.com/itm/cat_test",
            seller=None,
            image=None,
            availability=None,
            category_ids=None,
        )
        search_response = EbaySearchResponse(total=1, item_summaries=[listing])

        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.return_value = (search_response, [])

            adapter = EbayAdapter()
            result = await adapter.fetch()

            assert len(result.events) == 1
            payload = result.events[0].payload
            assert payload.category == "uncategorized"


# ---------------------------------------------------------------------------
# 4. Malformed upstream record
# ---------------------------------------------------------------------------


class TestMalformedRecords:
    """Test handling of malformed source records."""

    @pytest.mark.asyncio
    async def test_malformed_record_separated(
        self,
        multiple_listings: list[dict[str, Any]],
        malformed_listing_dict: dict[str, Any],
    ) -> None:
        """Malformed records are separated into malformed tuple, not events."""
        valid_listings = [EbayListingSummary.model_validate(p) for p in multiple_listings]
        malformed_entry = {
            "raw_record": malformed_listing_dict,
            "reason": "Item summary validation failed at index 0: ...",
        }
        search_response = EbaySearchResponse(total=3, item_summaries=valid_listings)

        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.return_value = (search_response, [malformed_entry])

            adapter = EbayAdapter()
            result = await adapter.fetch()

            # Valid listings make it through, malformed is captured separately
            assert len(result.events) == 3
            assert len(result.malformed) == 1
            assert "raw_record" in result.malformed[0]
            assert "reason" in result.malformed[0]
            # total_records includes both valid and malformed
            assert result.total_records == 4

    @pytest.mark.asyncio
    async def test_all_malformed_yields_empty_events(self) -> None:
        """When all records are malformed, events is empty but malformed is not (protocol invariant #4)."""
        malformed_entries = [
            {"raw_record": {"bad": "data"}, "reason": "Validation failed at index 0: ..."},
            {"raw_record": {"also": "bad"}, "reason": "Validation failed at index 1: ..."},
        ]
        search_response = EbaySearchResponse(total=0, item_summaries=[])

        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.return_value = (search_response, malformed_entries)

            adapter = EbayAdapter()
            result = await adapter.fetch()

            assert len(result.events) == 0
            assert len(result.malformed) == 2
            assert result.total_records == 2  # Counts raw records before filtering


# ---------------------------------------------------------------------------
# 5. HTTP timeout/error
# ---------------------------------------------------------------------------


class TestHTTPErrors:
    """Test HTTP error handling."""

    @pytest.mark.asyncio
    async def test_timeout_raises_source_fetch_error(self) -> None:
        """HTTP timeout raises SourceFetchError."""
        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.side_effect = SourceFetchError(
                "eBay API request timed out",
                source="ebay",
            )

            adapter = EbayAdapter()

            with pytest.raises(SourceFetchError) as exc_info:
                await adapter.fetch()

            assert exc_info.value.source == "ebay"
            assert "timed out" in exc_info.value.args[0].lower()

    @pytest.mark.asyncio
    async def test_5xx_error_raises_source_fetch_error(self) -> None:
        """5xx errors raise SourceFetchError."""
        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.side_effect = SourceFetchError(
                "eBay API returned HTTP 503",
                source="ebay",
            )

            adapter = EbayAdapter()

            with pytest.raises(SourceFetchError) as exc_info:
                await adapter.fetch()

            assert exc_info.value.source == "ebay"

    @pytest.mark.asyncio
    async def test_4xx_error_raises_source_fetch_error(self) -> None:
        """4xx errors raise SourceFetchError."""
        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.side_effect = SourceFetchError(
                "eBay API returned HTTP 404",
                source="ebay",
            )

            adapter = EbayAdapter()

            with pytest.raises(SourceFetchError) as exc_info:
                await adapter.fetch()

            assert exc_info.value.source == "ebay"

    @pytest.mark.asyncio
    async def test_invalid_json_raises_source_fetch_error(self) -> None:
        """Invalid JSON response raises SourceFetchError."""
        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.side_effect = SourceFetchError(
                "eBay API returned invalid JSON",
                source="ebay",
            )

            adapter = EbayAdapter()

            with pytest.raises(SourceFetchError) as exc_info:
                await adapter.fetch()

            assert "invalid json" in exc_info.value.args[0].lower()


# ---------------------------------------------------------------------------
# 6. Rate-limit handling
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """Test explicit rate-limit response handling."""

    @pytest.mark.asyncio
    async def test_429_rate_limit_raises_source_fetch_error(self) -> None:
        """HTTP 429 raises SourceFetchError with retry-after info."""
        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.side_effect = SourceFetchError(
                "eBay API rate limited (Retry-After: 30s)",
                source="ebay",
            )

            adapter = EbayAdapter()

            with pytest.raises(SourceFetchError) as exc_info:
                await adapter.fetch()

            assert exc_info.value.source == "ebay"
            assert "rate limited" in exc_info.value.args[0].lower()


# ---------------------------------------------------------------------------
# 7. Auth failure
# ---------------------------------------------------------------------------


class TestAuthFailure:
    """Test authentication failure handling."""

    @pytest.mark.asyncio
    async def test_auth_failure_raises_source_fetch_error(self) -> None:
        """Auth failure raises SourceFetchError."""
        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.side_effect = SourceFetchError(
                "eBay authentication failed: HTTP 401",
                source="ebay",
            )

            adapter = EbayAdapter()

            with pytest.raises(SourceFetchError) as exc_info:
                await adapter.fetch()

            assert exc_info.value.source == "ebay"
            assert "authentication" in exc_info.value.args[0].lower()

    @pytest.mark.asyncio
    async def test_missing_credentials_raises_source_fetch_error(self) -> None:
        """Missing credentials raises SourceFetchError."""
        # Create client without credentials
        client = EbayClient(app_id=None, cert_id=None, dev_id=None)

        with patch.object(client, "_authenticate") as mock_auth:
            mock_auth.side_effect = SourceFetchError(
                "eBay API credentials not configured (EBAY_APP_ID, EBAY_CERT_ID, EBAY_DEV_ID)",
                source="ebay",
            )

            with patch.object(EbayClient, "search_items") as mock_search:
                mock_search.side_effect = SourceFetchError(
                    "eBay API credentials not configured (EBAY_APP_ID, EBAY_CERT_ID, EBAY_DEV_ID)",
                    source="ebay",
                )

                adapter = EbayAdapter(client=client)

                with pytest.raises(SourceFetchError) as exc_info:
                    await adapter.fetch()

                assert exc_info.value.source == "ebay"
                assert "credentials" in exc_info.value.args[0].lower()


# ---------------------------------------------------------------------------
# 8. Empty source response
# ---------------------------------------------------------------------------


class TestEmptyResponse:
    """Test handling of empty API responses."""

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty_events(self) -> None:
        """Empty listing list returns FetchResult with no events."""
        search_response = EbaySearchResponse(total=0, item_summaries=[])

        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.return_value = (search_response, [])

            adapter = EbayAdapter()
            result = await adapter.fetch()

            assert len(result.events) == 0
            assert len(result.malformed) == 0
            assert result.total_records == 0
            assert result.source == "ebay"
            assert not result.has_events


# ---------------------------------------------------------------------------
# 9. Canonical event compatibility
# ---------------------------------------------------------------------------


class TestCanonicalCompatibility:
    """Verify events conform to the canonical contract."""

    @pytest.mark.asyncio
    async def test_events_have_required_fields(self, sample_listing_dict: dict[str, Any]) -> None:
        """All emitted events have required canonical envelope fields."""
        listing = EbayListingSummary.model_validate(sample_listing_dict)
        search_response = EbaySearchResponse(total=1, item_summaries=[listing])

        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.return_value = (search_response, [])

            adapter = EbayAdapter()
            result = await adapter.fetch()

            assert len(result.events) == 1
            event = result.events[0]

            # Envelope fields
            assert event.event_id is not None
            assert event.event_type == "product.observation"
            assert event.schema_version == 1
            assert event.source == "ebay"
            assert event.produced_at is not None
            assert event.produced_at.tzinfo is not None

            # Payload fields
            payload = event.payload
            assert payload.external_id is not None
            assert payload.name is not None
            assert payload.url is not None
            assert payload.price is not None
            assert payload.currency == "USD"
            assert payload.availability in ("in_stock", "out_of_stock", "preorder", "unknown")
            assert payload.category is not None
            assert payload.collected_at is not None
            assert payload.collected_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_no_source_specific_fields_leak(
        self, sample_listing_dict: dict[str, Any]
    ) -> None:
        """Events contain only canonical fields; no eBay-specific data leaks."""
        listing = EbayListingSummary.model_validate(sample_listing_dict)
        search_response = EbaySearchResponse(total=1, item_summaries=[listing])

        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.return_value = (search_response, [])

            adapter = EbayAdapter()
            result = await adapter.fetch()

            event_dict = result.events[0].model_dump()
            # Canonical envelope has exactly these top-level keys
            assert set(event_dict.keys()) == {
                "event_id",
                "event_type",
                "schema_version",
                "source",
                "produced_at",
                "payload",
            }

            # Payload should not have eBay-specific fields like 'seller', 'condition', 'image'
            payload_keys = set(event_dict["payload"].keys())
            assert "seller" not in payload_keys
            assert "condition" not in payload_keys
            assert "image" not in payload_keys
            assert "rating" not in payload_keys


# ---------------------------------------------------------------------------
# 10. Seller identity preservation
# ---------------------------------------------------------------------------


class TestSellerIdentity:
    """Test that seller/listing identifiers are preserved for downstream use."""

    @pytest.mark.asyncio
    async def test_listing_id_preserved_as_external_id(
        self, sample_listing: EbayListingSummary
    ) -> None:
        """eBay item_id is preserved as external_id without transformation."""
        search_response = EbaySearchResponse(total=1, item_summaries=[sample_listing])

        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.return_value = (search_response, [])

            adapter = EbayAdapter()
            result = await adapter.fetch()

            assert len(result.events) == 1
            payload = result.events[0].payload
            assert payload.external_id == "123456789012"

    @pytest.mark.asyncio
    async def test_seller_username_available_in_raw_data(
        self, sample_listing: EbayListingSummary
    ) -> None:
        """Seller username is available in the original listing for downstream normalization."""
        search_response = EbaySearchResponse(total=1, item_summaries=[sample_listing])

        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.return_value = (search_response, [])

            adapter = EbayAdapter()
            await adapter.fetch()

            # The canonical event doesn't leak seller info, but the raw listing has it
            assert sample_listing.seller is not None
            assert sample_listing.seller.username == "top_seller_123"


# ---------------------------------------------------------------------------
# 11. Adapter protocol compliance
# ---------------------------------------------------------------------------


class TestAdapterProtocol:
    """Verify EbayAdapter implements SourceAdapterProtocol correctly."""

    def test_source_name_property(self) -> None:
        """source_name returns 'ebay'."""
        adapter = EbayAdapter()
        assert adapter.source_name == "ebay"

    @pytest.mark.asyncio
    async def test_fetch_returns_fetch_result(self, sample_listing_dict: dict[str, Any]) -> None:
        """fetch() returns a FetchResult instance."""
        listing = EbayListingSummary.model_validate(sample_listing_dict)
        search_response = EbaySearchResponse(total=1, item_summaries=[listing])

        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.return_value = (search_response, [])

            adapter = EbayAdapter()
            result = await adapter.fetch()

            assert isinstance(result, FetchResult)
            assert result.source == "ebay"

    @pytest.mark.asyncio
    async def test_close_releases_resources(self) -> None:
        """close() releases underlying HTTP client resources."""
        with patch.object(EbayClient, "search_items") as mock_search:
            mock_search.return_value = (EbaySearchResponse(total=0, item_summaries=[]), [])

            mock_client = MagicMock()
            mock_client.search_items = AsyncMock(
                return_value=(EbaySearchResponse(total=0, item_summaries=[]), [])
            )
            mock_client.close = AsyncMock()

            adapter = EbayAdapter(client=mock_client)
            await adapter.close()
            mock_client.close.assert_called_once()
