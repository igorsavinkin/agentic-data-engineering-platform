"""Tests for the web retailer HTML parser and adapter integration.

Covers:
- Representative product extraction (all fields populated)
- Multiple products on one page
- Missing price -> null price
- Missing availability -> unknown
- Malformed HTML / unexpected structure -> no crash, partial results + malformed
- Empty page -> empty FetchResult
- Canonical event compatibility
- Price parsing edge cases (currency symbols, thousands separators, zero)
- Realistic ../../ relative URL resolution (F1)
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from libs.adapters import SourceFetchError
from libs.adapters.web_retailer import WebRetailerAdapter, WebRetailerClient
from libs.adapters.web_retailer.parser import extract_next_page_url, parse_listing_page

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "web_retailer"
PAGE_URL = "http://books.toscrape.com/catalogue/category/books_1/index.html"


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Parser: representative extraction
# ---------------------------------------------------------------------------


class TestParseListingPage:
    """Tests for parse_listing_page() with fixed HTML fixtures."""

    def test_extracts_multiple_products(self) -> None:
        html = _load_fixture("listing_page.html")
        products, malformed = parse_listing_page(html, page_url=PAGE_URL)
        assert len(products) == 3
        assert len(malformed) == 0

    def test_all_fields_populated(self) -> None:
        html = _load_fixture("listing_page.html")
        products, _ = parse_listing_page(html, page_url=PAGE_URL)

        first = products[0]
        assert first.product_id == "a-light-in-the-attic_1000"
        assert first.name == "A Light in the Attic"
        assert first.price == Decimal("51.77")
        assert first.currency == "GBP"
        assert first.availability == "in_stock"
        assert first.category == "Travel"

    def test_url_resolved_correctly_with_relative_links(self) -> None:
        """Real books.toscrape.com uses ../../ relative links (F1)."""
        html = _load_fixture("listing_page.html")
        products, _ = parse_listing_page(html, page_url=PAGE_URL)

        assert (
            products[0].url
            == "http://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
        )
        assert (
            products[1].url
            == "http://books.toscrape.com/catalogue/tipping-the-velvet_999/index.html"
        )
        assert products[2].url == "http://books.toscrape.com/catalogue/soumission_998/index.html"

    def test_out_of_stock_product(self) -> None:
        html = _load_fixture("listing_page.html")
        products, _ = parse_listing_page(html, page_url=PAGE_URL)

        out_of_stock = products[2]
        assert out_of_stock.name == "Soumission"
        assert out_of_stock.availability == "out_of_stock"

    def test_category_from_breadcrumb(self) -> None:
        html = _load_fixture("listing_page.html")
        products, _ = parse_listing_page(html, page_url=PAGE_URL)

        for product in products:
            assert product.category == "Travel"

    def test_empty_html_returns_empty_lists(self) -> None:
        products, malformed = parse_listing_page("")
        assert products == []
        assert malformed == []
        products, malformed = parse_listing_page("   ")
        assert products == []
        assert malformed == []

    def test_empty_listing_returns_empty_lists(self) -> None:
        html = _load_fixture("empty_listing.html")
        products, malformed = parse_listing_page(html, page_url=PAGE_URL)
        assert products == []
        assert malformed == []

    def test_malformed_structure_partial_results(self) -> None:
        html = _load_fixture("malformed_structure.html")
        products, malformed = parse_listing_page(html, page_url=PAGE_URL)

        valid = [p for p in products if p.product_id == "valid-book_300"]
        assert len(valid) == 1
        assert valid[0].name == "Valid Book"
        assert valid[0].price == Decimal("30.00")
        assert len(malformed) == 2


# ---------------------------------------------------------------------------
# Parser: missing/malformed fields
# ---------------------------------------------------------------------------


class TestMissingFields:
    """Tests for graceful handling of missing or malformed HTML elements."""

    def test_missing_price_element(self) -> None:
        html = _load_fixture("missing_price.html")
        products, _ = parse_listing_page(html, page_url=PAGE_URL)

        missing = next(p for p in products if p.name == "Missing Price Book")
        assert missing.price is None
        assert missing.currency == "GBP"

    def test_unparseable_price_text(self) -> None:
        html = _load_fixture("missing_price.html")
        products, _ = parse_listing_page(html, page_url=PAGE_URL)

        malformed_price = next(p for p in products if p.name == "Malformed Price Book")
        assert malformed_price.price is None

    def test_zero_price_is_valid(self) -> None:
        html = _load_fixture("missing_price.html")
        products, _ = parse_listing_page(html, page_url=PAGE_URL)

        zero = next(p for p in products if p.name == "Zero Price Book")
        assert zero.price == Decimal("0.00")

    def test_missing_availability_element(self) -> None:
        html = _load_fixture("missing_availability.html")
        products, _ = parse_listing_page(html, page_url=PAGE_URL)

        no_avail = next(p for p in products if p.name == "No Availability Book")
        assert no_avail.availability == "unknown"

    def test_unrecognized_availability_class(self) -> None:
        html = _load_fixture("missing_availability.html")
        products, _ = parse_listing_page(html, page_url=PAGE_URL)

        unknown = next(p for p in products if p.name == "Unknown Availability Book")
        assert unknown.availability == "unknown"


# ---------------------------------------------------------------------------
# Parser: price parsing edge cases
# ---------------------------------------------------------------------------


class TestPriceParsing:
    """Tests for price string parsing edge cases."""

    def test_gbp_pound_symbol(self) -> None:
        html = '<article class="product_pod"><h3><a href="test_1/index.html" title="Test">Test</a></h3><div class="product_price"><p class="price_color">&pound;99.99</p><p class="instock availability">In stock</p></div></article>'
        products, _ = parse_listing_page(html)
        assert products[0].price == Decimal("99.99")
        assert products[0].currency == "GBP"

    def test_dollar_sign(self) -> None:
        html = '<article class="product_pod"><h3><a href="test_1/index.html" title="Test">Test</a></h3><div class="product_price"><p class="price_color">$42.50</p><p class="instock availability">In stock</p></div></article>'
        products, _ = parse_listing_page(html)
        assert products[0].price == Decimal("42.50")
        assert products[0].currency == "USD"

    def test_euro_sign(self) -> None:
        html = '<article class="product_pod"><h3><a href="test_1/index.html" title="Test">Test</a></h3><div class="product_price"><p class="price_color">\u20ac15.00</p><p class="instock availability">In stock</p></div></article>'
        products, _ = parse_listing_page(html)
        assert products[0].price == Decimal("15.00")
        assert products[0].currency == "EUR"

    def test_integer_price(self) -> None:
        html = '<article class="product_pod"><h3><a href="test_1/index.html" title="Test">Test</a></h3><div class="product_price"><p class="price_color">&pound;50</p><p class="instock availability">In stock</p></div></article>'
        products, _ = parse_listing_page(html)
        assert products[0].price == Decimal("50")

    def test_thousands_separator_comma(self) -> None:
        """F6: thousands-separated price is parsed correctly."""
        html = '<article class="product_pod"><h3><a href="test_1/index.html" title="Test">Test</a></h3><div class="product_price"><p class="price_color">&pound;1,234.56</p><p class="instock availability">In stock</p></div></article>'
        products, _ = parse_listing_page(html)
        assert products[0].price == Decimal("1234.56")


# ---------------------------------------------------------------------------
# Adapter: canonical event integration
# ---------------------------------------------------------------------------


class TestAdapterIntegration:
    """Tests for the adapter producing canonical ProductObservationEvent."""

    @pytest.fixture
    def mock_client(self) -> WebRetailerClient:
        client = AsyncMock(spec=WebRetailerClient)
        client.base_url = "http://books.toscrape.com"
        client.catalog_path = "/catalogue/category/books_1/index.html"
        return client

    @pytest.mark.asyncio
    async def test_fetch_returns_canonical_events(self, mock_client: WebRetailerClient) -> None:
        html = _load_fixture("listing_page.html")
        mock_client.fetch_listing_page = AsyncMock(return_value=html)  # type: ignore[method-assign]

        adapter = WebRetailerAdapter(client=mock_client)
        result = await adapter.fetch()

        assert result.has_events
        assert len(result.events) == 3
        assert result.source == "web_retailer"
        assert result.total_records == 3

    @pytest.mark.asyncio
    async def test_event_source_matches_adapter(self, mock_client: WebRetailerClient) -> None:
        html = _load_fixture("listing_page.html")
        mock_client.fetch_listing_page = AsyncMock(return_value=html)  # type: ignore[method-assign]

        adapter = WebRetailerAdapter(client=mock_client)
        result = await adapter.fetch()

        for event in result.events:
            assert event.source == "web_retailer"

    @pytest.mark.asyncio
    async def test_external_id_is_stable(self, mock_client: WebRetailerClient) -> None:
        html = _load_fixture("listing_page.html")
        mock_client.fetch_listing_page = AsyncMock(return_value=html)  # type: ignore[method-assign]

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
        mock_client.fetch_listing_page = AsyncMock(return_value="")  # type: ignore[method-assign]

        adapter = WebRetailerAdapter(client=mock_client)
        with pytest.raises(SourceFetchError, match="empty HTML"):
            await adapter.fetch()

    @pytest.mark.asyncio
    async def test_empty_listing_returns_zero_events(self, mock_client: WebRetailerClient) -> None:
        html = _load_fixture("empty_listing.html")
        mock_client.fetch_listing_page = AsyncMock(return_value=html)  # type: ignore[method-assign]

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
        mock_client.fetch_listing_page = AsyncMock(return_value=html)  # type: ignore[method-assign]

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
        mock_client.fetch_listing_page = AsyncMock(return_value=html)  # type: ignore[method-assign]

        adapter = WebRetailerAdapter(client=mock_client)
        result = await adapter.fetch()

        valid_events = [e for e in result.events if e.payload.name == "Valid Book"]
        assert len(valid_events) == 1
        assert result.has_malformed
        assert len(result.malformed) == 2
        assert result.total_records == 3

    @pytest.mark.asyncio
    async def test_event_id_is_deterministic(self, mock_client: WebRetailerClient) -> None:
        html = _load_fixture("listing_page.html")
        mock_client.fetch_listing_page = AsyncMock(return_value=html)  # type: ignore[method-assign]

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
        mock_client.fetch_listing_page = AsyncMock(return_value=html)  # type: ignore[method-assign]

        adapter = WebRetailerAdapter(client=mock_client)
        result = await adapter.fetch()

        avail_map = {e.payload.name: e.payload.availability.value for e in result.events}
        assert avail_map["A Light in the Attic"] == "in_stock"
        assert avail_map["Soumission"] == "out_of_stock"

    @pytest.mark.asyncio
    async def test_urls_resolved_correctly(self, mock_client: WebRetailerClient) -> None:
        """F1: adapter resolves ../../ relative URLs to canonical catalogue paths."""
        html = _load_fixture("listing_page.html")
        mock_client.fetch_listing_page = AsyncMock(return_value=html)  # type: ignore[method-assign]

        adapter = WebRetailerAdapter(client=mock_client)
        result = await adapter.fetch()

        urls = {e.payload.name: e.payload.url for e in result.events}
        assert (
            urls["A Light in the Attic"]
            == "http://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
        )


# ---------------------------------------------------------------------------
# Parser: pagination extraction (TASK-048)
# ---------------------------------------------------------------------------


class TestExtractNextPageUrl:
    """Tests for extract_next_page_url() pagination link extraction."""

    def test_extracts_next_page_relative_link(self) -> None:
        html = """\
        <html><body>
        <ul class="pager">
            <li class="current">Page 1 of 3</li>
            <li class="next"><a href="page-2.html">next</a></li>
        </ul>
        </body></html>
        """
        result = extract_next_page_url(html, PAGE_URL)
        assert result == "http://books.toscrape.com/catalogue/category/books_1/page-2.html"

    def test_returns_none_when_no_pager(self) -> None:
        html = "<html><body><p>No pager here</p></body></html>"
        assert extract_next_page_url(html, PAGE_URL) is None

    def test_returns_none_on_last_page(self) -> None:
        html = """\
        <html><body>
        <ul class="pager">
            <li class="current">Page 3 of 3</li>
        </ul>
        </body></html>
        """
        assert extract_next_page_url(html, PAGE_URL) is None

    def test_resolves_absolute_url(self) -> None:
        html = """\
        <html><body>
        <ul class="pager">
            <li class="next"><a href="http://example.com/page-2.html">next</a></li>
        </ul>
        </body></html>
        """
        result = extract_next_page_url(html, PAGE_URL)
        assert result == "http://example.com/page-2.html"

    def test_returns_none_for_empty_html(self) -> None:
        assert extract_next_page_url("", PAGE_URL) is None
        assert extract_next_page_url("   ", PAGE_URL) is None

    def test_returns_none_when_no_page_url(self) -> None:
        html = """\
        <html><body>
        <ul class="pager">
            <li class="next"><a href="page-2.html">next</a></li>
        </ul>
        </body></html>
        """
        assert extract_next_page_url(html, "") is None

    def test_returns_none_for_empty_href(self) -> None:
        html = """\
        <html><body>
        <ul class="pager">
            <li class="next"><a href="">next</a></li>
        </ul>
        </body></html>
        """
        assert extract_next_page_url(html, PAGE_URL) is None
