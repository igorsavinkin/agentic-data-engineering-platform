"""eBay integration tests for TASK-045.

Verifies that eBay listings flow through the complete ingestion pipeline:
adapter -> canonical event -> mock Kafka producer -> processor pipeline.
Covers multiple sellers, marketplace identity (listing_id/seller_id),
replay determinism with deduplication, malformed input, error isolation,
ambiguity, and regression smoke tests alongside existing sources.

NOTE: The eBay Browse API item_summary/search endpoint does not expose
product-level identifiers (UPC/GTIN/EAN/ASIN), so end-to-end product
grouping is not testable at this layer.  The marketplace identity
primitives for product grouping exist in libs.marketplace.identity and
are tested in TASK-044.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from libs.adapters import SourceFetchError
from libs.adapters.ebay.adapter import EbayAdapter
from libs.adapters.ebay.models import (
    EbayAvailability,
    EbayListingSummary,
    EbayPrice,
    EbaySearchResponse,
    EbaySeller,
)
from libs.common.kafka_consumer import ConsumerMessage
from libs.common.kafka_producer import DeliveryReceipt
from libs.event_contracts import ProductObservationEvent
from services.ingestion.runner import IngestionRunner
from services.processor.deduplication import DeduplicationState
from services.processor.pipeline import ProcessorPipeline

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_UNSET: object = object()


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


def _make_listing(
    item_id: str,
    title: str,
    price_value: float | None = 29.99,
    currency: str = "USD",
    seller_username: str | None = "seller1",
    feedback_score: int | None = 100,
    feedback_pct: float | None = 98.5,
    in_stock: bool = True,
    category_ids: list[str] | None | object = _UNSET,
    item_web_url: str | None = None,
) -> EbayListingSummary:
    """Build a deterministic EbayListingSummary for testing."""
    seller = None
    if seller_username is not None:
        seller = EbaySeller(
            username=seller_username,
            feedback_score=feedback_score,
            feedback_percentage=feedback_pct,
        )
    price = None
    if price_value is not None:
        price = EbayPrice(value=price_value, currency=currency)
    availability = None
    if in_stock:
        availability = EbayAvailability(
            ship_to_location_availability=[{"quantity": 1}],
        )
    else:
        availability = EbayAvailability()
    if category_ids is _UNSET:
        resolved_categories: list[str] | None = ["12345"]
    else:
        resolved_categories = category_ids  # type: ignore[assignment]
    return EbayListingSummary(
        item_id=item_id,
        title=title,
        price=price,
        seller=seller,
        availability=availability,
        category_ids=resolved_categories,
        item_web_url=item_web_url,
    )


def _make_search_response(
    listings: list[EbayListingSummary],
    total: int | None = None,
) -> EbaySearchResponse:
    """Wrap listings into an EbaySearchResponse."""
    return EbaySearchResponse(total=total or len(listings), item_summaries=listings)


def _wrap_as_consumer_message(event: ProductObservationEvent, offset: int = 0) -> ConsumerMessage:
    """Wrap an event in a ConsumerMessage for processor input."""
    return ConsumerMessage(
        event=event,
        topic="products.raw.v1",
        partition=0,
        offset=offset,
        raw_value=None,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_producer() -> MockProducer:
    return MockProducer()


@pytest.fixture
def mock_ebay_client() -> AsyncMock:
    client = AsyncMock()
    client.search_items = AsyncMock(
        return_value=(_make_search_response([]), []),
    )
    return client


@pytest.fixture
def ebay_adapter(mock_ebay_client: AsyncMock) -> EbayAdapter:
    return EbayAdapter(
        query="test query",
        category_ids=["12345"],
        limit=10,
        client=mock_ebay_client,
    )


# ---------------------------------------------------------------------------
# Tests: Basic eBay ingestion
# ---------------------------------------------------------------------------


class TestEbayIngestion:
    """Verify eBay listings flow through ingestion to the mock producer."""

    @pytest.mark.asyncio
    async def test_single_listing_published(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """A single eBay listing produces one canonical event."""
        listing = _make_listing("11111", "Test Widget")
        mock_ebay_client.search_items.return_value = (
            _make_search_response([listing]),
            [],
        )

        runner = IngestionRunner(
            adapters=[ebay_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert len(mock_producer.published) == 1
        event = mock_producer.published[0]
        assert event.source == "ebay"
        assert event.payload.external_id == "11111"
        assert event.payload.name == "Test Widget"
        assert event.payload.price is not None
        assert event.payload.currency == "USD"

    @pytest.mark.asyncio
    async def test_multiple_listings_from_different_sellers(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """Multiple listings from different sellers all produce events."""
        listings = [
            _make_listing("L1", "Product A", seller_username="seller_alpha"),
            _make_listing("L2", "Product B", seller_username="seller_beta"),
            _make_listing("L3", "Product C", seller_username="seller_gamma"),
        ]
        mock_ebay_client.search_items.return_value = (
            _make_search_response(listings),
            [],
        )

        runner = IngestionRunner(
            adapters=[ebay_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert len(mock_producer.published) == 3
        external_ids = {e.payload.external_id for e in mock_producer.published}
        assert external_ids == {"L1", "L2", "L3"}
        for event in mock_producer.published:
            assert event.source == "ebay"

    @pytest.mark.asyncio
    async def test_partition_key_format(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """Events use the expected partition key format."""
        mock_ebay_client.search_items.return_value = (
            _make_search_response([_make_listing("ITEM42", "Gadget")]),
            [],
        )

        runner = IngestionRunner(
            adapters=[ebay_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        event = mock_producer.published[0]
        assert event.partition_key.startswith("ebay:")
        assert "ITEM42" in event.partition_key


# ---------------------------------------------------------------------------
# Tests: Marketplace identity — listing_id and seller_id
# ---------------------------------------------------------------------------


class TestMarketplaceIdentity:
    """Verify listing_id and seller_id are populated for eBay listings."""

    @pytest.mark.asyncio
    async def test_listing_id_populated(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """listing_id is set to 'ebay:<item_id>' for each listing."""
        listing = _make_listing("MKID1", "Identity Check")
        mock_ebay_client.search_items.return_value = (
            _make_search_response([listing]),
            [],
        )

        runner = IngestionRunner(
            adapters=[ebay_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        event = mock_producer.published[0]
        assert event.payload.listing_id == "ebay:MKID1"

    @pytest.mark.asyncio
    async def test_seller_id_populated(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """seller_id is set to 'ebay:<username>' when seller is present."""
        listing = _make_listing("SEL1", "Seller Check", seller_username="top_seller")
        mock_ebay_client.search_items.return_value = (
            _make_search_response([listing]),
            [],
        )

        runner = IngestionRunner(
            adapters=[ebay_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        event = mock_producer.published[0]
        assert event.payload.seller_id == "ebay:top_seller"

    @pytest.mark.asyncio
    async def test_seller_id_null_when_no_seller(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """seller_id is None when the listing has no seller info."""
        listing = _make_listing("NOSLR", "No Seller", seller_username=None)
        mock_ebay_client.search_items.return_value = (
            _make_search_response([listing]),
            [],
        )

        runner = IngestionRunner(
            adapters=[ebay_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        event = mock_producer.published[0]
        assert event.payload.seller_id is None
        assert event.payload.listing_id == "ebay:NOSLR"


# ---------------------------------------------------------------------------
# Tests: Multiple listings from different sellers (Milestone 5A prerequisite)
# ---------------------------------------------------------------------------


class TestMultipleListingsSameProduct:
    """Verify multiple eBay listings flow through the pipeline without breaking.

    NOTE: The eBay Browse API ``item_summary/search`` endpoint does not expose
    product-level identifiers (UPC, GTIN, EAN, ASIN).  Therefore, end-to-end
    grouping of multiple listings into one logical product is not possible
    with the current data source.  The marketplace identity primitives
    (``ListingProductMapper``, ``derive_product_key_from_listing``) exist in
    ``libs.marketplace.identity`` and are tested in TASK-044 — they will
    activate when a richer data source provides product identifiers.

    These tests verify that multiple listings from different sellers coexist
    in the canonical pipeline with distinct ``listing_id``/``seller_id``,
    which is the prerequisite for future product-level grouping.
    """

    @pytest.mark.asyncio
    async def test_two_sellers_similar_listings(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """Two listings with the same title from different sellers produce
        distinct events with separate listing_id/seller_id.  The eBay
        item_summary endpoint does not expose product identifiers (UPC/GTIN),
        so these listings share only a title — they remain separate items
        in the canonical pipeline."""
        listings = [
            _make_listing(
                "SAMEPROD-A",
                "Wireless Mouse",
                price_value=19.99,
                seller_username="seller_alice",
            ),
            _make_listing(
                "SAMEPROD-B",
                "Wireless Mouse",
                price_value=24.99,
                seller_username="seller_bob",
            ),
        ]
        mock_ebay_client.search_items.return_value = (
            _make_search_response(listings),
            [],
        )

        runner = IngestionRunner(
            adapters=[ebay_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert len(mock_producer.published) == 2

        event_a, event_b = mock_producer.published

        assert event_a.payload.listing_id == "ebay:SAMEPROD-A"
        assert event_b.payload.listing_id == "ebay:SAMEPROD-B"
        assert event_a.payload.seller_id == "ebay:seller_alice"
        assert event_b.payload.seller_id == "ebay:seller_bob"

        assert event_a.payload.name == event_b.payload.name == "Wireless Mouse"
        assert event_a.payload.listing_id != event_b.payload.listing_id
        assert event_a.payload.seller_id != event_b.payload.seller_id

    @pytest.mark.asyncio
    async def test_same_product_listings_survive_pipeline(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """Multiple listings for the same product all pass through the
        processor pipeline as separate validated events."""
        listings = [
            _make_listing("MP1", "USB Cable", price_value=5.99, seller_username="shop_a"),
            _make_listing("MP2", "USB Cable", price_value=7.49, seller_username="shop_b"),
            _make_listing("MP3", "USB Cable", price_value=6.25, seller_username="shop_c"),
        ]
        mock_ebay_client.search_items.return_value = (
            _make_search_response(listings),
            [],
        )

        runner = IngestionRunner(
            adapters=[ebay_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        raw_events = mock_producer.published
        assert len(raw_events) == 3

        sinks = TrackingSinks()
        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
            dedup_state=DeduplicationState(),
        )
        messages = [
            _wrap_as_consumer_message(event, offset=i) for i, event in enumerate(raw_events)
        ]
        result = pipeline.process_batch(messages)

        assert result.published_valid == 3
        listing_ids = {e.payload.listing_id for e in sinks.validated_events}
        assert listing_ids == {"ebay:MP1", "ebay:MP2", "ebay:MP3"}
        seller_ids = {e.payload.seller_id for e in sinks.validated_events}
        assert seller_ids == {"ebay:shop_a", "ebay:shop_b", "ebay:shop_c"}

    @pytest.mark.asyncio
    async def test_listings_without_product_id_remain_distinct(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """eBay item_summary listings lack product identifiers (UPC/GTIN),
        so two listings for the same-titled item from different sellers
        remain distinct in the pipeline.  Product-level grouping requires
        a richer data source and is deferred (see class docstring)."""
        listings = [
            _make_listing(
                "DIST-A", "Bluetooth Speaker", price_value=29.99, seller_username="audio_shop"
            ),
            _make_listing(
                "DIST-B", "Bluetooth Speaker", price_value=34.50, seller_username="sound_store"
            ),
        ]
        mock_ebay_client.search_items.return_value = (
            _make_search_response(listings),
            [],
        )

        runner = IngestionRunner(
            adapters=[ebay_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert len(mock_producer.published) == 2
        event_a, event_b = mock_producer.published

        assert event_a.payload.listing_id == "ebay:DIST-A"
        assert event_b.payload.listing_id == "ebay:DIST-B"
        assert event_a.payload.seller_id == "ebay:audio_shop"
        assert event_b.payload.seller_id == "ebay:sound_store"
        assert event_a.payload.external_id != event_b.payload.external_id

    @pytest.mark.asyncio
    async def test_whitespace_only_seller_username_produces_null_seller_id(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """A whitespace-only seller username yields seller_id=None, matching
        the normalizer's strip-and-reject behavior."""
        listing = _make_listing("WS1", "Whitespace Seller", seller_username="   ")
        mock_ebay_client.search_items.return_value = (
            _make_search_response([listing]),
            [],
        )

        runner = IngestionRunner(
            adapters=[ebay_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert len(mock_producer.published) == 1
        event = mock_producer.published[0]
        assert event.payload.seller_id is None
        assert event.payload.listing_id == "ebay:WS1"


# ---------------------------------------------------------------------------
# Tests: Processor pipeline — final stored state
# ---------------------------------------------------------------------------


class TestProcessorPipeline:
    """Verify eBay events flow through the processor pipeline to validated output."""

    @pytest.mark.asyncio
    async def test_ebay_through_full_pipeline(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """eBay event flows: adapter -> Kafka -> processor -> validated sink."""
        listing = _make_listing("PP1", "Pipeline Widget", seller_username="pipe_seller")
        mock_ebay_client.search_items.return_value = (
            _make_search_response([listing]),
            [],
        )

        runner = IngestionRunner(
            adapters=[ebay_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        raw_event = mock_producer.published[0]
        assert raw_event.source == "ebay"
        assert raw_event.payload.external_id == "PP1"

        sinks = TrackingSinks()
        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
            dedup_state=DeduplicationState(),
        )
        msg = _wrap_as_consumer_message(raw_event, offset=0)
        result = pipeline.process_batch([msg])

        assert result.published_valid == 1
        assert len(sinks.validated_events) == 1
        validated = sinks.validated_events[0]
        assert validated.source == "ebay"
        assert validated.payload.external_id == "PP1"
        assert validated.payload.listing_id == "ebay:PP1"
        assert validated.payload.seller_id == "ebay:pipe_seller"
        assert validated.event_id == raw_event.event_id

    @pytest.mark.asyncio
    async def test_ebay_traceability_across_layers(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """Same event_id and external_id survive from raw through validated."""
        listing = _make_listing("TRACE1", "Traceable eBay Item", seller_username="trace_seller")
        mock_ebay_client.search_items.return_value = (
            _make_search_response([listing]),
            [],
        )

        runner = IngestionRunner(
            adapters=[ebay_adapter],
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
        assert validated.payload.external_id == raw_event.payload.external_id == "TRACE1"
        assert validated.source == raw_event.source == "ebay"
        assert validated.payload.listing_id == raw_event.payload.listing_id == "ebay:TRACE1"


# ---------------------------------------------------------------------------
# Tests: Replay idempotency with deduplication
# ---------------------------------------------------------------------------


class TestReplayIdempotency:
    """Verify replay determinism and deduplication via ProcessorPipeline.

    NOTE: ``event_id`` is derived from ``collected_at = datetime.now(utc)``
    per fetch cycle, so two real fetch cycles of the same listing produce
    *different* ``event_id`` values and are NOT deduplicated.  This is by
    design: each observation is a distinct temporal event.  The dedup test
    below demonstrates that replaying the *same* Kafka message (same
    ``event_id``) is correctly handled by ``DeduplicationState``.
    Cross-cycle deduplication would require a separate identity layer
    (e.g. warehouse ``UNIQUE(source, external_id)`` constraint).
    """

    @pytest.mark.asyncio
    async def test_same_input_produces_same_external_ids(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """Two fetch cycles with the same data produce events with same IDs."""
        listings = [
            _make_listing("R1", "Replay Product", price_value=15.00),
            _make_listing("R2", "Another Product", price_value=25.00),
        ]
        mock_ebay_client.search_items.return_value = (
            _make_search_response(listings),
            [],
        )

        runner = IngestionRunner(
            adapters=[ebay_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )

        await runner.run_once()
        first_run_ids = {e.payload.external_id for e in mock_producer.published}
        first_run_sources = {e.source for e in mock_producer.published}

        mock_producer.published.clear()
        mock_ebay_client.search_items.return_value = (
            _make_search_response(listings),
            [],
        )
        await runner.run_once()
        second_run_ids = {e.payload.external_id for e in mock_producer.published}
        second_run_sources = {e.source for e in mock_producer.published}

        assert first_run_ids == second_run_ids
        assert first_run_sources == second_run_sources

    @pytest.mark.asyncio
    async def test_same_input_produces_same_prices(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """Replayed listings preserve price and currency deterministically."""
        listing = _make_listing("P1", "Price Check", price_value=42.50, currency="EUR")
        mock_ebay_client.search_items.return_value = (
            _make_search_response([listing]),
            [],
        )

        runner = IngestionRunner(
            adapters=[ebay_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )

        await runner.run_once()
        first_price = mock_producer.published[0].payload.price
        first_currency = mock_producer.published[0].payload.currency

        mock_producer.published.clear()
        mock_ebay_client.search_items.return_value = (
            _make_search_response([listing]),
            [],
        )
        await runner.run_once()
        second_price = mock_producer.published[0].payload.price
        second_currency = mock_producer.published[0].payload.currency

        assert first_price == second_price == Decimal("42.50")
        assert first_currency == second_currency == "EUR"

    @pytest.mark.asyncio
    async def test_deduplication_via_processor_pipeline(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """Feeding the same event (same event_id) twice through
        ProcessorPipeline with shared DeduplicationState demonstrates
        that the duplicate is skipped."""
        listing = _make_listing("DEDUP1", "Dedup Product", price_value=10.00)
        mock_ebay_client.search_items.return_value = (
            _make_search_response([listing]),
            [],
        )

        runner = IngestionRunner(
            adapters=[ebay_adapter],
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
# Tests: Malformed input handling
# ---------------------------------------------------------------------------


class TestMalformedInput:
    """Verify malformed records are tracked without halting ingestion."""

    @pytest.mark.asyncio
    async def test_malformed_records_from_client(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """Client-level malformed records are tracked in stats."""
        listing = _make_listing("M1", "Valid Listing")
        client_malformed = [{"raw": "bad_data", "reason": "missing item_id"}]
        mock_ebay_client.search_items.return_value = (
            _make_search_response([listing]),
            client_malformed,
        )

        runner = IngestionRunner(
            adapters=[ebay_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert len(mock_producer.published) == 1
        stats = runner.stats
        assert stats.total_malformed == 1

    @pytest.mark.asyncio
    async def test_all_listings_malformed_produces_no_events(
        self,
        mock_producer: MockProducer,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """When all items fail canonical mapping, no events are published."""
        broken_summary = EbayListingSummary.model_construct(
            item_id="BAD1",
            title=None,  # type: ignore[arg-type]  # intentional: triggers mapping failure
            price=None,
            seller=None,
            availability=None,
            category_ids=None,
            item_web_url=None,
        )
        search_response = EbaySearchResponse.model_construct(
            total=1,
            item_summaries=[broken_summary],
        )
        mock_ebay_client.search_items.return_value = (
            search_response,
            [],
        )

        adapter = EbayAdapter(
            query="test",
            client=mock_ebay_client,
        )
        runner = IngestionRunner(
            adapters=[adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert len(mock_producer.published) == 0


# ---------------------------------------------------------------------------
# Tests: Error isolation
# ---------------------------------------------------------------------------


class TestEbayErrorIsolation:
    """Verify eBay failures don't block other sources."""

    @pytest.mark.asyncio
    async def test_ebay_failure_does_not_block_other_sources(
        self,
        mock_producer: MockProducer,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """When eBay fails, other adapters still publish."""
        from libs.adapters.fake_store.adapter import FakeStoreAdapter

        mock_ebay_client.search_items.side_effect = SourceFetchError(
            "eBay API timeout", source="ebay"
        )

        ebay = EbayAdapter(query="test", client=mock_ebay_client)

        mock_fs_client = AsyncMock()
        mock_fs_client.fetch_products = AsyncMock(
            return_value=(
                [MagicMock(id=1, title="FS Product", price=10.0, category="cat")],
                [],
            ),
        )
        fake_store = FakeStoreAdapter(client=mock_fs_client)

        runner = IngestionRunner(
            adapters=[ebay, fake_store],
            producer=mock_producer,  # type: ignore[arg-type]
            max_retries=1,
        )
        await runner.run_once()

        assert len(mock_producer.published) == 1
        assert mock_producer.published[0].source == "fake_store"
        assert runner.stats.total_errors > 0

    @pytest.mark.asyncio
    async def test_ebay_empty_response_produces_no_events(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """An empty search response produces zero events without errors."""
        mock_ebay_client.search_items.return_value = (
            _make_search_response([]),
            [],
        )

        runner = IngestionRunner(
            adapters=[ebay_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert len(mock_producer.published) == 0
        assert runner.stats.total_errors == 0


# ---------------------------------------------------------------------------
# Tests: Ambiguity — listings with missing or null fields
# ---------------------------------------------------------------------------


class TestAmbiguity:
    """Verify handling of listings with missing or ambiguous data."""

    @pytest.mark.asyncio
    async def test_listing_without_price(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """Listings without price still produce events with null price."""
        listing = _make_listing("NP1", "No Price Item", price_value=None)
        mock_ebay_client.search_items.return_value = (
            _make_search_response([listing]),
            [],
        )

        runner = IngestionRunner(
            adapters=[ebay_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert len(mock_producer.published) == 1
        assert mock_producer.published[0].payload.price is None

    @pytest.mark.asyncio
    async def test_listing_without_seller(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """Listings without seller info still produce valid events."""
        listing = _make_listing("NS1", "No Seller Item", seller_username=None)
        mock_ebay_client.search_items.return_value = (
            _make_search_response([listing]),
            [],
        )

        runner = IngestionRunner(
            adapters=[ebay_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert len(mock_producer.published) == 1
        event = mock_producer.published[0]
        assert event.payload.external_id == "NS1"
        assert event.payload.seller_id is None
        assert event.payload.listing_id == "ebay:NS1"

    @pytest.mark.asyncio
    async def test_listing_without_category(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """Listings without category get 'uncategorized'."""
        listing = _make_listing("NC1", "No Category", category_ids=None)
        mock_ebay_client.search_items.return_value = (
            _make_search_response([listing]),
            [],
        )

        runner = IngestionRunner(
            adapters=[ebay_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert len(mock_producer.published) == 1
        assert mock_producer.published[0].payload.category == "uncategorized"

    @pytest.mark.asyncio
    async def test_out_of_stock_listing(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """Out-of-stock listings produce events with out_of_stock availability."""
        listing = _make_listing("OOS1", "Out of Stock Item", in_stock=False)
        mock_ebay_client.search_items.return_value = (
            _make_search_response([listing]),
            [],
        )

        runner = IngestionRunner(
            adapters=[ebay_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert len(mock_producer.published) == 1
        assert mock_producer.published[0].payload.availability == "out_of_stock"


# ---------------------------------------------------------------------------
# Tests: Regression — all sources together
# ---------------------------------------------------------------------------


class TestRegressionSmoke:
    """Smoke tests ensuring eBay coexists with existing sources."""

    @pytest.mark.asyncio
    async def test_all_three_sources_in_one_cycle(
        self,
        mock_producer: MockProducer,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """All three sources publish events in a single ingestion cycle."""
        from libs.adapters.best_buy.adapter import BestBuyAdapter
        from libs.adapters.best_buy.models import BestBuyProduct
        from libs.adapters.fake_store.adapter import FakeStoreAdapter

        mock_ebay_client.search_items.return_value = (
            _make_search_response([_make_listing("E1", "eBay Item")]),
            [],
        )
        ebay = EbayAdapter(query="test", client=mock_ebay_client)

        mock_fs_client = AsyncMock()
        mock_fs_client.fetch_products = AsyncMock(
            return_value=(
                [MagicMock(id=1, title="FS Item", price=10.0, category="cat")],
                [],
            ),
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
            ),
        )
        best_buy = BestBuyAdapter(api_key="test", client=mock_bb_client)

        runner = IngestionRunner(
            adapters=[fake_store, best_buy, ebay],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        assert len(mock_producer.published) == 3
        sources = {e.source for e in mock_producer.published}
        assert sources == {"fake_store", "best_buy", "ebay"}

    @pytest.mark.asyncio
    async def test_ebay_does_not_leak_source_specific_fields(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """eBay events conform to the canonical contract without eBay-specific fields."""
        listing = _make_listing(
            "LEAK1",
            "Leak Check",
            seller_username="leak_seller",
            feedback_score=500,
            feedback_pct=99.9,
        )
        mock_ebay_client.search_items.return_value = (
            _make_search_response([listing]),
            [],
        )

        runner = IngestionRunner(
            adapters=[ebay_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        event = mock_producer.published[0]
        payload_dict = event.payload.model_dump()
        assert "feedback_score" not in payload_dict
        assert "feedback_percentage" not in payload_dict
        assert "seller" not in payload_dict
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

        assert event.payload.listing_id == "ebay:LEAK1"
        assert event.payload.seller_id == "ebay:leak_seller"

    @pytest.mark.asyncio
    async def test_multiple_ebay_fetch_cycles(
        self,
        mock_producer: MockProducer,
        ebay_adapter: EbayAdapter,
        mock_ebay_client: AsyncMock,
    ) -> None:
        """Successive fetch cycles accumulate events correctly."""
        listings_cycle1 = [
            _make_listing("C1L1", "Cycle 1 Item 1"),
            _make_listing("C1L2", "Cycle 1 Item 2"),
        ]
        listings_cycle2 = [
            _make_listing("C2L1", "Cycle 2 Item 1"),
        ]

        mock_ebay_client.search_items.return_value = (
            _make_search_response(listings_cycle1),
            [],
        )
        runner = IngestionRunner(
            adapters=[ebay_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()
        assert len(mock_producer.published) == 2

        mock_ebay_client.search_items.return_value = (
            _make_search_response(listings_cycle2),
            [],
        )
        await runner.run_once()
        assert len(mock_producer.published) == 3

        all_ids = {e.payload.external_id for e in mock_producer.published}
        assert all_ids == {"C1L1", "C1L2", "C2L1"}
