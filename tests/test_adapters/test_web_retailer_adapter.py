"""Tests for the web retailer adapter (TASK-046).

Covers:
- adapter construction and source_name correctness
- HTTP client success (mocked 200 response returns HTML body)
- HTTP client failure modes (timeout, 403, 404, 500, connection error)
- configuration via environment variables
- configuration validation (missing/invalid base URL, timeout)
- adapter protocol compliance (returns FetchResult, event source matches)
- empty HTML body raises SourceFetchError
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from libs.adapters import FetchResult, SourceFetchError
from libs.adapters.web_retailer.adapter import WebRetailerAdapter
from libs.adapters.web_retailer.client import WebRetailerClient

SAMPLE_HTML = """\
<!DOCTYPE html>
<html>
<head><title>Books - Products</title></head>
<body>
<article class="product_pod">
  <h3><a href="product1.html">A Light in the Attic</a></h3>
  <p class="price_color">£51.77</p>
  <p class="instock availability">In stock (25 available)</p>
</article>
</body>
</html>
"""


def _mock_httpx_response(
    *,
    status_code: int = 200,
    text: str = SAMPLE_HTML,
) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
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
    async def test_fetch_429_raises_source_fetch_error(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = _mock_httpx_response(status_code=429)

        client = WebRetailerClient(http_client=mock_client)

        with pytest.raises(SourceFetchError, match="429"):
            await client.fetch_listing_page()

    @pytest.mark.asyncio
    async def test_fetch_500_raises_source_fetch_error(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = _mock_httpx_response(status_code=500)

        client = WebRetailerClient(http_client=mock_client)

        with pytest.raises(SourceFetchError, match="500"):
            await client.fetch_listing_page()

    @pytest.mark.asyncio
    async def test_fetch_timeout_raises_source_fetch_error(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.TimeoutException("timed out")

        client = WebRetailerClient(http_client=mock_client)

        with pytest.raises(SourceFetchError, match="timed out"):
            await client.fetch_listing_page()

    @pytest.mark.asyncio
    async def test_fetch_connection_error_raises_source_fetch_error(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.ConnectError("connection refused")

        client = WebRetailerClient(http_client=mock_client)

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
# Configuration tests
# ---------------------------------------------------------------------------


class TestConfiguration:
    """Tests for environment variable and constructor configuration."""

    def test_default_config(self) -> None:
        """Client constructs with sensible defaults."""
        client = WebRetailerClient()
        assert client._base_url == "http://books.toscrape.com"
        assert client._timeout == 30.0

    def test_constructor_overrides(self) -> None:
        """Constructor arguments override defaults."""
        client = WebRetailerClient(
            base_url="http://example.com",
            timeout=15.0,
            user_agent="TestAgent/1.0",
            catalog_path="/custom/path",
        )
        assert client._base_url == "http://example.com"
        assert client._timeout == 15.0
        assert client._user_agent == "TestAgent/1.0"
        assert client._catalog_path == "/custom/path"

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
    async def test_fetch_returns_empty_fetch_result(self) -> None:
        """TASK-046: fetch returns empty FetchResult after successful HTML fetch."""
        mock_client = AsyncMock(spec=WebRetailerClient)
        mock_client.fetch_listing_page.return_value = SAMPLE_HTML

        adapter = WebRetailerAdapter(client=mock_client)
        result = await adapter.fetch()

        assert isinstance(result, FetchResult)
        assert result.source == "web_retailer"
        assert result.events == ()
        assert result.malformed == ()
        assert result.total_records == 0
        assert result.has_events is False
        assert result.has_malformed is False

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
        mock_client.fetch_listing_page.return_value = SAMPLE_HTML

        metrics = SourceMetrics(source_name="web_retailer")
        adapter = WebRetailerAdapter(client=mock_client, metrics=metrics)

        await adapter.fetch()

        snapshot = metrics.snapshot()
        assert snapshot[SourceMetric.FETCH_ATTEMPTS] == 1
        assert snapshot[SourceMetric.FETCH_SUCCESS] == 1
        assert snapshot[SourceMetric.FETCH_FAILURE] == 0

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
        mock_client.fetch_listing_page.return_value = SAMPLE_HTML

        adapter = WebRetailerAdapter(catalog_path="/custom/catalog", client=mock_client)
        await adapter.fetch()

        mock_client.fetch_listing_page.assert_awaited_once_with("/custom/catalog")
