"""Tests for source degradation detection (TASK-053).

Covers:
- healthy source
- HTTP success + parser structural failure
- partially parseable response
- rate-limited state
- unreachable state
- empty-result scenario
- recovery from degraded to healthy
- metric/state classification
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from libs.adapters import SourceFetchError
from libs.adapters.difficult_retailer.adapter import DifficultRetailerAdapter
from libs.adapters.difficult_retailer.client import DifficultRetailerClient
from libs.observability.health_assessment import (
    SourceDegradationState,
    SourceHealthAssessor,
    SourceHealthConfig,
    SourceHealthTracker,
)
from libs.observability.source_metrics import SourceMetrics

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "difficult_retailer"


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


SUCCESS_HTML = _load_fixture("success_page.html")
RATE_LIMITED_HTML = _load_fixture("rate_limited_page.html")
UNAVAILABLE_HTML = _load_fixture("unavailable_page.html")
BLOCKED_HTML = _load_fixture("blocked_page.html")
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
    max_retries: int = 1,
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
    max_retries: int = 1,
    metrics: SourceMetrics | None = None,
    health_config: SourceHealthConfig | None = None,
    **kwargs: Any,
) -> DifficultRetailerAdapter:
    client = _make_client(mock_http=mock_http, max_retries=max_retries, metrics=metrics)
    return DifficultRetailerAdapter(
        client=client, metrics=metrics, health_config=health_config, **kwargs
    )


# ---------------------------------------------------------------------------
# SourceHealthAssessor unit tests
# ---------------------------------------------------------------------------


class TestSourceHealthAssessor:
    """Unit tests for the stateless health assessor."""

    def test_no_history_is_healthy(self) -> None:
        assessor = SourceHealthAssessor()
        result = assessor.assess(source_name="test", outcomes=[])
        assert result.state == SourceDegradationState.HEALTHY
        assert result.source == "test"
        assert result.signals["total_fetches"] == 0

    def test_all_successful_with_data_is_healthy(self) -> None:
        from libs.observability.health_assessment import _FetchOutcome

        outcomes = [
            _FetchOutcome(success=True, events_emitted=10, total_records=10, malformed_count=0),
            _FetchOutcome(success=True, events_emitted=8, total_records=8, malformed_count=0),
        ]
        assessor = SourceHealthAssessor()
        result = assessor.assess(source_name="test", outcomes=outcomes)
        assert result.state == SourceDegradationState.HEALTHY
        assert result.reasons == []

    def test_low_success_ratio_is_unreachable(self) -> None:
        from libs.observability.health_assessment import _FetchOutcome

        outcomes = [
            _FetchOutcome(success=False, failure_reason="timeout"),
            _FetchOutcome(success=False, failure_reason="connection refused"),
            _FetchOutcome(success=True, events_emitted=5, total_records=5),
        ]
        config = SourceHealthConfig(min_success_ratio=0.5)
        assessor = SourceHealthAssessor(config)
        result = assessor.assess(source_name="test", outcomes=outcomes)
        assert result.state == SourceDegradationState.UNREACHABLE
        assert any("success ratio" in r for r in result.reasons)

    def test_rate_limited_detected(self) -> None:
        from libs.observability.health_assessment import _FetchOutcome

        outcomes = [
            _FetchOutcome(success=True, events_emitted=5, total_records=5),
            _FetchOutcome(success=False, failure_reason="Rate limited (HTTP 429, Retry-After: 5)"),
        ]
        assessor = SourceHealthAssessor()
        result = assessor.assess(source_name="test", outcomes=outcomes)
        assert result.state == SourceDegradationState.RATE_LIMITED

    def test_structural_change_detected(self) -> None:
        from libs.observability.health_assessment import _FetchOutcome

        outcomes = [
            _FetchOutcome(success=True, events_emitted=5, total_records=5),
            _FetchOutcome(
                success=False,
                failure_reason="page structure has changed: expected containers not found",
            ),
        ]
        assessor = SourceHealthAssessor()
        result = assessor.assess(source_name="test", outcomes=outcomes)
        assert result.state == SourceDegradationState.STRUCTURALLY_CHANGED

    def test_consecutive_empty_results(self) -> None:
        from libs.observability.health_assessment import _FetchOutcome

        outcomes = [
            _FetchOutcome(success=True, events_emitted=0, total_records=0),
            _FetchOutcome(success=True, events_emitted=0, total_records=0),
            _FetchOutcome(success=True, events_emitted=0, total_records=0),
        ]
        config = SourceHealthConfig(max_empty_fetches=3)
        assessor = SourceHealthAssessor(config)
        result = assessor.assess(source_name="test", outcomes=outcomes, consecutive_empty=3)
        assert result.state == SourceDegradationState.EMPTY_RESULT

    def test_below_min_expected_records(self) -> None:
        from libs.observability.health_assessment import _FetchOutcome

        outcomes = [
            _FetchOutcome(success=True, events_emitted=2, total_records=2),
        ]
        config = SourceHealthConfig(min_expected_records=10)
        assessor = SourceHealthAssessor(config)
        result = assessor.assess(source_name="test", outcomes=outcomes)
        assert result.state == SourceDegradationState.EMPTY_RESULT

    def test_high_malformed_ratio_is_partially_parseable(self) -> None:
        from libs.observability.health_assessment import _FetchOutcome

        outcomes = [
            _FetchOutcome(success=True, events_emitted=2, total_records=10, malformed_count=8),
        ]
        config = SourceHealthConfig(max_malformed_ratio=0.5)
        assessor = SourceHealthAssessor(config)
        result = assessor.assess(source_name="test", outcomes=outcomes)
        assert result.state == SourceDegradationState.PARTIALLY_PARSEABLE
        assert any("malformed ratio" in r for r in result.reasons)

    def test_recovery_from_degraded_to_healthy(self) -> None:
        from libs.observability.health_assessment import _FetchOutcome

        outcomes = [
            _FetchOutcome(success=False, failure_reason="timeout"),
            _FetchOutcome(success=False, failure_reason="timeout"),
            _FetchOutcome(success=True, events_emitted=10, total_records=10),
            _FetchOutcome(success=True, events_emitted=10, total_records=10),
            _FetchOutcome(success=True, events_emitted=10, total_records=10),
        ]
        config = SourceHealthConfig(min_success_ratio=0.5)
        assessor = SourceHealthAssessor(config)
        result = assessor.assess(source_name="test", outcomes=outcomes)
        assert result.state == SourceDegradationState.HEALTHY

    def test_signals_include_all_metrics(self) -> None:
        from libs.observability.health_assessment import _FetchOutcome

        outcomes = [
            _FetchOutcome(success=True, events_emitted=5, total_records=10, malformed_count=2),
            _FetchOutcome(success=False, failure_reason="timeout"),
        ]
        assessor = SourceHealthAssessor()
        result = assessor.assess(source_name="test", outcomes=outcomes)
        signals = result.signals
        assert signals["total_fetches"] == 2
        assert signals["successful_fetches"] == 1
        assert signals["failed_fetches"] == 1
        assert signals["total_records"] == 10
        assert signals["total_malformed"] == 2
        assert signals["total_events"] == 5


# ---------------------------------------------------------------------------
# SourceHealthTracker tests
# ---------------------------------------------------------------------------


class TestSourceHealthTracker:
    """Tests for the stateful health tracker."""

    def test_initial_state_is_healthy(self) -> None:
        tracker = SourceHealthTracker(source_name="test")
        assessment = tracker.assess()
        assert assessment.state == SourceDegradationState.HEALTHY

    def test_record_success_tracks_outcomes(self) -> None:
        tracker = SourceHealthTracker(source_name="test")
        tracker.record_fetch_success(events_emitted=5, total_records=5)
        assessment = tracker.assess()
        assert assessment.state == SourceDegradationState.HEALTHY
        assert assessment.signals["total_fetches"] == 1
        assert assessment.signals["successful_fetches"] == 1

    def test_record_failure_tracks_outcomes(self) -> None:
        tracker = SourceHealthTracker(source_name="test")
        tracker.record_fetch_failure("timeout")
        assessment = tracker.assess()
        assert assessment.signals["failed_fetches"] == 1

    def test_consecutive_empty_tracked(self) -> None:
        tracker = SourceHealthTracker(
            source_name="test",
            config=SourceHealthConfig(max_empty_fetches=2),
        )
        tracker.record_fetch_success(events_emitted=0, total_records=0)
        tracker.record_fetch_success(events_emitted=0, total_records=0)
        assessment = tracker.assess()
        assert assessment.state == SourceDegradationState.EMPTY_RESULT

    def test_non_empty_resets_consecutive_empty(self) -> None:
        tracker = SourceHealthTracker(
            source_name="test",
            config=SourceHealthConfig(max_empty_fetches=3),
        )
        tracker.record_fetch_success(events_emitted=0, total_records=0)
        tracker.record_fetch_success(events_emitted=0, total_records=0)
        tracker.record_fetch_success(events_emitted=5, total_records=5)
        assessment = tracker.assess()
        assert assessment.state == SourceDegradationState.HEALTHY
        assert assessment.signals["consecutive_empty_fetches"] == 0

    def test_history_bounded(self) -> None:
        tracker = SourceHealthTracker(source_name="test", max_history=5)
        for i in range(10):
            tracker.record_fetch_success(events_emitted=i, total_records=i)
        assessment = tracker.assess()
        assert assessment.signals["total_fetches"] == 5

    def test_custom_config(self) -> None:
        config = SourceHealthConfig(
            min_success_ratio=0.8,
            max_malformed_ratio=0.1,
            max_empty_fetches=1,
        )
        tracker = SourceHealthTracker(source_name="test", config=config)
        tracker.record_fetch_success(events_emitted=5, total_records=10, malformed_count=5)
        assessment = tracker.assess()
        assert assessment.state == SourceDegradationState.PARTIALLY_PARSEABLE


# ---------------------------------------------------------------------------
# Adapter integration tests
# ---------------------------------------------------------------------------


class TestAdapterHealthIntegration:
    """Integration tests for health tracking through the adapter."""

    @pytest.mark.asyncio
    async def test_healthy_source(self) -> None:
        mock_http = _make_mock_client()
        adapter = _make_adapter(mock_http=mock_http)
        result = await adapter.fetch()
        assert len(result.events) == 3

        assessment = adapter.health_assessment()
        assert assessment.state == SourceDegradationState.HEALTHY
        assert assessment.source == "premium_retailer"

    @pytest.mark.asyncio
    async def test_unreachable_source(self) -> None:
        unavailable_resp = _mock_httpx_response(status_code=503, text=UNAVAILABLE_HTML)
        mock_http = _make_mock_client(responses=[unavailable_resp])
        adapter = _make_adapter(mock_http=mock_http, max_retries=1)

        with pytest.raises(SourceFetchError):
            await adapter.fetch()

        assessment = adapter.health_assessment()
        assert assessment.state == SourceDegradationState.UNREACHABLE

    @pytest.mark.asyncio
    async def test_partially_parseable_source(self) -> None:
        mock_http = _make_mock_client(status_code=200, text=PARTIAL_PARSE_HTML)
        adapter = _make_adapter(
            mock_http=mock_http,
            health_config=SourceHealthConfig(max_malformed_ratio=0.1),
        )
        result = await adapter.fetch()
        assert len(result.events) == 2
        assert len(result.malformed) == 2

        assessment = adapter.health_assessment()
        assert assessment.state == SourceDegradationState.PARTIALLY_PARSEABLE

    @pytest.mark.asyncio
    async def test_structural_change_detected(self) -> None:
        structural_html = _load_fixture("structural_change_page.html")
        mock_http = _make_mock_client(status_code=200, text=structural_html)
        adapter = _make_adapter(mock_http=mock_http)

        with pytest.raises(SourceFetchError, match="structure"):
            await adapter.fetch()

        assessment = adapter.health_assessment()
        assert assessment.state == SourceDegradationState.STRUCTURALLY_CHANGED

    @pytest.mark.asyncio
    async def test_rate_limited_state(self) -> None:
        rate_limited_resp = _mock_httpx_response(
            status_code=429,
            text=RATE_LIMITED_HTML,
            headers={},
        )
        mock_http = _make_mock_client(responses=[rate_limited_resp])
        adapter = _make_adapter(mock_http=mock_http, max_retries=1)

        with pytest.raises(SourceFetchError):
            await adapter.fetch()

        assessment = adapter.health_assessment()
        assert assessment.state == SourceDegradationState.RATE_LIMITED

    @pytest.mark.asyncio
    async def test_empty_result_scenario(self) -> None:
        empty_html = "<html><body><div class='product-list'></div></body></html>"
        mock_http = _make_mock_client(status_code=200, text=empty_html)
        adapter = _make_adapter(
            mock_http=mock_http,
            health_config=SourceHealthConfig(max_empty_fetches=1),
        )
        result = await adapter.fetch()
        assert len(result.events) == 0

        assessment = adapter.health_assessment()
        assert assessment.state == SourceDegradationState.EMPTY_RESULT

    @pytest.mark.asyncio
    async def test_recovery_from_degraded(self) -> None:
        unavailable_resp = _mock_httpx_response(status_code=503, text=UNAVAILABLE_HTML)
        success_resp = _mock_httpx_response(status_code=200, text=SUCCESS_HTML)
        mock_http = _make_mock_client(responses=[unavailable_resp, success_resp])
        adapter = _make_adapter(mock_http=mock_http, max_retries=1)

        with pytest.raises(SourceFetchError):
            await adapter.fetch()
        assert adapter.health_assessment().state == SourceDegradationState.UNREACHABLE

        result = await adapter.fetch()
        assert len(result.events) == 3
        assert adapter.health_assessment().state == SourceDegradationState.HEALTHY

    @pytest.mark.asyncio
    async def test_health_assessment_does_not_mutate_data(self) -> None:
        mock_http = _make_mock_client()
        adapter = _make_adapter(mock_http=mock_http)
        result = await adapter.fetch()
        events_before = list(result.events)

        assessment = adapter.health_assessment()
        assert assessment.state == SourceDegradationState.HEALTHY

        events_after = list(result.events)
        assert len(events_before) == len(events_after)
        for before, after in zip(events_before, events_after):
            assert before.event_id == after.event_id

    @pytest.mark.asyncio
    async def test_metric_state_classification(self) -> None:
        metrics = SourceMetrics(source_name="premium_retailer")
        unavailable_resp = _mock_httpx_response(status_code=503, text=UNAVAILABLE_HTML)
        mock_http = _make_mock_client(responses=[unavailable_resp])
        adapter = _make_adapter(mock_http=mock_http, max_retries=1, metrics=metrics)

        with pytest.raises(SourceFetchError):
            await adapter.fetch()

        snapshot = metrics.snapshot()
        assert snapshot["source_fetch_failure_total"] != 0

        assessment = adapter.health_assessment()
        assert assessment.state == SourceDegradationState.UNREACHABLE
        assert assessment.signals["failed_fetches"] >= 1

    @pytest.mark.asyncio
    async def test_http_200_with_structural_failure_not_healthy(self) -> None:
        structural_html = _load_fixture("structural_change_page.html")
        mock_http = _make_mock_client(status_code=200, text=structural_html)
        adapter = _make_adapter(mock_http=mock_http)

        with pytest.raises(SourceFetchError):
            await adapter.fetch()

        assessment = adapter.health_assessment()
        assert assessment.state != SourceDegradationState.HEALTHY
        assert assessment.state == SourceDegradationState.STRUCTURALLY_CHANGED

    @pytest.mark.asyncio
    async def test_health_tracker_property(self) -> None:
        adapter = _make_adapter()
        assert adapter.health_tracker is not None
        assert adapter.health_tracker.source_name == "premium_retailer"
