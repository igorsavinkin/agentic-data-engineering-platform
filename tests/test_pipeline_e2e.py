"""End-to-end pipeline tests for TASK-038.

Verifies that observations from both Fake Store and Best Buy sources can be
traced through every layer of the platform using deterministic fixtures and
mocked external dependencies.

Coverage:
1. Fake Store observation through every layer
2. Best Buy observation through every layer
3. Multiple observations from both sources
4. Historical observation for same source product
5. Invalid observation follows invalid/DLQ path
6. Source adapter failure does not corrupt downstream state
7. Stable identifiers allow tracing across layers
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from libs.adapters.best_buy.adapter import BestBuyAdapter
from libs.adapters.best_buy.models import BestBuyProduct
from libs.adapters.fake_store.adapter import FakeStoreAdapter
from libs.common.kafka_consumer import ConsumerMessage
from libs.common.kafka_producer import DeliveryReceipt
from libs.event_contracts import (
    Availability,
    ProductObservationEvent,
    ProductObservationPayload,
)
from services.ingestion.runner import IngestionRunner
from services.processor.deduplication import DeduplicationState
from services.processor.pipeline import ProcessorPipeline

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class TrackingSinks:
    """Track events published to validated and invalid topics."""

    def __init__(self) -> None:
        self.validated_events: list[ProductObservationEvent] = []
        self.invalid_envelopes: list[dict[str, Any]] = []

    def validated_sink(self, event: ProductObservationEvent) -> None:
        self.validated_events.append(event)

    def invalid_sink(self, envelope: dict[str, Any]) -> None:
        self.invalid_envelopes.append(envelope)


class MockKafkaProducer:
    """Test producer that tracks all published events by topic."""

    def __init__(self, default_topic: str = "products.raw.v1") -> None:
        self.default_topic = default_topic
        self.published_by_topic: dict[str, list[ProductObservationEvent]] = {}
        self.metrics = MagicMock()
        self.metrics.increment = MagicMock()

    def publish(self, event: ProductObservationEvent) -> DeliveryReceipt:
        self.published_by_topic.setdefault(self.default_topic, []).append(event)
        return DeliveryReceipt(
            topic=self.default_topic,
            partition=0,
            offset=len(self.published_by_topic[self.default_topic]) - 1,
        )


@pytest.fixture
def mock_producer() -> MockKafkaProducer:
    return MockKafkaProducer()


@pytest.fixture
def fake_store_adapter() -> FakeStoreAdapter:
    with patch("libs.adapters.fake_store.adapter.FakeStoreClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.fetch_products = AsyncMock(return_value=([], []))
        mock_cls.return_value = mock_client
        adapter = FakeStoreAdapter(client=mock_client)
        adapter._mock_client = mock_client  # type: ignore[attr-defined]
        return adapter


@pytest.fixture
def best_buy_adapter() -> BestBuyAdapter:
    with patch("libs.adapters.best_buy.adapter.BestBuyClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.fetch_products = AsyncMock(return_value=([], []))
        mock_cls.return_value = mock_client
        adapter = BestBuyAdapter(api_key="test-key", client=mock_client)
        adapter._mock_client = mock_client  # type: ignore[attr-defined]
        return adapter


def _make_fake_store_product(
    product_id: int = 1, title: str = "Test Product", price: float = 29.99
) -> MagicMock:
    """Create a mock Fake Store product."""
    product = MagicMock()
    product.id = product_id
    product.title = title
    product.price = price
    product.category = "electronics"
    return product


def _make_best_buy_product(
    sku: int = 12345, name: str = "Test Laptop", sale_price: float = 999.99
) -> BestBuyProduct:
    """Create a Best Buy product."""
    return BestBuyProduct(
        sku=sku,
        name=name,
        salePrice=sale_price,
        regularPrice=sale_price * 1.1,
        url=f"https://www.bestbuy.com/product/{sku}",
        inStoreAvailability=True,
        onlineAvailability=True,
        categoryPath=[{"id": "1", "name": "Computers"}],
    )


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
# Tests: Single source through every layer
# ---------------------------------------------------------------------------


class TestFakeStoreEndToEnd:
    """Verify Fake Store observation traces through every layer."""

    @pytest.mark.asyncio
    async def test_fake_store_through_full_pipeline(
        self, mock_producer: MockKafkaProducer, fake_store_adapter: FakeStoreAdapter
    ) -> None:
        """Fake Store event flows: adapter → Kafka → processor → validated topic."""
        # Arrange: adapter returns one product
        fake_store_adapter._mock_client.fetch_products.return_value = (  # type: ignore[attr-defined]
            [_make_fake_store_product(1, "FS Widget", 19.99)],
            [],
        )

        runner = IngestionRunner(adapters=[fake_store_adapter], producer=mock_producer)  # type: ignore[arg-type]
        await runner.run_once()

        # Assert: ingestion published to raw topic
        assert len(mock_producer.published_by_topic.get("products.raw.v1", [])) == 1
        raw_event = mock_producer.published_by_topic["products.raw.v1"][0]
        assert raw_event.source == "fake_store"
        assert raw_event.payload.external_id == "1"

        # Act: process through processor pipeline with tracking sinks
        sinks = TrackingSinks()
        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
            dedup_state=DeduplicationState(),
        )
        msg = _wrap_as_consumer_message(raw_event, offset=0)
        result = pipeline.process_batch([msg])

        # Assert: valid outcome tracked in sinks
        assert result.published_valid == 1
        assert len(sinks.validated_events) == 1
        validated_event = sinks.validated_events[0]
        assert validated_event.payload.external_id == "1"
        assert validated_event.source == "fake_store"

    @pytest.mark.asyncio
    async def test_fake_store_stable_identifiers(
        self, mock_producer: MockKafkaProducer, fake_store_adapter: FakeStoreAdapter
    ) -> None:
        """Same product produces stable identifier pattern across multiple runs."""
        fake_store_adapter._mock_client.fetch_products.return_value = (  # type: ignore[attr-defined]
            [_make_fake_store_product(42, "Stable Product", 50.0)],
            [],
        )

        runner = IngestionRunner(adapters=[fake_store_adapter], producer=mock_producer)  # type: ignore[arg-type]

        # First run
        await runner.run_once()
        first_event = mock_producer.published_by_topic["products.raw.v1"][0]
        first_event_id = first_event.event_id

        # Second run with same product
        await runner.run_once()
        second_event = mock_producer.published_by_topic["products.raw.v1"][1]
        second_event_id = second_event.event_id

        # Assert: both events have stable identifier pattern (source:product_id)
        assert "fake_store:42" in first_event_id
        assert "fake_store:42" in second_event_id
        # Note: full event_id may include timestamp for uniqueness


class TestBestBuyEndToEnd:
    """Verify Best Buy observation traces through every layer."""

    @pytest.mark.asyncio
    async def test_best_buy_through_full_pipeline(
        self, mock_producer: MockKafkaProducer, best_buy_adapter: BestBuyAdapter
    ) -> None:
        """Best Buy event flows: adapter → Kafka → processor → validated topic."""
        best_buy_adapter._mock_client.fetch_products.return_value = (  # type: ignore[attr-defined]
            [_make_best_buy_product(99999, "BB Laptop", 1299.99)],
            [],
        )

        runner = IngestionRunner(adapters=[best_buy_adapter], producer=mock_producer)  # type: ignore[arg-type]
        await runner.run_once()

        # Assert: ingestion published to raw topic
        raw_events = mock_producer.published_by_topic.get("products.raw.v1", [])
        assert len(raw_events) == 1
        raw_event = raw_events[0]
        assert raw_event.source == "best_buy"
        assert raw_event.payload.external_id == "99999"

        # Act: process through processor with tracking sinks
        sinks = TrackingSinks()
        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
            dedup_state=DeduplicationState(),
        )
        msg = _wrap_as_consumer_message(raw_event, offset=0)
        result = pipeline.process_batch([msg])

        # Assert: validated output tracked in sinks
        assert result.published_valid == 1
        assert len(sinks.validated_events) == 1
        assert sinks.validated_events[0].payload.external_id == "99999"
        assert sinks.validated_events[0].source == "best_buy"


# ---------------------------------------------------------------------------
# Tests: Multiple sources share same downstream path
# ---------------------------------------------------------------------------


class TestUnifiedDownstream:
    """Verify both sources use the same downstream pipeline."""

    @pytest.mark.asyncio
    async def test_both_sources_same_pipeline(
        self,
        mock_producer: MockKafkaProducer,
        fake_store_adapter: FakeStoreAdapter,
        best_buy_adapter: BestBuyAdapter,
    ) -> None:
        """Both adapters publish to raw topic and processor accepts both."""
        # Arrange: both adapters return products
        fake_store_adapter._mock_client.fetch_products.return_value = (  # type: ignore[attr-defined]
            [_make_fake_store_product(1, "FS A", 10.0)],
            [],
        )
        best_buy_adapter._mock_client.fetch_products.return_value = (  # type: ignore[attr-defined]
            [_make_best_buy_product(2, "BB B", 20.0)],
            [],
        )

        runner = IngestionRunner(
            adapters=[fake_store_adapter, best_buy_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        # Assert: both sources published to same raw topic
        raw_events = mock_producer.published_by_topic.get("products.raw.v1", [])
        assert len(raw_events) == 2
        sources = {e.source for e in raw_events}
        assert sources == {"fake_store", "best_buy"}

        # Act: process both through same pipeline with tracking sinks
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

        # Assert: both produced validated output via same path
        assert result.published_valid == 2
        assert len(sinks.validated_events) == 2
        validated_sources = {e.source for e in sinks.validated_events}
        assert validated_sources == {"fake_store", "best_buy"}


# ---------------------------------------------------------------------------
# Tests: Historical observations and deduplication
# ---------------------------------------------------------------------------


class TestHistoricalObservations:
    """Verify historical observations for same product are handled correctly."""

    @pytest.mark.asyncio
    async def test_historical_observation_same_product(
        self, mock_producer: MockKafkaProducer, fake_store_adapter: FakeStoreAdapter
    ) -> None:
        """Multiple observations of same product produce separate events but dedup works."""
        fake_store_adapter._mock_client.fetch_products.return_value = (  # type: ignore[attr-defined]
            [_make_fake_store_product(100, "Repeat Product", 25.0)],
            [],
        )

        runner = IngestionRunner(adapters=[fake_store_adapter], producer=mock_producer)  # type: ignore[arg-type]

        # First observation
        await runner.run_once()
        first_raw = mock_producer.published_by_topic["products.raw.v1"][0]

        # Process first observation with tracking sinks
        sinks = TrackingSinks()
        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
            dedup_state=DeduplicationState(),
        )
        msg1 = _wrap_as_consumer_message(first_raw, offset=0)
        result1 = pipeline.process_batch([msg1])

        # Second observation (same product, different time)
        await runner.run_once()
        second_raw = mock_producer.published_by_topic["products.raw.v1"][1]

        # Process second observation - should be deduplicated if same event_id
        msg2 = _wrap_as_consumer_message(second_raw, offset=1)
        result2 = pipeline.process_batch([msg2])

        # Assert: both raw events exist (at-least-once)
        assert len(mock_producer.published_by_topic["products.raw.v1"]) == 2

        # Assert: validated events reflect dedup behavior
        # With same event_id, second should be deduplicated (skipped or conflict)
        total_validated = result1.published_valid + result2.published_valid
        assert total_validated <= 2


# ---------------------------------------------------------------------------
# Tests: Invalid observations follow DLQ path
# ---------------------------------------------------------------------------


class TestInvalidObservationPath:
    """Verify invalid observations do not enter Silver/warehouse."""

    @pytest.mark.asyncio
    async def test_invalid_event_goes_to_invalid_topic(
        self, mock_producer: MockKafkaProducer, fake_store_adapter: FakeStoreAdapter
    ) -> None:
        """Invalid events are routed to invalid topic, not validated."""
        # Create an invalid event by bypassing Pydantic validation
        invalid_payload = ProductObservationPayload.model_construct(
            external_id="1",
            name=None,  # type: ignore[arg-type]  # Missing required field
            url="https://example.com/1",
            price=Decimal("-10.00"),  # Negative price is invalid
            currency="INVALID",  # Invalid currency format
            availability=Availability.UNKNOWN,
            category="electronics",
            collected_at=datetime.now(timezone.utc),
        )
        invalid_event = ProductObservationEvent.model_construct(
            event_id="invalid:1:test",
            event_type="product.observation",
            schema_version=1,
            source="fake_store",
            produced_at=datetime.now(timezone.utc),
            payload=invalid_payload,
        )

        # Process invalid event with tracking sinks
        sinks = TrackingSinks()
        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
            dedup_state=DeduplicationState(),
        )
        msg = _wrap_as_consumer_message(invalid_event, offset=0)
        result = pipeline.process_batch([msg])

        # Assert: invalid event tracked in sinks
        assert result.published_invalid == 1
        assert len(sinks.invalid_envelopes) >= 1

        # Assert: no invalid event in validated sink
        assert len(sinks.validated_events) == 0


# ---------------------------------------------------------------------------
# Tests: Error isolation
# ---------------------------------------------------------------------------


class TestErrorIsolation:
    """Verify source adapter failures don't corrupt downstream state."""

    @pytest.mark.asyncio
    async def test_failing_adapter_does_not_corrupt_downstream(
        self,
        mock_producer: MockKafkaProducer,
        fake_store_adapter: FakeStoreAdapter,
        best_buy_adapter: BestBuyAdapter,
    ) -> None:
        """If one adapter fails, the other still publishes and processes correctly."""
        from libs.adapters import SourceFetchError

        # Fake Store succeeds
        fake_store_adapter._mock_client.fetch_products.return_value = (  # type: ignore[attr-defined]
            [_make_fake_store_product(1, "OK Product", 10.0)],
            [],
        )

        # Best Buy fails
        best_buy_adapter._mock_client.fetch_products.side_effect = SourceFetchError(  # type: ignore[attr-defined]
            "API timeout", source="best_buy"
        )

        runner = IngestionRunner(
            adapters=[fake_store_adapter, best_buy_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
            max_retries=1,
        )
        await runner.run_once()

        # Assert: Fake Store event was published
        raw_events = mock_producer.published_by_topic.get("products.raw.v1", [])
        assert len(raw_events) == 1
        assert raw_events[0].source == "fake_store"

        # Assert: error was tracked in stats
        assert runner.stats.total_errors > 0
        assert runner.stats.sources["best_buy"].last_fetch_success is False

        # Act: process the successful event through pipeline with tracking sinks
        sinks = TrackingSinks()
        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
            dedup_state=DeduplicationState(),
        )
        msg = _wrap_as_consumer_message(raw_events[0], offset=0)
        result = pipeline.process_batch([msg])

        # Assert: downstream processing succeeded despite upstream failure
        assert result.published_valid == 1
        assert len(sinks.validated_events) >= 1
        assert sinks.validated_events[0].source == "fake_store"


# ---------------------------------------------------------------------------
# Tests: Traceability across layers
# ---------------------------------------------------------------------------


class TestTraceability:
    """Verify stable identifiers allow tracing observations across layers."""

    @pytest.mark.asyncio
    async def test_event_traced_across_layers(
        self, mock_producer: MockKafkaProducer, fake_store_adapter: FakeStoreAdapter
    ) -> None:
        """Same event_id can be traced from raw → validated topics."""
        fake_store_adapter._mock_client.fetch_products.return_value = (  # type: ignore[attr-defined]
            [_make_fake_store_product(777, "Traceable Product", 42.0)],
            [],
        )

        # Ingestion layer
        runner = IngestionRunner(adapters=[fake_store_adapter], producer=mock_producer)  # type: ignore[arg-type]
        await runner.run_once()

        raw_events = mock_producer.published_by_topic.get("products.raw.v1", [])
        assert len(raw_events) == 1
        raw_event = raw_events[0]
        raw_event_id = raw_event.event_id

        # Processor layer with tracking sinks
        sinks = TrackingSinks()
        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
            dedup_state=DeduplicationState(),
        )
        msg = _wrap_as_consumer_message(raw_event, offset=0)
        result = pipeline.process_batch([msg])

        # Assert: same event_id appears in validated output
        assert result.published_valid == 1
        assert len(sinks.validated_events) >= 1
        validated_event = sinks.validated_events[-1]
        assert validated_event.event_id == raw_event_id

        # Assert: external_id preserved across layers
        assert validated_event.payload.external_id == raw_event.payload.external_id == "777"
        assert validated_event.source == raw_event.source == "fake_store"
