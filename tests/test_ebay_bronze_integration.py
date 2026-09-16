"""Integration tests for eBay events through Bronze Parquet (TASK-045).

These tests require a running MinIO container.  They verify:
* eBay events persist to Bronze Parquet with correct stored state;
* listing_id and seller_id survive the round-trip;
* partition structure places eBay events under source=ebay;
* replay idempotency (same event_id overwrites, not duplicates).

Run with: pytest -m integration
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
from libs.partitioning import LakeLayer, build_partition_key
from libs.raw_writer import BronzeWriter

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def minio_settings() -> MinIOSettings:
    """Settings pointing at the local MinIO container."""
    return MinIOSettings(
        minio_endpoint="http://localhost:9000",
        minio_access_key="minioadmin",
        minio_secret_key="minioadmin-local",
        minio_bucket_bronze="test-bronze",
    )


@pytest.fixture(scope="module")
def storage(minio_settings: MinIOSettings) -> Generator[MinIOStorage, None, None]:
    """Real MinIO storage client with bucket initialised."""
    s = MinIOStorage(minio_settings)
    s.ensure_bucket(minio_settings.minio_bucket_bronze)
    yield s
    try:
        response = s._client.list_objects(Bucket=minio_settings.minio_bucket_bronze, Prefix="")
        for obj in response.get("Contents", []):
            s._client.delete_object(
                Bucket=minio_settings.minio_bucket_bronze,
                Key=obj["Key"],
            )
    except Exception:
        pass
    s.close()


def make_ebay_event(
    event_id: str = "ebay-int-001",
    external_id: str = "12345",
    listing_id: str | None = "ebay:12345",
    seller_id: str | None = "ebay:test_seller",
    price: Decimal | None = Decimal("29.99"),
) -> ProductObservationEvent:
    """Build a deterministic eBay event for integration testing."""
    return ProductObservationEvent(
        event_id=event_id,
        source="ebay",
        produced_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
        payload=ProductObservationPayload(
            external_id=external_id,
            name="eBay Integration Test Item",
            url=f"https://www.ebay.com/itm/{external_id}",
            price=price,
            currency="USD",
            availability=Availability.IN_STOCK,
            category="ebay_category_12345",
            collected_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
            listing_id=listing_id,
            seller_id=seller_id,
        ),
    )


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestEbayBronzeStoredState:
    """Verify eBay events persist to Bronze Parquet with correct stored state."""

    def test_ebay_event_write_and_read_back(
        self, storage: MinIOStorage, minio_settings: MinIOSettings
    ) -> None:
        """Write an eBay event to MinIO Bronze and read it back as Parquet."""
        writer = BronzeWriter(
            storage=storage, bucket=minio_settings.minio_bucket_bronze, batch_size=10
        )
        event = make_ebay_event("ebay-rw-1", external_id="EB-RW-1")
        writer.add_event(event)
        writer.flush_batch()

        key = build_partition_key(event, LakeLayer.BRONZE)
        parquet_bytes = storage.get_object(minio_settings.minio_bucket_bronze, key)
        buf = io.BytesIO(parquet_bytes)
        df = pl.read_parquet(buf)

        assert df.height == 1
        row = df.row(0, named=True)
        assert row["event_id"] == "ebay-rw-1"
        assert row["source"] == "ebay"
        assert row["external_id"] == "EB-RW-1"
        assert row["price"] == "29.99"

    def test_ebay_partition_structure(
        self, storage: MinIOStorage, minio_settings: MinIOSettings
    ) -> None:
        """eBay events land under bronze/source=ebay/ in the partition hierarchy."""
        writer = BronzeWriter(
            storage=storage, bucket=minio_settings.minio_bucket_bronze, batch_size=10
        )
        event = make_ebay_event("ebay-part-1", external_id="EB-PART-1")
        writer.add_event(event)
        writer.flush_batch()

        key = build_partition_key(event, LakeLayer.BRONZE)
        assert key.startswith("bronze/")
        assert "source=ebay" in key
        assert "year=2026" in key
        assert "month=09" in key
        assert "day=16" in key

    def test_ebay_replay_idempotency(
        self, storage: MinIOStorage, minio_settings: MinIOSettings
    ) -> None:
        """Writing the same eBay event twice produces one file (overwrite)."""
        writer = BronzeWriter(
            storage=storage, bucket=minio_settings.minio_bucket_bronze, batch_size=10
        )
        event = make_ebay_event("ebay-idem-1", external_id="EB-IDEM-1")
        key = build_partition_key(event, LakeLayer.BRONZE)

        writer.add_event(event)
        writer.flush_batch()
        assert storage.object_exists(minio_settings.minio_bucket_bronze, key)

        writer.add_event(event)
        writer.flush_batch()
        assert storage.object_exists(minio_settings.minio_bucket_bronze, key)

        parquet_bytes = storage.get_object(minio_settings.minio_bucket_bronze, key)
        df = pl.read_parquet(io.BytesIO(parquet_bytes))
        assert df.height == 1

    def test_multiple_ebay_listings_different_sellers(
        self, storage: MinIOStorage, minio_settings: MinIOSettings
    ) -> None:
        """Multiple eBay listings from different sellers persist as separate Parquet files."""
        writer = BronzeWriter(
            storage=storage, bucket=minio_settings.minio_bucket_bronze, batch_size=10
        )

        event_a = make_ebay_event(
            "ebay-multi-a",
            external_id="EB-MA",
            listing_id="ebay:EB-MA",
            seller_id="ebay:seller_alice",
            price=Decimal("19.99"),
        )
        event_b = make_ebay_event(
            "ebay-multi-b",
            external_id="EB-MB",
            listing_id="ebay:EB-MB",
            seller_id="ebay:seller_bob",
            price=Decimal("24.99"),
        )

        writer.add_event(event_a)
        writer.add_event(event_b)
        writer.flush_batch()

        key_a = build_partition_key(event_a, LakeLayer.BRONZE)
        key_b = build_partition_key(event_b, LakeLayer.BRONZE)

        assert storage.object_exists(minio_settings.minio_bucket_bronze, key_a)
        assert storage.object_exists(minio_settings.minio_bucket_bronze, key_b)
        assert key_a != key_b

        parquet_a = storage.get_object(minio_settings.minio_bucket_bronze, key_a)
        df_a = pl.read_parquet(io.BytesIO(parquet_a))
        assert df_a.height == 1
        assert df_a.row(0, named=True)["external_id"] == "EB-MA"

        parquet_b = storage.get_object(minio_settings.minio_bucket_bronze, key_b)
        df_b = pl.read_parquet(io.BytesIO(parquet_b))
        assert df_b.height == 1
        assert df_b.row(0, named=True)["external_id"] == "EB-MB"
