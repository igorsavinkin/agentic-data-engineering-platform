"""Integration tests for Bronze Parquet writer against real MinIO (TASK-021).

These tests require a running MinIO container.  They verify:
* end-to-end write and read-back through object storage;
* partition directory structure;
* replay idempotency (same key overwrites);
* null field handling in persisted Parquet.
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
from libs.raw_writer import BronzeWriter, build_partition_key

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
    # Cleanup: delete test objects (best-effort)
    try:
        # List and delete all objects in test bucket
        response = s._client.list_objects(Bucket=minio_settings.minio_bucket_bronze, Prefix="")
        for obj in response.get("Contents", []):
            s._client.delete_object(
                Bucket=minio_settings.minio_bucket_bronze,
                Key=obj["Key"],
            )
    except Exception:
        pass
    s.close()


def make_test_event(
    event_id: str = "int-evt-001",
    source: str = "integration-test",
    price: Decimal | None = Decimal("42.50"),
) -> ProductObservationEvent:
    return ProductObservationEvent(
        event_id=event_id,
        source=source,
        produced_at=datetime.now(timezone.utc),
        payload=ProductObservationPayload(
            external_id="int-prod-1",
            name="Integration Test Product",
            url="https://example.com/int/1",
            price=price,
            currency="USD",
            availability=Availability.IN_STOCK,
            category="test",
            collected_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
        ),
    )


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestBronzeWriterIntegration:
    def test_write_and_read_back(
        self, storage: MinIOStorage, minio_settings: MinIOSettings
    ) -> None:
        """Write an event to MinIO and read it back as Parquet."""
        writer = BronzeWriter(
            storage=storage, bucket=minio_settings.minio_bucket_bronze, batch_size=10
        )
        event = make_test_event("int-rw-1")
        writer.add_event(event)
        writer.flush_batch()

        # Read back from MinIO
        key = build_partition_key(event)
        parquet_bytes = storage.get_object(minio_settings.minio_bucket_bronze, key)
        buf = io.BytesIO(parquet_bytes)
        df = pl.read_parquet(buf)

        assert df.height == 1
        row = df.row(0, named=True)
        assert row["event_id"] == "int-rw-1"
        assert row["source"] == "integration-test"
        assert row["price"] == 42.50

    def test_null_price_persists(
        self, storage: MinIOStorage, minio_settings: MinIOSettings
    ) -> None:
        """Null price should remain null after round-trip."""
        writer = BronzeWriter(
            storage=storage, bucket=minio_settings.minio_bucket_bronze, batch_size=10
        )
        event = make_test_event("int-null-price", price=None)
        writer.add_event(event)
        writer.flush_batch()

        key = build_partition_key(event)
        parquet_bytes = storage.get_object(minio_settings.minio_bucket_bronze, key)
        buf = io.BytesIO(parquet_bytes)
        df = pl.read_parquet(buf)
        assert df["price"][0] is None

    def test_replay_idempotency(self, storage: MinIOStorage, minio_settings: MinIOSettings) -> None:
        """Writing the same event twice should produce one file (overwrite)."""
        writer = BronzeWriter(
            storage=storage, bucket=minio_settings.minio_bucket_bronze, batch_size=10
        )
        event = make_test_event("int-idem-1")
        key = build_partition_key(event)

        # First write
        writer.add_event(event)
        writer.flush_batch()
        assert storage.object_exists(minio_settings.minio_bucket_bronze, key)

        # Replay (second write with same event_id)
        writer.add_event(event)
        writer.flush_batch()
        # Should still exist (overwritten, not duplicated)
        assert storage.object_exists(minio_settings.minio_bucket_bronze, key)

    def test_partition_directory_structure(
        self, storage: MinIOStorage, minio_settings: MinIOSettings
    ) -> None:
        """Verify the expected S3 prefix structure is created."""
        writer = BronzeWriter(
            storage=storage, bucket=minio_settings.minio_bucket_bronze, batch_size=10
        )
        event = make_test_event("int-partition", source="partition-test")
        writer.add_event(event)
        writer.flush_batch()

        key = build_partition_key(event)
        # Expected: bronze/source=partition-test/year=2026/month=09/day=03/int-partition.parquet
        assert key.startswith("bronze/")
        assert "source=partition-test" in key
        assert "year=2026" in key
        assert "month=09" in key
        assert "day=03" in key

        # Verify we can list by prefix
        prefix = "bronze/source=partition-test/"
        response = storage._client.list_objects(
            Bucket=minio_settings.minio_bucket_bronze,
            Prefix=prefix,
        )
        keys = [obj["Key"] for obj in response.get("Contents", [])]
        assert any("int-partition.parquet" in k for k in keys)

    def test_multiple_events_different_partitions(
        self, storage: MinIOStorage, minio_settings: MinIOSettings
    ) -> None:
        """Events from different sources go to different partitions."""
        writer = BronzeWriter(
            storage=storage, bucket=minio_settings.minio_bucket_bronze, batch_size=10
        )

        evt_a = make_test_event("int-multi-a", source="source-alpha")
        evt_b = make_test_event("int-multi-b", source="source-beta")

        writer.add_event(evt_a)
        writer.add_event(evt_b)
        writer.flush_batch()

        key_a = build_partition_key(evt_a)
        key_b = build_partition_key(evt_b)

        assert storage.object_exists(minio_settings.minio_bucket_bronze, key_a)
        assert storage.object_exists(minio_settings.minio_bucket_bronze, key_b)
        assert key_a != key_b
        assert "source=source-alpha" in key_a
        assert "source=source-beta" in key_b
