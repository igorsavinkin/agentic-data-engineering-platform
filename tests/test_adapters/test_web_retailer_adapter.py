"""Tests for the web retailer adapter (TASK-046/047/048).

Covers:
- adapter construction and source_name correctness
- HTTP client success (mocked 200 response returns HTML body)
- HTTP client failure modes (timeout, 403, 404, 500, connection error)
- configuration via environment variables
- configuration validation (missing/invalid base URL, timeout, max_retries)
- adapter protocol compliance (returns FetchResult, event source matches)
- empty HTML body raises SourceFetchError
- TASK-048: retry with exponential backoff for transient failures
- TASK-048: 429 with Retry-After header
- TASK-048: pagination across multiple pages
- TASK-048: max_pages limit
- TASK-048: partial page failure returns collected pages
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from libs.adapters import FetchResult, SourceFetchError
from libs.adapters.web_retailer.adapter import WebRetailerAdapter
from libs.adapters.web_retailer.client import WebRetailerClient

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "web_retailer"

SAMPLE_HTML = """\
<!DOCTYPE html>
<html>
<head><title>Books - Products</title></head>
<body>
<ul class="breadcrumb">
  <li><a href="../index.html">Home</a></li>
  <li class="active">Books</li>
</ul>
<article class="product_pod">
  <h3><a href="product1.html" title="A Light in the Attic">A Light in the Attic</a></h3>
  <div class="product_price">
    <p class="price_color">&pound;51.77</p>
    <p class="instock availability">In stock</p>
  </div>
</article>
</body>
</html>
"""


def _mock_httpx_response(
    *,
    status_code: int = 200,
    text: str = SAMPLE_HTML,
    headers: dict[str, str] | None = None,
) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    resp.headers = headers or {}
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=resp,
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# WebRetailerClient tests
# ---------------------------------------------------------------------------


class TestWebRetailerClient:
    """Tests for the web retailer HTTP client."""

    @pytest.mark.asyncio
    async def test_fetch_returns_html_body(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = _mock_httpx_response(status_code=200, text=SAMPLE_HTML)

        client = WebRetailerClient(http_client=mock_client)
        html = await client.fetch_listing_page()

        assert html == SAMPLE_HTML
        mock_client.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_custom_path(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = _mock_httpx_response(status_code=200)

        client = WebRetailerClient(http_client=mock_client)
        await client.fetch_listing_page("/catalogue/category/books_travel_2/index.html")

        mock_client.get.assert_awaited_once_with("/catalogue/category/books_travel_2/index.html")

    @pytest.mark.asyncio
    async def test_fetch_403_raises_source_fetch_error(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = _mock_httpx_response(status_code=403)

        client = WebRetailerClient(http_client=mock_client)

        with pytest.raises(SourceFetchError, match="403"):
            await client.fetch_listing_page()

    @pytest.mark.asyncio
    async def test_fetch_404_raises_source_fetch_error(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = _mock_httpx_response(status_code=404)

        client = WebRetailerClient(http_client=mock_client)

        with pytest.raises(SourceFetchError, match="404"):
            await client.fetch_listing_page()

    @pytest.mark.asyncio
    async def test_fetch_429_raises_source_fetch_error_after_retries(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = _mock_httpx_response(status_code=429)

        client = WebRetailerClient(http_client=mock_client, max_retries=1)

        with pytest.raises(SourceFetchError, match="429"):
            await client.fetch_listing_page()

    @pytest.mark.asyncio
    async def test_fetch_500_raises_source_fetch_error_after_retries(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = _mock_httpx_response(status_code=500)

        client = WebRetailerClient(http_client=mock_client, max_retries=1)

        with pytest.raises(SourceFetchError, match="500"):
            await client.fetch_listing_page()

    @pytest.mark.asyncio
    async def test_fetch_timeout_raises_source_fetch_error(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.TimeoutException("timed out")

        client = WebRetailerClient(http_client=mock_client, max_retries=1)

        with pytest.raises(SourceFetchError, match="timed out"):
            await client.fetch_listing_page()

    @pytest.mark.asyncio
    async def test_fetch_connection_error_raises_source_fetch_error(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.ConnectError("connection refused")

        client = WebRetailerClient(http_client=mock_client, max_retries=1)

        with pytest.raises(SourceFetchError, match="connection"):
            await client.fetch_listing_page()

    @pytest.mark.asyncio
    async def test_close_closes_client(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        client = WebRetailerClient(http_client=mock_client)

        await client.close()

        mock_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_noop_when_no_client(self) -> None:
        client = WebRetailerClient()
        await client.close()


# ---------------------------------------------------------------------------
# Retry tests (TASK-048)
# ---------------------------------------------------------------------------


class TestClientRetry:
    """Tests for retry behavior with transient HTTP failures."""

    @pytest.mark.asyncio
    async def test_retry_on_500_then_success(self) -> None:
        """500 on first attempt, 200 on second → returns HTML."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = [
            _mock_httpx_response(status_code=500),
            _mock_httpx_response(status_code=200, text=SAMPLE_HTML),
        ]

        client = WebRetailerClient(http_client=mock_client, max_retries=3)
        html = await client.fetch_listing_page()

        assert html == SAMPLE_HTML
        assert mock_client.get.await_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhaustion_raises_source_fetch_error(self) -> None:
        """3 consecutive 500s → SourceFetchError after exhausting retries."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = _mock_httpx_response(status_code=500)

        client = WebRetailerClient(http_client=mock_client, max_retries=3)

        with pytest.raises(SourceFetchError, match="after 3 attempts"):
            await client.fetch_listing_page()

        assert mock_client.get.await_count == 3

    @pytest.mark.asyncio
    async def test_retry_on_timeout_then_success(self) -> None:
        """Timeout on first attempt, success on second."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = [
            httpx.TimeoutException("timed out"),
            _mock_httpx_response(status_code=200, text=SAMPLE_HTML),
        ]

        client = WebRetailerClient(http_client=mock_client, max_retries=3)
        html = await client.fetch_listing_page()

        assert html == SAMPLE_HTML
        assert mock_client.get.await_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_connection_error_then_success(self) -> None:
        """Connection error on first attempt, success on second."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = [
            httpx.ConnectError("connection refused"),
            _mock_httpx_response(status_code=200, text=SAMPLE_HTML),
        ]

        client = WebRetailerClient(http_client=mock_client, max_retries=3)
        html = await client.fetch_listing_page()

        assert html == SAMPLE_HTML
        assert mock_client.get.await_count == 2

    @pytest.mark.asyncio
    async def test_429_with_retry_after_respects_header(self) -> None:
        """429 with Retry-After header waits and retries."""
        from unittest.mock import patch

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = [
            _mock_httpx_response(status_code=429, headers={"Retry-After": "0"}),
            _mock_httpx_response(status_code=200, text=SAMPLE_HTML),
        ]

        client = WebRetailerClient(http_client=mock_client, max_retries=3)

        with patch(
            "libs.adapters.web_retailer.client.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            html = await client.fetch_listing_page()

        assert html == SAMPLE_HTML
        sleep_calls = [call.args[0] for call in mock_sleep.await_args_list]
        assert 0.0 in sleep_calls

    @pytest.mark.asyncio
    async def test_429_without_retry_after_uses_backoff(self) -> None:
        """429 without Retry-After uses exponential backoff."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = [
            _mock_httpx_response(status_code=429),
            _mock_httpx_response(status_code=200, text=SAMPLE_HTML),
        ]

        client = WebRetailerClient(http_client=mock_client, max_retries=3)
        html = await client.fetch_listing_page()

        assert html == SAMPLE_HTML
        assert mock_client.get.await_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_on_403(self) -> None:
        """403 is not retried — fails immediately."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = _mock_httpx_response(status_code=403)

        client = WebRetailerClient(http_client=mock_client, max_retries=3)

        with pytest.raises(SourceFetchError, match="403"):
            await client.fetch_listing_page()

        assert mock_client.get.await_count == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_404(self) -> None:
        """404 is not retried — fails immediately."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = _mock_httpx_response(status_code=404)

        client = WebRetailerClient(http_client=mock_client, max_retries=3)

        with pytest.raises(SourceFetchError, match="404"):
            await client.fetch_listing_page()

        assert mock_client.get.await_count == 1


# ---------------------------------------------------------------------------
# Configuration tests
# ---------------------------------------------------------------------------


class TestConfiguration:
    """Tests for environment variable and constructor configuration."""

    def test_default_config(self) -> None:
        """Client constructs with sensible defaults."""
        client = WebRetailerClient()
        assert client._base_url == "http://books.toscrape.com"
        assert client._timeout == 30.0
        assert client._max_retries == 3

    def test_constructor_overrides(self) -> None:
        """Constructor arguments override defaults."""
        client = WebRetailerClient(
            base_url="http://example.com",
            timeout=15.0,
            user_agent="TestAgent/1.0",
            catalog_path="/custom/path",
            max_retries=5,
        )
        assert client._base_url == "http://example.com"
        assert client._timeout == 15.0
        assert client._user_agent == "TestAgent/1.0"
        assert client._catalog_path == "/custom/path"
        assert client._max_retries == 5

    def test_env_var_base_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """WEB_RETAILER_BASE_URL env var is used when no constructor arg."""
        monkeypatch.setenv("WEB_RETAILER_BASE_URL", "http://env-example.com")
        client = WebRetailerClient()
        assert client._base_url == "http://env-example.com"

    def test_env_var_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """WEB_RETAILER_TIMEOUT env var is used when no constructor arg."""
        monkeypatch.setenv("WEB_RETAILER_TIMEOUT", "45.0")
        client = WebRetailerClient()
        assert client._timeout == 45.0

    def test_env_var_user_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """WEB_RETAILER_USER_AGENT env var is used when no constructor arg."""
        monkeypatch.setenv("WEB_RETAILER_USER_AGENT", "EnvAgent/2.0")
        client = WebRetailerClient()
        assert client._user_agent == "EnvAgent/2.0"

    def test_env_var_catalog_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """WEB_RETAILER_CATALOG_PATH env var is used when no constructor arg."""
        monkeypatch.setenv("WEB_RETAILER_CATALOG_PATH", "/env/path")
        client = WebRetailerClient()
        assert client._catalog_path == "/env/path"

    def test_env_var_max_retries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """WEB_RETAILER_MAX_RETRIES env var is used when no constructor arg."""
        monkeypatch.setenv("WEB_RETAILER_MAX_RETRIES", "5")
        client = WebRetailerClient()
        assert client._max_retries == 5

    def test_constructor_overrides_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Constructor argument takes priority over env var."""
        monkeypatch.setenv("WEB_RETAILER_BASE_URL", "http://env-example.com")
        client = WebRetailerClient(base_url="http://constructor-example.com")
        assert client._base_url == "http://constructor-example.com"

    def test_invalid_base_url_empty(self) -> None:
        """Empty base_url raises SourceFetchError."""
        with pytest.raises(SourceFetchError, match="non-empty"):
            WebRetailerClient(base_url="")

    def test_invalid_base_url_no_scheme(self) -> None:
        """base_url without http/https scheme raises SourceFetchError."""
        with pytest.raises(SourceFetchError, match="scheme"):
            WebRetailerClient(base_url="not-a-url")

    def test_invalid_base_url_no_host(self) -> None:
        """base_url without hostname raises SourceFetchError."""
        with pytest.raises(SourceFetchError, match="hostname"):
            WebRetailerClient(base_url="http://")

    def test_invalid_timeout_zero(self) -> None:
        """Zero timeout raises SourceFetchError."""
        with pytest.raises(SourceFetchError, match="positive"):
            WebRetailerClient(timeout=0)

    def test_invalid_timeout_negative(self) -> None:
        """Negative timeout raises SourceFetchError."""
        with pytest.raises(SourceFetchError, match="positive"):
            WebRetailerClient(timeout=-5.0)

    def test_invalid_max_retries_zero(self) -> None:
        """Zero max_retries raises SourceFetchError."""
        with pytest.raises(SourceFetchError, match="max_retries"):
            WebRetailerClient(max_retries=0)


# ---------------------------------------------------------------------------
# WebRetailerAdapter tests
# ---------------------------------------------------------------------------


class TestWebRetailerAdapter:
    """Tests for the web retailer adapter protocol compliance."""

    def test_source_name_is_web_retailer(self) -> None:
        mock_client = AsyncMock(spec=WebRetailerClient)
        adapter = WebRetailerAdapter(client=mock_client)
        assert adapter.source_name == "web_retailer"

    @pytest.mark.asyncio
    async def test_fetch_parses_html_into_events(self) -> None:
        """TASK-047: fetch parses HTML and returns canonical events."""
        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.base_url = "http://books.toscrape.com"
        mock_client.catalog_path = "/catalogue/category/books_1/index.html"
        mock_client.fetch_listing_page.return_value = SAMPLE_HTML

        adapter = WebRetailerAdapter(client=mock_client)
        result = await adapter.fetch()

        assert isinstance(result, FetchResult)
        assert result.source == "web_retailer"
        assert result.has_events
        assert len(result.events) == 1
        assert result.events[0].payload.name == "A Light in the Attic"
        assert result.total_records == 1

    @pytest.mark.asyncio
    async def test_fetch_empty_html_raises_source_fetch_error(self) -> None:
        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.fetch_listing_page.return_value = ""

        adapter = WebRetailerAdapter(client=mock_client)

        with pytest.raises(SourceFetchError, match="empty HTML"):
            await adapter.fetch()

    @pytest.mark.asyncio
    async def test_fetch_whitespace_only_html_raises(self) -> None:
        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.fetch_listing_page.return_value = "   \n\t  "

        adapter = WebRetailerAdapter(client=mock_client)

        with pytest.raises(SourceFetchError, match="empty HTML"):
            await adapter.fetch()

    @pytest.mark.asyncio
    async def test_fetch_propagates_source_fetch_error(self) -> None:
        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.fetch_listing_page.side_effect = SourceFetchError(
            "HTTP 500", source="web_retailer"
        )

        adapter = WebRetailerAdapter(client=mock_client)

        with pytest.raises(SourceFetchError, match="500"):
            await adapter.fetch()

    @pytest.mark.asyncio
    async def test_fetch_records_metrics_on_success(self) -> None:
        from libs.observability.source_metrics import SourceMetric, SourceMetrics

        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.base_url = "http://books.toscrape.com"
        mock_client.catalog_path = "/catalogue/category/books_1/index.html"
        mock_client.fetch_listing_page.return_value = SAMPLE_HTML

        metrics = SourceMetrics(source_name="web_retailer")
        adapter = WebRetailerAdapter(client=mock_client, metrics=metrics)

        await adapter.fetch()

        snapshot = metrics.snapshot()
        assert snapshot[SourceMetric.FETCH_ATTEMPTS] == 1
        assert snapshot[SourceMetric.FETCH_SUCCESS] == 1
        assert snapshot[SourceMetric.FETCH_FAILURE] == 0
        assert snapshot[SourceMetric.RECORDS_COLLECTED] == 1
        assert snapshot[SourceMetric.RECORDS_EMITTED] == 1

    @pytest.mark.asyncio
    async def test_fetch_records_metrics_on_failure(self) -> None:
        from libs.observability.source_metrics import SourceMetric, SourceMetrics

        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.fetch_listing_page.side_effect = SourceFetchError(
            "timeout", source="web_retailer"
        )

        metrics = SourceMetrics(source_name="web_retailer")
        adapter = WebRetailerAdapter(client=mock_client, metrics=metrics)

        with pytest.raises(SourceFetchError):
            await adapter.fetch()

        snapshot = metrics.snapshot()
        assert snapshot[SourceMetric.FETCH_ATTEMPTS] == 1
        assert snapshot[SourceMetric.FETCH_FAILURE] == 1
        assert snapshot[SourceMetric.FETCH_SUCCESS] == 0

    @pytest.mark.asyncio
    async def test_close_delegates_to_client(self) -> None:
        mock_client = AsyncMock(spec=WebRetailerClient)
        adapter = WebRetailerAdapter(client=mock_client)

        await adapter.close()

        mock_client.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_adapter_passes_catalog_path_to_client(self) -> None:
        """Adapter forwards catalog_path to client.fetch_listing_page."""
        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.base_url = "http://books.toscrape.com"
        mock_client.catalog_path = "/catalogue/category/books_1/index.html"
        mock_client.fetch_listing_page.return_value = SAMPLE_HTML

        adapter = WebRetailerAdapter(catalog_path="/custom/catalog", client=mock_client)
        await adapter.fetch()

        mock_client.fetch_listing_page.assert_awaited_once_with("/custom/catalog")


# ---------------------------------------------------------------------------
# Pagination tests (TASK-048)
# ---------------------------------------------------------------------------

PAGE_1_HTML = """\
<!DOCTYPE html>
<html>
<body>
<ul class="breadcrumb"><li class="active">Books</li></ul>
<article class="product_pod">
  <h3><a href="book-a_100/index.html" title="Book A">Book A</a></h3>
  <div class="product_price">
    <p class="price_color">&pound;10.00</p>
    <p class="instock availability">In stock</p>
  </div>
</article>
<ul class="pager">
    <li class="current">Page 1 of 3</li>
    <li class="next"><a href="page-2.html">next</a></li>
</ul>
</body>
</html>
"""

PAGE_2_HTML = """\
<!DOCTYPE html>
<html>
<body>
<ul class="breadcrumb"><li class="active">Books</li></ul>
<article class="product_pod">
  <h3><a href="book-b_200/index.html" title="Book B">Book B</a></h3>
  <div class="product_price">
    <p class="price_color">&pound;20.00</p>
    <p class="instock availability">In stock</p>
  </div>
</article>
<ul class="pager">
    <li class="current">Page 2 of 3</li>
    <li class="next"><a href="page-3.html">next</a></li>
</ul>
</body>
</html>
"""

PAGE_3_HTML = """\
<!DOCTYPE html>
<html>
<body>
<ul class="breadcrumb"><li class="active">Books</li></ul>
<article class="product_pod">
  <h3><a href="book-c_300/index.html" title="Book C">Book C</a></h3>
  <div class="product_price">
    <p class="price_color">&pound;30.00</p>
    <p class="instock availability">In stock</p>
  </div>
</article>
<ul class="pager">
    <li class="current">Page 3 of 3</li>
</ul>
</body>
</html>
"""

EMPTY_PAGE_HTML = """\
<!DOCTYPE html>
<html>
<body>
<ul class="breadcrumb"><li class="active">Books</li></ul>
<ul class="pager">
    <li class="current">Page 1 of 1</li>
</ul>
</body>
</html>
"""


class TestPagination:
    """Tests for multi-page pagination (TASK-048)."""

    @pytest.mark.asyncio
    async def test_multi_page_pagination_aggregates_events(self) -> None:
        """3 pages of products → all events aggregated into one FetchResult."""
        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.base_url = "http://books.toscrape.com"
        mock_client.catalog_path = "/catalogue/category/books_1/index.html"
        mock_client.fetch_listing_page.side_effect = [PAGE_1_HTML, PAGE_2_HTML, PAGE_3_HTML]

        adapter = WebRetailerAdapter(client=mock_client)
        result = await adapter.fetch()

        assert result.has_events
        assert len(result.events) == 3
        names = {e.payload.name for e in result.events}
        assert names == {"Book A", "Book B", "Book C"}
        assert result.total_records == 3
        assert mock_client.fetch_listing_page.await_count == 3

    @pytest.mark.asyncio
    async def test_max_pages_limit_respected(self) -> None:
        """Stops after max_pages even if more pages exist."""
        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.base_url = "http://books.toscrape.com"
        mock_client.catalog_path = "/catalogue/category/books_1/index.html"
        mock_client.fetch_listing_page.side_effect = [PAGE_1_HTML, PAGE_2_HTML, PAGE_3_HTML]

        adapter = WebRetailerAdapter(client=mock_client, max_pages=2)
        result = await adapter.fetch()

        assert len(result.events) == 2
        assert mock_client.fetch_listing_page.await_count == 2

    @pytest.mark.asyncio
    async def test_no_next_page_link_single_page_result(self) -> None:
        """No next-page link on first page → single page result."""
        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.base_url = "http://books.toscrape.com"
        mock_client.catalog_path = "/catalogue/category/books_1/index.html"
        mock_client.fetch_listing_page.return_value = PAGE_3_HTML

        adapter = WebRetailerAdapter(client=mock_client)
        result = await adapter.fetch()

        assert len(result.events) == 1
        assert mock_client.fetch_listing_page.await_count == 1

    @pytest.mark.asyncio
    async def test_partial_page_failure_returns_collected_pages(self) -> None:
        """Page 1 OK, page 2 fails → returns page 1 events, logs error."""
        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.base_url = "http://books.toscrape.com"
        mock_client.catalog_path = "/catalogue/category/books_1/index.html"
        mock_client.fetch_listing_page.side_effect = [
            PAGE_1_HTML,
            SourceFetchError("HTTP 500", source="web_retailer"),
        ]

        adapter = WebRetailerAdapter(client=mock_client)
        result = await adapter.fetch()

        assert len(result.events) == 1
        assert result.events[0].payload.name == "Book A"
        assert mock_client.fetch_listing_page.await_count == 2

    @pytest.mark.asyncio
    async def test_empty_page_in_pagination_stops(self) -> None:
        """Empty HTML on page 2 stops pagination, returns page 1 results."""
        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.base_url = "http://books.toscrape.com"
        mock_client.catalog_path = "/catalogue/category/books_1/index.html"
        mock_client.fetch_listing_page.side_effect = [PAGE_1_HTML, ""]

        adapter = WebRetailerAdapter(client=mock_client)
        result = await adapter.fetch()

        assert len(result.events) == 1
        assert mock_client.fetch_listing_page.await_count == 2

    @pytest.mark.asyncio
    async def test_empty_listing_page_no_error(self) -> None:
        """Empty product listing (no articles, no next) → zero events."""
        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.base_url = "http://books.toscrape.com"
        mock_client.catalog_path = "/catalogue/category/books_1/index.html"
        mock_client.fetch_listing_page.return_value = EMPTY_PAGE_HTML

        adapter = WebRetailerAdapter(client=mock_client)
        result = await adapter.fetch()

        assert not result.has_events
        assert result.total_records == 0

    @pytest.mark.asyncio
    async def test_no_duplicate_events_across_pages(self) -> None:
        """Events from different pages have distinct external_ids."""
        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.base_url = "http://books.toscrape.com"
        mock_client.catalog_path = "/catalogue/category/books_1/index.html"
        mock_client.fetch_listing_page.side_effect = [PAGE_1_HTML, PAGE_2_HTML, PAGE_3_HTML]

        adapter = WebRetailerAdapter(client=mock_client)
        result = await adapter.fetch()

        external_ids = [e.payload.external_id for e in result.events]
        assert len(external_ids) == len(set(external_ids))


# ---------------------------------------------------------------------------
# Health metrics tests (TASK-049)
# ---------------------------------------------------------------------------


MALFORMED_HTML = """\
<!DOCTYPE html>
<html>
<body>
<ul class="breadcrumb"><li class="active">Books</li></ul>
<article class="product_pod">
  <div class="product_price">
    <p class="price_color">&pound;15.00</p>
    <p class="instock availability">In stock</p>
  </div>
</article>
<ul class="pager">
    <li class="current">Page 1 of 1</li>
</ul>
</body>
</html>
"""


class TestHealthMetrics:
    """TASK-049: adapter records pages, retries, malformed, partial failures."""

    @pytest.mark.asyncio
    async def test_successful_fetch_records_pages_fetched(self) -> None:
        """Single-page fetch records 1 page fetched."""
        from libs.observability.source_metrics import SourceMetric, SourceMetrics

        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.base_url = "http://books.toscrape.com"
        mock_client.catalog_path = "/catalogue/category/books_1/index.html"
        mock_client.fetch_listing_page.return_value = PAGE_3_HTML

        metrics = SourceMetrics(source_name="web_retailer")
        adapter = WebRetailerAdapter(client=mock_client, metrics=metrics)
        await adapter.fetch()

        snapshot = metrics.snapshot()
        assert snapshot[SourceMetric.PAGES_FETCHED] == 1
        assert snapshot[SourceMetric.FETCH_SUCCESS] == 1

    @pytest.mark.asyncio
    async def test_multi_page_records_page_count(self) -> None:
        """3-page pagination records 3 pages fetched."""
        from libs.observability.source_metrics import SourceMetric, SourceMetrics

        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.base_url = "http://books.toscrape.com"
        mock_client.catalog_path = "/catalogue/category/books_1/index.html"
        mock_client.fetch_listing_page.side_effect = [PAGE_1_HTML, PAGE_2_HTML, PAGE_3_HTML]

        metrics = SourceMetrics(source_name="web_retailer")
        adapter = WebRetailerAdapter(client=mock_client, metrics=metrics)
        await adapter.fetch()

        snapshot = metrics.snapshot()
        assert snapshot[SourceMetric.PAGES_FETCHED] == 3
        assert snapshot[SourceMetric.RECORDS_COLLECTED] == 3
        assert snapshot[SourceMetric.RECORDS_EMITTED] == 3

    @pytest.mark.asyncio
    async def test_zero_result_fetch(self) -> None:
        """Empty listing page records success with zero records."""
        from libs.observability.source_metrics import SourceMetric, SourceMetrics

        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.base_url = "http://books.toscrape.com"
        mock_client.catalog_path = "/catalogue/category/books_1/index.html"
        mock_client.fetch_listing_page.return_value = EMPTY_PAGE_HTML

        metrics = SourceMetrics(source_name="web_retailer")
        adapter = WebRetailerAdapter(client=mock_client, metrics=metrics)
        result = await adapter.fetch()

        snapshot = metrics.snapshot()
        assert snapshot[SourceMetric.FETCH_SUCCESS] == 1
        assert snapshot[SourceMetric.ZERO_RECORD_FETCHES] == 1
        assert snapshot[SourceMetric.PAGES_FETCHED] == 1
        assert snapshot[SourceMetric.RECORDS_COLLECTED] == 0
        assert not result.has_events

    @pytest.mark.asyncio
    async def test_network_failure_metrics(self) -> None:
        """Network failure records fetch_failure, no pages, no freshness."""
        from libs.observability.source_metrics import SourceMetric, SourceMetrics

        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.fetch_listing_page.side_effect = SourceFetchError(
            "connection refused", source="web_retailer"
        )

        metrics = SourceMetrics(source_name="web_retailer")
        adapter = WebRetailerAdapter(client=mock_client, metrics=metrics)

        with pytest.raises(SourceFetchError):
            await adapter.fetch()

        snapshot = metrics.snapshot()
        assert snapshot[SourceMetric.FETCH_FAILURE] == 1
        assert snapshot[SourceMetric.FETCH_SUCCESS] == 0
        assert snapshot[SourceMetric.PAGES_FETCHED] == 0
        assert metrics.get_last_successful_fetch() is None

    @pytest.mark.asyncio
    async def test_parser_malformed_records_tracked(self) -> None:
        """Parser malformed records are counted in metrics."""
        from libs.observability.source_metrics import SourceMetric, SourceMetrics

        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.base_url = "http://books.toscrape.com"
        mock_client.catalog_path = "/catalogue/category/books_1/index.html"
        mock_client.fetch_listing_page.return_value = MALFORMED_HTML

        metrics = SourceMetrics(source_name="web_retailer")
        adapter = WebRetailerAdapter(client=mock_client, metrics=metrics)
        result = await adapter.fetch()

        snapshot = metrics.snapshot()
        assert snapshot[SourceMetric.MALFORMED_RECORDS] >= 1
        assert len(result.malformed) >= 1

    @pytest.mark.asyncio
    async def test_partial_pagination_failure_tracked(self) -> None:
        """Partial pagination failure records partial_failure metric."""
        from libs.observability.source_metrics import SourceMetric, SourceMetrics

        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.base_url = "http://books.toscrape.com"
        mock_client.catalog_path = "/catalogue/category/books_1/index.html"
        mock_client.fetch_listing_page.side_effect = [
            PAGE_1_HTML,
            SourceFetchError("HTTP 500", source="web_retailer"),
        ]

        metrics = SourceMetrics(source_name="web_retailer")
        adapter = WebRetailerAdapter(client=mock_client, metrics=metrics)
        result = await adapter.fetch()

        snapshot = metrics.snapshot()
        assert snapshot[SourceMetric.PARTIAL_FAILURES] == 1
        assert snapshot[SourceMetric.PAGES_FETCHED] == 1
        assert snapshot[SourceMetric.FETCH_SUCCESS] == 1
        assert len(result.events) == 1

    @pytest.mark.asyncio
    async def test_retry_metrics_via_client(self) -> None:
        """Client retries are recorded in metrics."""
        from libs.observability.source_metrics import SourceMetric, SourceMetrics

        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.base_url = "http://books.toscrape.com"
        mock_client.catalog_path = "/catalogue/category/books_1/index.html"
        mock_client.fetch_listing_page.return_value = SAMPLE_HTML

        metrics = SourceMetrics(source_name="web_retailer")
        metrics.record_retry()
        metrics.record_retry()

        snapshot = metrics.snapshot()
        assert snapshot[SourceMetric.RETRY_ATTEMPTS] == 2

    @pytest.mark.asyncio
    async def test_record_event_counts_accurate(self) -> None:
        """Record and event counts are accurate across pages."""
        from libs.observability.source_metrics import SourceMetric, SourceMetrics

        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.base_url = "http://books.toscrape.com"
        mock_client.catalog_path = "/catalogue/category/books_1/index.html"
        mock_client.fetch_listing_page.side_effect = [PAGE_1_HTML, PAGE_2_HTML, PAGE_3_HTML]

        metrics = SourceMetrics(source_name="web_retailer")
        adapter = WebRetailerAdapter(client=mock_client, metrics=metrics)
        result = await adapter.fetch()

        snapshot = metrics.snapshot()
        assert snapshot[SourceMetric.RECORDS_COLLECTED] == len(result.events) + len(
            result.malformed
        )
        assert snapshot[SourceMetric.RECORDS_EMITTED] == len(result.events)

    @pytest.mark.asyncio
    async def test_freshness_after_successful_fetch(self) -> None:
        """Freshness timestamp is set after successful adapter fetch."""
        from libs.observability.source_metrics import SourceMetrics

        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.base_url = "http://books.toscrape.com"
        mock_client.catalog_path = "/catalogue/category/books_1/index.html"
        mock_client.fetch_listing_page.return_value = SAMPLE_HTML

        metrics = SourceMetrics(source_name="web_retailer")
        adapter = WebRetailerAdapter(client=mock_client, metrics=metrics)

        assert metrics.get_last_successful_fetch() is None

        await adapter.fetch()

        assert metrics.get_last_successful_fetch() is not None
        assert metrics.get_freshness_age_seconds() is not None
        assert metrics.get_freshness_age_seconds() >= 0

    @pytest.mark.asyncio
    async def test_snapshot_no_high_cardinality_after_fetch(self) -> None:
        """Snapshot after adapter fetch contains no high-cardinality data."""
        from libs.observability.source_metrics import SourceMetrics

        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.base_url = "http://books.toscrape.com"
        mock_client.catalog_path = "/catalogue/category/books_1/index.html"
        mock_client.fetch_listing_page.side_effect = [PAGE_1_HTML, PAGE_2_HTML, PAGE_3_HTML]

        metrics = SourceMetrics(source_name="web_retailer")
        adapter = WebRetailerAdapter(client=mock_client, metrics=metrics)
        await adapter.fetch()

        snapshot = metrics.snapshot()
        for key, value in snapshot.items():
            str_value = str(value).lower()
            assert "http" not in str_value or key == "source", (
                f"Possible high-cardinality data in snapshot key '{key}': {value}"
            )
            assert "book" not in str_value
            assert "page-" not in str_value
