"""Tests for the Best Buy API adapter.

Covers:
- representative mapping
- API-key/config validation
- malformed response
- auth failure
- rate-limit/error response
- empty results
- canonical compatibility
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from libs.adapters import FetchResult, SourceFetchError
from libs.adapters.best_buy import BestBuyAdapter, BestBuyClient, BestBuyProduct

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_product_dict() -> dict[str, Any]:
    """Representative Best Buy product response."""
    return {
        "sku": 8880044,
        "name": "Batman Begins (Blu-ray Disc)",
        "salePrice": 7.99,
        "regularPrice": 19.99,
        "manufacturer": "Warner Home Video",
        "modelNumber": "1234567",
        "categoryPath": [
            {"id": "cat00000", "name": "Best Buy"},
            {"id": "pcmcat128500050004", "name": "Movies & TV Shows"},
            {"id": "pcmcat297000050005", "name": "Blu-ray"},
        ],
        "url": "https://api.bestbuy.com/click/-/8880044/pdp",
        "image": "http://img.bbystatic.com/BestBuy_US/images/products/8880/8880044_rc.jpg",
        "customerReviewCount": 411,
        "customerReviewAverage": 4.1,
        "inStoreAvailability": True,
        "onlineAvailability": True,
        "releaseDate": "2005-03-08",
    }


@pytest.fixture
def sample_product(sample_product_dict: dict[str, Any]) -> BestBuyProduct:
    """Typed BestBuyProduct from dict."""
    return BestBuyProduct.model_validate(sample_product_dict)


@pytest.fixture
def multiple_products() -> list[dict[str, Any]]:
    """Multiple products for batch testing."""
    return [
        {
            "sku": 1001,
            "name": "Product One",
            "salePrice": 10.0,
            "regularPrice": 15.0,
            "categoryPath": [{"id": "cat1", "name": "Electronics"}],
            "inStoreAvailability": True,
            "onlineAvailability": True,
        },
        {
            "sku": 1002,
            "name": "Product Two",
            "salePrice": None,
            "regularPrice": 20.50,
            "categoryPath": [{"id": "cat2", "name": "Jewelry"}],
            "inStoreAvailability": False,
            "onlineAvailability": True,
        },
        {
            "sku": 1003,
            "name": "Product Three",
            "salePrice": 0.0,
            "regularPrice": None,
            "categoryPath": [],
            "inStoreAvailability": False,
            "onlineAvailability": False,
        },
    ]


# ---------------------------------------------------------------------------
# 1. Representative mapping
# ---------------------------------------------------------------------------


class TestProductMapping:
    """Test single product mapping to canonical events."""

    @pytest.mark.asyncio
    async def test_map_single_product(self, sample_product: BestBuyProduct) -> None:
        """A single BestBuyProduct maps to a valid canonical event."""
        with patch("libs.adapters.best_buy.adapter.BestBuyClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(return_value=[sample_product])
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = BestBuyAdapter(api_key="test-key")
            result = await adapter.fetch()

            assert len(result.events) == 1
            event = result.events[0]
            payload = event.payload

            assert payload.external_id == "8880044"
            assert payload.name == sample_product.name
            # Price is Decimal in canonical model
            assert (
                float(payload.price) == sample_product.salePrice
                if payload.price
                else sample_product.salePrice is None
            )
            assert payload.currency == "USD"
            assert payload.availability == "in_stock"
            assert payload.category == "Blu-ray"  # Most specific category
            assert "bestbuy.com" in payload.url

    def test_external_id_is_string(self, sample_product: BestBuyProduct) -> None:
        """external_id must be a string even though source uses integer SKU."""
        assert isinstance(sample_product.sku, int)
        # The adapter converts to str when building events
        assert str(sample_product.sku) == "8880044"


# ---------------------------------------------------------------------------
# 2. Multiple records
# ---------------------------------------------------------------------------


class TestMultipleRecords:
    """Test fetching and mapping multiple products."""

    @pytest.mark.asyncio
    async def test_fetch_multiple_products(self, multiple_products: list[dict[str, Any]]) -> None:
        """Adapter fetches and maps multiple products correctly."""
        typed_products = [BestBuyProduct.model_validate(p) for p in multiple_products]

        with patch("libs.adapters.best_buy.adapter.BestBuyClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(return_value=typed_products)
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = BestBuyAdapter(api_key="test-key", page_size=10)
            result = await adapter.fetch()

            assert len(result.events) == 3
            assert result.total_records == 3
            assert all(e.source == "best_buy" for e in result.events)
            assert result.events[0].payload.external_id == "1001"
            assert result.events[1].payload.external_id == "1002"
            assert result.events[2].payload.external_id == "1003"

    @pytest.mark.asyncio
    async def test_falls_back_to_regular_price(self) -> None:
        """When salePrice is None, falls back to regularPrice."""
        product_dict = {
            "sku": 2001,
            "name": "No Sale Price",
            "salePrice": None,
            "regularPrice": 25.0,
            "categoryPath": [],
        }
        product = BestBuyProduct.model_validate(product_dict)

        with patch("libs.adapters.best_buy.adapter.BestBuyClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(return_value=[product])
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = BestBuyAdapter(api_key="test-key")
            result = await adapter.fetch()

            assert len(result.events) == 1
            price = result.events[0].payload.price
            assert price is not None and float(price) == 25.0

    @pytest.mark.asyncio
    async def test_availability_mapping(self) -> None:
        """Availability is mapped correctly from inStore/online flags."""
        # Both available -> in_stock
        p1 = BestBuyProduct(sku=1, name="A", inStoreAvailability=True, onlineAvailability=True)
        # Neither available -> out_of_stock
        p2 = BestBuyProduct(sku=2, name="B", inStoreAvailability=False, onlineAvailability=False)
        # Unknown when both None
        p3 = BestBuyProduct(sku=3, name="C", inStoreAvailability=None, onlineAvailability=None)

        with patch("libs.adapters.best_buy.adapter.BestBuyClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(return_value=[p1, p2, p3])
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = BestBuyAdapter(api_key="test-key")
            result = await adapter.fetch()

            assert result.events[0].payload.availability == "in_stock"
            assert result.events[1].payload.availability == "out_of_stock"
            assert result.events[2].payload.availability == "unknown"


# ---------------------------------------------------------------------------
# 3. API key / config validation
# ---------------------------------------------------------------------------


class TestApiKeyValidation:
    """Test API key configuration and validation."""

    def test_missing_api_key_raises_error(self) -> None:
        """Creating client without API key raises SourceFetchError."""
        # Ensure env var is not set
        original = os.environ.pop("BESTBUY_API_KEY", None)
        try:
            with pytest.raises(SourceFetchError) as exc_info:
                BestBuyClient()
            assert "api key" in exc_info.value.args[0].lower()
            assert exc_info.value.source == "best_buy"
        finally:
            if original:
                os.environ["BESTBUY_API_KEY"] = original

    def test_api_key_from_env_var(self) -> None:
        """API key can be provided via BESTBUY_API_KEY environment variable."""
        os.environ["BESTBUY_API_KEY"] = "env-test-key"
        try:
            client = BestBuyClient()
            assert client._api_key == "env-test-key"
        finally:
            del os.environ["BESTBUY_API_KEY"]

    def test_api_key_parameter_overrides_env(self) -> None:
        """Explicit api_key parameter takes precedence over env var."""
        os.environ["BESTBUY_API_KEY"] = "env-key"
        try:
            client = BestBuyClient(api_key="param-key")
            assert client._api_key == "param-key"
        finally:
            del os.environ["BESTBUY_API_KEY"]


# ---------------------------------------------------------------------------
# 4. Malformed response
# ---------------------------------------------------------------------------


class TestMalformedResponse:
    """Test handling of malformed API responses."""

    @pytest.mark.asyncio
    async def test_missing_products_key_raises_error(self) -> None:
        """Response without 'products' key raises SourceFetchError."""
        with patch("libs.adapters.best_buy.client.httpx.AsyncClient") as MockHttpClient:
            mock_response = MagicMock()
            mock_response.json.return_value = {"items": []}  # Wrong key
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()

            mock_client_instance = MagicMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            MockHttpClient.return_value = mock_client_instance

            client = BestBuyClient(api_key="test-key", http_client=mock_client_instance)

            with pytest.raises(SourceFetchError) as exc_info:
                await client.fetch_products()
            assert "products" in exc_info.value.args[0].lower()

    @pytest.mark.asyncio
    async def test_non_list_products_raises_error(self) -> None:
        """Response with non-list 'products' field raises SourceFetchError."""
        with patch("libs.adapters.best_buy.client.httpx.AsyncClient") as MockHttpClient:
            mock_response = MagicMock()
            mock_response.json.return_value = {"products": "not-a-list"}
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()

            mock_client_instance = MagicMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            MockHttpClient.return_value = mock_client_instance

            client = BestBuyClient(api_key="test-key", http_client=mock_client_instance)

            with pytest.raises(SourceFetchError) as exc_info:
                await client.fetch_products()
            assert "list" in exc_info.value.args[0].lower()


# ---------------------------------------------------------------------------
# 5. Auth failure
# ---------------------------------------------------------------------------


class TestAuthFailure:
    """Test authentication error handling."""

    @pytest.mark.asyncio
    async def test_403_raises_auth_error(self) -> None:
        """HTTP 403 raises SourceFetchError with auth message."""
        with patch("libs.adapters.best_buy.adapter.BestBuyClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(
                side_effect=SourceFetchError(
                    "Best Buy API authentication failed (403). Check your API key.",
                    source="best_buy",
                )
            )
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = BestBuyAdapter(api_key="invalid-key")

            with pytest.raises(SourceFetchError) as exc_info:
                await adapter.fetch()

            assert exc_info.value.source == "best_buy"
            assert (
                "authentication" in exc_info.value.args[0].lower()
                or "403" in exc_info.value.args[0]
            )


# ---------------------------------------------------------------------------
# 6. Rate limit / error response
# ---------------------------------------------------------------------------


class TestRateLimitErrors:
    """Test rate limit and other HTTP error handling."""

    @pytest.mark.asyncio
    async def test_429_raises_rate_limit_error(self) -> None:
        """HTTP 429 raises SourceFetchError with rate limit message."""
        with patch("libs.adapters.best_buy.adapter.BestBuyClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(
                side_effect=SourceFetchError(
                    "Best Buy API rate limit exceeded (429). Retry after cooldown.",
                    source="best_buy",
                )
            )
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = BestBuyAdapter(api_key="test-key")

            with pytest.raises(SourceFetchError) as exc_info:
                await adapter.fetch()

            assert exc_info.value.source == "best_buy"
            assert "rate limit" in exc_info.value.args[0].lower() or "429" in exc_info.value.args[0]

    @pytest.mark.asyncio
    async def test_5xx_raises_source_fetch_error(self) -> None:
        """5xx errors raise SourceFetchError."""
        with patch("libs.adapters.best_buy.adapter.BestBuyClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(
                side_effect=SourceFetchError(
                    "Best Buy API returned HTTP 500",
                    source="best_buy",
                )
            )
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = BestBuyAdapter(api_key="test-key")

            with pytest.raises(SourceFetchError) as exc_info:
                await adapter.fetch()

            assert exc_info.value.source == "best_buy"


# ---------------------------------------------------------------------------
# 7. Empty results
# ---------------------------------------------------------------------------


class TestEmptyResults:
    """Test handling of empty API responses."""

    @pytest.mark.asyncio
    async def test_empty_products_list_returns_empty_events(self) -> None:
        """Empty products list returns FetchResult with no events."""
        with patch("libs.adapters.best_buy.adapter.BestBuyClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(return_value=[])
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = BestBuyAdapter(api_key="test-key")
            result = await adapter.fetch()

            assert len(result.events) == 0
            assert len(result.malformed) == 0
            assert result.total_records == 0
            assert result.source == "best_buy"
            assert not result.has_events


# ---------------------------------------------------------------------------
# 8. Canonical compatibility
# ---------------------------------------------------------------------------


class TestCanonicalCompatibility:
    """Verify events conform to the canonical contract."""

    @pytest.mark.asyncio
    async def test_events_have_required_fields(self, sample_product_dict: dict[str, Any]) -> None:
        """All emitted events have required canonical envelope fields."""
        product = BestBuyProduct.model_validate(sample_product_dict)

        with patch("libs.adapters.best_buy.adapter.BestBuyClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(return_value=[product])
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = BestBuyAdapter(api_key="test-key")
            result = await adapter.fetch()

            assert len(result.events) == 1
            event = result.events[0]

            # Envelope fields
            assert event.event_id is not None
            assert event.event_type == "product.observation"
            assert event.schema_version == 1
            assert event.source == "best_buy"
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
        self, sample_product_dict: dict[str, Any]
    ) -> None:
        """Events contain only canonical fields; no Best Buy-specific data leaks."""
        product = BestBuyProduct.model_validate(sample_product_dict)

        with patch("libs.adapters.best_buy.adapter.BestBuyClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(return_value=[product])
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = BestBuyAdapter(api_key="test-key")
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

            # Payload should not have Best Buy-specific fields
            payload_keys = set(event_dict["payload"].keys())
            assert "manufacturer" not in payload_keys
            assert "modelNumber" not in payload_keys
            assert "customerReviewCount" not in payload_keys
            assert "customerReviewAverage" not in payload_keys
            assert "releaseDate" not in payload_keys


# ---------------------------------------------------------------------------
# 9. Adapter protocol compliance
# ---------------------------------------------------------------------------


class TestAdapterProtocol:
    """Verify BestBuyAdapter implements SourceAdapterProtocol correctly."""

    def test_source_name_property(self) -> None:
        """source_name returns 'best_buy'."""
        adapter = BestBuyAdapter(api_key="test-key")
        assert adapter.source_name == "best_buy"

    @pytest.mark.asyncio
    async def test_fetch_returns_fetch_result(self, sample_product_dict: dict[str, Any]) -> None:
        """fetch() returns a FetchResult instance."""
        product = BestBuyProduct.model_validate(sample_product_dict)

        with patch("libs.adapters.best_buy.adapter.BestBuyClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(return_value=[product])
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = BestBuyAdapter(api_key="test-key")
            result = await adapter.fetch()

            assert isinstance(result, FetchResult)
            assert result.source == "best_buy"

    @pytest.mark.asyncio
    async def test_close_releases_resources(self) -> None:
        """close() releases underlying HTTP client resources."""
        with patch("libs.adapters.best_buy.adapter.BestBuyClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(return_value=[])
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = BestBuyAdapter(api_key="test-key")
            await adapter.close()
            mock_instance.close.assert_called_once()
