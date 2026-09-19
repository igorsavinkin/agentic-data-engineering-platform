"""Retailer integration tests for TASK-050.

Verifies the web retailer observation flows through the complete pipeline:
fixture HTML → adapter → parser → pagination/retry → canonical event →
mock Kafka → processor → validated sink → bronze Parquet (mocked storage).

Coverage:
1. Single observation traceable through the full pipeline
2. Multiple pages aggregated correctly
3. Malformed records do not enter valid downstream data
4. Transient failure followed by retry/recovery
5. Partial pagination failure (TASK-048)
6. Replay/idempotency via DeduplicationState
7. Source-health metrics for healthy and degraded runs
8. Regression smoke for existing adapters alongside web_retailer
"""

from __future__ import annotations

import io
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import polars as pl
import pytest

from libs.adapters import SourceFetchError
from libs.adapters.web_retailer.adapter import WebRetailerAdapter
from libs.adapters.web_retailer.client import WebRetailerClient
from libs.common.kafka_consumer import ConsumerMessage
from libs.common.kafka_producer import DeliveryReceipt
from libs.common.minio_storage import MinIOStorage
from libs.event_contracts import ProductObservationEvent
from libs.lake_writer.silver_writer import SilverWriter, validated_event_to_row
from libs.observability.source_metrics import SourceMetrics
from libs.raw_writer import BronzeWriter
from services.ingestion.runner import IngestionRunner
from services.processor.deduplication import DeduplicationState
from services.processor.pipeline import ProcessorPipeline

# ---------------------------------------------------------------------------
# Deterministic HTML fixtures
# ---------------------------------------------------------------------------

PAGE_1_HTML = """\
<!DOCTYPE html>
<html>
<head><title>Books</title></head>
<body>
<ul class="breadcrumb">
  <li><a href="../index.html">Home</a></li>
  <li class="active">Travel</li>
</ul>
<article class="product_pod">
  <h3><a href="a-light-in-the-attic_1000/index.html" title="A Light in the Attic">A Light in the ...</a></h3>
  <div class="product_price">
    <p class="price_color">&pound;51.77</p>
    <p class="instock availability">In stock</p>
  </div>
</article>
<article class="product_pod">
  <h3><a href="tipping-the-velvet_999/index.html" title="Tipping the Velvet">Tipping the Velvet</a></h3>
  <div class="product_price">
    <p class="price_color">&pound;25.00</p>
    <p class="instock availability">In stock</p>
  </div>
</article>
<nav><ul class="pager">
  <li class="next"><a href="page-2.html">next</a></li>
</ul></nav>
</body>
</html>
"""

PAGE_2_HTML = """\
<!DOCTYPE html>
<html>
<head><title>Books - Page 2</title></head>
<body>
<ul class="breadcrumb">
  <li><a href="../index.html">Home</a></li>
  <li class="active">Travel</li>
</ul>
<article class="product_pod">
  <h3><a href="soumission_998/index.html" title="Soumission">Soumission</a></h3>
  <div class="product_price">
    <p class="price_color">&pound;50.14</p>
    <p class="availoffset availability">Out of stock</p>
  </div>
</article>
</body>
</html>
"""

MALFORMED_HTML = """\
<!DOCTYPE html>
<html>
<body>
<ul class="breadcrumb">
  <li><a href="../index.html">Home</a></li>
  <li class="active">Books</li>
</ul>
<article class="product_pod">
  <h3><a href="good-book_500/index.html" title="Good Book">Good Book</a></h3>
  <div class="product_price">
    <p class="price_color">&pound;15.00</p>
    <p class="instock availability">In stock</p>
  </div>
</article>
<article class="product_pod">
  <div class="product_price">
    <p class="price_color">&pound;20.00</p>
  </div>
</article>
</body>
</html>
"""

SINGLE_PAGE_HTML = """\
<!DOCTYPE html>
<html>
<body>
<ul class="breadcrumb">
  <li><a href="../index.html">Home</a></li>
  <li class="active">Books</li>
</ul>
<article class="product_pod">
  <h3><a href="solo-book_100/index.html" title="Solo Book">Solo Book</a></h3>
  <div class="product_price">
    <p class="price_color">&pound;30.00</p>
    <p class="instock availability">In stock</p>
  </div>
</article>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class MockProducer:
    """Test helper that tracks published events without real Kafka."""

    def __init__(self) -> None:
        self.published: list[ProductObservationEvent] = []
        self.metrics = MagicMock()
        self.metrics.increment = MagicMock()

    def publish(
        self,
        event: ProductObservationEvent,
        headers: list[tuple[str, bytes]] | None = None,
    ) -> DeliveryReceipt:
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


def _make_mock_client(
    pages: list[str] | None = None,
) -> AsyncMock:
    """Create a mock WebRetailerClient returning the given HTML pages."""
    client = AsyncMock(spec=WebRetailerClient)
    client.base_url = "http://books.toscrape.com"
    client.catalog_path = "/catalogue/category/books_1/index.html"
    if pages is not None:
        client.fetch_listing_page = AsyncMock(side_effect=pages)
    else:
        client.fetch_listing_page = AsyncMock(return_value=SINGLE_PAGE_HTML)
    client.close = AsyncMock()
    return client


def _make_adapter(
    client: AsyncMock | None = None,
    metrics: SourceMetrics | None = None,
    max_pages: int = 5,
) -> WebRetailerAdapter:
    if client is None:
        client = _make_mock_client()
    return WebRetailerAdapter(client=client, metrics=metrics, max_pages=max_pages)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_producer() -> MockProducer:
    return MockProducer()


@pytest.fixture
def mock_client() -> AsyncMock:
    return _make_mock_client()


@pytest.fixture
def adapter(mock_client: AsyncMock) -> WebRetailerAdapter:
    return _make_adapter(client=mock_client)


# ---------------------------------------------------------------------------
# Tests: Single observation traceable through the full pipeline
# ---------------------------------------------------------------------------


class TestFullPipelineTraceability:
    """Verify a retailer observation can be traced from HTML to validated output."""

    @pytest.mark.asyncio
    async def test_single_product_through_full_pipeline(self, mock_producer: MockProducer) -> None:
        """A single product traverses: HTML → adapter → Kafka → processor → validated."""
        client = _make_mock_client(pages=[SINGLE_PAGE_HTML])
        adapter = _make_adapter(client=client)

        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert len(mock_producer.published) == 1
        raw_event = mock_producer.published[0]
        assert raw_event.source == "web_retailer"
        assert raw_event.payload.external_id == "solo-book_100"
        assert raw_event.payload.name == "Solo Book"
        assert raw_event.payload.price == Decimal("30.00")
        assert raw_event.payload.currency == "GBP"
        assert raw_event.payload.availability == "in_stock"

        sinks = TrackingSinks()
        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
            dedup_state=DeduplicationState(),
        )
        msg = _wrap_as_consumer_message(raw_event, offset=0)
        result = pipeline.process_batch([msg])

        assert result.published_valid == 1
        validated = sinks.validated_events[0]
        assert validated.event_id == raw_event.event_id
        assert validated.payload.external_id == "solo-book_100"
        assert validated.source == "web_retailer"

    @pytest.mark.asyncio
    async def test_traceability_across_layers(self, mock_producer: MockProducer) -> None:
        """Same event_id and external_id survive from raw through validated."""
        client = _make_mock_client(pages=[SINGLE_PAGE_HTML])
        adapter = _make_adapter(client=client)

        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        raw_event = mock_producer.published[0]

        sinks = TrackingSinks()
        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
            dedup_state=DeduplicationState(),
        )
        msg = _wrap_as_consumer_message(raw_event, offset=0)
        result = pipeline.process_batch([msg])

        assert result.published_valid == 1
        validated = sinks.validated_events[0]
        assert validated.event_id == raw_event.event_id
        assert validated.payload.external_id == raw_event.payload.external_id
        assert validated.source == raw_event.source == "web_retailer"


# ---------------------------------------------------------------------------
# Tests: Multiple pages aggregated correctly
# ---------------------------------------------------------------------------


class TestMultiPageAggregation:
    """Verify multi-page pagination aggregates events correctly."""

    @pytest.mark.asyncio
    async def test_two_pages_aggregated(self, mock_producer: MockProducer) -> None:
        """Events from two pages are all published and processable."""
        client = _make_mock_client(pages=[PAGE_1_HTML, PAGE_2_HTML])
        adapter = _make_adapter(client=client)

        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert len(mock_producer.published) == 3
        external_ids = {e.payload.external_id for e in mock_producer.published}
        assert external_ids == {
            "a-light-in-the-attic_1000",
            "tipping-the-velvet_999",
            "soumission_998",
        }

        sinks = TrackingSinks()
        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
            dedup_state=DeduplicationState(),
        )
        messages = [
            _wrap_as_consumer_message(e, offset=i) for i, e in enumerate(mock_producer.published)
        ]
        result = pipeline.process_batch(messages)

        assert result.published_valid == 3
        validated_ids = {e.payload.external_id for e in sinks.validated_events}
        assert validated_ids == external_ids

    @pytest.mark.asyncio
    async def test_multi_page_preserves_prices(self, mock_producer: MockProducer) -> None:
        """Prices from different pages are preserved correctly."""
        client = _make_mock_client(pages=[PAGE_1_HTML, PAGE_2_HTML])
        adapter = _make_adapter(client=client)

        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        prices = {e.payload.external_id: e.payload.price for e in mock_producer.published}
        assert prices["a-light-in-the-attic_1000"] == Decimal("51.77")
        assert prices["tipping-the-velvet_999"] == Decimal("25.00")
        assert prices["soumission_998"] == Decimal("50.14")

    @pytest.mark.asyncio
    async def test_multi_page_availability_variety(self, mock_producer: MockProducer) -> None:
        """Availability values from different pages are correctly mapped."""
        client = _make_mock_client(pages=[PAGE_1_HTML, PAGE_2_HTML])
        adapter = _make_adapter(client=client)

        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        availability = {
            e.payload.external_id: e.payload.availability for e in mock_producer.published
        }
        assert availability["a-light-in-the-attic_1000"] == "in_stock"
        assert availability["soumission_998"] == "out_of_stock"


# ---------------------------------------------------------------------------
# Tests: Malformed records do not enter valid downstream data
# ---------------------------------------------------------------------------


class TestMalformedInput:
    """Verify malformed/unparseable records are excluded from valid output."""

    @pytest.mark.asyncio
    async def test_malformed_excluded_from_valid(self, mock_producer: MockProducer) -> None:
        """Malformed HTML articles produce no valid events."""
        client = _make_mock_client(pages=[MALFORMED_HTML])
        adapter = _make_adapter(client=client)

        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert len(mock_producer.published) == 1
        assert mock_producer.published[0].payload.external_id == "good-book_500"
        assert runner.stats.total_malformed == 1

    @pytest.mark.asyncio
    async def test_malformed_do_not_reach_processor(self, mock_producer: MockProducer) -> None:
        """Only valid events reach the processor pipeline."""
        client = _make_mock_client(pages=[MALFORMED_HTML])
        adapter = _make_adapter(client=client)

        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        sinks = TrackingSinks()
        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
            dedup_state=DeduplicationState(),
        )
        messages = [
            _wrap_as_consumer_message(e, offset=i) for i, e in enumerate(mock_producer.published)
        ]
        result = pipeline.process_batch(messages)

        assert result.published_valid == 1
        assert result.published_invalid == 0
        assert len(sinks.invalid_envelopes) == 0

    @pytest.mark.asyncio
    async def test_malformed_tracked_in_stats(self, mock_producer: MockProducer) -> None:
        """Malformed count is tracked in ingestion stats."""
        client = _make_mock_client(pages=[MALFORMED_HTML])
        adapter = _make_adapter(client=client)

        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert runner.stats.total_malformed == 1
        status = runner.stats.sources["web_retailer"]
        assert status.malformed_count == 1


# ---------------------------------------------------------------------------
# Tests: Transient failure followed by retry/recovery
# ---------------------------------------------------------------------------


class TestTransientFailureAndRetry:
    """Verify transient failures and recovery behavior."""

    @pytest.mark.asyncio
    async def test_first_page_failure_raises(self, mock_producer: MockProducer) -> None:
        """First-page failure raises SourceFetchError, no events published."""
        client = AsyncMock(spec=WebRetailerClient)
        client.base_url = "http://books.toscrape.com"
        client.catalog_path = "/catalogue/category/books_1/index.html"
        client.fetch_listing_page = AsyncMock(
            side_effect=SourceFetchError("Connection refused", source="web_retailer")
        )
        client.close = AsyncMock()
        adapter = _make_adapter(client=client)

        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
            max_retries=1,
        )
        await runner.run_once()

        assert len(mock_producer.published) == 0
        assert runner.stats.total_errors > 0

    @pytest.mark.asyncio
    async def test_recovery_after_failure(self, mock_producer: MockProducer) -> None:
        """Adapter recovers in a subsequent cycle after a failure."""
        client = AsyncMock(spec=WebRetailerClient)
        client.base_url = "http://books.toscrape.com"
        client.catalog_path = "/catalogue/category/books_1/index.html"
        client.close = AsyncMock()

        client.fetch_listing_page = AsyncMock(
            side_effect=SourceFetchError("Timeout", source="web_retailer")
        )
        adapter = _make_adapter(client=client)

        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
            max_retries=1,
        )
        await runner.run_once()
        assert len(mock_producer.published) == 0

        client.fetch_listing_page = AsyncMock(return_value=SINGLE_PAGE_HTML)
        await runner.run_once()
        assert len(mock_producer.published) == 1
        assert mock_producer.published[0].source == "web_retailer"


# ---------------------------------------------------------------------------
# Tests: Partial pagination failure (TASK-048)
# ---------------------------------------------------------------------------


class TestPartialPaginationFailure:
    """Verify partial pagination failure returns collected pages."""

    @pytest.mark.asyncio
    async def test_partial_failure_returns_collected_pages(
        self, mock_producer: MockProducer
    ) -> None:
        """Page 2 fails after page 1 succeeds — page 1 events are preserved."""
        client = AsyncMock(spec=WebRetailerClient)
        client.base_url = "http://books.toscrape.com"
        client.catalog_path = "/catalogue/category/books_1/index.html"
        client.close = AsyncMock()
        client.fetch_listing_page = AsyncMock(
            side_effect=[PAGE_1_HTML, SourceFetchError("Timeout", source="web_retailer")]
        )
        adapter = _make_adapter(client=client)

        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert len(mock_producer.published) == 2
        external_ids = {e.payload.external_id for e in mock_producer.published}
        assert external_ids == {"a-light-in-the-attic_1000", "tipping-the-velvet_999"}

    @pytest.mark.asyncio
    async def test_partial_failure_events_process_correctly(
        self, mock_producer: MockProducer
    ) -> None:
        """Partial-failure events flow through the processor correctly."""
        client = AsyncMock(spec=WebRetailerClient)
        client.base_url = "http://books.toscrape.com"
        client.catalog_path = "/catalogue/category/books_1/index.html"
        client.close = AsyncMock()
        client.fetch_listing_page = AsyncMock(
            side_effect=[PAGE_1_HTML, SourceFetchError("Timeout", source="web_retailer")]
        )
        adapter = _make_adapter(client=client)

        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        sinks = TrackingSinks()
        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
            dedup_state=DeduplicationState(),
        )
        messages = [
            _wrap_as_consumer_message(e, offset=i) for i, e in enumerate(mock_producer.published)
        ]
        result = pipeline.process_batch(messages)

        assert result.published_valid == 2
        assert result.published_invalid == 0


# ---------------------------------------------------------------------------
# Tests: Replay/idempotency
# ---------------------------------------------------------------------------


class TestReplayIdempotency:
    """Verify replaying the same observation does not create duplicates."""

    @pytest.mark.asyncio
    async def test_same_input_produces_same_external_ids(self, mock_producer: MockProducer) -> None:
        """Two fetch cycles with same data produce same external_ids."""
        client = _make_mock_client(pages=[SINGLE_PAGE_HTML])
        adapter = _make_adapter(client=client)

        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()
        first_ids = {e.payload.external_id for e in mock_producer.published}

        mock_producer.published.clear()
        client.fetch_listing_page = AsyncMock(return_value=SINGLE_PAGE_HTML)
        await runner.run_once()
        second_ids = {e.payload.external_id for e in mock_producer.published}

        assert first_ids == second_ids

    @pytest.mark.asyncio
    async def test_deduplication_via_processor(self, mock_producer: MockProducer) -> None:
        """Same event_id replayed through processor is deduplicated."""
        client = _make_mock_client(pages=[SINGLE_PAGE_HTML])
        adapter = _make_adapter(client=client)

        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        original_event = mock_producer.published[0]

        sinks = TrackingSinks()
        shared_dedup = DeduplicationState()
        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
            dedup_state=shared_dedup,
        )

        msg1 = _wrap_as_consumer_message(original_event, offset=0)
        result1 = pipeline.process_batch([msg1])
        assert result1.published_valid == 1
        assert result1.duplicates_skipped == 0

        msg2 = _wrap_as_consumer_message(original_event, offset=1)
        result2 = pipeline.process_batch([msg2])
        assert result2.published_valid == 0
        assert result2.duplicates_skipped == 1

        assert len(sinks.validated_events) == 1


# ---------------------------------------------------------------------------
# Tests: Source-health metrics
# ---------------------------------------------------------------------------


class TestSourceHealthMetrics:
    """Verify source-health metrics for healthy and degraded runs."""

    @pytest.mark.asyncio
    async def test_healthy_run_metrics(self, mock_producer: MockProducer) -> None:
        """A healthy run records correct metrics."""
        metrics = SourceMetrics(source_name="web_retailer")
        client = _make_mock_client(pages=[PAGE_1_HTML, PAGE_2_HTML])
        adapter = _make_adapter(client=client, metrics=metrics)

        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert metrics.get_last_successful_fetch() is not None
        age = metrics.get_freshness_age_seconds()
        assert age is not None
        assert age >= 0

    @pytest.mark.asyncio
    async def test_degraded_run_metrics(self, mock_producer: MockProducer) -> None:
        """A degraded run (malformed + partial failure) records metrics."""
        metrics = SourceMetrics(source_name="web_retailer")
        client = AsyncMock(spec=WebRetailerClient)
        client.base_url = "http://books.toscrape.com"
        client.catalog_path = "/catalogue/category/books_1/index.html"
        client.close = AsyncMock()
        client.fetch_listing_page = AsyncMock(
            side_effect=[
                MALFORMED_HTML,
                SourceFetchError("Timeout", source="web_retailer"),
            ]
        )
        adapter = _make_adapter(client=client, metrics=metrics)

        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert metrics.get_last_successful_fetch() is not None
        assert len(mock_producer.published) == 1

    @pytest.mark.asyncio
    async def test_failed_run_no_freshness_update(self, mock_producer: MockProducer) -> None:
        """A complete failure does not update freshness."""
        metrics = SourceMetrics(source_name="web_retailer")
        client = AsyncMock(spec=WebRetailerClient)
        client.base_url = "http://books.toscrape.com"
        client.catalog_path = "/catalogue/category/books_1/index.html"
        client.close = AsyncMock()
        client.fetch_listing_page = AsyncMock(
            side_effect=SourceFetchError("Connection refused", source="web_retailer")
        )
        adapter = _make_adapter(client=client, metrics=metrics)

        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
            max_retries=1,
        )
        await runner.run_once()

        assert metrics.get_last_successful_fetch() is None
        assert metrics.get_freshness_age_seconds() is None

    @pytest.mark.asyncio
    async def test_runner_exposes_freshness(self, mock_producer: MockProducer) -> None:
        """IngestionRunner.get_source_freshness() returns correct data."""
        metrics = SourceMetrics(source_name="web_retailer")
        client = _make_mock_client(pages=[SINGLE_PAGE_HTML])
        adapter = _make_adapter(client=client, metrics=metrics)

        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        freshness = runner.get_source_freshness()
        assert "web_retailer" in freshness
        assert freshness["web_retailer"]["last_successful_fetch"] is not None
        age = freshness["web_retailer"]["freshness_age_seconds"]
        assert age is not None
        assert age >= 0


# ---------------------------------------------------------------------------
# Tests: Bronze Parquet layer (mocked storage)
# ---------------------------------------------------------------------------


class TestBronzeParquetLayer:
    """Verify retailer events can be persisted to Bronze Parquet."""

    @pytest.mark.asyncio
    async def test_retailer_event_to_bronze_parquet(self, mock_producer: MockProducer) -> None:
        """A retailer event round-trips through Bronze Parquet."""
        client = _make_mock_client(pages=[SINGLE_PAGE_HTML])
        adapter = _make_adapter(client=client)

        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        event = mock_producer.published[0]

        mock_storage = MagicMock(spec=MinIOStorage)
        mock_storage.put_object = MagicMock()
        mock_storage.get_object = MagicMock(return_value=b"")

        writer = BronzeWriter(storage=mock_storage, bucket="test-bronze", batch_size=10)
        writer.add_event(event)
        writer.flush_batch()

        mock_storage.put_object.assert_called_once()
        call_args = mock_storage.put_object.call_args
        assert call_args[0][0] == "test-bronze"
        key = call_args[0][1]
        assert key.startswith("bronze/")
        assert "source=web_retailer" in key
        assert "solo-book_100" in key

        parquet_bytes = call_args[0][2]
        df = pl.read_parquet(io.BytesIO(parquet_bytes))
        assert df.height == 1
        row = df.row(0, named=True)
        assert row["event_id"] == event.event_id
        assert row["source"] == "web_retailer"
        assert row["external_id"] == "solo-book_100"
        assert row["price"] == "30.00"

    @pytest.mark.asyncio
    async def test_multi_page_bronze_parquet(self, mock_producer: MockProducer) -> None:
        """Multi-page events each produce separate Bronze Parquet files."""
        client = _make_mock_client(pages=[PAGE_1_HTML, PAGE_2_HTML])
        adapter = _make_adapter(client=client)

        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        mock_storage = MagicMock(spec=MinIOStorage)
        mock_storage.put_object = MagicMock()

        writer = BronzeWriter(storage=mock_storage, bucket="test-bronze", batch_size=10)
        for event in mock_producer.published:
            writer.add_event(event)
        writer.flush_batch()

        assert mock_storage.put_object.call_count == 3


# ---------------------------------------------------------------------------
# Tests: Silver Parquet layer (mocked storage)
# ---------------------------------------------------------------------------


class TestSilverParquetLayer:
    """Verify validated retailer events can be persisted to Silver Parquet."""

    @pytest.mark.asyncio
    async def test_validated_event_to_silver_parquet(self, mock_producer: MockProducer) -> None:
        """A validated retailer event round-trips through Silver Parquet."""
        client = _make_mock_client(pages=[SINGLE_PAGE_HTML])
        adapter = _make_adapter(client=client)

        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        raw_event = mock_producer.published[0]

        sinks = TrackingSinks()
        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
            dedup_state=DeduplicationState(),
        )
        msg = _wrap_as_consumer_message(raw_event, offset=0)
        pipeline.process_batch([msg])

        validated_event = sinks.validated_events[0]
        row = validated_event_to_row(validated_event)

        assert row["event_id"] == validated_event.event_id
        assert row["source"] == "web_retailer"
        assert row["external_id"] == "solo-book_100"

        mock_storage = MagicMock(spec=MinIOStorage)
        mock_storage.put_object = MagicMock()

        writer = SilverWriter(storage=mock_storage, bucket="test-silver", batch_size=10)
        writer.add_event(validated_event)
        writer.flush_batch()

        mock_storage.put_object.assert_called_once()
        call_args = mock_storage.put_object.call_args
        key = call_args[0][1]
        assert key.startswith("silver/")
        assert "source=web_retailer" in key


# ---------------------------------------------------------------------------
# Tests: Regression smoke — all sources together
# ---------------------------------------------------------------------------


class TestRegressionSmoke:
    """Smoke tests ensuring web_retailer coexists with existing adapters."""

    @pytest.mark.asyncio
    async def test_all_sources_in_one_cycle(self, mock_producer: MockProducer) -> None:
        """All four sources publish events in a single ingestion cycle."""
        from libs.adapters.best_buy.adapter import BestBuyAdapter
        from libs.adapters.best_buy.models import BestBuyProduct
        from libs.adapters.ebay.adapter import EbayAdapter
        from libs.adapters.ebay.models import (
            EbayAvailability,
            EbayListingSummary,
            EbayPrice,
            EbaySearchResponse,
            EbaySeller,
        )
        from libs.adapters.fake_store.adapter import FakeStoreAdapter

        wr_client = _make_mock_client(pages=[SINGLE_PAGE_HTML])
        web_retailer = _make_adapter(client=wr_client)

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
        best_buy = BestBuyAdapter(api_key="test", client=mock_bb_client)

        mock_ebay_client = AsyncMock()
        ebay_listing = EbayListingSummary(
            item_id="E1",
            title="eBay Item",
            price=EbayPrice(value=15.0, currency="USD"),
            seller=EbaySeller(username="seller1", feedback_score=100, feedback_percentage=98.0),
            availability=EbayAvailability(ship_to_location_availability=[{"quantity": 1}]),
            category_ids=["12345"],
            item_web_url=None,
        )
        mock_ebay_client.search_items = AsyncMock(
            return_value=(EbaySearchResponse(total=1, item_summaries=[ebay_listing]), [])
        )
        ebay = EbayAdapter(query="test", client=mock_ebay_client)

        runner = IngestionRunner(
            adapters=[fake_store, best_buy, ebay, web_retailer],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert len(mock_producer.published) == 4
        sources = {e.source for e in mock_producer.published}
        assert sources == {"fake_store", "best_buy", "ebay", "web_retailer"}

    @pytest.mark.asyncio
    async def test_web_retailer_failure_does_not_block_others(
        self, mock_producer: MockProducer
    ) -> None:
        """Web retailer failure does not prevent other adapters from publishing."""
        from libs.adapters.fake_store.adapter import FakeStoreAdapter

        wr_client = AsyncMock(spec=WebRetailerClient)
        wr_client.base_url = "http://books.toscrape.com"
        wr_client.catalog_path = "/catalogue/category/books_1/index.html"
        wr_client.close = AsyncMock()
        wr_client.fetch_listing_page = AsyncMock(
            side_effect=SourceFetchError("Timeout", source="web_retailer")
        )
        web_retailer = _make_adapter(client=wr_client)

        mock_fs_client = AsyncMock()
        mock_fs_client.fetch_products = AsyncMock(
            return_value=(
                [MagicMock(id=1, title="FS Item", price=10.0, category="cat")],
                [],
            )
        )
        fake_store = FakeStoreAdapter(client=mock_fs_client)

        runner = IngestionRunner(
            adapters=[web_retailer, fake_store],
            producer=mock_producer,  # type: ignore[arg-type]
            max_retries=1,
        )
        await runner.run_once()

        assert len(mock_producer.published) == 1
        assert mock_producer.published[0].source == "fake_store"

    @pytest.mark.asyncio
    async def test_web_retailer_canonical_contract(self, mock_producer: MockProducer) -> None:
        """Web retailer events conform to the canonical contract."""
        client = _make_mock_client(pages=[SINGLE_PAGE_HTML])
        adapter = _make_adapter(client=client)

        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        event = mock_producer.published[0]
        payload_dict = event.payload.model_dump()
        canonical_keys = {
            "external_id",
            "name",
            "url",
            "price",
            "currency",
            "availability",
            "category",
            "collected_at",
            "listing_id",
            "seller_id",
        }
        assert set(payload_dict.keys()) == canonical_keys

        assert event.partition_key.startswith("web_retailer:")
