"""Tests for the Wayfair adapter (TASK-046).

Covers:
- adapter construction and source_name correctness
- HTTP client success (mocked 200 response returns HTML body)
- HTTP client failure modes (timeout, 403, 404, 500, connection error)
- configuration validation (timeout)
- adapter protocol compliance (returns FetchResult, event source matches)
- empty HTML body raises SourceFetchError
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from libs.adapters import FetchResult, SourceFetchError
from libs.adapters.wayfair.adapter import WayfairAdapter
from libs.adapters.wayfair.client import WayfairClient

SAMPLE_HTML = """\
<!DOCTYPE html>
<html>
<head><title>Wayfair - Electronics</title></head>
<body>
<div class="product-card">
  <span class="product-id">WF-12345</span>
  <h2 class="product-name">LED Smart TV 55"</h2>
  <span class="price">$499.99</span>
  <span class="availability">In Stock</span>
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# WayfairClient tests
# ---------------------------------------------------------------------------


def _mock_httpx_response(
    *,
    status_code: int = 200,
    text: str = SAMPLE_HTML,
) -> MagicMock:
    """Build a mock httpx.Response."""
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


class TestWayfairClient:
    """Tests for the Wayfair HTTP client."""

    @pytest.mark.asyncio
    async def test_fetch_returns_html_body(self) -> None:
        """Mocked 200 response returns HTML body."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = _mock_httpx_response(status_code=200, text=SAMPLE_HTML)

        client = WayfairClient(http_client=mock_client)
        html = await client.fetch_listing_page()

        assert html == SAMPLE_HTML
        mock_client.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_custom_path(self) -> None:
        """Client fetches a custom path when provided."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = _mock_httpx_response(status_code=200)

        client = WayfairClient(http_client=mock_client)
        await client.fetch_listing_page("/custom/path?q=lamps")

        mock_client.get.assert_awaited_once_with("/custom/path?q=lamps")

    @pytest.mark.asyncio
    async def test_fetch_403_raises_source_fetch_error(self) -> None:
        """HTTP 403 raises SourceFetchError with source='wayfair'."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = _mock_httpx_response(status_code=403)

        client = WayfairClient(http_client=mock_client)

        with pytest.raises(SourceFetchError, match="403"):
            await client.fetch_listing_page()

    @pytest.mark.asyncio
    async def test_fetch_404_raises_source_fetch_error(self) -> None:
        """HTTP 404 raises SourceFetchError."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = _mock_httpx_response(status_code=404)

        client = WayfairClient(http_client=mock_client)

        with pytest.raises(SourceFetchError, match="404"):
            await client.fetch_listing_page()

    @pytest.mark.asyncio
    async def test_fetch_429_raises_source_fetch_error(self) -> None:
        """HTTP 429 rate limit raises SourceFetchError."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = _mock_httpx_response(status_code=429)

        client = WayfairClient(http_client=mock_client)

        with pytest.raises(SourceFetchError, match="429"):
            await client.fetch_listing_page()

    @pytest.mark.asyncio
    async def test_fetch_500_raises_source_fetch_error(self) -> None:
        """HTTP 500 raises SourceFetchError."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = _mock_httpx_response(status_code=500)

        client = WayfairClient(http_client=mock_client)

        with pytest.raises(SourceFetchError, match="500"):
            await client.fetch_listing_page()

    @pytest.mark.asyncio
    async def test_fetch_timeout_raises_source_fetch_error(self) -> None:
        """Timeout raises SourceFetchError."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.TimeoutException("timed out")

        client = WayfairClient(http_client=mock_client)

        with pytest.raises(SourceFetchError, match="timed out"):
            await client.fetch_listing_page()

    @pytest.mark.asyncio
    async def test_fetch_connection_error_raises_source_fetch_error(self) -> None:
        """Connection error raises SourceFetchError."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.ConnectError("connection refused")

        client = WayfairClient(http_client=mock_client)

        with pytest.raises(SourceFetchError, match="connection"):
            await client.fetch_listing_page()

    @pytest.mark.asyncio
    async def test_close_closes_client(self) -> None:
        """close() closes the underlying HTTP client."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        client = WayfairClient(http_client=mock_client)

        await client.close()

        mock_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_noop_when_no_client(self) -> None:
        """close() is safe when no client was created."""
        client = WayfairClient()
        await client.close()


# ---------------------------------------------------------------------------
# WayfairAdapter tests
# ---------------------------------------------------------------------------


class TestWayfairAdapter:
    """Tests for the Wayfair adapter protocol compliance."""

    def test_source_name_is_wayfair(self) -> None:
        """Adapter source_name is 'wayfair'."""
        mock_client = AsyncMock(spec=WayfairClient)
        adapter = WayfairAdapter(client=mock_client)
        assert adapter.source_name == "wayfair"

    @pytest.mark.asyncio
    async def test_fetch_returns_empty_fetch_result(self) -> None:
        """TASK-046: fetch returns empty FetchResult after successful HTML fetch."""
        mock_client = AsyncMock(spec=WayfairClient)
        mock_client.fetch_listing_page.return_value = SAMPLE_HTML

        adapter = WayfairAdapter(client=mock_client)
        result = await adapter.fetch()

        assert isinstance(result, FetchResult)
        assert result.source == "wayfair"
        assert result.events == ()
        assert result.malformed == ()
        assert result.total_records == 0
        assert result.has_events is False
        assert result.has_malformed is False

    @pytest.mark.asyncio
    async def test_fetch_empty_html_raises_source_fetch_error(self) -> None:
        """Empty HTML body raises SourceFetchError."""
        mock_client = AsyncMock(spec=WayfairClient)
        mock_client.fetch_listing_page.return_value = ""

        adapter = WayfairAdapter(client=mock_client)

        with pytest.raises(SourceFetchError, match="empty HTML"):
            await adapter.fetch()

    @pytest.mark.asyncio
    async def test_fetch_whitespace_only_html_raises(self) -> None:
        """Whitespace-only HTML body raises SourceFetchError."""
        mock_client = AsyncMock(spec=WayfairClient)
        mock_client.fetch_listing_page.return_value = "   \n\t  "

        adapter = WayfairAdapter(client=mock_client)

        with pytest.raises(SourceFetchError, match="empty HTML"):
            await adapter.fetch()

    @pytest.mark.asyncio
    async def test_fetch_propagates_source_fetch_error(self) -> None:
        """Client SourceFetchError propagates through adapter."""
        mock_client = AsyncMock(spec=WayfairClient)
        mock_client.fetch_listing_page.side_effect = SourceFetchError(
            "Wayfair returned HTTP 500", source="wayfair"
        )

        adapter = WayfairAdapter(client=mock_client)

        with pytest.raises(SourceFetchError, match="500"):
            await adapter.fetch()

    @pytest.mark.asyncio
    async def test_fetch_records_metrics_on_success(self) -> None:
        """Successful fetch records metrics."""
        from libs.observability.source_metrics import SourceMetric, SourceMetrics

        mock_client = AsyncMock(spec=WayfairClient)
        mock_client.fetch_listing_page.return_value = SAMPLE_HTML

        metrics = SourceMetrics(source_name="wayfair")
        adapter = WayfairAdapter(client=mock_client, metrics=metrics)

        await adapter.fetch()

        snapshot = metrics.snapshot()
        assert snapshot[SourceMetric.FETCH_ATTEMPTS] == 1
        assert snapshot[SourceMetric.FETCH_SUCCESS] == 1
        assert snapshot[SourceMetric.FETCH_FAILURE] == 0

    @pytest.mark.asyncio
    async def test_fetch_records_metrics_on_failure(self) -> None:
        """Failed fetch records failure metrics."""
        from libs.observability.source_metrics import SourceMetric, SourceMetrics

        mock_client = AsyncMock(spec=WayfairClient)
        mock_client.fetch_listing_page.side_effect = SourceFetchError("timeout", source="wayfair")

        metrics = SourceMetrics(source_name="wayfair")
        adapter = WayfairAdapter(client=mock_client, metrics=metrics)

        with pytest.raises(SourceFetchError):
            await adapter.fetch()

        snapshot = metrics.snapshot()
        assert snapshot[SourceMetric.FETCH_ATTEMPTS] == 1
        assert snapshot[SourceMetric.FETCH_FAILURE] == 1
        assert snapshot[SourceMetric.FETCH_SUCCESS] == 0

    @pytest.mark.asyncio
    async def test_close_delegates_to_client(self) -> None:
        """Adapter close() delegates to client close()."""
        mock_client = AsyncMock(spec=WayfairClient)
        adapter = WayfairAdapter(client=mock_client)

        await adapter.close()

        mock_client.close.assert_awaited_once()

    def test_adapter_creates_client_with_config(self) -> None:
        """Adapter constructs client with provided configuration."""
        adapter = WayfairAdapter(
            search_path="/search/products?keyword=lamps",
            timeout=15.0,
            user_agent="TestAgent/1.0",
        )
        assert adapter.source_name == "wayfair"
        assert adapter._search_path == "/search/products?keyword=lamps"
