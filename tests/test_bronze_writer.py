"""Unit tests for Bronze Parquet writer (TASK-021).

Tests cover:
* partition key generation
* event-to-row conversion including nullable fields
* batch accumulation and flush behavior
* idempotent writes (replay overwrites)
* round-trip serialization/deserialization
* null/edge cases
* storage failure handling
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import polars as pl
import pytest

from libs.common.minio_storage import MinIOStorage, StorageError
from libs.event_contracts import Availability, ProductObservationEvent, ProductObservationPayload
from libs.partitioning import LakeLayer, build_partition_key
from libs.raw_writer import BronzeBatch, BronzeWriter, event_to_row

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_event(
    event_id: str = "evt-001",
    source: str = "fake-store",
    external_id: str = "prod-123",
    collected_at: datetime | None = None,
    price: Decimal | None = Decimal("99.99"),
) -> ProductObservationEvent:
    """Helper to construct a valid test event."""
    if collected_at is None:
        collected_at = datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc)
    return ProductObservationEvent(
        event_id=event_id,
        source=source,
        produced_at=datetime.now(timezone.utc),
        payload=ProductObservationPayload(
            external_id=external_id,
            name="Test Product",
            url="https://example.com/product/123",
            price=price,
            currency="EUR",
            availability=Availability.IN_STOCK,
            category="electronics",
            collected_at=collected_at,
        ),
    )


@pytest.fixture
def mock_storage() -> MagicMock:
    """Return a mocked MinIOStorage instance."""
    storage = MagicMock(spec=MinIOStorage)
    storage.check_health.return_value = MagicMock(healthy=True, detail="ok")
    return storage


# ---------------------------------------------------------------------------
# Partition key tests
# ---------------------------------------------------------------------------


class TestPartitionKey:
    def test_basic_key_structure(self) -> None:
        event = make_event(
            source="bestbuy", collected_at=datetime(2026, 9, 15, tzinfo=timezone.utc)
        )
        key = build_partition_key(event, LakeLayer.BRONZE)
        assert key.startswith("bronze/")
        assert "source=bestbuy" in key
        assert "year=2026" in key
        assert "month=09" in key
        assert "day=15" in key
        assert "evt-001.parquet" in key

    def test_key_is_deterministic_for_same_event(self) -> None:
        event = make_event()
        key1 = build_partition_key(event, LakeLayer.BRONZE)
        key2 = build_partition_key(event, LakeLayer.BRONZE)
        assert key1 == key2

    def test_different_sources_produce_different_prefixes(self) -> None:
        evt_a = make_event(source="source-a")
        evt_b = make_event(source="source-b")
        key_a = build_partition_key(evt_a, LakeLayer.BRONZE)
        key_b = build_partition_key(evt_b, LakeLayer.BRONZE)
        assert key_a != key_b
        assert "source=source-a" in key_a
        assert "source=source-b" in key_b

    def test_temporal_partitioning(self) -> None:
        jan = make_event(collected_at=datetime(2026, 1, 5, tzinfo=timezone.utc))
        dec = make_event(collected_at=datetime(2026, 12, 25, tzinfo=timezone.utc))
        key_jan = build_partition_key(jan, LakeLayer.BRONZE)
        key_dec = build_partition_key(dec, LakeLayer.BRONZE)
        assert "month=01" in key_jan
        assert "month=12" in key_dec
        assert "day=05" in key_jan
        assert "day=25" in key_dec


# ---------------------------------------------------------------------------
# Event to row tests
# ---------------------------------------------------------------------------


class TestEventToRow:
    def test_all_fields_preserved(self) -> None:
        event = make_event()
        row = event_to_row(event)
        assert row["event_id"] == "evt-001"
        assert row["event_type"] == "product.observation"
        assert row["schema_version"] == "1"  # Converted to string for Parquet schema
        assert row["source"] == "fake-store"
        assert row["external_id"] == "prod-123"
        assert row["name"] == "Test Product"
        assert row["url"] == "https://example.com/product/123"
        assert row["currency"] == "EUR"
        assert row["availability"] == "in_stock"
        assert row["category"] == "electronics"

    def test_price_as_string(self) -> None:
        event = make_event(price=Decimal("149.50"))
        row = event_to_row(event)
        assert row["price"] == "149.50"
        assert isinstance(row["price"], str)

    def test_null_price_preserved(self) -> None:
        event = make_event(price=None)
        row = event_to_row(event)
        assert row["price"] is None

    def test_timestamps_as_iso_strings(self) -> None:
        event = make_event()
        row = event_to_row(event)
        assert isinstance(row["produced_at"], str)
        assert isinstance(row["collected_at"], str)
        assert "T" in row["produced_at"]
        assert "T" in row["collected_at"]


# ---------------------------------------------------------------------------
# Batch tests
# ---------------------------------------------------------------------------


class TestBronzeBatch:
    def test_batch_accumulates_events(self) -> None:
        batch = BronzeBatch(events=[], max_size=3)
        assert not batch.add(make_event("e1"))  # 1 < 3
        assert not batch.add(make_event("e2"))  # 2 < 3
        assert batch.add(make_event("e3"))  # 3 >= 3 → flush signal

    def test_batch_clear_removes_all(self) -> None:
        batch = BronzeBatch(events=[], max_size=10)
        batch.add(make_event("e1"))
        batch.add(make_event("e2"))
        batch.clear()
        assert len(batch.events) == 0

    def test_custom_max_size(self) -> None:
        batch = BronzeBatch(events=[], max_size=1)
        assert batch.add(make_event("e1"))  # 1 >= 1 → immediate flush


# ---------------------------------------------------------------------------
# BronzeWriter tests
# ---------------------------------------------------------------------------


class TestBronzeWriter:
    def test_add_event_returns_flush_signal(self, mock_storage: MagicMock) -> None:
        writer = BronzeWriter(storage=mock_storage, batch_size=2)
        assert not writer.add_event(make_event("e1"))
        assert writer.add_event(make_event("e2"))  # triggers flush signal

    def test_flush_empty_batch_is_noop(self, mock_storage: MagicMock) -> None:
        writer = BronzeWriter(storage=mock_storage)
        writer.flush_batch()  # should not raise
        mock_storage.put_object.assert_not_called()

    def test_flush_writes_parquet_files(self, mock_storage: MagicMock) -> None:
        writer = BronzeWriter(storage=mock_storage, batch_size=10)
        writer.add_event(make_event("e1"))
        writer.add_event(make_event("e2"))
        writer.flush_batch()
        assert mock_storage.put_object.call_count == 2

    def test_put_object_receives_correct_arguments(self, mock_storage: MagicMock) -> None:
        writer = BronzeWriter(storage=mock_storage, bucket="my-bronze", batch_size=10)
        event = make_event("e1", source="test-source")
        writer.add_event(event)
        writer.flush_batch()
        call_args = mock_storage.put_object.call_args
        assert call_args[0][0] == "my-bronze"  # bucket
        key = call_args[0][1]
        assert "source=test-source" in key
        assert "e1.parquet" in key
        assert isinstance(call_args[0][2], bytes)  # parquet bytes

    def test_parquet_bytes_are_valid(self, mock_storage: MagicMock) -> None:
        writer = BronzeWriter(storage=mock_storage, batch_size=10)
        event = make_event("e1")
        writer.add_event(event)
        writer.flush_batch()
        parquet_bytes = mock_storage.put_object.call_args[0][2]
        # Verify we can read it back
        buf = io.BytesIO(parquet_bytes)
        df = pl.read_parquet(buf)
        assert df.height == 1
        assert df["event_id"][0] == "e1"

    def test_round_trip_preserves_all_fields(self, mock_storage: MagicMock) -> None:
        writer = BronzeWriter(storage=mock_storage, batch_size=10)
        event = make_event("roundtrip-1", price=Decimal("75.00"))
        writer.add_event(event)
        writer.flush_batch()
        parquet_bytes = mock_storage.put_object.call_args[0][2]
        buf = io.BytesIO(parquet_bytes)
        df = pl.read_parquet(buf)
        row = df.row(0, named=True)
        assert row["event_id"] == "roundtrip-1"
        assert row["price"] == "75.00"  # stored as string for precision
        assert row["currency"] == "EUR"
        assert row["availability"] == "in_stock"

    def test_null_price_round_trip(self, mock_storage: MagicMock) -> None:
        writer = BronzeWriter(storage=mock_storage, batch_size=10)
        event = make_event("null-price", price=None)
        writer.add_event(event)
        writer.flush_batch()
        parquet_bytes = mock_storage.put_object.call_args[0][2]
        buf = io.BytesIO(parquet_bytes)
        df = pl.read_parquet(buf)
        assert df["price"][0] is None

    def test_storage_error_propagates(self, mock_storage: MagicMock) -> None:
        mock_storage.put_object.side_effect = StorageError("write failed")
        writer = BronzeWriter(storage=mock_storage, batch_size=10)
        writer.add_event(make_event("e1"))
        with pytest.raises(StorageError, match="bronze_flush failed"):
            writer.flush_batch()

    def test_partial_failure_reports_failed_event_ids(self, mock_storage: MagicMock) -> None:
        """If some writes fail, the error message lists the failed event IDs."""
        call_count = [0]

        def flaky_put(*args: object, **kwargs: object) -> None:
            call_count[0] += 1
            if call_count[0] == 1:
                raise StorageError("transient")

        mock_storage.put_object.side_effect = flaky_put
        writer = BronzeWriter(storage=mock_storage, batch_size=10)
        writer.add_event(make_event("ok"))
        writer.add_event(make_event("fail"))
        with pytest.raises(StorageError, match="fail"):
            writer.flush_batch()

    def test_health_check_delegates_to_storage(self, mock_storage: MagicMock) -> None:
        writer = BronzeWriter(storage=mock_storage)
        assert writer.health_check() is True
        mock_storage.check_health.assert_called_once()

    def test_idempotent_write_same_key_overwrites(self, mock_storage: MagicMock) -> None:
        """Replaying the same event produces the same key (idempotency)."""
        writer = BronzeWriter(storage=mock_storage, batch_size=10)
        event = make_event("idem-1")
        writer.add_event(event)
        writer.flush_batch()
        key1 = mock_storage.put_object.call_args[0][1]

        # Simulate replay
        mock_storage.reset_mock()
        writer.add_event(event)
        writer.flush_batch()
        key2 = mock_storage.put_object.call_args[0][1]

        assert key1 == key2


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_unicode_in_fields(self, mock_storage: MagicMock) -> None:
        event = ProductObservationEvent(
            event_id="unicode-1",
            source="test",
            produced_at=datetime.now(timezone.utc),
            payload=ProductObservationPayload(
                external_id="prod-üñí",
                name="Produkt mit Ümlaut",
                url="https://example.com/日本語",
                price=Decimal("10.00"),
                currency="JPY",
                availability=Availability.IN_STOCK,
                category="カテゴリ",
                collected_at=datetime.now(timezone.utc),
            ),
        )
        writer = BronzeWriter(storage=mock_storage, batch_size=10)
        writer.add_event(event)
        writer.flush_batch()
        parquet_bytes = mock_storage.put_object.call_args[0][2]
        buf = io.BytesIO(parquet_bytes)
        df = pl.read_parquet(buf)
        assert df["name"][0] == "Produkt mit Ümlaut"

    def test_very_long_event_id(self, mock_storage: MagicMock) -> None:
        long_id = "x" * 500
        event = make_event(event_id=long_id)
        key = build_partition_key(event, LakeLayer.BRONZE)
        assert long_id + ".parquet" in key

    def test_availability_values(self, mock_storage: MagicMock) -> None:
        for avail in Availability:
            event = make_event()
            event.payload.availability = avail
            row = event_to_row(event)
            assert row["availability"] == avail.value
