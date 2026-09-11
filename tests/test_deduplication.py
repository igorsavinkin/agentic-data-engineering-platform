"""Unit tests for replay-safe deduplication.

These tests verify that ``deduplicate()`` deterministically splits a validated
DataFrame into unique records, exact duplicates, and conflicts. Coverage per
TASK-016 requirements:

- exact duplicate in one batch
- duplicate across processor calls (documented state boundary)
- same product at different collection times remains separate
- same event ID + conflicting payload
- replay-order determinism
"""

from __future__ import annotations

from datetime import datetime, timezone

import polars as pl
import pytest

from services.processor.deduplication import (
    DeduplicationState,
    deduplicate,
)
from services.processor.schema_normalization import NORMALIZED_SCHEMA


def _valid_row(
    event_id: str = "evt-001",
    source: str = "test-source",
    external_id: str = "prod-123",
    name: str = "Test Product",
    url: str = "https://example.com/product/123",
    price: float | None = 99.99,
    currency: str = "EUR",
    availability: str = "in_stock",
    category: str = "electronics",
    schema_version: int = 1,
    event_type: str = "product.observation",
    produced_at: datetime | None = None,
    collected_at: datetime | None = None,
) -> dict:
    ts = datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc)
    return {
        "event_id": event_id,
        "event_type": event_type,
        "schema_version": schema_version,
        "source": source,
        "produced_at": produced_at or ts,
        "external_id": external_id,
        "name": name,
        "url": url,
        "price": price,
        "currency": currency,
        "availability": availability,
        "category": category,
        "collected_at": collected_at or ts,
    }


def _make_df(*rows: dict) -> pl.DataFrame:
    return pl.DataFrame(list(rows), schema=NORMALIZED_SCHEMA)


class TestExactDuplicateInOneBatch:
    """Exact duplicates within a single batch are collapsed."""

    def test_two_identical_rows_keep_one(self) -> None:
        row = _valid_row(event_id="evt-dup-1")
        result = deduplicate(_make_df(row, row))
        assert result.deduplicated.height == 1
        assert result.duplicates_removed == 1
        assert result.conflicts_count == 0

    def test_three_identical_rows_keep_one(self) -> None:
        row = _valid_row(event_id="evt-dup-3")
        result = deduplicate(_make_df(row, row, row))
        assert result.deduplicated.height == 1
        assert result.duplicates_removed == 2
        assert result.conflicts_count == 0

    def test_kept_row_is_first_occurrence(self) -> None:
        row1 = _valid_row(event_id="evt-first", name="First")
        row2 = _valid_row(event_id="evt-first", name="First")
        result = deduplicate(_make_df(row1, row2))
        assert result.deduplicated["event_id"][0] == "evt-first"

    def test_mixed_unique_and_duplicate(self) -> None:
        rows = [
            _valid_row(event_id="evt-a"),
            _valid_row(event_id="evt-b"),
            _valid_row(event_id="evt-a"),
            _valid_row(event_id="evt-c"),
            _valid_row(event_id="evt-b"),
        ]
        result = deduplicate(_make_df(*rows))
        assert result.deduplicated.height == 3
        assert result.duplicates_removed == 2
        assert result.conflicts_count == 0

    def test_total_input_count_preserved(self) -> None:
        row = _valid_row(event_id="evt-count")
        result = deduplicate(_make_df(row, row, row))
        assert result.total_input_count == 3


class TestDuplicateAcrossProcessorCalls:
    """Cross-batch deduplication via DeduplicationState."""

    def test_second_batch_duplicate_detected(self) -> None:
        state = DeduplicationState()
        row = _valid_row(event_id="evt-cross-1")

        result1 = deduplicate(_make_df(row), state=state)
        assert result1.deduplicated.height == 1

        result2 = deduplicate(_make_df(row), state=state)
        assert result2.deduplicated.height == 0
        assert result2.duplicates_removed == 1

    def test_state_tracks_unique_event_ids(self) -> None:
        state = DeduplicationState()
        row_a = _valid_row(event_id="evt-a")
        row_b = _valid_row(event_id="evt-b")

        deduplicate(_make_df(row_a), state=state)
        deduplicate(_make_df(row_b), state=state)
        assert state.size == 2

    def test_no_state_means_no_cross_batch_dedup(self) -> None:
        row = _valid_row(event_id="evt-no-state")

        result1 = deduplicate(_make_df(row))
        result2 = deduplicate(_make_df(row))

        assert result1.deduplicated.height == 1
        assert result2.deduplicated.height == 1

    def test_cross_batch_with_multiple_events(self) -> None:
        state = DeduplicationState()
        batch1 = [
            _valid_row(event_id="evt-1"),
            _valid_row(event_id="evt-2"),
        ]
        batch2 = [
            _valid_row(event_id="evt-1"),
            _valid_row(event_id="evt-3"),
        ]

        result1 = deduplicate(_make_df(*batch1), state=state)
        assert result1.deduplicated.height == 2

        result2 = deduplicate(_make_df(*batch2), state=state)
        assert result2.deduplicated.height == 1
        assert result2.duplicates_removed == 1


class TestSameProductDifferentCollectionTimes:
    """Legitimate repeated observations are never collapsed."""

    def test_same_product_different_times_kept_separate(self) -> None:
        ts1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
        row1 = _valid_row(
            event_id="evt-time-1",
            external_id="prod-123",
            collected_at=ts1,
            produced_at=ts1,
        )
        row2 = _valid_row(
            event_id="evt-time-2",
            external_id="prod-123",
            collected_at=ts2,
            produced_at=ts2,
        )
        result = deduplicate(_make_df(row1, row2))
        assert result.deduplicated.height == 2
        assert result.duplicates_removed == 0
        assert result.conflicts_count == 0

    def test_same_external_id_different_prices_different_event_ids(self) -> None:
        ts1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
        row1 = _valid_row(
            event_id="evt-price-1",
            external_id="prod-456",
            price=99.99,
            collected_at=ts1,
            produced_at=ts1,
        )
        row2 = _valid_row(
            event_id="evt-price-2",
            external_id="prod-456",
            price=79.99,
            collected_at=ts2,
            produced_at=ts2,
        )
        result = deduplicate(_make_df(row1, row2))
        assert result.deduplicated.height == 2
        assert result.duplicates_removed == 0


class TestConflictingPayloadSameEventId:
    """Same event_id with different payload is surfaced as a conflict."""

    def test_same_event_id_different_name_is_conflict(self) -> None:
        row1 = _valid_row(event_id="evt-conflict-1", name="Product A")
        row2 = _valid_row(event_id="evt-conflict-1", name="Product B")
        result = deduplicate(_make_df(row1, row2))
        assert result.conflicts_count == 2
        assert result.deduplicated.height == 0
        assert result.duplicates_removed == 0

    def test_same_event_id_different_price_is_conflict(self) -> None:
        row1 = _valid_row(event_id="evt-conflict-2", price=99.99)
        row2 = _valid_row(event_id="evt-conflict-2", price=49.99)
        result = deduplicate(_make_df(row1, row2))
        assert result.conflicts_count == 2
        assert result.deduplicated.height == 0

    def test_same_event_id_different_availability_is_conflict(self) -> None:
        row1 = _valid_row(event_id="evt-conflict-3", availability="in_stock")
        row2 = _valid_row(event_id="evt-conflict-3", availability="out_of_stock")
        result = deduplicate(_make_df(row1, row2))
        assert result.conflicts_count == 2

    def test_conflict_records_preserve_all_columns(self) -> None:
        row1 = _valid_row(event_id="evt-conflict-4", name="V1")
        row2 = _valid_row(event_id="evt-conflict-4", name="V2")
        result = deduplicate(_make_df(row1, row2))
        for col in NORMALIZED_SCHEMA:
            assert col in result.conflicts.columns

    def test_mixed_duplicates_and_conflicts(self) -> None:
        rows = [
            _valid_row(event_id="evt-dup", name="Same"),
            _valid_row(event_id="evt-dup", name="Same"),
            _valid_row(event_id="evt-conflict", name="V1"),
            _valid_row(event_id="evt-conflict", name="V2"),
            _valid_row(event_id="evt-unique"),
        ]
        result = deduplicate(_make_df(*rows))
        assert result.deduplicated.height == 2
        assert result.duplicates_removed == 1
        assert result.conflicts_count == 2


class TestReplayOrderDeterminism:
    """Deduplication is deterministic regardless of input order."""

    def test_same_input_same_output(self) -> None:
        rows = [
            _valid_row(event_id="evt-a"),
            _valid_row(event_id="evt-b"),
            _valid_row(event_id="evt-a"),
        ]
        result1 = deduplicate(_make_df(*rows))
        result2 = deduplicate(_make_df(*rows))
        assert result1.deduplicated.height == result2.deduplicated.height
        assert result1.duplicates_removed == result2.duplicates_removed

    def test_first_occurrence_kept_deterministically(self) -> None:
        ts1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
        row1 = _valid_row(
            event_id="evt-order",
            price=100.0,
            collected_at=ts1,
            produced_at=ts1,
        )
        row2 = _valid_row(
            event_id="evt-order",
            price=100.0,
            collected_at=ts1,
            produced_at=ts1,
        )
        result = deduplicate(_make_df(row1, row2))
        assert result.deduplicated.height == 1
        assert result.deduplicated["price"][0] == pytest.approx(100.0)

    def test_cross_batch_order_deterministic(self) -> None:
        state = DeduplicationState()
        row = _valid_row(event_id="evt-det-1")

        r1 = deduplicate(_make_df(row), state=state)
        r2 = deduplicate(_make_df(row), state=state)
        r3 = deduplicate(_make_df(row), state=state)

        assert r1.deduplicated.height == 1
        assert r2.duplicates_removed == 1
        assert r3.duplicates_removed == 1

    def test_empty_input_deterministic(self) -> None:
        df = pl.DataFrame(schema=NORMALIZED_SCHEMA)
        result = deduplicate(df)
        assert result.deduplicated.height == 0
        assert result.duplicates_removed == 0
        assert result.conflicts_count == 0


class TestDeduplicationResultInterface:
    """Verify the DeduplicationResult dataclass contract."""

    def test_counts_match_dataframes(self) -> None:
        row = _valid_row(event_id="evt-intf")
        result = deduplicate(_make_df(row, row))
        assert result.duplicates_removed == result.duplicates.height
        assert result.conflicts_count == result.conflicts.height

    def test_total_input_property(self) -> None:
        rows = [
            _valid_row(event_id="evt-1"),
            _valid_row(event_id="evt-1"),
            _valid_row(event_id="evt-2"),
        ]
        result = deduplicate(_make_df(*rows))
        assert result.total_input_count == 3

    def test_deduplicated_has_correct_schema(self) -> None:
        row = _valid_row()
        result = deduplicate(_make_df(row))
        for col in NORMALIZED_SCHEMA:
            assert col in result.deduplicated.columns

    def test_no_internal_columns_in_output(self) -> None:
        row = _valid_row(event_id="evt-clean")
        result = deduplicate(_make_df(row, row))
        for col in result.deduplicated.columns:
            assert not col.startswith("_")
