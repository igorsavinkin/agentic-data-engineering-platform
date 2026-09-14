"""Tests for the Fake Store API adapter.

Covers:
- representative product mapping
- multiple records
- nullable fields
- malformed upstream record
- HTTP timeout/error
- empty source response
- canonical event compatibility
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from libs.adapters import FetchResult, SourceFetchError
from libs.adapters.fake_store import FakeStoreAdapter, FakeStoreProduct
from libs.event_contracts.product_observation import (
    ProductObservationPayload,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_product_dict() -> dict[str, Any]:
    """Representative Fake Store product response."""
    return {
        "id": 1,
        "title": "Fjallraven - Foldsack No. 1 Backpack, Fits 15 Laptops",
        "price": 109.95,
        "description": "Your perfect pack for everyday use and walks in the forest.",
        "category": "men's clothing",
        "image": "https://fakestoreapi.com/img/81fPKd-2AYL._AC_SL1500_.jpg",
        "rating": {"rate": 3.9, "count": 120},
    }


@pytest.fixture
def sample_product(sample_product_dict: dict[str, Any]) -> FakeStoreProduct:
    """Typed FakeStoreProduct from dict."""
    return FakeStoreProduct.model_validate(sample_product_dict)


@pytest.fixture
def multiple_products() -> list[dict[str, Any]]:
    """Multiple products for batch testing."""
    return [
        {
            "id": 1,
            "title": "Product One",
            "price": 10.0,
            "description": "First product",
            "category": "electronics",
            "image": None,
            "rating": None,
        },
        {
            "id": 2,
            "title": "Product Two",
            "price": 20.50,
            "description": "Second product",
            "category": "jewelery",
            "image": "https://example.com/img.jpg",
            "rating": {"rate": 4.5, "count": 50},
        },
        {
            "id": 3,
            "title": "Product Three",
            "price": 0.0,
            "description": "Free item",
            "category": "men's clothing",
            "image": None,
            "rating": None,
        },
    ]


@pytest.fixture
def malformed_product_dict() -> dict[str, Any]:
    """Product missing required fields to trigger validation failure."""
    return {
        "id": 999,
        # Missing title, price, description, category — should fail validation
    }


# ---------------------------------------------------------------------------
# 1. Representative product mapping
# ---------------------------------------------------------------------------


class TestProductMapping:
    """Test single product mapping to canonical events."""

    @pytest.mark.asyncio
    async def test_map_single_product(self, sample_product: FakeStoreProduct) -> None:
        """A single FakeStoreProduct maps to a valid canonical event."""
        with patch("libs.adapters.fake_store.adapter.FakeStoreClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(return_value=([sample_product], []))
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = FakeStoreAdapter()
            result = await adapter.fetch()

            assert len(result.events) == 1
            event = result.events[0]
            payload = event.payload

            assert isinstance(payload, ProductObservationPayload)
            assert payload.external_id == "1"
            assert payload.name == sample_product.title
            # Price is converted to Decimal by _build_event for precision
            assert (
                float(payload.price) == sample_product.price
                if payload.price
                else sample_product.price is None
            )
            assert payload.currency == "USD"
            assert payload.availability == "in_stock"
            assert payload.category == sample_product.category
            assert "fakestoreapi.com/products/1" in payload.url

    @pytest.mark.asyncio
    async def test_external_id_is_string(self, sample_product: FakeStoreProduct) -> None:
        """external_id must be a string even though source uses integer IDs."""
        with patch("libs.adapters.fake_store.adapter.FakeStoreClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(return_value=([sample_product], []))
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = FakeStoreAdapter()
            result = await adapter.fetch()

            assert len(result.events) == 1
            payload = result.events[0].payload
            assert isinstance(payload.external_id, str)
            assert payload.external_id == "1"


# ---------------------------------------------------------------------------
# 2. Multiple records
# ---------------------------------------------------------------------------


class TestMultipleRecords:
    """Test fetching and mapping multiple products."""

    @pytest.mark.asyncio
    async def test_fetch_multiple_products(self, multiple_products: list[dict[str, Any]]) -> None:
        """Adapter fetches and maps multiple products correctly."""
        typed_products = [FakeStoreProduct.model_validate(p) for p in multiple_products]

        with patch("libs.adapters.fake_store.adapter.FakeStoreClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(return_value=(typed_products, []))
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = FakeStoreAdapter(limit=10)
            result = await adapter.fetch()

            assert len(result.events) == 3
            assert result.total_records == 3
            assert all(e.source == "fake_store" for e in result.events)
            assert result.events[0].payload.external_id == "1"
            assert result.events[1].payload.external_id == "2"
            assert result.events[2].payload.external_id == "3"

    @pytest.mark.asyncio
    async def test_fetch_with_limit(self, multiple_products: list[dict[str, Any]]) -> None:
        """Adapter passes limit parameter to client."""
        typed_products = [FakeStoreProduct.model_validate(p) for p in multiple_products[:1]]

        with patch("libs.adapters.fake_store.adapter.FakeStoreClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(return_value=(typed_products, []))
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = FakeStoreAdapter(limit=1)
            await adapter.fetch()

            mock_instance.fetch_products.assert_called_once_with(limit=1)


# ---------------------------------------------------------------------------
# 3. Nullable fields
# ---------------------------------------------------------------------------


class TestNullableFields:
    """Test handling of nullable/optional fields."""

    @pytest.mark.asyncio
    async def test_null_image_field(self) -> None:
        """Product with null image still maps correctly."""
        product = FakeStoreProduct(
            id=1,
            title="Test",
            price=10.0,
            description="Desc",
            category="cat",
            image=None,
            rating=None,
        )

        with patch("libs.adapters.fake_store.adapter.FakeStoreClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(return_value=([product], []))
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = FakeStoreAdapter()
            result = await adapter.fetch()

            assert len(result.events) == 1
            payload = result.events[0].payload
            assert payload.external_id == "1"
            assert payload.price == 10.0

    @pytest.mark.asyncio
    async def test_zero_price(self) -> None:
        """Product with zero price is preserved (not treated as null)."""
        product = FakeStoreProduct(
            id=1,
            title="Free Item",
            price=0.0,
            description="Desc",
            category="cat",
            image=None,
            rating=None,
        )

        with patch("libs.adapters.fake_store.adapter.FakeStoreClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(return_value=([product], []))
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = FakeStoreAdapter()
            result = await adapter.fetch()

            assert len(result.events) == 1
            payload = result.events[0].payload
            assert payload.price == 0.0


# ---------------------------------------------------------------------------
# 4. Malformed upstream record
# ---------------------------------------------------------------------------


class TestMalformedRecords:
    """Test handling of malformed source records."""

    @pytest.mark.asyncio
    async def test_malformed_record_separated(
        self,
        multiple_products: list[dict[str, Any]],
        malformed_product_dict: dict[str, Any],
    ) -> None:
        """Malformed records are separated into malformed tuple, not events."""
        # Client returns valid products and captures malformed ones with reason
        valid_products = [FakeStoreProduct.model_validate(p) for p in multiple_products]
        malformed_entry = {
            "raw_record": malformed_product_dict,
            "reason": "Validation failed at index 0: ...",
        }

        with patch("libs.adapters.fake_store.adapter.FakeStoreClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(
                return_value=(valid_products, [malformed_entry])
            )
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = FakeStoreAdapter()
            result = await adapter.fetch()

            # Valid products make it through, malformed is captured separately
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

        with patch("libs.adapters.fake_store.adapter.FakeStoreClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(return_value=([], malformed_entries))
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = FakeStoreAdapter()
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
        with patch("libs.adapters.fake_store.adapter.FakeStoreClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(
                side_effect=SourceFetchError(
                    "Fake Store API request timed out",
                    source="fake_store",
                )
            )
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = FakeStoreAdapter()

            with pytest.raises(SourceFetchError) as exc_info:
                await adapter.fetch()

            assert exc_info.value.source == "fake_store"
            assert "timed out" in exc_info.value.args[0].lower()

    @pytest.mark.asyncio
    async def test_5xx_error_raises_source_fetch_error(self) -> None:
        """5xx errors raise SourceFetchError."""
        with patch("libs.adapters.fake_store.adapter.FakeStoreClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(
                side_effect=SourceFetchError(
                    "Fake Store API returned HTTP 503",
                    source="fake_store",
                )
            )
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = FakeStoreAdapter()

            with pytest.raises(SourceFetchError) as exc_info:
                await adapter.fetch()

            assert exc_info.value.source == "fake_store"

    @pytest.mark.asyncio
    async def test_4xx_error_raises_source_fetch_error(self) -> None:
        """4xx errors raise SourceFetchError."""
        with patch("libs.adapters.fake_store.adapter.FakeStoreClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(
                side_effect=SourceFetchError(
                    "Fake Store API returned HTTP 404",
                    source="fake_store",
                )
            )
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = FakeStoreAdapter()

            with pytest.raises(SourceFetchError) as exc_info:
                await adapter.fetch()

            assert exc_info.value.source == "fake_store"

    @pytest.mark.asyncio
    async def test_invalid_json_raises_source_fetch_error(self) -> None:
        """Invalid JSON response raises SourceFetchError."""
        with patch("libs.adapters.fake_store.adapter.FakeStoreClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(
                side_effect=SourceFetchError(
                    "Fake Store API returned invalid JSON",
                    source="fake_store",
                )
            )
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = FakeStoreAdapter()

            with pytest.raises(SourceFetchError) as exc_info:
                await adapter.fetch()

            assert "invalid json" in exc_info.value.args[0].lower()


# ---------------------------------------------------------------------------
# 6. Empty source response
# ---------------------------------------------------------------------------


class TestEmptyResponse:
    """Test handling of empty API responses."""

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty_events(self) -> None:
        """Empty product list returns FetchResult with no events."""
        with patch("libs.adapters.fake_store.adapter.FakeStoreClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(return_value=([], []))
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = FakeStoreAdapter()
            result = await adapter.fetch()

            assert len(result.events) == 0
            assert len(result.malformed) == 0
            assert result.total_records == 0
            assert result.source == "fake_store"
            assert not result.has_events


# ---------------------------------------------------------------------------
# 7. Canonical event compatibility
# ---------------------------------------------------------------------------


class TestCanonicalCompatibility:
    """Verify events conform to the canonical contract."""

    @pytest.mark.asyncio
    async def test_events_have_required_fields(self, sample_product_dict: dict[str, Any]) -> None:
        """All emitted events have required canonical envelope fields."""
        product = FakeStoreProduct.model_validate(sample_product_dict)

        with patch("libs.adapters.fake_store.adapter.FakeStoreClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(return_value=([product], []))
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = FakeStoreAdapter()
            result = await adapter.fetch()

            assert len(result.events) == 1
            event = result.events[0]

            # Envelope fields
            assert event.event_id is not None
            assert event.event_type == "product.observation"
            assert event.schema_version == 1
            assert event.source == "fake_store"
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
        """Events contain only canonical fields; no Fake Store-specific data leaks."""
        product = FakeStoreProduct.model_validate(sample_product_dict)

        with patch("libs.adapters.fake_store.adapter.FakeStoreClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(return_value=([product], []))
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = FakeStoreAdapter()
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

            # Payload should not have Fake Store-specific fields like 'rating' or 'image'
            payload_keys = set(event_dict["payload"].keys())
            assert "rating" not in payload_keys
            assert "image" not in payload_keys
            assert "description" not in payload_keys


# ---------------------------------------------------------------------------
# 8. Adapter protocol compliance
# ---------------------------------------------------------------------------


class TestAdapterProtocol:
    """Verify FakeStoreAdapter implements SourceAdapterProtocol correctly."""

    def test_source_name_property(self) -> None:
        """source_name returns 'fake_store'."""
        adapter = FakeStoreAdapter()
        assert adapter.source_name == "fake_store"

    @pytest.mark.asyncio
    async def test_fetch_returns_fetch_result(self, sample_product_dict: dict[str, Any]) -> None:
        """fetch() returns a FetchResult instance."""
        product = FakeStoreProduct.model_validate(sample_product_dict)

        with patch("libs.adapters.fake_store.adapter.FakeStoreClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(return_value=([product], []))
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = FakeStoreAdapter()
            result = await adapter.fetch()

            assert isinstance(result, FetchResult)
            assert result.source == "fake_store"

    @pytest.mark.asyncio
    async def test_close_releases_resources(self) -> None:
        """close() releases underlying HTTP client resources."""
        with patch("libs.adapters.fake_store.adapter.FakeStoreClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.fetch_products = AsyncMock(return_value=([], []))
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            adapter = FakeStoreAdapter()
            await adapter.close()
            mock_instance.close.assert_called_once()
