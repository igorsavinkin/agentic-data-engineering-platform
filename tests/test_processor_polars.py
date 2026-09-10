"""Unit tests for processor Polars transformation module.

These tests verify that canonical ``ProductObservationEvent`` instances are
correctly converted into Polars DataFrames while preserving all identifiers,
timestamps, and optional fields. The tests cover:

- single event to Polars row/DataFrame
- multi-event deterministic schema/columns
- exact identifier/timestamp preservation
- nullable/optional fields (null price)
- empty input handling
- deterministic behavior / no input mutation
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from libs.event_contracts import (
    Availability,
    ProductObservationEvent,
    ProductObservationPayload,
)
from services.processor.polars_transform import events_to_polars


def _make_event(
    event_id: str = "evt-001",
    source: str = "test-source",
    external_id: str = "prod-123",
    name: str = "Test Product",
    url: str = "https://example.com/product/123",
    price: Decimal | None = Decimal("99.99"),
    currency: str = "EUR",
    availability: Availability = Availability.IN_STOCK,
    category: str = "electronics",
    collected_at: datetime | None = None,
    produced_at: datetime | None = None,
) -> ProductObservationEvent:
    """Helper to construct a valid test event with sensible defaults."""
    ts_collected = collected_at or datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc)
    ts_produced = produced_at or datetime(2026, 9, 3, 8, 1, 0, tzinfo=timezone.utc)
    return ProductObservationEvent(
        event_id=event_id,
        event_type="product.observation",
        schema_version=1,
        source=source,
        produced_at=ts_produced,
        payload=ProductObservationPayload(
            external_id=external_id,
            name=name,
            url=url,
            price=price,
            currency=currency,
            availability=availability,
            category=category,
            collected_at=ts_collected,
        ),
    )


class TestSingleEventToPolars:
    """Tests for converting a single canonical event to a Polars DataFrame."""

    def test_single_event_creates_dataframe_with_correct_columns(self) -> None:
        event = _make_event()
        df = events_to_polars([event])

        expected_columns = [
            "event_id",
            "event_type",
            "schema_version",
            "source",
            "produced_at",
            "external_id",
            "name",
            "url",
            "price",
            "currency",
            "availability",
            "category",
            "collected_at",
        ]
        assert df.columns == expected_columns

    def test_single_event_row_count(self) -> None:
        event = _make_event()
        df = events_to_polars([event])
        assert df.height == 1

    def test_single_event_preserves_event_id(self) -> None:
        event = _make_event(event_id="unique-evt-42")
        df = events_to_polars([event])
        assert df["event_id"][0] == "unique-evt-42"

    def test_single_event_preserves_source(self) -> None:
        event = _make_event(source="bestbuy-api")
        df = events_to_polars([event])
        assert df["source"][0] == "bestbuy-api"

    def test_single_event_preserves_external_id(self) -> None:
        event = _make_event(external_id="BB-98765")
        df = events_to_polars([event])
        assert df["external_id"][0] == "BB-98765"

    def test_single_event_preserves_timestamps(self) -> None:
        collected = datetime(2026, 9, 3, 7, 59, 30, tzinfo=timezone.utc)
        produced = datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc)
        event = _make_event(collected_at=collected, produced_at=produced)
        df = events_to_polars([event])

        assert df["collected_at"][0] == collected
        assert df["produced_at"][0] == produced

    def test_single_event_preserves_price(self) -> None:
        event = _make_event(price=Decimal("149.99"))
        df = events_to_polars([event])
        assert df["price"][0] == pytest.approx(149.99)

    def test_single_event_preserves_currency(self) -> None:
        event = _make_event(currency="USD")
        df = events_to_polars([event])
        assert df["currency"][0] == "USD"

    def test_single_event_preserves_availability(self) -> None:
        event = _make_event(availability=Availability.OUT_OF_STOCK)
        df = events_to_polars([event])
        assert df["availability"][0] == "out_of_stock"


class TestMultiEventDeterministicSchema:
    """Tests for converting multiple events with deterministic column ordering."""

    def test_multi_event_column_order_is_deterministic(self) -> None:
        events = [_make_event(event_id=f"evt-{i}", external_id=f"prod-{i}") for i in range(3)]
        df = events_to_polars(events)

        expected_columns = [
            "event_id",
            "event_type",
            "schema_version",
            "source",
            "produced_at",
            "external_id",
            "name",
            "url",
            "price",
            "currency",
            "availability",
            "category",
            "collected_at",
        ]
        assert df.columns == expected_columns

    def test_multi_event_row_count_matches_input(self) -> None:
        events = [_make_event(event_id=f"evt-{i}") for i in range(5)]
        df = events_to_polars(events)
        assert df.height == 5

    def test_multi_event_preserves_all_event_ids(self) -> None:
        event_ids = ["evt-a", "evt-b", "evt-c"]
        events = [_make_event(event_id=eid) for eid in event_ids]
        df = events_to_polars(events)

        result_ids = df["event_id"].to_list()
        assert result_ids == event_ids

    def test_multi_event_mixed_sources(self) -> None:
        events = [
            _make_event(event_id="evt-1", source="fakestore"),
            _make_event(event_id="evt-2", source="bestbuy"),
        ]
        df = events_to_polars(events)

        sources = df["source"].to_list()
        assert sources == ["fakestore", "bestbuy"]


class TestIdentifierAndTimestampPreservation:
    """Tests ensuring exact preservation of critical identifiers and timestamps."""

    def test_external_id_not_confused_with_platform_id(self) -> None:
        """Verify external_id is preserved distinctly from any platform ID."""
        event = _make_event(external_id="source-specific-12345")
        df = events_to_polars([event])
        assert df["external_id"][0] == "source-specific-12345"

    def test_collected_at_distinct_from_produced_at(self) -> None:
        """Ensure collected_at and produced_at remain separate fields."""
        collected = datetime(2026, 9, 3, 7, 59, 30, tzinfo=timezone.utc)
        produced = datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc)
        event = _make_event(collected_at=collected, produced_at=produced)
        df = events_to_polars([event])

        assert df["collected_at"][0] != df["produced_at"][0]
        assert df["collected_at"][0] == collected
        assert df["produced_at"][0] == produced

    def test_schema_version_preserved(self) -> None:
        event = _make_event()
        df = events_to_polars([event])
        assert df["schema_version"][0] == 1


class TestNullableAndOptionalFields:
    """Tests for nullable fields, particularly price."""

    def test_null_price_preserved_as_none(self) -> None:
        event = _make_event(price=None)
        df = events_to_polars([event])
        assert df["price"][0] is None

    def test_mixed_null_and_non_null_prices(self) -> None:
        events = [
            _make_event(event_id="evt-1", price=Decimal("10.00")),
            _make_event(event_id="evt-2", price=None),
            _make_event(event_id="evt-3", price=Decimal("20.50")),
        ]
        df = events_to_polars(events)

        prices = df["price"].to_list()
        assert prices[0] == pytest.approx(10.00)
        assert prices[1] is None
        assert prices[2] == pytest.approx(20.50)


class TestEmptyInput:
    """Tests for empty input handling."""

    def test_empty_list_returns_zero_row_dataframe(self) -> None:
        df = events_to_polars([])
        assert df.height == 0

    def test_empty_list_has_correct_schema(self) -> None:
        df = events_to_polars([])

        expected_columns = [
            "event_id",
            "event_type",
            "schema_version",
            "source",
            "produced_at",
            "external_id",
            "name",
            "url",
            "price",
            "currency",
            "availability",
            "category",
            "collected_at",
        ]
        assert df.columns == expected_columns


class TestDeterministicBehavior:
    """Tests ensuring deterministic behavior and no input mutation."""

    def test_no_input_mutation(self) -> None:
        """Verify the function does not mutate input events."""
        event = _make_event()
        original_event_dict = event.model_dump()

        events = [event]
        events_to_polars(events)

        assert event.model_dump() == original_event_dict

    def test_deterministic_output_for_same_input(self) -> None:
        """Multiple calls with same input produce identical DataFrames."""
        events = [
            _make_event(event_id="evt-1"),
            _make_event(event_id="evt-2"),
        ]

        df1 = events_to_polars(events)
        df2 = events_to_polars(events)

        assert df1.equals(df2)

    def test_deep_copy_input_not_mutated(self) -> None:
        """Even with deep-copied events, original remains unchanged."""
        event = _make_event()
        event_copy = copy.deepcopy(event)

        events_to_polars([event])

        assert event.model_dump() == event_copy.model_dump()
