"""Tests for the web retailer HTML parser and adapter integration.

Covers:
- Representative product extraction (all fields populated)
- Multiple products on one page
- Missing price -> null price
- Missing availability -> unknown
- Malformed HTML / unexpected structure -> no crash, partial results
- Empty page -> empty FetchResult
- Canonical event compatibility
- Price parsing edge cases
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from libs.adapters import SourceFetchError
from libs.adapters.web_retailer import WebRetailerAdapter, WebRetailerClient
from libs.adapters.web_retailer.parser import parse_listing_page

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "web_retailer"
BASE_URL = "http://books.toscrape.com"


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Parser: representative extraction
# ---------------------------------------------------------------------------


class TestParseListingPage:
    """Tests for parse_listing_page() with fixed HTML fixtures."""

    def test_extracts_multiple_products(self) -> None:
        html = _load_fixture("listing_page.html")
        products = parse_listing_page(html, base_url=BASE_URL)
        assert len(products) == 3

    def test_all_fields_populated(self) -> None:
        html = _load_fixture("listing_page.html")
        products = parse_listing_page(html, base_url=BASE_URL)

        first = products[0]
        assert first.product_id == "a-light-in-the-attic_1000"
        assert first.name == "A Light in the Attic"
        assert first.price == Decimal("51.77")
        assert first.currency == "GBP"
        assert first.availability == "in_stock"
        assert first.category == "Travel"
        assert "a-light-in-the-attic_1000/index.html" in first.url

    def test_out_of_stock_product(self) -> None:
        html = _load_fixture("listing_page.html")
        products = parse_listing_page(html, base_url=BASE_URL)

        out_of_stock = products[2]
        assert out_of_stock.name == "Soumission"
        assert out_of_stock.availability == "out_of_stock"

    def test_category_from_breadcrumb(self) -> None:
        html = _load_fixture("listing_page.html")
        products = parse_listing_page(html, base_url=BASE_URL)

        for product in products:
            assert product.category == "Travel"

    def test_url_resolution_with_base_url(self) -> None:
        html = _load_fixture("listing_page.html")
        products = parse_listing_page(html, base_url=BASE_URL)

        first = products[0]
        assert first.url.startswith(BASE_URL)
        assert "a-light-in-the-attic_1000/index.html" in first.url

    def test_empty_html_returns_empty_list(self) -> None:
        assert parse_listing_page("") == []
        assert parse_listing_page("   ") == []

    def test_empty_listing_returns_empty_list(self) -> None:
        html = _load_fixture("empty_listing.html")
        products = parse_listing_page(html, base_url=BASE_URL)
        assert products == []

    def test_malformed_structure_does_not_crash(self) -> None:
        html = _load_fixture("malformed_structure.html")
        products = parse_listing_page(html, base_url=BASE_URL)

        valid = [p for p in products if p.product_id == "valid-book_300"]
        assert len(valid) == 1
        assert valid[0].name == "Valid Book"
        assert valid[0].price == Decimal("30.00")


# ---------------------------------------------------------------------------
# Parser: missing/malformed fields
# ---------------------------------------------------------------------------


class TestMissingFields:
    """Tests for graceful handling of missing or malformed HTML elements."""

    def test_missing_price_element(self) -> None:
        html = _load_fixture("missing_price.html")
        products = parse_listing_page(html, base_url=BASE_URL)

        missing = next(p for p in products if p.name == "Missing Price Book")
        assert missing.price is None
        assert missing.currency == "GBP"

    def test_unparseable_price_text(self) -> None:
        html = _load_fixture("missing_price.html")
        products = parse_listing_page(html, base_url=BASE_URL)

        malformed = next(p for p in products if p.name == "Malformed Price Book")
        assert malformed.price is None

    def test_zero_price_is_valid(self) -> None:
        html = _load_fixture("missing_price.html")
        products = parse_listing_page(html, base_url=BASE_URL)

        zero = next(p for p in products if p.name == "Zero Price Book")
        assert zero.price == Decimal("0.00")

    def test_missing_availability_element(self) -> None:
        html = _load_fixture("missing_availability.html")
        products = parse_listing_page(html, base_url=BASE_URL)

        no_avail = next(p for p in products if p.name == "No Availability Book")
        assert no_avail.availability == "unknown"

    def test_unrecognized_availability_class(self) -> None:
        html = _load_fixture("missing_availability.html")
        products = parse_listing_page(html, base_url=BASE_URL)

        unknown = next(p for p in products if p.name == "Unknown Availability Book")
        assert unknown.availability == "unknown"


# ---------------------------------------------------------------------------
# Parser: price parsing edge cases
# ---------------------------------------------------------------------------


class TestPriceParsing:
    """Tests for price string parsing edge cases."""

    def test_gbp_pound_symbol(self) -> None:
        html = '<article class="product_pod"><h3><a href="test_1/index.html" title="Test">Test</a></h3><div class="product_price"><p class="price_color">&pound;99.99</p><p class="instock availability">In stock</p></div></article>'
        products = parse_listing_page(html)
        assert products[0].price == Decimal("99.99")
        assert products[0].currency == "GBP"

    def test_dollar_sign(self) -> None:
        html = '<article class="product_pod"><h3><a href="test_1/index.html" title="Test">Test</a></h3><div class="product_price"><p class="price_color">$42.50</p><p class="instock availability">In stock</p></div></article>'
        products = parse_listing_page(html)
        assert products[0].price == Decimal("42.50")
        assert products[0].currency == "USD"

    def test_euro_sign(self) -> None:
        html = '<article class="product_pod"><h3><a href="test_1/index.html" title="Test">Test</a></h3><div class="product_price"><p class="price_color">\u20ac15.00</p><p class="instock availability">In stock</p></div></article>'
        products = parse_listing_page(html)
        assert products[0].price == Decimal("15.00")
        assert products[0].currency == "EUR"

    def test_integer_price(self) -> None:
        html = '<article class="product_pod"><h3><a href="test_1/index.html" title="Test">Test</a></h3><div class="product_price"><p class="price_color">&pound;50</p><p class="instock availability">In stock</p></div></article>'
        products = parse_listing_page(html)
        assert products[0].price == Decimal("50")


# ---------------------------------------------------------------------------
# Adapter: canonical event integration
# ---------------------------------------------------------------------------


class TestAdapterIntegration:
    """Tests for the adapter producing canonical ProductObservationEvent."""

    @pytest.fixture
    def mock_client(self) -> WebRetailerClient:
        client = AsyncMock(spec=WebRetailerClient)
        client._base_url = BASE_URL
        return client

    @pytest.mark.asyncio
    async def test_fetch_returns_canonical_events(self, mock_client: WebRetailerClient) -> None:
        html = _load_fixture("listing_page.html")
        mock_client.fetch_listing_page = AsyncMock(return_value=html)

        adapter = WebRetailerAdapter(client=mock_client)
        result = await adapter.fetch()

        assert result.has_events
        assert len(result.events) == 3
        assert result.source == "web_retailer"
        assert result.total_records == 3

    @pytest.mark.asyncio
    async def test_event_source_matches_adapter(self, mock_client: WebRetailerClient) -> None:
        html = _load_fixture("listing_page.html")
        mock_client.fetch_listing_page = AsyncMock(return_value=html)

        adapter = WebRetailerAdapter(client=mock_client)
        result = await adapter.fetch()

        for event in result.events:
            assert event.source == "web_retailer"

    @pytest.mark.asyncio
    async def test_external_id_is_stable(self, mock_client: WebRetailerClient) -> None:
        html = _load_fixture("listing_page.html")
        mock_client.fetch_listing_page = AsyncMock(return_value=html)

        adapter = WebRetailerAdapter(client=mock_client)
        result1 = await adapter.fetch()
        result2 = await adapter.fetch()

        ids1 = [e.payload.external_id for e in result1.events]
        ids2 = [e.payload.external_id for e in result2.events]
        assert ids1 == ids2

    @pytest.mark.asyncio
    async def test_empty_html_raises_source_fetch_error(
        self, mock_client: WebRetailerClient
    ) -> None:
        mock_client.fetch_listing_page = AsyncMock(return_value="")

        adapter = WebRetailerAdapter(client=mock_client)
        with pytest.raises(SourceFetchError, match="empty HTML"):
            await adapter.fetch()

    @pytest.mark.asyncio
    async def test_empty_listing_returns_zero_events(self, mock_client: WebRetailerClient) -> None:
        html = _load_fixture("empty_listing.html")
        mock_client.fetch_listing_page = AsyncMock(return_value=html)

        adapter = WebRetailerAdapter(client=mock_client)
        result = await adapter.fetch()

        assert not result.has_events
        assert result.total_records == 0
        assert not result.has_malformed

    @pytest.mark.asyncio
    async def test_missing_price_produces_null_price_event(
        self, mock_client: WebRetailerClient
    ) -> None:
        html = _load_fixture("missing_price.html")
        mock_client.fetch_listing_page = AsyncMock(return_value=html)

        adapter = WebRetailerAdapter(client=mock_client)
        result = await adapter.fetch()

        assert result.has_events
        missing_price_events = [e for e in result.events if e.payload.name == "Missing Price Book"]
        assert len(missing_price_events) == 1
        assert missing_price_events[0].payload.price is None

    @pytest.mark.asyncio
    async def test_malformed_structure_partial_results(
        self, mock_client: WebRetailerClient
    ) -> None:
        html = _load_fixture("malformed_structure.html")
        mock_client.fetch_listing_page = AsyncMock(return_value=html)

        adapter = WebRetailerAdapter(client=mock_client)
        result = await adapter.fetch()

        valid_events = [e for e in result.events if e.payload.name == "Valid Book"]
        assert len(valid_events) == 1

    @pytest.mark.asyncio
    async def test_event_id_is_deterministic(self, mock_client: WebRetailerClient) -> None:
        html = _load_fixture("listing_page.html")
        mock_client.fetch_listing_page = AsyncMock(return_value=html)

        adapter = WebRetailerAdapter(client=mock_client)

        result = await adapter.fetch()

        for event in result.events:
            expected_id = (
                f"web_retailer:{event.payload.external_id}:{event.payload.collected_at.isoformat()}"
            )
            assert event.event_id == expected_id

    @pytest.mark.asyncio
    async def test_availability_mapped_correctly(self, mock_client: WebRetailerClient) -> None:
        html = _load_fixture("listing_page.html")
        mock_client.fetch_listing_page = AsyncMock(return_value=html)

        adapter = WebRetailerAdapter(client=mock_client)
        result = await adapter.fetch()

        avail_map = {e.payload.name: e.payload.availability.value for e in result.events}
        assert avail_map["A Light in the Attic"] == "in_stock"
        assert avail_map["Soumission"] == "out_of_stock"
