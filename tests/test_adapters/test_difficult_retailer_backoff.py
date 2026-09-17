"""Tests for rate-limit / backoff strategy (TASK-052).

Covers:
- 429 + Retry-After (respected and capped)
- 429 without Retry-After
- transient 5xx (500/502/503/504) then recovery
- non-transient 5xx (501/505) not retried
- timeout/connection retry then recovery
- exhausted retry budget
- non-retryable failure (no retry for 403/blocked)
- bounded maximum wait/attempts
- partial success preservation
- replay/idempotency
- retry metrics/logging (exact counts)
- backoff parameter validation
- env var configuration for backoff params
- injectable sleep for deterministic tests
- negative/zero Retry-After sanitization
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from libs.adapters import SourceFetchError
from libs.adapters.difficult_retailer.adapter import DifficultRetailerAdapter
from libs.adapters.difficult_retailer.client import (
    DEFAULT_BACKOFF_MAX,
    DEFAULT_MAX_RETRY_AFTER,
    DifficultRetailerClient,
)
from libs.observability.source_metrics import SourceMetrics

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "difficult_retailer"


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


SUCCESS_HTML = _load_fixture("success_page.html")
RATE_LIMITED_HTML = _load_fixture("rate_limited_page.html")
UNAVAILABLE_HTML = _load_fixture("unavailable_page.html")
BLOCKED_HTML = _load_fixture("blocked_page.html")


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
    responses: list[MagicMock] | None = None,
    status_code: int = 200,
    text: str = SUCCESS_HTML,
    headers: dict[str, str] | None = None,
) -> AsyncMock:
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    if responses is not None:
        mock_http.get.side_effect = responses
    else:
        mock_http.get.return_value = _mock_httpx_response(
            status_code=status_code, text=text, headers=headers
        )
    return mock_http


def _make_client(
    *,
    mock_http: AsyncMock | None = None,
    max_retries: int = 3,
    sleep_fn: Any = None,
    metrics: SourceMetrics | None = None,
    **kwargs: Any,
) -> DifficultRetailerClient:
    if mock_http is None:
        mock_http = _make_mock_client()
    return DifficultRetailerClient(
        base_url="https://premium-retailer.example.com",
        http_client=mock_http,
        max_retries=max_retries,
        backoff_min=0.001,
        backoff_max=0.01,
        metrics=metrics,
        sleep_fn=sleep_fn,
        **kwargs,
    )


def _make_adapter(
    *,
    mock_http: AsyncMock | None = None,
    max_retries: int = 3,
    sleep_fn: Any = None,
    metrics: SourceMetrics | None = None,
    **kwargs: Any,
) -> DifficultRetailerAdapter:
    client = _make_client(
        mock_http=mock_http,
        max_retries=max_retries,
        sleep_fn=sleep_fn,
        metrics=metrics,
    )
    return DifficultRetailerAdapter(client=client, metrics=metrics, **kwargs)


# ---------------------------------------------------------------------------
# 429 + Retry-After tests
# ---------------------------------------------------------------------------


class TestRetryAfterHandling:
    """Tests for 429 responses with Retry-After header."""

    @pytest.mark.asyncio
    async def test_429_with_retry_after_waits(self) -> None:
        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        rate_limited_resp = _mock_httpx_response(
            status_code=429,
            text=RATE_LIMITED_HTML,
            headers={"Retry-After": "5"},
        )
        success_resp = _mock_httpx_response(status_code=200, text=SUCCESS_HTML)
        mock_http = _make_mock_client(responses=[rate_limited_resp, success_resp])

        adapter = _make_adapter(mock_http=mock_http, sleep_fn=mock_sleep)
        result = await adapter.fetch()

        assert len(result.events) == 3
        assert len(sleep_calls) == 1
        assert sleep_calls[0] == 5.0

    @pytest.mark.asyncio
    async def test_429_retry_after_capped_at_max(self) -> None:
        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        rate_limited_resp = _mock_httpx_response(
            status_code=429,
            text=RATE_LIMITED_HTML,
            headers={"Retry-After": "300"},
        )
        success_resp = _mock_httpx_response(status_code=200, text=SUCCESS_HTML)
        mock_http = _make_mock_client(responses=[rate_limited_resp, success_resp])

        client = DifficultRetailerClient(
            base_url="https://premium-retailer.example.com",
            http_client=mock_http,
            max_retries=3,
            backoff_min=0.001,
            backoff_max=0.01,
            max_retry_after=30.0,
            sleep_fn=mock_sleep,
        )
        adapter = DifficultRetailerAdapter(client=client)
        result = await adapter.fetch()

        assert len(result.events) == 3
        assert len(sleep_calls) == 1
        assert sleep_calls[0] == 30.0

    @pytest.mark.asyncio
    async def test_429_without_retry_after_no_sleep(self) -> None:
        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        rate_limited_resp = _mock_httpx_response(
            status_code=429,
            text=RATE_LIMITED_HTML,
            headers={},
        )
        success_resp = _mock_httpx_response(status_code=200, text=SUCCESS_HTML)
        mock_http = _make_mock_client(responses=[rate_limited_resp, success_resp])

        adapter = _make_adapter(mock_http=mock_http, sleep_fn=mock_sleep)
        result = await adapter.fetch()

        assert len(result.events) == 3
        assert len(sleep_calls) == 0

    @pytest.mark.asyncio
    async def test_429_invalid_retry_after_ignored(self) -> None:
        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        rate_limited_resp = _mock_httpx_response(
            status_code=429,
            text=RATE_LIMITED_HTML,
            headers={"Retry-After": "not-a-number"},
        )
        success_resp = _mock_httpx_response(status_code=200, text=SUCCESS_HTML)
        mock_http = _make_mock_client(responses=[rate_limited_resp, success_resp])

        adapter = _make_adapter(mock_http=mock_http, sleep_fn=mock_sleep)
        result = await adapter.fetch()

        assert len(result.events) == 3
        assert len(sleep_calls) == 0


# ---------------------------------------------------------------------------
# Transient 5xx then recovery tests
# ---------------------------------------------------------------------------


class TestTransientRecovery:
    """Tests for transient failures followed by recovery."""

    @pytest.mark.asyncio
    async def test_503_then_success(self) -> None:
        unavailable_resp = _mock_httpx_response(status_code=503, text=UNAVAILABLE_HTML)
        success_resp = _mock_httpx_response(status_code=200, text=SUCCESS_HTML)
        mock_http = _make_mock_client(responses=[unavailable_resp, success_resp])

        adapter = _make_adapter(mock_http=mock_http)
        result = await adapter.fetch()

        assert len(result.events) == 3
        assert mock_http.get.call_count == 2

    @pytest.mark.asyncio
    async def test_500_then_success(self) -> None:
        error_resp = _mock_httpx_response(status_code=500, text="Internal Server Error")
        success_resp = _mock_httpx_response(status_code=200, text=SUCCESS_HTML)
        mock_http = _make_mock_client(responses=[error_resp, success_resp])

        adapter = _make_adapter(mock_http=mock_http)
        result = await adapter.fetch()

        assert len(result.events) == 3
        assert mock_http.get.call_count == 2

    @pytest.mark.asyncio
    async def test_timeout_then_success(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.get.side_effect = [
            httpx.TimeoutException("timed out"),
            _mock_httpx_response(status_code=200, text=SUCCESS_HTML),
        ]

        adapter = _make_adapter(mock_http=mock_http)
        result = await adapter.fetch()

        assert len(result.events) == 3
        assert mock_http.get.call_count == 2

    @pytest.mark.asyncio
    async def test_connection_error_then_success(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.get.side_effect = [
            httpx.ConnectError("connection refused"),
            _mock_httpx_response(status_code=200, text=SUCCESS_HTML),
        ]

        adapter = _make_adapter(mock_http=mock_http)
        result = await adapter.fetch()

        assert len(result.events) == 3
        assert mock_http.get.call_count == 2

    @pytest.mark.asyncio
    async def test_multiple_transient_then_success(self) -> None:
        unavailable_resp = _mock_httpx_response(status_code=503, text=UNAVAILABLE_HTML)
        success_resp = _mock_httpx_response(status_code=200, text=SUCCESS_HTML)
        mock_http = _make_mock_client(responses=[unavailable_resp, unavailable_resp, success_resp])

        adapter = _make_adapter(mock_http=mock_http, max_retries=3)
        result = await adapter.fetch()

        assert len(result.events) == 3
        assert mock_http.get.call_count == 3


# ---------------------------------------------------------------------------
# Exhausted retry budget tests
# ---------------------------------------------------------------------------


class TestExhaustedRetryBudget:
    """Tests for retry budget exhaustion."""

    @pytest.mark.asyncio
    async def test_all_503_exhausts_budget(self) -> None:
        unavailable_resp = _mock_httpx_response(status_code=503, text=UNAVAILABLE_HTML)
        mock_http = _make_mock_client(
            responses=[unavailable_resp, unavailable_resp, unavailable_resp]
        )

        adapter = _make_adapter(mock_http=mock_http, max_retries=3)
        with pytest.raises(SourceFetchError) as exc_info:
            await adapter.fetch()
        assert exc_info.value.source == "premium_retailer"
        assert mock_http.get.call_count == 3

    @pytest.mark.asyncio
    async def test_all_timeouts_exhausts_budget(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.get.side_effect = httpx.TimeoutException("timed out")

        adapter = _make_adapter(mock_http=mock_http, max_retries=3)
        with pytest.raises(SourceFetchError, match="timed out"):
            await adapter.fetch()
        assert mock_http.get.call_count == 3

    @pytest.mark.asyncio
    async def test_all_connection_errors_exhausts_budget(self) -> None:
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.get.side_effect = httpx.ConnectError("refused")

        adapter = _make_adapter(mock_http=mock_http, max_retries=2)
        with pytest.raises(SourceFetchError, match="connection failed"):
            await adapter.fetch()
        assert mock_http.get.call_count == 2

    @pytest.mark.asyncio
    async def test_all_429_exhausts_budget(self) -> None:
        rate_limited_resp = _mock_httpx_response(
            status_code=429,
            text=RATE_LIMITED_HTML,
            headers={"Retry-After": "0"},
        )
        mock_http = _make_mock_client(
            responses=[rate_limited_resp, rate_limited_resp, rate_limited_resp]
        )

        adapter = _make_adapter(mock_http=mock_http, max_retries=3)
        with pytest.raises(SourceFetchError):
            await adapter.fetch()
        assert mock_http.get.call_count == 3


# ---------------------------------------------------------------------------
# Non-retryable failure tests
# ---------------------------------------------------------------------------


class TestNonRetryableFailures:
    """Tests verifying non-retryable errors are not retried."""

    @pytest.mark.asyncio
    async def test_403_blocked_not_retried(self) -> None:
        blocked_resp = _mock_httpx_response(status_code=403, text=BLOCKED_HTML)
        mock_http = _make_mock_client(responses=[blocked_resp])

        adapter = _make_adapter(mock_http=mock_http, max_retries=5)
        with pytest.raises(SourceFetchError):
            await adapter.fetch()
        assert mock_http.get.call_count == 1

    @pytest.mark.asyncio
    async def test_200_captcha_not_retried(self) -> None:
        captcha_resp = _mock_httpx_response(status_code=200, text=BLOCKED_HTML)
        mock_http = _make_mock_client(responses=[captcha_resp])

        adapter = _make_adapter(mock_http=mock_http, max_retries=5)
        with pytest.raises(SourceFetchError):
            await adapter.fetch()
        assert mock_http.get.call_count == 1

    @pytest.mark.asyncio
    async def test_200_maintenance_not_retried(self) -> None:
        maintenance_resp = _mock_httpx_response(status_code=200, text=UNAVAILABLE_HTML)
        mock_http = _make_mock_client(responses=[maintenance_resp])

        adapter = _make_adapter(mock_http=mock_http, max_retries=5)
        with pytest.raises(SourceFetchError):
            await adapter.fetch()
        assert mock_http.get.call_count == 1

    @pytest.mark.asyncio
    async def test_404_not_retried(self) -> None:
        not_found_resp = _mock_httpx_response(status_code=404, text="Not Found")
        mock_http = _make_mock_client(responses=[not_found_resp])

        adapter = _make_adapter(mock_http=mock_http, max_retries=5)
        with pytest.raises(SourceFetchError):
            await adapter.fetch()
        assert mock_http.get.call_count == 1

    @pytest.mark.asyncio
    async def test_501_not_implemented_not_retried(self) -> None:
        not_impl_resp = _mock_httpx_response(status_code=501, text="Not Implemented")
        mock_http = _make_mock_client(responses=[not_impl_resp])

        adapter = _make_adapter(mock_http=mock_http, max_retries=5)
        with pytest.raises(SourceFetchError):
            await adapter.fetch()
        assert mock_http.get.call_count == 1

    @pytest.mark.asyncio
    async def test_505_http_version_not_retried(self) -> None:
        version_resp = _mock_httpx_response(status_code=505, text="HTTP Version Not Supported")
        mock_http = _make_mock_client(responses=[version_resp])

        adapter = _make_adapter(mock_http=mock_http, max_retries=5)
        with pytest.raises(SourceFetchError):
            await adapter.fetch()
        assert mock_http.get.call_count == 1


# ---------------------------------------------------------------------------
# Bounded maximum wait/attempts tests
# ---------------------------------------------------------------------------


class TestBoundedBackoff:
    """Tests for backoff parameter bounds."""

    def test_default_backoff_parameters(self) -> None:
        client = DifficultRetailerClient()
        assert client.backoff_max == DEFAULT_BACKOFF_MAX
        assert client.max_retry_after == DEFAULT_MAX_RETRY_AFTER
        assert client.max_retries == 3

    def test_custom_backoff_parameters(self) -> None:
        client = DifficultRetailerClient(
            backoff_multiplier=2.0,
            backoff_min=1.0,
            backoff_max=60.0,
        )
        assert client.backoff_max == 60.0

    def test_invalid_backoff_multiplier(self) -> None:
        with pytest.raises(SourceFetchError, match="backoff_multiplier"):
            DifficultRetailerClient(backoff_multiplier=0)

    def test_invalid_backoff_min(self) -> None:
        with pytest.raises(SourceFetchError, match="backoff_min"):
            DifficultRetailerClient(backoff_min=0)

    def test_invalid_backoff_max(self) -> None:
        with pytest.raises(SourceFetchError, match="backoff_max"):
            DifficultRetailerClient(backoff_max=0)

    def test_backoff_max_less_than_min(self) -> None:
        with pytest.raises(SourceFetchError, match="backoff_max.*backoff_min"):
            DifficultRetailerClient(backoff_min=10.0, backoff_max=5.0)


# ---------------------------------------------------------------------------
# Partial success preservation tests
# ---------------------------------------------------------------------------


class TestPartialSuccessPreservation:
    """Tests verifying partial valid work is preserved."""

    @pytest.mark.asyncio
    async def test_partial_parse_preserves_valid_events(self) -> None:
        partial_html = _load_fixture("partial_parse_page.html")
        mock_http = _make_mock_client(status_code=200, text=partial_html)

        adapter = _make_adapter(mock_http=mock_http)
        result = await adapter.fetch()

        assert len(result.events) == 2
        assert len(result.malformed) == 2
        assert result.total_records == 4

    @pytest.mark.asyncio
    async def test_partial_parse_events_are_valid(self) -> None:
        partial_html = _load_fixture("partial_parse_page.html")
        mock_http = _make_mock_client(status_code=200, text=partial_html)

        adapter = _make_adapter(mock_http=mock_http)
        result = await adapter.fetch()

        for event in result.events:
            assert event.event_type == "product.observation"
            assert event.source == "premium_retailer"
            assert event.payload.external_id is not None
            assert event.payload.name is not None


# ---------------------------------------------------------------------------
# Replay/idempotency tests
# ---------------------------------------------------------------------------


class TestReplayIdempotency:
    """Tests verifying retries do not create duplicate logical data."""

    @pytest.mark.asyncio
    async def test_retry_produces_same_external_ids(self) -> None:
        unavailable_resp = _mock_httpx_response(status_code=503, text=UNAVAILABLE_HTML)
        success_resp = _mock_httpx_response(status_code=200, text=SUCCESS_HTML)
        mock_http = _make_mock_client(responses=[unavailable_resp, success_resp])

        adapter = _make_adapter(mock_http=mock_http)
        result = await adapter.fetch()

        external_ids = sorted(e.payload.external_id for e in result.events)
        assert external_ids == sorted(["1001", "1002", "1003"])

    @pytest.mark.asyncio
    async def test_replay_produces_same_results(self) -> None:
        results = []
        for _ in range(3):
            mock_http = _make_mock_client()
            adapter = _make_adapter(mock_http=mock_http)
            result = await adapter.fetch()
            results.append(result)

        for r in results[1:]:
            ext_ids_r = sorted(e.payload.external_id for e in r.events)
            ext_ids_0 = sorted(e.payload.external_id for e in results[0].events)
            assert ext_ids_r == ext_ids_0
            names_r = sorted(e.payload.name for e in r.events)
            names_0 = sorted(e.payload.name for e in results[0].events)
            assert names_r == names_0


# ---------------------------------------------------------------------------
# Retry metrics/logging tests
# ---------------------------------------------------------------------------


class TestRetryMetrics:
    """Tests for retry metric recording."""

    @pytest.mark.asyncio
    async def test_retry_metric_incremented_on_transient(self) -> None:
        metrics = SourceMetrics(source_name="premium_retailer")
        unavailable_resp = _mock_httpx_response(status_code=503, text=UNAVAILABLE_HTML)
        success_resp = _mock_httpx_response(status_code=200, text=SUCCESS_HTML)
        mock_http = _make_mock_client(responses=[unavailable_resp, success_resp])

        adapter = _make_adapter(mock_http=mock_http, metrics=metrics)
        await adapter.fetch()

        snapshot = metrics.snapshot()
        assert snapshot["source_retry_attempts_total"] == 1

    @pytest.mark.asyncio
    async def test_retry_metric_incremented_per_retry(self) -> None:
        metrics = SourceMetrics(source_name="premium_retailer")
        unavailable_resp = _mock_httpx_response(status_code=503, text=UNAVAILABLE_HTML)
        success_resp = _mock_httpx_response(status_code=200, text=SUCCESS_HTML)
        mock_http = _make_mock_client(responses=[unavailable_resp, unavailable_resp, success_resp])

        adapter = _make_adapter(mock_http=mock_http, metrics=metrics, max_retries=3)
        await adapter.fetch()

        snapshot = metrics.snapshot()
        assert snapshot["source_retry_attempts_total"] == 2

    @pytest.mark.asyncio
    async def test_no_retry_metric_on_success(self) -> None:
        metrics = SourceMetrics(source_name="premium_retailer")
        mock_http = _make_mock_client()

        adapter = _make_adapter(mock_http=mock_http, metrics=metrics)
        await adapter.fetch()

        snapshot = metrics.snapshot()
        assert snapshot["source_retry_attempts_total"] == 0

    @pytest.mark.asyncio
    async def test_no_retry_metric_on_non_retryable(self) -> None:
        metrics = SourceMetrics(source_name="premium_retailer")
        blocked_resp = _mock_httpx_response(status_code=403, text=BLOCKED_HTML)
        mock_http = _make_mock_client(responses=[blocked_resp])

        adapter = _make_adapter(mock_http=mock_http, metrics=metrics)
        with pytest.raises(SourceFetchError):
            await adapter.fetch()

        snapshot = metrics.snapshot()
        assert snapshot["source_retry_attempts_total"] == 0

    @pytest.mark.asyncio
    async def test_fetch_failure_metric_on_exhaustion(self) -> None:
        metrics = SourceMetrics(source_name="premium_retailer")
        unavailable_resp = _mock_httpx_response(status_code=503, text=UNAVAILABLE_HTML)
        mock_http = _make_mock_client(
            responses=[unavailable_resp, unavailable_resp, unavailable_resp]
        )

        adapter = _make_adapter(mock_http=mock_http, metrics=metrics, max_retries=3)
        with pytest.raises(SourceFetchError):
            await adapter.fetch()

        snapshot = metrics.snapshot()
        assert snapshot["source_fetch_failure_total"] == 1


# ---------------------------------------------------------------------------
# Environment variable configuration tests
# ---------------------------------------------------------------------------


class TestBackoffEnvVars:
    """Tests for backoff configuration via environment variables."""

    def test_env_var_backoff_max(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIFFICULT_RETAILER_BACKOFF_MAX", "120")
        client = DifficultRetailerClient()
        assert client.backoff_max == 120.0

    def test_env_var_max_retry_after(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIFFICULT_RETAILER_MAX_RETRY_AFTER", "90")
        client = DifficultRetailerClient()
        assert client.max_retry_after == 90.0

    def test_constructor_overrides_env_backoff(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIFFICULT_RETAILER_BACKOFF_MAX", "120")
        client = DifficultRetailerClient(backoff_max=60.0)
        assert client.backoff_max == 60.0

    def test_env_var_backoff_multiplier(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIFFICULT_RETAILER_BACKOFF_MULTIPLIER", "2.5")
        client = DifficultRetailerClient()
        assert client is not None


# ---------------------------------------------------------------------------
# Retry-After capping tests
# ---------------------------------------------------------------------------


class TestRetryAfterCapping:
    """Tests for Retry-After header capping."""

    def test_cap_retry_after_none(self) -> None:
        client = DifficultRetailerClient(max_retry_after=60.0)
        assert client._cap_retry_after(None) is None

    def test_cap_retry_after_under_limit(self) -> None:
        client = DifficultRetailerClient(max_retry_after=60.0)
        assert client._cap_retry_after(30.0) == 30.0

    def test_cap_retry_after_at_limit(self) -> None:
        client = DifficultRetailerClient(max_retry_after=60.0)
        assert client._cap_retry_after(60.0) == 60.0

    def test_cap_retry_after_over_limit(self) -> None:
        client = DifficultRetailerClient(max_retry_after=60.0)
        assert client._cap_retry_after(300.0) == 60.0

    def test_cap_retry_after_custom_max(self) -> None:
        client = DifficultRetailerClient(max_retry_after=10.0)
        assert client._cap_retry_after(120.0) == 10.0

    def test_cap_retry_after_negative_returns_none(self) -> None:
        client = DifficultRetailerClient(max_retry_after=60.0)
        assert client._cap_retry_after(-5.0) is None

    def test_cap_retry_after_zero_returns_none(self) -> None:
        client = DifficultRetailerClient(max_retry_after=60.0)
        assert client._cap_retry_after(0.0) is None


# ---------------------------------------------------------------------------
# Injectable sleep tests
# ---------------------------------------------------------------------------


class TestInjectableSleep:
    """Tests for injectable sleep function (deterministic testing)."""

    @pytest.mark.asyncio
    async def test_sync_sleep_fn_called(self) -> None:
        sleep_calls: list[float] = []

        def sync_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        rate_limited_resp = _mock_httpx_response(
            status_code=429,
            text=RATE_LIMITED_HTML,
            headers={"Retry-After": "5"},
        )
        success_resp = _mock_httpx_response(status_code=200, text=SUCCESS_HTML)
        mock_http = _make_mock_client(responses=[rate_limited_resp, success_resp])

        adapter = _make_adapter(mock_http=mock_http, sleep_fn=sync_sleep)
        await adapter.fetch()

        assert len(sleep_calls) == 1
        assert sleep_calls[0] == 5.0

    @pytest.mark.asyncio
    async def test_async_sleep_fn_called(self) -> None:
        sleep_calls: list[float] = []

        async def async_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        rate_limited_resp = _mock_httpx_response(
            status_code=429,
            text=RATE_LIMITED_HTML,
            headers={"Retry-After": "3"},
        )
        success_resp = _mock_httpx_response(status_code=200, text=SUCCESS_HTML)
        mock_http = _make_mock_client(responses=[rate_limited_resp, success_resp])

        adapter = _make_adapter(mock_http=mock_http, sleep_fn=async_sleep)
        await adapter.fetch()

        assert len(sleep_calls) == 1
        assert sleep_calls[0] == 3.0

    @pytest.mark.asyncio
    async def test_no_real_sleep_in_tests(self) -> None:
        """Verify that with injected sleep, no real time passes."""
        import time

        sleep_calls: list[float] = []

        def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        rate_limited_resp = _mock_httpx_response(
            status_code=429,
            text=RATE_LIMITED_HTML,
            headers={"Retry-After": "999"},
        )
        success_resp = _mock_httpx_response(status_code=200, text=SUCCESS_HTML)
        mock_http = _make_mock_client(responses=[rate_limited_resp, success_resp])

        adapter = _make_adapter(mock_http=mock_http, sleep_fn=mock_sleep)

        start = time.monotonic()
        await adapter.fetch()
        elapsed = time.monotonic() - start

        assert elapsed < 1.0
        assert sleep_calls[0] == 60.0  # capped at default max_retry_after
