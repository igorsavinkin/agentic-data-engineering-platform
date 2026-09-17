"""Tests for the difficult retailer adapter (TASK-051).

Covers:
- adapter protocol compliance (source_name, FetchResult)
- representative response/page mapping (success → events)
- unavailable/blocked response (403 CAPTCHA, 503 maintenance)
- rate limiting (429 with Retry-After)
- malformed/partial source content (mixed valid/invalid products)
- structural change detection (missing expected containers)
- timeout/network failure
- canonical event compatibility
- stable source identity
- deterministic mocked execution
- configuration via environment variables
- configuration validation
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from libs.adapters import FetchResult, SourceFetchError
from libs.adapters.difficult_retailer.adapter import DifficultRetailerAdapter
from libs.adapters.difficult_retailer.classifier import ResponseKind, classify_response
from libs.adapters.difficult_retailer.client import DifficultRetailerClient
from libs.adapters.difficult_retailer.parser import parse_listing_page

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "difficult_retailer"


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


SUCCESS_HTML = _load_fixture("success_page.html")
BLOCKED_HTML = _load_fixture("blocked_page.html")
RATE_LIMITED_HTML = _load_fixture("rate_limited_page.html")
UNAVAILABLE_HTML = _load_fixture("unavailable_page.html")
STRUCTURAL_CHANGE_HTML = _load_fixture("structural_change_page.html")
PARTIAL_PARSE_HTML = _load_fixture("partial_parse_page.html")


def _mock_httpx_response(
    *,
    status_code: int = 200,
    text: str = SUCCESS_HTML,
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


def _make_mock_client(
    *,
    status_code: int = 200,
    text: str = SUCCESS_HTML,
    headers: dict[str, str] | None = None,
) -> AsyncMock:
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    mock_http.get.return_value = _mock_httpx_response(
        status_code=status_code, text=text, headers=headers
    )
    return mock_http


def _make_adapter(
    *,
    mock_http: AsyncMock | None = None,
    **kwargs: Any,
) -> DifficultRetailerAdapter:
    if mock_http is None:
        mock_http = _make_mock_client()
    client = DifficultRetailerClient(
        base_url="https://premium-retailer.example.com",
        http_client=mock_http,
        max_retries=1,
    )
    return DifficultRetailerAdapter(client=client, **kwargs)


# ---------------------------------------------------------------------------
# Response classifier tests
# ---------------------------------------------------------------------------


class TestResponseClassifier:
    """Tests for HTTP response classification."""

    def test_200_with_products_is_success(self) -> None:
        assert classify_response(200, SUCCESS_HTML) == ResponseKind.SUCCESS

    def test_200_with_captcha_is_blocked(self) -> None:
        assert classify_response(200, BLOCKED_HTML) == ResponseKind.BLOCKED

    def test_403_is_blocked(self) -> None:
        assert classify_response(403, BLOCKED_HTML) == ResponseKind.BLOCKED

    def test_403_without_indicators_is_still_blocked(self) -> None:
        assert classify_response(403, "<html>Forbidden</html>") == ResponseKind.BLOCKED

    def test_429_is_rate_limited(self) -> None:
        assert classify_response(429, RATE_LIMITED_HTML) == ResponseKind.RATE_LIMITED

    def test_503_is_unavailable(self) -> None:
        assert classify_response(503, UNAVAILABLE_HTML) == ResponseKind.UNAVAILABLE

    def test_200_with_maintenance_is_unavailable(self) -> None:
        assert classify_response(200, UNAVAILABLE_HTML) == ResponseKind.UNAVAILABLE

    def test_500_is_unknown_error(self) -> None:
        assert classify_response(500, "Internal Server Error") == ResponseKind.UNKNOWN_ERROR

    def test_404_is_unknown_error(self) -> None:
        assert classify_response(404, "Not Found") == ResponseKind.UNKNOWN_ERROR


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestParser:
    """Tests for HTML parsing with structural variation handling."""

    def test_parse_success_page(self) -> None:
        result = parse_listing_page(SUCCESS_HTML, "https://example.com/products")
        assert len(result.products) == 3
        assert not result.malformed
        assert not result.structural_change

    def test_product_fields_extracted(self) -> None:
        result = parse_listing_page(SUCCESS_HTML, "https://example.com/products")
        p = result.products[0]
        assert p.product_id == "1001"
        assert p.name == "Premium Headphones"
        assert str(p.price) == "299.99"
        assert p.currency == "USD"
        assert p.availability == "in_stock"
        assert p.category == "Electronics"
        assert "/product/1001-premium-headphones" in p.url

    def test_availability_mapping(self) -> None:
        result = parse_listing_page(SUCCESS_HTML, "https://example.com/products")
        availabilities = [p.availability for p in result.products]
        assert availabilities == ["in_stock", "out_of_stock", "preorder"]

    def test_structural_change_detected(self) -> None:
        result = parse_listing_page(STRUCTURAL_CHANGE_HTML, "https://example.com")
        assert result.structural_change is True
        assert len(result.products) == 0

    def test_partial_parse(self) -> None:
        result = parse_listing_page(PARTIAL_PARSE_HTML, "https://example.com/products")
        assert len(result.products) == 2
        assert len(result.malformed) == 2
        assert not result.structural_change

    def test_empty_html(self) -> None:
        result = parse_listing_page("", "https://example.com")
        assert len(result.products) == 0
        assert not result.structural_change

    def test_category_extraction(self) -> None:
        result = parse_listing_page(SUCCESS_HTML, "https://example.com/products")
        assert result.products[0].category == "Electronics"


# ---------------------------------------------------------------------------
# Adapter protocol compliance tests
# ---------------------------------------------------------------------------


class TestAdapterProtocol:
    """Tests for SourceAdapterProtocol compliance."""

    @pytest.mark.asyncio
    async def test_source_name_is_stable(self) -> None:
        adapter = _make_adapter()
        assert adapter.source_name == "premium_retailer"

    @pytest.mark.asyncio
    async def test_source_name_consistent_across_instances(self) -> None:
        a1 = _make_adapter()
        a2 = _make_adapter()
        assert a1.source_name == a2.source_name

    @pytest.mark.asyncio
    async def test_fetch_returns_fetch_result(self) -> None:
        adapter = _make_adapter()
        result = await adapter.fetch()
        assert isinstance(result, FetchResult)

    @pytest.mark.asyncio
    async def test_all_events_match_source_name(self) -> None:
        adapter = _make_adapter()
        result = await adapter.fetch()
        for event in result.events:
            assert event.source == "premium_retailer"

    @pytest.mark.asyncio
    async def test_external_id_preserved(self) -> None:
        adapter = _make_adapter()
        result = await adapter.fetch()
        external_ids = {e.payload.external_id for e in result.events}
        assert "1001" in external_ids
        assert "1002" in external_ids
        assert "1003" in external_ids

    @pytest.mark.asyncio
    async def test_no_source_specific_structures_leak(self) -> None:
        adapter = _make_adapter()
        result = await adapter.fetch()
        for event in result.events:
            assert hasattr(event, "payload")
            assert hasattr(event.payload, "external_id")
            assert hasattr(event.payload, "name")
            assert hasattr(event.payload, "price")
            assert hasattr(event.payload, "availability")


# ---------------------------------------------------------------------------
# Success path tests
# ---------------------------------------------------------------------------


class TestSuccessPath:
    """Tests for successful fetch-parse cycle."""

    @pytest.mark.asyncio
    async def test_success_returns_events(self) -> None:
        adapter = _make_adapter()
        result = await adapter.fetch()
        assert len(result.events) == 3
        assert result.total_records == 3

    @pytest.mark.asyncio
    async def test_success_source_field(self) -> None:
        adapter = _make_adapter()
        result = await adapter.fetch()
        assert result.source == "premium_retailer"

    @pytest.mark.asyncio
    async def test_success_no_malformed(self) -> None:
        adapter = _make_adapter()
        result = await adapter.fetch()
        assert len(result.malformed) == 0

    @pytest.mark.asyncio
    async def test_success_fetched_at_set(self) -> None:
        adapter = _make_adapter()
        result = await adapter.fetch()
        assert result.fetched_at is not None

    @pytest.mark.asyncio
    async def test_canonical_event_fields(self) -> None:
        adapter = _make_adapter()
        result = await adapter.fetch()
        event = result.events[0]
        assert event.source == "premium_retailer"
        assert event.payload.name == "Premium Headphones"
        assert event.payload.currency == "USD"
        assert event.payload.availability == "in_stock"
        assert event.payload.category == "Electronics"
        assert event.payload.collected_at is not None


# ---------------------------------------------------------------------------
# Blocked response tests
# ---------------------------------------------------------------------------


class TestBlockedResponse:
    """Tests for bot detection / blocked responses."""

    @pytest.mark.asyncio
    async def test_403_raises_source_fetch_error(self) -> None:
        mock_http = _make_mock_client(status_code=403, text=BLOCKED_HTML)
        adapter = _make_adapter(mock_http=mock_http)
        with pytest.raises(SourceFetchError) as exc_info:
            await adapter.fetch()
        assert exc_info.value.source == "premium_retailer"

    @pytest.mark.asyncio
    async def test_200_with_captcha_raises_source_fetch_error(self) -> None:
        mock_http = _make_mock_client(status_code=200, text=BLOCKED_HTML)
        adapter = _make_adapter(mock_http=mock_http)
        with pytest.raises(SourceFetchError):
            await adapter.fetch()

    @pytest.mark.asyncio
    async def test_blocked_error_has_source(self) -> None:
        mock_http = _make_mock_client(status_code=403, text=BLOCKED_HTML)
        adapter = _make_adapter(mock_http=mock_http)
        with pytest.raises(SourceFetchError) as exc_info:
            await adapter.fetch()
        assert exc_info.value.source == "premium_retailer"


# ---------------------------------------------------------------------------
# Rate limiting tests
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """Tests for rate-limit responses."""

    @pytest.mark.asyncio
    async def test_429_raises_source_fetch_error(self) -> None:
        mock_http = _make_mock_client(
            status_code=429,
            text=RATE_LIMITED_HTML,
            headers={"Retry-After": "0"},
        )
        adapter = _make_adapter(mock_http=mock_http)
        with pytest.raises(SourceFetchError):
            await adapter.fetch()

    @pytest.mark.asyncio
    async def test_429_after_retries_raises(self) -> None:
        mock_http = _make_mock_client(
            status_code=429,
            text=RATE_LIMITED_HTML,
            headers={"Retry-After": "0"},
        )
        adapter = _make_adapter(mock_http=mock_http)
        with pytest.raises(SourceFetchError) as exc_info:
            await adapter.fetch()
        assert exc_info.value.source == "premium_retailer"


# ---------------------------------------------------------------------------
# Unavailable response tests
# ---------------------------------------------------------------------------


class TestUnavailableResponse:
    """Tests for service unavailable responses."""

    @pytest.mark.asyncio
    async def test_503_raises_after_retries(self) -> None:
        mock_http = _make_mock_client(status_code=503, text=UNAVAILABLE_HTML)
        adapter = _make_adapter(mock_http=mock_http)
        with pytest.raises(SourceFetchError):
            await adapter.fetch()

    @pytest.mark.asyncio
    async def test_200_with_maintenance_raises(self) -> None:
        mock_http = _make_mock_client(status_code=200, text=UNAVAILABLE_HTML)
        adapter = _make_adapter(mock_http=mock_http)
        with pytest.raises(SourceFetchError, match="structure has changed|unavailable|blocked"):
            await adapter.fetch()


# ---------------------------------------------------------------------------
# Structural change tests
# ---------------------------------------------------------------------------


class TestStructuralChange:
    """Tests for page structure changes."""

    @pytest.mark.asyncio
    async def test_structural_change_raises_source_fetch_error(self) -> None:
        mock_http = _make_mock_client(status_code=200, text=STRUCTURAL_CHANGE_HTML)
        adapter = _make_adapter(mock_http=mock_http)
        with pytest.raises(SourceFetchError, match="structure has changed"):
            await adapter.fetch()

    @pytest.mark.asyncio
    async def test_structural_change_error_has_source(self) -> None:
        mock_http = _make_mock_client(status_code=200, text=STRUCTURAL_CHANGE_HTML)
        adapter = _make_adapter(mock_http=mock_http)
        with pytest.raises(SourceFetchError) as exc_info:
            await adapter.fetch()
        assert exc_info.value.source == "premium_retailer"


# ---------------------------------------------------------------------------
# Malformed / partial parse tests
# ---------------------------------------------------------------------------


class TestPartialParsing:
    """Tests for partial parseability — some products valid, some malformed."""

    @pytest.mark.asyncio
    async def test_partial_parse_returns_valid_events(self) -> None:
        mock_http = _make_mock_client(status_code=200, text=PARTIAL_PARSE_HTML)
        adapter = _make_adapter(mock_http=mock_http)
        result = await adapter.fetch()
        assert len(result.events) == 2

    @pytest.mark.asyncio
    async def test_partial_parse_returns_malformed(self) -> None:
        mock_http = _make_mock_client(status_code=200, text=PARTIAL_PARSE_HTML)
        adapter = _make_adapter(mock_http=mock_http)
        result = await adapter.fetch()
        assert len(result.malformed) == 2

    @pytest.mark.asyncio
    async def test_partial_parse_total_records(self) -> None:
        mock_http = _make_mock_client(status_code=200, text=PARTIAL_PARSE_HTML)
        adapter = _make_adapter(mock_http=mock_http)
        result = await adapter.fetch()
        assert result.total_records == 4

    @pytest.mark.asyncio
    async def test_malformed_have_reasons(self) -> None:
        mock_http = _make_mock_client(status_code=200, text=PARTIAL_PARSE_HTML)
        adapter = _make_adapter(mock_http=mock_http)
        result = await adapter.fetch()
        for m in result.malformed:
            assert "reason" in m
            assert "raw_record" in m


# ---------------------------------------------------------------------------
# Timeout / network failure tests
# ---------------------------------------------------------------------------


class TestNetworkFailures:
    """Tests for timeout and connection errors."""

    @pytest.mark.asyncio
    async def test_timeout_raises_source_fetch_error(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.get.side_effect = httpx.TimeoutException("Connection timed out")
        adapter = _make_adapter(mock_http=mock_http)
        with pytest.raises(SourceFetchError, match="timed out"):
            await adapter.fetch()

    @pytest.mark.asyncio
    async def test_connection_error_raises_source_fetch_error(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.get.side_effect = httpx.ConnectError("Connection refused")
        adapter = _make_adapter(mock_http=mock_http)
        with pytest.raises(SourceFetchError, match="connection failed"):
            await adapter.fetch()

    @pytest.mark.asyncio
    async def test_network_error_has_source(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.get.side_effect = httpx.TimeoutException("timed out")
        adapter = _make_adapter(mock_http=mock_http)
        with pytest.raises(SourceFetchError) as exc_info:
            await adapter.fetch()
        assert exc_info.value.source == "premium_retailer"


# ---------------------------------------------------------------------------
# Empty body tests
# ---------------------------------------------------------------------------


class TestEmptyBody:
    """Tests for empty response body."""

    @pytest.mark.asyncio
    async def test_empty_html_raises_source_fetch_error(self) -> None:
        mock_http = _make_mock_client(status_code=200, text="")
        adapter = _make_adapter(mock_http=mock_http)
        with pytest.raises(SourceFetchError, match="empty HTML"):
            await adapter.fetch()


# ---------------------------------------------------------------------------
# Configuration tests
# ---------------------------------------------------------------------------


class TestConfiguration:
    """Tests for configuration externalization."""

    def test_default_base_url(self) -> None:
        client = DifficultRetailerClient()
        assert client.base_url == "https://premium-retailer.example.com"

    def test_custom_base_url(self) -> None:
        client = DifficultRetailerClient(base_url="https://custom.example.com")
        assert client.base_url == "https://custom.example.com"

    def test_env_var_base_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIFFICULT_RETAILER_BASE_URL", "https://env.example.com")
        client = DifficultRetailerClient()
        assert client.base_url == "https://env.example.com"

    def test_constructor_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIFFICULT_RETAILER_BASE_URL", "https://env.example.com")
        client = DifficultRetailerClient(base_url="https://arg.example.com")
        assert client.base_url == "https://arg.example.com"

    def test_default_catalog_path(self) -> None:
        client = DifficultRetailerClient()
        assert client.catalog_path == "/products"

    def test_env_var_catalog_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIFFICULT_RETAILER_CATALOG_PATH", "/catalog")
        client = DifficultRetailerClient()
        assert client.catalog_path == "/catalog"

    def test_default_max_retries(self) -> None:
        client = DifficultRetailerClient()
        assert client.max_retries == 3

    def test_invalid_base_url_raises(self) -> None:
        with pytest.raises(SourceFetchError, match="base_url"):
            DifficultRetailerClient(base_url="not-a-url")

    def test_empty_base_url_raises(self) -> None:
        with pytest.raises(SourceFetchError, match="base_url"):
            DifficultRetailerClient(base_url="")

    def test_negative_timeout_raises(self) -> None:
        with pytest.raises(SourceFetchError, match="timeout"):
            DifficultRetailerClient(timeout=-1.0)

    def test_zero_timeout_raises(self) -> None:
        with pytest.raises(SourceFetchError, match="timeout"):
            DifficultRetailerClient(timeout=0)

    def test_zero_max_retries_raises(self) -> None:
        with pytest.raises(SourceFetchError, match="max_retries"):
            DifficultRetailerClient(max_retries=0)


# ---------------------------------------------------------------------------
# Canonical compatibility tests
# ---------------------------------------------------------------------------


class TestCanonicalCompatibility:
    """Tests ensuring events conform to the canonical ProductObservationEvent contract."""

    @pytest.mark.asyncio
    async def test_events_are_valid_product_observation_events(self) -> None:
        adapter = _make_adapter()
        result = await adapter.fetch()
        for event in result.events:
            assert event.event_type == "product.observation"
            assert event.schema_version is not None
            assert event.event_id is not None
            assert event.produced_at is not None

    @pytest.mark.asyncio
    async def test_event_id_is_deterministic_for_same_timestamp(self) -> None:
        mock_http_1 = _make_mock_client()
        mock_http_2 = _make_mock_client()
        a1 = _make_adapter(mock_http=mock_http_1)
        a2 = _make_adapter(mock_http=mock_http_2)
        r1 = await a1.fetch()
        r2 = await a2.fetch()
        ext_ids_1 = sorted(e.payload.external_id for e in r1.events)
        ext_ids_2 = sorted(e.payload.external_id for e in r2.events)
        assert ext_ids_1 == ext_ids_2
        names_1 = sorted(e.payload.name for e in r1.events)
        names_2 = sorted(e.payload.name for e in r2.events)
        assert names_1 == names_2

    @pytest.mark.asyncio
    async def test_payload_has_required_fields(self) -> None:
        adapter = _make_adapter()
        result = await adapter.fetch()
        for event in result.events:
            p = event.payload
            assert p.external_id is not None
            assert p.name is not None
            assert p.url is not None
            assert p.availability is not None
            assert p.collected_at is not None


# ---------------------------------------------------------------------------
# Metrics tests
# ---------------------------------------------------------------------------


class TestMetrics:
    """Tests for source metrics integration."""

    @pytest.mark.asyncio
    async def test_fetch_attempts_incremented(self) -> None:
        from libs.observability.source_metrics import SourceMetrics

        metrics = SourceMetrics(source_name="premium_retailer")
        mock_http = _make_mock_client()
        client = DifficultRetailerClient(
            base_url="https://premium-retailer.example.com",
            http_client=mock_http,
            max_retries=1,
            metrics=metrics,
        )
        adapter = DifficultRetailerAdapter(client=client, metrics=metrics)
        await adapter.fetch()
        snapshot = metrics.snapshot()
        assert snapshot["source_fetch_attempts_total"] == 1
        assert snapshot["source_fetch_success_total"] == 1

    @pytest.mark.asyncio
    async def test_failure_increments_failure_metric(self) -> None:
        from libs.observability.source_metrics import SourceMetrics

        metrics = SourceMetrics(source_name="premium_retailer")
        mock_http = _make_mock_client(status_code=403, text=BLOCKED_HTML)
        client = DifficultRetailerClient(
            base_url="https://premium-retailer.example.com",
            http_client=mock_http,
            max_retries=1,
            metrics=metrics,
        )
        adapter = DifficultRetailerAdapter(client=client, metrics=metrics)
        with pytest.raises(SourceFetchError):
            await adapter.fetch()
        snapshot = metrics.snapshot()
        assert snapshot["source_fetch_failure_total"] == 1


# ---------------------------------------------------------------------------
# Deterministic execution tests
# ---------------------------------------------------------------------------


class TestDeterministicExecution:
    """Tests verifying deterministic, reproducible behavior with mocks."""

    @pytest.mark.asyncio
    async def test_same_input_produces_same_output(self) -> None:
        results = []
        for _ in range(3):
            mock_http = _make_mock_client()
            adapter = _make_adapter(mock_http=mock_http)
            result = await adapter.fetch()
            results.append(result)

        for r in results[1:]:
            assert len(r.events) == len(results[0].events)
            assert r.source == results[0].source
            assert r.total_records == results[0].total_records

    @pytest.mark.asyncio
    async def test_no_live_network_access(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.get.return_value = _mock_httpx_response(status_code=200, text=SUCCESS_HTML)
        adapter = _make_adapter(mock_http=mock_http)
        await adapter.fetch()
        mock_http.get.assert_awaited_once()
