"""Integration tests for the Silver Parquet writer (TASK-022).

These tests require a running MinIO container and validate end-to-end
Silver Parquet persistence including read-back verification.
"""

from __future__ import annotations

import io
from collections.abc import Generator
from datetime import datetime, timezone
from decimal import Decimal

import polars as pl
import pytest

from libs.common.minio_storage import MinIOSettings, MinIOStorage
from libs.event_contracts import Availability, ProductObservationEvent, ProductObservationPayload
from libs.lake_writer import SilverWriter, build_silver_partition_key

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minio_settings() -> MinIOSettings:
    return MinIOSettings(
        minio_endpoint="http://localhost:9000",
        minio_access_key="minioadmin",
        minio_secret_key="minioadmin-local",
        minio_region="us-east-1",
        minio_bucket_bronze="bronze",
        minio_bucket_silver="silver",
    )


@pytest.fixture
def storage(minio_settings: MinIOSettings) -> Generator[MinIOStorage, None, None]:
    s = MinIOStorage(minio_settings)
    s.ensure_bucket(minio_settings.minio_bucket_silver)
    yield s
    s.close()


@pytest.fixture
def sample_event() -> ProductObservationEvent:
    return ProductObservationEvent(
        event_id="integration-evt-001",
        event_type="product.observation",
        schema_version=1,
        source="fake-store",
        produced_at=datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc),
        payload=ProductObservationPayload(
            external_id="PROD-INT-123",
            name="Integration Test Widget",
            url="https://example.com/product/int-123",
            price=Decimal("299.50"),
            currency="USD",
            availability=Availability.IN_STOCK,
            category="electronics",
            collected_at=datetime(2026, 9, 3, 7, 59, 30, tzinfo=timezone.utc),
        ),
    )


@pytest.fixture
def silver_writer(storage: MinIOStorage, minio_settings: MinIOSettings) -> SilverWriter:
    return SilverWriter(storage=storage, bucket=minio_settings.minio_bucket_silver)


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestSilverWriterIntegration:
    def test_write_and_read_back_single_event(
        self,
        silver_writer: SilverWriter,
        storage: MinIOStorage,
        sample_event: ProductObservationEvent,
        minio_settings: MinIOSettings,
    ) -> None:
        """Write an event to Silver and verify it can be read back correctly."""
        # Write
        silver_writer.write_event(sample_event)

        # Read back
        key = build_silver_partition_key(sample_event)
        parquet_bytes = storage.get_object(minio_settings.minio_bucket_silver, key)

        # Verify content
        df = pl.read_parquet(io.BytesIO(parquet_bytes))
        assert len(df) == 1
        assert df["event_id"][0] == "integration-evt-001"
        assert df["source"][0] == "fake-store"
        assert df["external_id"][0] == "PROD-INT-123"
        assert df["name"][0] == "Integration Test Widget"
        assert df["price"][0] == "299.50"
        assert df["currency"][0] == "USD"
        assert df["availability"][0] == "in_stock"

    def test_idempotent_replay_overwrites(
        self,
        silver_writer: SilverWriter,
        storage: MinIOStorage,
        sample_event: ProductObservationEvent,
        minio_settings: MinIOSettings,
    ) -> None:
        """Writing the same event twice should overwrite, not duplicate."""
        key = build_silver_partition_key(sample_event)

        # Write twice
        silver_writer.write_event(sample_event)
        silver_writer.write_event(sample_event)

        # Should still be exactly one file
        parquet_bytes = storage.get_object(minio_settings.minio_bucket_silver, key)
        df = pl.read_parquet(io.BytesIO(parquet_bytes))
        assert len(df) == 1

    def test_null_price_roundtrip(
        self,
        silver_writer: SilverWriter,
        storage: MinIOStorage,
        minio_settings: MinIOSettings,
    ) -> None:
        """Events with null price should preserve None through write/read."""
        event = ProductObservationEvent(
            event_id="null-price-evt",
            event_type="product.observation",
            schema_version=1,
            source="best-buy",
            produced_at=datetime(2026, 9, 3, 9, 0, 0, tzinfo=timezone.utc),
            payload=ProductObservationPayload(
                external_id="PROD-NULL",
                name="No Price Item",
                url="https://example.com/product/null",
                price=None,
                currency="EUR",
                availability=Availability.UNKNOWN,
                category="misc",
                collected_at=datetime(2026, 9, 3, 8, 59, 0, tzinfo=timezone.utc),
            ),
        )

        silver_writer.write_event(event)

        key = build_silver_partition_key(event)
        parquet_bytes = storage.get_object(minio_settings.minio_bucket_silver, key)
        df = pl.read_parquet(io.BytesIO(parquet_bytes))
        assert df["price"][0] is None

    def test_multiple_events_different_partitions(
        self,
        silver_writer: SilverWriter,
        storage: MinIOStorage,
        minio_settings: MinIOSettings,
    ) -> None:
        """Events from different sources/dates land in different partitions."""
        events = [
            ProductObservationEvent(
                event_id=f"multi-evt-{i}",
                event_type="product.observation",
                schema_version=1,
                source=fake_source,
                produced_at=datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc),
                payload=ProductObservationPayload(
                    external_id=f"PROD-{i}",
                    name=f"Product {i}",
                    url=f"https://example.com/{i}",
                    price=Decimal(str(i * 10)),
                    currency="USD",
                    availability=Availability.IN_STOCK,
                    category="test",
                    collected_at=datetime(2026, 9, 3 + i, 7, 0, 0, tzinfo=timezone.utc),
                ),
            )
            for i, fake_source in enumerate(["source-a", "source-b"], start=1)
        ]

        for event in events:
            silver_writer.write_event(event)

        # Verify each event exists at its own key
        for event in events:
            key = build_silver_partition_key(event)
            assert storage.object_exists(minio_settings.minio_bucket_silver, key)

    def test_health_check_passes(self, silver_writer: SilverWriter) -> None:
        """Health check should report healthy when MinIO is reachable."""
        assert silver_writer.health_check() is True

    def test_batch_flush_writes_all_events(
        self,
        silver_writer: SilverWriter,
        storage: MinIOStorage,
        sample_event: ProductObservationEvent,
        minio_settings: MinIOSettings,
    ) -> None:
        """Flushing a batch should persist all accumulated events."""
        silver_writer.add_event(sample_event)
        silver_writer.flush_batch()

        key = build_silver_partition_key(sample_event)
        assert storage.object_exists(minio_settings.minio_bucket_silver, key)
