"""Difficult-source integration tests for TASK-055.

Integration gate proving graceful degradation of the difficult source through
the complete pipeline:
  fixture HTML -> adapter -> retry/backoff -> degradation/freshness state ->
  canonical event -> mock Kafka -> processor -> bronze/silver Parquet

Covers 10 required scenarios:
1.  healthy observation through the pipeline
2.  rate-limited then recovered
3.  persistent rate limiting
4.  source unavailable
5.  structural/parser change
6.  partially parseable source
7.  freshness becomes stale
8.  recovery from degraded/stale state
9.  replay/duplicate delivery
10. regression smoke test for earlier sources
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import polars as pl
import pytest

from libs.adapters import SourceFetchError
from libs.adapters.difficult_retailer.adapter import DifficultRetailerAdapter
from libs.adapters.difficult_retailer.client import DifficultRetailerClient
from libs.common.kafka_consumer import ConsumerMessage
from libs.common.kafka_producer import DeliveryReceipt
from libs.common.minio_storage import MinIOStorage
from libs.event_contracts import ProductObservationEvent
from libs.lake_writer.silver_writer import SilverWriter, validated_event_to_row
from libs.observability.health_assessment import (
    SourceDegradationState,
    SourceHealthConfig,
    SourceHealthTracker,
)
from libs.observability.source_metrics import SourceMetrics
from libs.raw_writer import BronzeWriter
from services.ingestion.runner import IngestionRunner
from services.processor.deduplication import DeduplicationState
from services.processor.pipeline import ProcessorPipeline

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "difficult_retailer"


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


SUCCESS_HTML = _load_fixture("success_page.html")
RATE_LIMITED_HTML = _load_fixture("rate_limited_page.html")
UNAVAILABLE_HTML = _load_fixture("unavailable_page.html")
BLOCKED_HTML = _load_fixture("blocked_page.html")
PARTIAL_PARSE_HTML = _load_fixture("partial_parse_page.html")
STRUCTURAL_CHANGE_HTML = _load_fixture("structural_change_page.html")
EMPTY_HTML = "<html><body><div class='product-list'></div></body></html>"


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class MockProducer:
    """Test helper that tracks published events without real Kafka."""

    def __init__(self) -> None:
        self.published: list[ProductObservationEvent] = []
        self.metrics = MagicMock()
        self.metrics.increment = MagicMock()

    def publish(self, event: ProductObservationEvent) -> DeliveryReceipt:
        self.published.append(event)
        return DeliveryReceipt(topic="products.raw.v1", partition=0, offset=len(self.published) - 1)


class TrackingSinks:
    """Track events published to validated and invalid topics."""

    def __init__(self) -> None:
        self.validated_events: list[ProductObservationEvent] = []
        self.invalid_envelopes: list[dict[str, Any]] = []

    def validated_sink(self, event: ProductObservationEvent) -> None:
        self.validated_events.append(event)

    def invalid_sink(self, envelope: dict[str, Any]) -> None:
        self.invalid_envelopes.append(envelope)


def _wrap_as_consumer_message(event: ProductObservationEvent, offset: int = 0) -> ConsumerMessage:
    return ConsumerMessage(
        event=event,
        topic="products.raw.v1",
        partition=0,
        offset=offset,
        raw_value=None,
    )


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
    )


def _make_adapter(
    *,
    mock_http: AsyncMock | None = None,
    max_retries: int = 1,
    metrics: SourceMetrics | None = None,
    health_config: SourceHealthConfig | None = None,
    clock: Any = None,
) -> DifficultRetailerAdapter:
    client = _make_client(mock_http=mock_http, max_retries=max_retries, metrics=metrics)
    health_tracker = SourceHealthTracker(
        source_name="premium_retailer",
        config=health_config,
        clock=clock,
    )
    return DifficultRetailerAdapter(
        client=client,
        metrics=metrics,
        health_tracker=health_tracker,
    )


def _run_pipeline(events: list[ProductObservationEvent]) -> TrackingSinks:
    """Run events through the processor pipeline and return tracking sinks."""
    sinks = TrackingSinks()
    pipeline = ProcessorPipeline(
        validated_sink=sinks.validated_sink,
        invalid_sink=sinks.invalid_sink,
        dedup_state=DeduplicationState(),
    )
    messages = [_wrap_as_consumer_message(e, offset=i) for i, e in enumerate(events)]
    pipeline.process_batch(messages)
    return sinks


# ---------------------------------------------------------------------------
# Scenario 1: Healthy observation through the pipeline
# ---------------------------------------------------------------------------


class TestHealthyObservation:
    """Verify a healthy difficult-source observation traverses the full pipeline."""

    @pytest.mark.asyncio
    async def test_healthy_product_through_full_pipeline(self) -> None:
        """A product traverses: HTML -> adapter -> mock Kafka -> processor -> validated."""
        mock_http = _make_mock_client()
        adapter = _make_adapter(mock_http=mock_http)
        producer = MockProducer()

        runner = IngestionRunner(
            adapters=[adapter],
            producer=producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert len(producer.published) == 3
        raw_event = producer.published[0]
        assert raw_event.source == "premium_retailer"
        assert raw_event.payload.external_id == "1001"
        assert raw_event.payload.name == "Premium Headphones"
        assert raw_event.payload.price == Decimal("299.99")
        assert raw_event.payload.currency == "USD"
        assert raw_event.payload.availability == "in_stock"

        sinks = _run_pipeline(producer.published)
        assert len(sinks.validated_events) == 3
        assert len(sinks.invalid_envelopes) == 0

        validated = sinks.validated_events[0]
        assert validated.event_id == raw_event.event_id
        assert validated.source == "premium_retailer"

    @pytest.mark.asyncio
    async def test_healthy_source_health_is_healthy(self) -> None:
        """A successful fetch reports healthy source state."""
        mock_http = _make_mock_client()
        adapter = _make_adapter(mock_http=mock_http)
        producer = MockProducer()

        runner = IngestionRunner(
            adapters=[adapter],
            producer=producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assessment = adapter.health_assessment()
        assert assessment.state == SourceDegradationState.HEALTHY

    @pytest.mark.asyncio
    async def test_healthy_event_to_bronze_parquet(self) -> None:
        """A healthy difficult-source event round-trips through Bronze Parquet."""
        mock_http = _make_mock_client()
        adapter = _make_adapter(mock_http=mock_http)
        producer = MockProducer()

        runner = IngestionRunner(
            adapters=[adapter],
            producer=producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        event = producer.published[0]

        mock_storage = MagicMock(spec=MinIOStorage)
        mock_storage.put_object = MagicMock()

        writer = BronzeWriter(storage=mock_storage, bucket="test-bronze", batch_size=10)
        writer.add_event(event)
        writer.flush_batch()

        mock_storage.put_object.assert_called_once()
        call_args = mock_storage.put_object.call_args
        key = call_args[0][1]
        assert key.startswith("bronze/")
        assert "source=premium_retailer" in key

        parquet_bytes = call_args[0][2]
        df = pl.read_parquet(io.BytesIO(parquet_bytes))
        assert df.height == 1
        row = df.row(0, named=True)
        assert row["source"] == "premium_retailer"
        assert row["external_id"] == "1001"

    @pytest.mark.asyncio
    async def test_healthy_event_to_silver_parquet(self) -> None:
        """A validated difficult-source event round-trips through Silver Parquet."""
        mock_http = _make_mock_client()
        adapter = _make_adapter(mock_http=mock_http)
        producer = MockProducer()

        runner = IngestionRunner(
            adapters=[adapter],
            producer=producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        sinks = _run_pipeline(producer.published)
        validated_event = sinks.validated_events[0]

        row = validated_event_to_row(validated_event)
        assert row["source"] == "premium_retailer"
        assert row["external_id"] == "1001"

        mock_storage = MagicMock(spec=MinIOStorage)
        mock_storage.put_object = MagicMock()

        writer = SilverWriter(storage=mock_storage, bucket="test-silver", batch_size=10)
        writer.add_event(validated_event)
        writer.flush_batch()

        mock_storage.put_object.assert_called_once()
        call_args = mock_storage.put_object.call_args
        key = call_args[0][1]
        assert key.startswith("silver/")
        assert "source=premium_retailer" in key


# ---------------------------------------------------------------------------
# Scenario 2: Rate-limited then recovered
# ---------------------------------------------------------------------------


class TestRateLimitedThenRecovered:
    """Verify rate limiting followed by recovery produces valid data."""

    @pytest.mark.asyncio
    async def test_rate_limit_then_success(self) -> None:
        """First fetch is rate-limited, runner retries and succeeds with valid data."""
        rate_limited_resp = _mock_httpx_response(
            status_code=429, text=RATE_LIMITED_HTML, headers={}
        )
        success_resp = _mock_httpx_response(status_code=200, text=SUCCESS_HTML)
        mock_http = _make_mock_client(responses=[rate_limited_resp, success_resp])
        adapter = _make_adapter(mock_http=mock_http, max_retries=1)
        producer = MockProducer()

        runner = IngestionRunner(
            adapters=[adapter],
            producer=producer,  # type: ignore[arg-type]
            max_retries=1,
        )
        await runner.run_once()

        assert len(producer.published) == 3
        external_ids = {e.payload.external_id for e in producer.published}
        assert "1001" in external_ids

        sinks = _run_pipeline(producer.published)
        assert len(sinks.validated_events) == 3

        for event in sinks.validated_events:
            assert event.source == "premium_retailer"
            assert event.payload.price is not None

    @pytest.mark.asyncio
    async def test_rate_limit_does_not_corrupt_downstream(self) -> None:
        """Rate limiting does not introduce source-specific branching downstream."""
        rate_limited_resp = _mock_httpx_response(
            status_code=429, text=RATE_LIMITED_HTML, headers={}
        )
        success_resp = _mock_httpx_response(status_code=200, text=SUCCESS_HTML)
        mock_http = _make_mock_client(responses=[rate_limited_resp, success_resp])
        adapter = _make_adapter(mock_http=mock_http, max_retries=1)
        producer = MockProducer()

        runner = IngestionRunner(
            adapters=[adapter],
            producer=producer,  # type: ignore[arg-type]
            max_retries=1,
        )
        await runner.run_once()

        sinks = _run_pipeline(producer.published)

        for event in sinks.validated_events:
            assert event.source == "premium_retailer"
            assert event.payload.price is not None
            assert event.payload.currency == "USD"


# ---------------------------------------------------------------------------
# Scenario 3: Persistent rate limiting
# ---------------------------------------------------------------------------


class TestPersistentRateLimiting:
    """Verify persistent rate limiting is detected as degradation."""

    @pytest.mark.asyncio
    async def test_persistent_rate_limit_detected(self) -> None:
        """All retries rate-limited: source is detected as RATE_LIMITED."""
        rate_limited_resp = _mock_httpx_response(
            status_code=429, text=RATE_LIMITED_HTML, headers={}
        )
        mock_http = _make_mock_client(responses=[rate_limited_resp])
        adapter = _make_adapter(mock_http=mock_http, max_retries=1)

        with pytest.raises(SourceFetchError):
            await adapter.fetch()

        assessment = adapter.health_assessment()
        assert assessment.state == SourceDegradationState.RATE_LIMITED

    @pytest.mark.asyncio
    async def test_persistent_rate_limit_no_events_published(self) -> None:
        """Persistent rate limiting produces no events, no corruption."""
        rate_limited_resp = _mock_httpx_response(
            status_code=429, text=RATE_LIMITED_HTML, headers={}
        )
        mock_http = _make_mock_client(responses=[rate_limited_resp])
        adapter = _make_adapter(mock_http=mock_http, max_retries=1)
        producer = MockProducer()

        runner = IngestionRunner(
            adapters=[adapter],
            producer=producer,  # type: ignore[arg-type]
            max_retries=1,
        )
        await runner.run_once()

        assert len(producer.published) == 0

        sinks = _run_pipeline(producer.published)
        assert len(sinks.validated_events) == 0
        assert len(sinks.invalid_envelopes) == 0


# ---------------------------------------------------------------------------
# Scenario 4: Source unavailable
# ---------------------------------------------------------------------------


class TestSourceUnavailable:
    """Verify source unavailability is detected as degradation."""

    @pytest.mark.asyncio
    async def test_unavailable_source_detected(self) -> None:
        """503 response is detected as UNREACHABLE."""
        unavailable_resp = _mock_httpx_response(status_code=503, text=UNAVAILABLE_HTML)
        mock_http = _make_mock_client(responses=[unavailable_resp])
        adapter = _make_adapter(mock_http=mock_http, max_retries=1)

        with pytest.raises(SourceFetchError):
            await adapter.fetch()

        assessment = adapter.health_assessment()
        assert assessment.state == SourceDegradationState.UNREACHABLE

    @pytest.mark.asyncio
    async def test_unavailable_does_not_affect_other_sources(self) -> None:
        """An unavailable difficult source does not block other sources."""
        from libs.adapters.fake_store.adapter import FakeStoreAdapter

        unavailable_resp = _mock_httpx_response(status_code=503, text=UNAVAILABLE_HTML)
        mock_http = _make_mock_client(responses=[unavailable_resp])
        difficult_adapter = _make_adapter(mock_http=mock_http, max_retries=1)

        mock_fs_client = AsyncMock()
        mock_fs_client.fetch_products = AsyncMock(
            return_value=(
                [MagicMock(id=1, title="FS Item", price=10.0, category="cat")],
                [],
            )
        )
        fake_store = FakeStoreAdapter(client=mock_fs_client)

        producer = MockProducer()
        runner = IngestionRunner(
            adapters=[difficult_adapter, fake_store],
            producer=producer,  # type: ignore[arg-type]
            max_retries=1,
        )
        await runner.run_once()

        fake_store_events = [e for e in producer.published if e.source == "fake_store"]
        assert len(fake_store_events) >= 1

        difficult_events = [e for e in producer.published if e.source == "premium_retailer"]
        assert len(difficult_events) == 0


# ---------------------------------------------------------------------------
# Scenario 5: Structural/parser change
# ---------------------------------------------------------------------------


class TestStructuralChange:
    """Verify structural page changes are detected."""

    @pytest.mark.asyncio
    async def test_structural_change_detected(self) -> None:
        """Page structure change raises SourceFetchError and reports STRUCTURALLY_CHANGED."""
        mock_http = _make_mock_client(status_code=200, text=STRUCTURAL_CHANGE_HTML)
        adapter = _make_adapter(mock_http=mock_http)

        with pytest.raises(SourceFetchError, match="structure"):
            await adapter.fetch()

        assessment = adapter.health_assessment()
        assert assessment.state == SourceDegradationState.STRUCTURALLY_CHANGED

    @pytest.mark.asyncio
    async def test_structural_change_no_downstream_impact(self) -> None:
        """Structural change produces no events; downstream is unaffected."""
        mock_http = _make_mock_client(status_code=200, text=STRUCTURAL_CHANGE_HTML)
        adapter = _make_adapter(mock_http=mock_http)
        producer = MockProducer()

        runner = IngestionRunner(
            adapters=[adapter],
            producer=producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        sinks = _run_pipeline(producer.published)
        assert len(sinks.validated_events) == 0
        assert len(sinks.invalid_envelopes) == 0


# ---------------------------------------------------------------------------
# Scenario 6: Partially parseable source
# ---------------------------------------------------------------------------


class TestPartiallyParseable:
    """Verify partial parsing produces valid events and tracks malformed records."""

    @pytest.mark.asyncio
    async def test_partial_parse_produces_valid_events(self) -> None:
        """Partial parse yields valid events for parseable products."""
        mock_http = _make_mock_client(status_code=200, text=PARTIAL_PARSE_HTML)
        adapter = _make_adapter(
            mock_http=mock_http,
            health_config=SourceHealthConfig(max_malformed_ratio=0.1),
        )
        producer = MockProducer()

        runner = IngestionRunner(
            adapters=[adapter],
            producer=producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert len(producer.published) == 2
        external_ids = {e.payload.external_id for e in producer.published}
        assert "3001" in external_ids
        assert "3004" in external_ids

    @pytest.mark.asyncio
    async def test_partial_parse_through_processor(self) -> None:
        """Partially parsed events pass through the processor cleanly."""
        mock_http = _make_mock_client(status_code=200, text=PARTIAL_PARSE_HTML)
        adapter = _make_adapter(
            mock_http=mock_http,
            health_config=SourceHealthConfig(max_malformed_ratio=0.1),
        )
        producer = MockProducer()

        runner = IngestionRunner(
            adapters=[adapter],
            producer=producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        sinks = _run_pipeline(producer.published)
        assert len(sinks.validated_events) == 2
        assert len(sinks.invalid_envelopes) == 0

    @pytest.mark.asyncio
    async def test_partial_parse_health_state(self) -> None:
        """High malformed ratio is detected as PARTIALLY_PARSEABLE."""
        mock_http = _make_mock_client(status_code=200, text=PARTIAL_PARSE_HTML)
        adapter = _make_adapter(
            mock_http=mock_http,
            health_config=SourceHealthConfig(max_malformed_ratio=0.1),
        )
        producer = MockProducer()

        runner = IngestionRunner(
            adapters=[adapter],
            producer=producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assessment = adapter.health_assessment()
        assert assessment.state == SourceDegradationState.PARTIALLY_PARSEABLE

    @pytest.mark.asyncio
    async def test_partial_parse_to_bronze_parquet(self) -> None:
        """Partially parsed valid events persist to Bronze Parquet correctly."""
        mock_http = _make_mock_client(status_code=200, text=PARTIAL_PARSE_HTML)
        adapter = _make_adapter(mock_http=mock_http)
        producer = MockProducer()

        runner = IngestionRunner(
            adapters=[adapter],
            producer=producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        mock_storage = MagicMock(spec=MinIOStorage)
        mock_storage.put_object = MagicMock()

        writer = BronzeWriter(storage=mock_storage, bucket="test-bronze", batch_size=10)
        for event in producer.published:
            writer.add_event(event)
        writer.flush_batch()

        assert mock_storage.put_object.call_count == 2


# ---------------------------------------------------------------------------
# Scenario 7: Freshness becomes stale
# ---------------------------------------------------------------------------


class TestFreshnessBecomesStale:
    """Verify freshness staleness is detected through the pipeline."""

    @pytest.mark.asyncio
    async def test_stale_freshness_detected(self) -> None:
        """A source that was successful but is now stale reports STALE state."""
        clock_list: list[datetime] = [datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)]

        def clock() -> datetime:
            return clock_list[0]

        mock_http = _make_mock_client()
        metrics = SourceMetrics(source_name="premium_retailer", clock=clock)
        adapter = _make_adapter(
            mock_http=mock_http,
            metrics=metrics,
            health_config=SourceHealthConfig(max_freshness_age_seconds=3600),
            clock=clock,
        )
        producer = MockProducer()

        runner = IngestionRunner(
            adapters=[adapter],
            producer=producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert len(producer.published) == 3
        assert adapter.health_assessment().state == SourceDegradationState.HEALTHY

        clock_list[0] = datetime(2026, 9, 17, 14, 0, 1, tzinfo=timezone.utc)

        assessment = adapter.health_assessment()
        assert assessment.state == SourceDegradationState.STALE

    @pytest.mark.asyncio
    async def test_stale_freshness_via_runner_api(self) -> None:
        """IngestionRunner exposes freshness data that can detect staleness."""
        clock_list: list[datetime] = [datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)]

        def clock() -> datetime:
            return clock_list[0]

        mock_http = _make_mock_client()
        metrics = SourceMetrics(source_name="premium_retailer", clock=clock)
        adapter = _make_adapter(mock_http=mock_http, metrics=metrics, clock=clock)
        producer = MockProducer()

        runner = IngestionRunner(
            adapters=[adapter],
            producer=producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        freshness = runner.get_source_freshness()
        assert freshness["premium_retailer"]["freshness_age_seconds"] is not None
        assert freshness["premium_retailer"]["freshness_age_seconds"] < 10

        clock_list[0] = datetime(2026, 9, 17, 14, 0, 0, tzinfo=timezone.utc)

        freshness_stale = runner.get_source_freshness()
        age = freshness_stale["premium_retailer"]["freshness_age_seconds"]
        assert age is not None
        assert age > 7000


# ---------------------------------------------------------------------------
# Scenario 8: Recovery from degraded/stale state
# ---------------------------------------------------------------------------


class TestRecoveryFromDegraded:
    """Verify recovery from degraded/stale state restores healthy."""

    @pytest.mark.asyncio
    async def test_recovery_from_unreachable(self) -> None:
        """Source recovers from UNREACHABLE to HEALTHY after a successful fetch."""
        unavailable_resp = _mock_httpx_response(status_code=503, text=UNAVAILABLE_HTML)
        success_resp = _mock_httpx_response(status_code=200, text=SUCCESS_HTML)
        mock_http = _make_mock_client(responses=[unavailable_resp, success_resp])
        adapter = _make_adapter(mock_http=mock_http, max_retries=1)
        producer = MockProducer()

        with pytest.raises(SourceFetchError):
            await adapter.fetch()
        assert adapter.health_assessment().state == SourceDegradationState.UNREACHABLE

        runner = IngestionRunner(
            adapters=[adapter],
            producer=producer,  # type: ignore[arg-type]
            max_retries=1,
        )
        await runner.run_once()
        assert len(producer.published) == 3
        assert adapter.health_assessment().state == SourceDegradationState.HEALTHY

        sinks = _run_pipeline(producer.published)
        assert len(sinks.validated_events) == 3

    @pytest.mark.asyncio
    async def test_recovery_from_stale(self) -> None:
        """Source recovers from STALE to HEALTHY after a fresh successful fetch."""
        clock_list: list[datetime] = [datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)]

        def clock() -> datetime:
            return clock_list[0]

        mock_http = _make_mock_client()
        metrics = SourceMetrics(source_name="premium_retailer", clock=clock)
        adapter = _make_adapter(
            mock_http=mock_http,
            metrics=metrics,
            health_config=SourceHealthConfig(max_freshness_age_seconds=3600),
            clock=clock,
        )
        producer = MockProducer()

        runner = IngestionRunner(
            adapters=[adapter],
            producer=producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        clock_list[0] = datetime(2026, 9, 17, 14, 0, 1, tzinfo=timezone.utc)
        assert adapter.health_assessment().state == SourceDegradationState.STALE

        clock_list[0] = datetime(2026, 9, 17, 14, 1, 0, tzinfo=timezone.utc)
        await runner.run_once()

        assert len(producer.published) == 6
        assert adapter.health_assessment().state == SourceDegradationState.HEALTHY


# ---------------------------------------------------------------------------
# Scenario 9: Replay/duplicate delivery
# ---------------------------------------------------------------------------


class TestReplayDuplicateDelivery:
    """Verify replay/idempotency semantics for the difficult source."""

    @pytest.mark.asyncio
    async def test_duplicate_events_deduplicated(self) -> None:
        """Duplicate events are deduplicated by the processor."""
        mock_http = _make_mock_client()
        adapter = _make_adapter(mock_http=mock_http)
        producer = MockProducer()

        runner = IngestionRunner(
            adapters=[adapter],
            producer=producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        original_events = list(producer.published)
        assert len(original_events) == 3

        sinks = TrackingSinks()
        dedup_state = DeduplicationState()
        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
            dedup_state=dedup_state,
        )

        first_batch = [
            _wrap_as_consumer_message(e, offset=i) for i, e in enumerate(original_events)
        ]
        pipeline.process_batch(first_batch)
        assert len(sinks.validated_events) == 3

        replay_batch = [
            _wrap_as_consumer_message(e, offset=i + 100) for i, e in enumerate(original_events)
        ]
        result2 = pipeline.process_batch(replay_batch)

        assert len(sinks.validated_events) == 3
        assert result2.duplicates_skipped == 3

    @pytest.mark.asyncio
    async def test_replay_produces_same_event_ids(self) -> None:
        """Re-running the adapter produces events with the same external_ids."""
        mock_http = _make_mock_client()
        adapter = _make_adapter(mock_http=mock_http)
        producer = MockProducer()

        runner = IngestionRunner(
            adapters=[adapter],
            producer=producer,  # type: ignore[arg-type]
        )
        await runner.run_once()
        first_run_ids = {e.payload.external_id for e in producer.published}

        producer2 = MockProducer()
        mock_http2 = _make_mock_client()
        adapter2 = _make_adapter(mock_http=mock_http2)
        runner2 = IngestionRunner(
            adapters=[adapter2],
            producer=producer2,  # type: ignore[arg-type]
        )
        await runner2.run_once()
        second_run_ids = {e.payload.external_id for e in producer2.published}

        assert first_run_ids == second_run_ids

    @pytest.mark.asyncio
    async def test_replay_bronze_parquet_idempotent(self) -> None:
        """Replayed events overwrite the same Bronze Parquet keys (idempotent)."""
        mock_http = _make_mock_client()
        adapter = _make_adapter(mock_http=mock_http)
        producer = MockProducer()

        runner = IngestionRunner(
            adapters=[adapter],
            producer=producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        mock_storage = MagicMock(spec=MinIOStorage)
        written_keys: list[str] = []
        mock_storage.put_object = MagicMock(
            side_effect=lambda bucket, key, data: written_keys.append(key)
        )

        writer = BronzeWriter(storage=mock_storage, bucket="test-bronze", batch_size=10)
        for event in producer.published:
            writer.add_event(event)
        writer.flush_batch()

        first_keys = list(written_keys)

        written_keys.clear()
        writer2 = BronzeWriter(storage=mock_storage, bucket="test-bronze", batch_size=10)
        for event in producer.published:
            writer2.add_event(event)
        writer2.flush_batch()

        assert written_keys == first_keys


# ---------------------------------------------------------------------------
# Scenario 10: Regression smoke test for earlier sources
# ---------------------------------------------------------------------------


class TestRegressionSmoke:
    """Smoke tests ensuring difficult source coexists with existing adapters."""

    @pytest.mark.asyncio
    async def test_all_sources_in_one_cycle(self) -> None:
        """All sources publish events in a single ingestion cycle."""
        from libs.adapters.best_buy.adapter import BestBuyAdapter
        from libs.adapters.best_buy.models import BestBuyProduct
        from libs.adapters.fake_store.adapter import FakeStoreAdapter

        mock_http = _make_mock_client()
        difficult_adapter = _make_adapter(mock_http=mock_http)

        mock_fs_client = AsyncMock()
        mock_fs_client.fetch_products = AsyncMock(
            return_value=(
                [MagicMock(id=1, title="FS Item", price=10.0, category="cat")],
                [],
            )
        )
        fake_store = FakeStoreAdapter(client=mock_fs_client)

        mock_bb_client = AsyncMock()
        mock_bb_client.fetch_products = AsyncMock(
            return_value=(
                [
                    BestBuyProduct(
                        sku=2,
                        name="BB Item",
                        salePrice=20.0,
                        regularPrice=20.0,
                        url="https://bb.com/2",
                        inStoreAvailability=True,
                        onlineAvailability=True,
                        categoryPath=[],
                    )
                ],
                [],
            )
        )
        best_buy = BestBuyAdapter(client=mock_bb_client)

        producer = MockProducer()
        runner = IngestionRunner(
            adapters=[difficult_adapter, fake_store, best_buy],
            producer=producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        sources = {e.source for e in producer.published}
        assert "premium_retailer" in sources
        assert "fake_store" in sources
        assert "best_buy" in sources

    @pytest.mark.asyncio
    async def test_difficult_source_failure_isolates_from_others(self) -> None:
        """Difficult source failure does not prevent other sources from publishing."""
        from libs.adapters.fake_store.adapter import FakeStoreAdapter

        unavailable_resp = _mock_httpx_response(status_code=503, text=UNAVAILABLE_HTML)
        mock_http = _make_mock_client(responses=[unavailable_resp])
        difficult_adapter = _make_adapter(mock_http=mock_http, max_retries=1)

        mock_fs_client = AsyncMock()
        mock_fs_client.fetch_products = AsyncMock(
            return_value=(
                [MagicMock(id=1, title="FS Item", price=10.0, category="cat")],
                [],
            )
        )
        fake_store = FakeStoreAdapter(client=mock_fs_client)

        producer = MockProducer()
        runner = IngestionRunner(
            adapters=[difficult_adapter, fake_store],
            producer=producer,  # type: ignore[arg-type]
            max_retries=1,
        )
        await runner.run_once()

        fake_store_events = [e for e in producer.published if e.source == "fake_store"]
        assert len(fake_store_events) >= 1

        difficult_events = [e for e in producer.published if e.source == "premium_retailer"]
        assert len(difficult_events) == 0

    @pytest.mark.asyncio
    async def test_no_source_specific_branching_in_processor(self) -> None:
        """Processor handles difficult-source events identically to other sources."""
        mock_http = _make_mock_client()
        adapter = _make_adapter(mock_http=mock_http)
        producer = MockProducer()

        runner = IngestionRunner(
            adapters=[adapter],
            producer=producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        sinks = _run_pipeline(producer.published)

        for event in sinks.validated_events:
            row = validated_event_to_row(event)
            assert "source" in row
            assert "external_id" in row
            assert "event_id" in row
            assert row["source"] == "premium_retailer"

    @pytest.mark.asyncio
    async def test_all_sources_through_processor(self) -> None:
        """Events from all sources pass through the processor without special-casing."""
        from libs.adapters.fake_store.adapter import FakeStoreAdapter

        mock_http = _make_mock_client()
        difficult_adapter = _make_adapter(mock_http=mock_http)

        mock_fs_client = AsyncMock()
        mock_fs_client.fetch_products = AsyncMock(
            return_value=(
                [MagicMock(id=1, title="FS Item", price=10.0, category="cat")],
                [],
            )
        )
        fake_store = FakeStoreAdapter(client=mock_fs_client)

        producer = MockProducer()
        runner = IngestionRunner(
            adapters=[difficult_adapter, fake_store],
            producer=producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        sinks = _run_pipeline(producer.published)
        assert len(sinks.validated_events) == len(producer.published)
        assert len(sinks.invalid_envelopes) == 0

        sources = {e.source for e in sinks.validated_events}
        assert "premium_retailer" in sources
        assert "fake_store" in sources
