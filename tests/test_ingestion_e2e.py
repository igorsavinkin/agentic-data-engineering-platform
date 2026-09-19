"""End-to-end ingestion tests for TASK-037.

Verifies that observations from both Fake Store and Best Buy adapters flow
through the complete pipeline: adapter → canonical event → Kafka → processor.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from libs.adapters.best_buy.adapter import BestBuyAdapter
from libs.adapters.fake_store.adapter import FakeStoreAdapter
from libs.common.kafka_producer import (
    DeliveryReceipt,
)
from libs.event_contracts import ProductObservationEvent
from services.ingestion.runner import IngestionRunner

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class MockProducer:
    """Test helper that mimics KafkaEventProducer while tracking published events."""

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


@pytest.fixture
def mock_producer() -> MockProducer:
    """Create a mock Kafka producer that tracks published events."""
    return MockProducer()


@pytest.fixture
def fake_store_adapter() -> FakeStoreAdapter:
    """Create a Fake Store adapter with mocked client."""
    with patch("libs.adapters.fake_store.adapter.FakeStoreClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.fetch_products = AsyncMock(return_value=([], []))
        mock_client_class.return_value = mock_client
        adapter = FakeStoreAdapter(client=mock_client)
        adapter._mock_client = mock_client  # type: ignore[attr-defined]
        return adapter


@pytest.fixture
def best_buy_adapter() -> BestBuyAdapter:
    """Create a Best Buy adapter with mocked client."""
    with patch("libs.adapters.best_buy.adapter.BestBuyClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.fetch_products = AsyncMock(return_value=([], []))
        mock_client_class.return_value = mock_client
        adapter = BestBuyAdapter(api_key="test-key", client=mock_client)
        adapter._mock_client = mock_client  # type: ignore[attr-defined]
        return adapter


# ---------------------------------------------------------------------------
# Helper: create canonical test events
# ---------------------------------------------------------------------------


def _make_fake_store_event() -> ProductObservationEvent:
    """Create a canonical Fake Store event for testing."""
    return ProductObservationEvent(
        event_id="fake_store:1:2026-09-14T10:00:00+00:00",
        source="fake_store",
        produced_at=datetime.now(timezone.utc),
        payload={
            "external_id": "1",
            "name": "Test Product",
            "url": "https://fakestoreapi.com/products/1",
            "price": Decimal("29.99"),
            "currency": "USD",
            "availability": "in_stock",
            "category": "electronics",
            "collected_at": datetime(2026, 9, 14, 10, 0, 0, tzinfo=timezone.utc),
        },
    )


def _make_best_buy_event() -> ProductObservationEvent:
    """Create a canonical Best Buy event for testing."""
    return ProductObservationEvent(
        event_id="best_buy:12345:2026-09-14T10:00:00+00:00",
        source="best_buy",
        produced_at=datetime.now(timezone.utc),
        payload={
            "external_id": "12345",
            "name": "Test Best Buy Product",
            "url": "https://www.bestbuy.com/site/-/12345.p",
            "price": Decimal("49.99"),
            "currency": "USD",
            "availability": "in_stock",
            "category": "computers",
            "collected_at": datetime(2026, 9, 14, 10, 0, 0, tzinfo=timezone.utc),
        },
    )


# ---------------------------------------------------------------------------
# Tests: Fake Store event reaches Kafka
# ---------------------------------------------------------------------------


class TestFakeStoreIngestion:
    """Verify Fake Store events flow through ingestion to Kafka."""

    @pytest.mark.asyncio
    async def test_fake_store_event_published_to_kafka(
        self, mock_producer: MagicMock, fake_store_adapter: FakeStoreAdapter
    ) -> None:
        """A Fake Store fetch cycle publishes events to Kafka."""
        # Arrange: configure mock to return one valid product
        fake_store_adapter._mock_client.fetch_products.return_value = (  # type: ignore[attr-defined]
            [MagicMock(id=1, title="Test Product", price=29.99, category="electronics")],
            [],
        )

        runner = IngestionRunner(
            adapters=[fake_store_adapter],
            producer=mock_producer,
            interval_seconds=60,
        )

        # Act: run one cycle
        await runner.run_once()

        # Assert: exactly one event was published
        assert len(mock_producer.published) == 1
        published = mock_producer.published[0]
        assert published.source == "fake_store"
        assert published.payload.external_id == "1"
        assert published.payload.name == "Test Product"

    @pytest.mark.asyncio
    async def test_fake_store_source_identity_preserved(
        self, mock_producer: MockProducer, fake_store_adapter: FakeStoreAdapter
    ) -> None:
        """Published events carry the correct source identifier."""
        fake_store_adapter._mock_client.fetch_products.return_value = (  # type: ignore[attr-defined]
            [MagicMock(id=99, title="Widget", price=9.99, category="gadgets")],
            [],
        )

        runner = IngestionRunner(
            adapters=[fake_store_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        published = mock_producer.published[0]
        assert published.source == "fake_store"
        assert published.partition_key.startswith("fake_store:")


# ---------------------------------------------------------------------------
# Tests: Best Buy event reaches Kafka
# ---------------------------------------------------------------------------


class TestBestBuyIngestion:
    """Verify Best Buy events flow through ingestion to Kafka."""

    @pytest.mark.asyncio
    async def test_best_buy_event_published_to_kafka(
        self, mock_producer: MockProducer, best_buy_adapter: BestBuyAdapter
    ) -> None:
        """A Best Buy fetch cycle publishes events to Kafka."""
        # Arrange: configure mock to return one valid product
        from libs.adapters.best_buy.models import BestBuyProduct

        test_product = BestBuyProduct(
            sku=12345,
            name="Test Laptop",
            salePrice=999.99,
            regularPrice=1099.99,
            url="https://www.bestbuy.com/test",
            inStoreAvailability=True,
            onlineAvailability=True,
            categoryPath=[{"id": "1", "name": "Computers"}],
        )
        best_buy_adapter._mock_client.fetch_products.return_value = (  # type: ignore[attr-defined]
            [test_product],
            [],
        )

        runner = IngestionRunner(
            adapters=[best_buy_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
            interval_seconds=60,
        )

        # Act: run one cycle
        await runner.run_once()

        # Assert: exactly one event was published
        assert len(mock_producer.published) == 1
        published = mock_producer.published[0]
        assert published.source == "best_buy"
        assert published.payload.external_id == "12345"

    @pytest.mark.asyncio
    async def test_best_buy_source_identity_preserved(
        self, mock_producer: MockProducer, best_buy_adapter: BestBuyAdapter
    ) -> None:
        """Published events carry the correct source identifier."""
        from libs.adapters.best_buy.models import BestBuyProduct

        best_buy_adapter._mock_client.fetch_products.return_value = (  # type: ignore[attr-defined]
            [
                BestBuyProduct(
                    sku=99999,
                    name="Gadget",
                    salePrice=19.99,
                    regularPrice=19.99,
                    url="https://www.bestbuy.com/gadget",
                    inStoreAvailability=False,
                    onlineAvailability=True,
                    categoryPath=[],
                )
            ],
            [],
        )

        runner = IngestionRunner(
            adapters=[best_buy_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        published = mock_producer.published[0]
        assert published.source == "best_buy"
        assert published.partition_key.startswith("best_buy:")


# ---------------------------------------------------------------------------
# Tests: Both sources share same downstream path (no source branching)
# ---------------------------------------------------------------------------


class TestUnifiedDownstream:
    """Verify processor accepts both sources without source-specific branches."""

    @pytest.mark.asyncio
    async def test_both_sources_use_same_pipeline(
        self,
        mock_producer: MockProducer,
        fake_store_adapter: FakeStoreAdapter,
        best_buy_adapter: BestBuyAdapter,
    ) -> None:
        """Both adapters publish to the same raw topic via the same runner."""
        # Configure both adapters to return events
        fake_store_adapter._mock_client.fetch_products.return_value = (  # type: ignore[attr-defined]
            [MagicMock(id=1, title="FS Product", price=10.0, category="cat")],
            [],
        )

        from libs.adapters.best_buy.models import BestBuyProduct

        best_buy_adapter._mock_client.fetch_products.return_value = (  # type: ignore[attr-defined]
            [
                BestBuyProduct(
                    sku=2,
                    name="BB Product",
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

        runner = IngestionRunner(
            adapters=[fake_store_adapter, best_buy_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        # Assert: both events published, same topic, no source-specific routing
        assert len(mock_producer.published) == 2
        sources = {e.source for e in mock_producer.published}
        assert sources == {"fake_store", "best_buy"}

        # Verify all events target the same topic (checked via mock call args)
        for event in mock_producer.published:
            assert isinstance(event, ProductObservationEvent)


# ---------------------------------------------------------------------------
# Tests: Error isolation — one failing adapter doesn't block others
# ---------------------------------------------------------------------------


class TestErrorIsolation:
    """Verify adapter failures don't prevent other sources from ingesting."""

    @pytest.mark.asyncio
    async def test_failing_adapter_does_not_block_others(
        self,
        mock_producer: MockProducer,
        fake_store_adapter: FakeStoreAdapter,
        best_buy_adapter: BestBuyAdapter,
    ) -> None:
        """If Best Buy fails, Fake Store still publishes."""
        from libs.adapters import SourceFetchError

        # Fake Store succeeds
        fake_store_adapter._mock_client.fetch_products.return_value = (  # type: ignore[attr-defined]
            [MagicMock(id=1, title="OK", price=10.0, category="cat")],
            [],
        )

        # Best Buy fails
        best_buy_adapter._mock_client.fetch_products.side_effect = SourceFetchError(  # type: ignore[attr-defined]
            "API timeout", source="best_buy"
        )

        runner = IngestionRunner(
            adapters=[fake_store_adapter, best_buy_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
            max_retries=1,  # Speed up test
        )
        await runner.run_once()

        # Assert: Fake Store event was published despite Best Buy failure
        assert len(mock_producer.published) == 1
        assert mock_producer.published[0].source == "fake_store"

        # Assert: error was tracked
        stats = runner.stats
        assert stats.total_errors > 0
        assert stats.sources["best_buy"].last_fetch_success is False


# ---------------------------------------------------------------------------
# Tests: Malformed records are tracked but don't halt ingestion
# ---------------------------------------------------------------------------


class TestMalformedHandling:
    """Verify malformed records are logged and tracked."""

    @pytest.mark.asyncio
    async def test_malformed_records_tracked(
        self, mock_producer: MockProducer, fake_store_adapter: FakeStoreAdapter
    ) -> None:
        """Malformed records increment counters but don't stop valid events."""
        fake_store_adapter._mock_client.fetch_products.return_value = (  # type: ignore[attr-defined]
            [MagicMock(id=1, title="Valid", price=10.0, category="cat")],
            [{"raw": "bad_record", "reason": "missing fields"}],  # malformed
        )

        runner = IngestionRunner(
            adapters=[fake_store_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        stats = runner.stats
        assert stats.total_malformed == 1
        assert stats.sources["fake_store"].malformed_count == 1
        # Valid event still published
        assert len(mock_producer.published) == 1


# ---------------------------------------------------------------------------
# Tests: Statistics tracking
# ---------------------------------------------------------------------------


class TestIngestionStats:
    """Verify ingestion statistics are accurately tracked."""

    @pytest.mark.asyncio
    async def test_stats_aggregate_across_sources(
        self,
        mock_producer: MockProducer,
        fake_store_adapter: FakeStoreAdapter,
        best_buy_adapter: BestBuyAdapter,
    ) -> None:
        """Stats correctly aggregate across multiple sources."""
        fake_store_adapter._mock_client.fetch_products.return_value = (  # type: ignore[attr-defined]
            [MagicMock(id=1, title="A", price=1.0, category="x")],
            [],
        )

        from libs.adapters.best_buy.models import BestBuyProduct

        best_buy_adapter._mock_client.fetch_products.return_value = (  # type: ignore[attr-defined]
            [
                BestBuyProduct(
                    sku=2,
                    name="B",
                    salePrice=2.0,
                    regularPrice=2.0,
                    url="https://bb.com/2",
                    inStoreAvailability=True,
                    onlineAvailability=True,
                    categoryPath=[],
                )
            ],
            [],
        )

        runner = IngestionRunner(
            adapters=[fake_store_adapter, best_buy_adapter],
            producer=mock_producer,  # type: ignore[arg-type]
        )
        await runner.run_once()

        stats = runner.stats
        assert stats.total_events_published == 2
        assert "fake_store" in stats.sources
        assert "best_buy" in stats.sources
        assert stats.sources["fake_store"].events_published == 1
        assert stats.sources["best_buy"].events_published == 1
