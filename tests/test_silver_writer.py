"""Unit tests for the Silver Parquet writer (TASK-022).

These tests validate event-to-row conversion, partition key generation,
and writer behavior without requiring external services.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from libs.event_contracts import Availability, ProductObservationEvent, ProductObservationPayload
from libs.lake_writer import SilverWriter, validated_event_to_row
from libs.partitioning import LakeLayer, build_partition_key

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_event() -> ProductObservationEvent:
    """A canonical validated product observation event."""
    return ProductObservationEvent(
        event_id="evt-001",
        event_type="product.observation",
        schema_version=1,
        source="fake-store",
        produced_at=datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc),
        payload=ProductObservationPayload(
            external_id="PROD-123",
            name="Test Widget",
            url="https://example.com/product/123",
            price=Decimal("149.99"),
            currency="EUR",
            availability=Availability.IN_STOCK,
            category="electronics",
            collected_at=datetime(2026, 9, 3, 7, 59, 30, tzinfo=timezone.utc),
        ),
    )


@pytest.fixture
def sample_event_null_price() -> ProductObservationEvent:
    """An event with a null price field."""
    return ProductObservationEvent(
        event_id="evt-002",
        event_type="product.observation",
        schema_version=1,
        source="best-buy",
        produced_at=datetime(2026, 9, 3, 9, 0, 0, tzinfo=timezone.utc),
        payload=ProductObservationPayload(
            external_id="PROD-456",
            name="Priceless Item",
            url="https://example.com/product/456",
            price=None,
            currency="USD",
            availability=Availability.UNKNOWN,
            category="miscellaneous",
            collected_at=datetime(2026, 9, 3, 8, 59, 0, tzinfo=timezone.utc),
        ),
    )


@pytest.fixture
def mock_storage() -> MagicMock:
    """Mock MinIOStorage that tracks put_object calls."""
    storage = MagicMock()
    storage.check_health.return_value = MagicMock(healthy=True)
    return storage


# ---------------------------------------------------------------------------
# Partition key tests
# ---------------------------------------------------------------------------


class TestPartitionKey:
    def test_builds_correct_key(self, sample_event: ProductObservationEvent) -> None:
        key = build_partition_key(sample_event, LakeLayer.SILVER)
        assert key == "silver/source=fake-store/year=2026/month=09/day=03/evt-001.parquet"

    def test_uses_collected_at_date(self, sample_event: ProductObservationEvent) -> None:
        # Change collected_at to a different date
        event = sample_event.model_copy(
            deep=True,
            update={
                "payload": sample_event.payload.model_copy(
                    update={"collected_at": datetime(2025, 12, 25, 12, 0, 0, tzinfo=timezone.utc)}
                )
            },
        )
        key = build_partition_key(event, LakeLayer.SILVER)
        assert "year=2025" in key
        assert "month=12" in key
        assert "day=25" in key

    def test_deterministic_for_same_event(self, sample_event: ProductObservationEvent) -> None:
        key1 = build_partition_key(sample_event, LakeLayer.SILVER)
        key2 = build_partition_key(sample_event, LakeLayer.SILVER)
        assert key1 == key2

    def test_different_events_produce_different_keys(
        self,
        sample_event: ProductObservationEvent,
        sample_event_null_price: ProductObservationEvent,
    ) -> None:
        key1 = build_partition_key(sample_event, LakeLayer.SILVER)
        key2 = build_partition_key(sample_event_null_price, LakeLayer.SILVER)
        assert key1 != key2


# ---------------------------------------------------------------------------
# Event-to-row tests
# ---------------------------------------------------------------------------


class TestEventToRow:
    def test_preserves_all_fields(self, sample_event: ProductObservationEvent) -> None:
        row = validated_event_to_row(sample_event)
        assert row["event_id"] == "evt-001"
        assert row["event_type"] == "product.observation"
        assert row["schema_version"] == "1"  # Converted to string for Parquet schema
        assert row["source"] == "fake-store"
        assert row["external_id"] == "PROD-123"
        assert row["name"] == "Test Widget"
        assert row["url"] == "https://example.com/product/123"
        assert row["currency"] == "EUR"
        assert row["availability"] == "in_stock"
        assert row["category"] == "electronics"

    def test_price_stored_as_string(self, sample_event: ProductObservationEvent) -> None:
        row = validated_event_to_row(sample_event)
        assert row["price"] == "149.99"
        assert isinstance(row["price"], str)

    def test_null_price_remains_none(
        self, sample_event_null_price: ProductObservationEvent
    ) -> None:
        row = validated_event_to_row(sample_event_null_price)
        assert row["price"] is None

    def test_timestamps_serialized_as_iso(self, sample_event: ProductObservationEvent) -> None:
        row = validated_event_to_row(sample_event)
        assert row["produced_at"] == "2026-09-03T08:00:00+00:00"
        assert row["collected_at"] == "2026-09-03T07:59:30+00:00"

    def test_availability_enum_serialized(self, sample_event: ProductObservationEvent) -> None:
        row = validated_event_to_row(sample_event)
        assert row["availability"] == "in_stock"


# ---------------------------------------------------------------------------
# SilverWriter tests
# ---------------------------------------------------------------------------


class TestSilverWriter:
    def test_initialization_logs(self, mock_storage: MagicMock) -> None:
        with patch("libs.lake_writer.silver_writer.logger") as mock_logger:
            SilverWriter(storage=mock_storage, bucket="silver", batch_size=50)
            mock_logger.info.assert_any_call(
                "silver_writer_initialized",
                extra={"bucket": "silver", "batch_size": 50},
            )

    def test_write_event_persists_single_file(
        self, mock_storage: MagicMock, sample_event: ProductObservationEvent
    ) -> None:
        writer = SilverWriter(storage=mock_storage, bucket="silver")
        writer.write_event(sample_event)

        assert mock_storage.put_object.called
        call_args = mock_storage.put_object.call_args
        assert call_args[0][0] == "silver"
        assert (
            call_args[0][1] == "silver/source=fake-store/year=2026/month=09/day=03/evt-001.parquet"
        )

    def test_write_event_verifies_parquet_content(
        self, mock_storage: MagicMock, sample_event: ProductObservationEvent
    ) -> None:
        writer = SilverWriter(storage=mock_storage, bucket="silver")
        writer.write_event(sample_event)

        call_args = mock_storage.put_object.call_args
        parquet_bytes = call_args[0][2]
        df = pl.read_parquet(io.BytesIO(parquet_bytes))
        assert len(df) == 1
        assert df["event_id"][0] == "evt-001"
        assert df["price"][0] == "149.99"

    def test_flush_batch_writes_all_events(
        self, mock_storage: MagicMock, sample_event: ProductObservationEvent
    ) -> None:
        writer = SilverWriter(storage=mock_storage, bucket="silver", batch_size=100)
        writer.add_event(sample_event)
        writer.flush_batch()

        assert mock_storage.put_object.call_count == 1

    def test_flush_empty_batch_is_noop(self, mock_storage: MagicMock) -> None:
        writer = SilverWriter(storage=mock_storage, bucket="silver")
        writer.flush_batch()
        mock_storage.put_object.assert_not_called()

    def test_health_check_delegates_to_storage(self, mock_storage: MagicMock) -> None:
        writer = SilverWriter(storage=mock_storage, bucket="silver")
        result = writer.health_check()
        assert result is True
        mock_storage.check_health.assert_called_once()

    def test_add_event_returns_true_at_threshold(
        self, mock_storage: MagicMock, sample_event: ProductObservationEvent
    ) -> None:
        writer = SilverWriter(storage=mock_storage, bucket="silver", batch_size=2)
        assert writer.add_event(sample_event) is False
        assert writer.add_event(sample_event) is True

    def test_batch_clear_after_flush(
        self, mock_storage: MagicMock, sample_event: ProductObservationEvent
    ) -> None:
        writer = SilverWriter(storage=mock_storage, bucket="silver", batch_size=2)
        assert writer.add_event(sample_event) is False  # 1/2
        writer.flush_batch()
        # After flush, batch is cleared; adding again starts from 0
        assert writer.add_event(sample_event) is False  # 1/2 again
        assert writer.add_event(sample_event) is True  # 2/2 → flush threshold


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_decimal_precision_preserved(self, sample_event: ProductObservationEvent) -> None:
        """Verify that high-precision Decimal values are stored exactly."""
        event = sample_event.model_copy(
            deep=True,
            update={
                "payload": sample_event.payload.model_copy(
                    update={"price": Decimal("12345.67890123")}
                )
            },
        )
        row = validated_event_to_row(event)
        assert row["price"] == "12345.67890123"

    def test_special_characters_in_source(self, sample_event: ProductObservationEvent) -> None:
        """Source names with hyphens produce valid partition keys."""
        event = sample_event.model_copy(update={"source": "my-special-source"})
        key = build_partition_key(event, LakeLayer.SILVER)
        assert "source=my-special-source" in key

    def test_year_month_day_zero_padding(self, sample_event: ProductObservationEvent) -> None:
        """Single-digit months/days are zero-padded."""
        event = sample_event.model_copy(
            deep=True,
            update={
                "payload": sample_event.payload.model_copy(
                    update={"collected_at": datetime(2026, 1, 5, 0, 0, 0, tzinfo=timezone.utc)}
                )
            },
        )
        key = build_partition_key(event, LakeLayer.SILVER)
        assert "year=2026/month=01/day=05" in key
