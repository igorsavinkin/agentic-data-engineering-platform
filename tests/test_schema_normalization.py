"""Unit tests for schema normalization module.

These tests verify that the ``normalize()`` function deterministically
transforms raw product-observation DataFrames into the canonical normalized
schema. Coverage includes:

- valid type normalization for all fields
- timestamp normalization (various timezone inputs → UTC)
- nullable fields (price=None stays None, not 0)
- malformed values remain detectable
- availability enum handling
- exact ID preservation (event_id, external_id unchanged)
- stable schema regardless of row order
- row count preservation (no silent dropping)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import polars as pl
import pytest

from libs.event_contracts import (
    Availability,
    ProductObservationEvent,
    ProductObservationPayload,
)
from services.processor.polars_transform import events_to_polars
from services.processor.schema_normalization import (
    NORMALIZED_SCHEMA,
    UTC_DATETIME,
    normalize,
)


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


def _events_to_df(*events: ProductObservationEvent) -> pl.DataFrame:
    return events_to_polars(list(events))


class TestNormalizedSchemaDefinition:
    """Verify the NORMALIZED_SCHEMA constant is well-formed."""

    def test_schema_has_all_expected_columns(self) -> None:
        expected = {
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
        }
        assert set(NORMALIZED_SCHEMA.keys()) == expected

    def test_timestamp_types_are_utc_datetime(self) -> None:
        assert NORMALIZED_SCHEMA["produced_at"] == UTC_DATETIME
        assert NORMALIZED_SCHEMA["collected_at"] == UTC_DATETIME

    def test_price_is_float64(self) -> None:
        assert NORMALIZED_SCHEMA["price"] == pl.Float64

    def test_schema_version_is_int64(self) -> None:
        assert NORMALIZED_SCHEMA["schema_version"] == pl.Int64


class TestValidTypeNormalization:
    """Verify all fields are cast to correct normalized types."""

    def test_output_schema_matches_normalized_schema(self) -> None:
        event = _make_event()
        df = _events_to_df(event)
        result = normalize(df)

        for col_name, expected_dtype in NORMALIZED_SCHEMA.items():
            actual_dtype = result.schema[col_name]
            assert actual_dtype == expected_dtype, (
                f"Column {col_name}: expected {expected_dtype}, got {actual_dtype}"
            )

    def test_output_column_order_matches_schema(self) -> None:
        event = _make_event()
        result = normalize(_events_to_df(event))
        assert result.columns == list(NORMALIZED_SCHEMA.keys())

    def test_string_fields_are_utf8(self) -> None:
        event = _make_event()
        result = normalize(_events_to_df(event))
        for col in [
            "event_id",
            "event_type",
            "source",
            "name",
            "url",
            "external_id",
            "currency",
            "availability",
            "category",
        ]:
            assert result.schema[col] == pl.Utf8

    def test_multi_event_schema_consistent(self) -> None:
        events = [_make_event(event_id=f"evt-{i}") for i in range(5)]
        result = normalize(_events_to_df(*events))
        for col_name, expected_dtype in NORMALIZED_SCHEMA.items():
            assert result.schema[col_name] == expected_dtype


class TestTimestampNormalization:
    """Verify timestamps are normalized to UTC Datetime("us", "UTC")."""

    def test_utc_timestamps_preserved(self) -> None:
        collected = datetime(2026, 9, 3, 7, 59, 30, tzinfo=timezone.utc)
        produced = datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc)
        event = _make_event(collected_at=collected, produced_at=produced)
        result = normalize(_events_to_df(event))

        assert result.schema["collected_at"] == UTC_DATETIME
        assert result.schema["produced_at"] == UTC_DATETIME

        assert result["collected_at"][0] == collected
        assert result["produced_at"][0] == produced

    def test_non_utc_timezone_converted_to_utc(self) -> None:
        tz_plus5 = timezone(timedelta(hours=5))
        collected = datetime(2026, 9, 3, 12, 59, 30, tzinfo=tz_plus5)
        produced = datetime(2026, 9, 3, 13, 0, 0, tzinfo=tz_plus5)
        event = _make_event(collected_at=collected, produced_at=produced)
        result = normalize(_events_to_df(event))

        expected_collected = collected.astimezone(timezone.utc)
        expected_produced = produced.astimezone(timezone.utc)

        assert result["collected_at"][0] == expected_collected
        assert result["produced_at"][0] == expected_produced

    def test_timestamp_dtype_has_utc_timezone(self) -> None:
        event = _make_event()
        result = normalize(_events_to_df(event))

        for col in ["produced_at", "collected_at"]:
            dtype = result.schema[col]
            assert isinstance(dtype, pl.Datetime)
            assert dtype.time_unit == "us"
            assert dtype.time_zone == "UTC"


class TestNullableFields:
    """Verify null handling — nulls propagate, not zero-filled."""

    def test_null_price_stays_null(self) -> None:
        event = _make_event(price=None)
        result = normalize(_events_to_df(event))
        assert result["price"][0] is None

    def test_null_price_not_zero(self) -> None:
        event = _make_event(price=None)
        result = normalize(_events_to_df(event))
        assert result["price"][0] != 0.0

    def test_mixed_null_and_valid_prices(self) -> None:
        events = [
            _make_event(event_id="evt-1", price=Decimal("10.00")),
            _make_event(event_id="evt-2", price=None),
            _make_event(event_id="evt-3", price=Decimal("20.50")),
        ]
        result = normalize(_events_to_df(*events))
        prices = result["price"].to_list()

        assert prices[0] == pytest.approx(10.00)
        assert prices[1] is None
        assert prices[2] == pytest.approx(20.50)

    def test_row_count_preserved_with_nulls(self) -> None:
        events = [
            _make_event(event_id=f"evt-{i}", price=None if i % 2 == 0 else Decimal("10.00"))
            for i in range(6)
        ]
        result = normalize(_events_to_df(*events))
        assert result.height == 6


class TestMalformedValuesDetectable:
    """Verify that malformed/unparseable values remain detectable."""

    def test_non_numeric_price_becomes_null_not_zero(self) -> None:
        df = pl.DataFrame(
            {
                "event_id": ["evt-bad"],
                "event_type": ["product.observation"],
                "schema_version": [1],
                "source": ["test"],
                "produced_at": [datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc)],
                "external_id": ["prod-bad"],
                "name": ["Bad Price Product"],
                "url": ["https://example.com/bad"],
                "price": ["not-a-number"],
                "currency": ["EUR"],
                "availability": ["in_stock"],
                "category": ["test"],
                "collected_at": [datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc)],
            }
        )
        result = normalize(df)

        assert result.height == 1
        assert result["price"][0] is None
        assert result["price"][0] != 0.0

    def test_row_preserved_when_price_unparseable(self) -> None:
        df = pl.DataFrame(
            {
                "event_id": ["evt-x"],
                "event_type": ["product.observation"],
                "schema_version": [1],
                "source": ["test"],
                "produced_at": [datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc)],
                "external_id": ["prod-x"],
                "name": ["Product X"],
                "url": ["https://example.com/x"],
                "price": ["$$$"],
                "currency": ["USD"],
                "availability": ["in_stock"],
                "category": ["test"],
                "collected_at": [datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc)],
            }
        )
        result = normalize(df)

        assert result.height == 1
        assert result["event_id"][0] == "evt-x"
        assert result["price"][0] is None

    def test_mixed_valid_and_invalid_prices(self) -> None:
        df = pl.DataFrame(
            {
                "event_id": ["evt-1", "evt-2", "evt-3"],
                "event_type": ["product.observation"] * 3,
                "schema_version": [1, 1, 1],
                "source": ["test"] * 3,
                "produced_at": [datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc)] * 3,
                "external_id": ["p1", "p2", "p3"],
                "name": ["A", "B", "C"],
                "url": ["https://a.com", "https://b.com", "https://c.com"],
                "price": ["10.0", "free", None],
                "currency": ["USD", "USD", "USD"],
                "availability": ["in_stock", "in_stock", "in_stock"],
                "category": ["cat"] * 3,
                "collected_at": [datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc)] * 3,
            }
        )
        result = normalize(df)

        assert result.height == 3
        prices = result["price"].to_list()
        assert prices[0] == pytest.approx(10.0)
        assert prices[1] is None
        assert prices[2] is None


class TestAvailabilityEnumHandling:
    """Verify availability normalization."""

    def test_valid_availability_values_pass_through(self) -> None:
        for avail in ["in_stock", "out_of_stock", "preorder", "unknown"]:
            event = _make_event(availability=Availability(avail))
            result = normalize(_events_to_df(event))
            assert result["availability"][0] == avail

    def test_availability_whitespace_stripped(self) -> None:
        event = _make_event()
        df = _events_to_df(event)
        df = df.with_columns(pl.lit("  in_stock  ").alias("availability"))
        result = normalize(df)
        assert result["availability"][0] == "in_stock"

    def test_availability_uppercased_normalized_to_lower(self) -> None:
        event = _make_event()
        df = _events_to_df(event)
        df = df.with_columns(pl.lit("IN_STOCK").alias("availability"))
        result = normalize(df)
        assert result["availability"][0] == "in_stock"

    def test_invalid_availability_preserved_for_validation(self) -> None:
        event = _make_event()
        df = _events_to_df(event)
        df = df.with_columns(pl.lit("discontinued").alias("availability"))
        result = normalize(df)

        assert result.height == 1
        assert result["availability"][0] == "discontinued"


class TestExactIDPreservation:
    """Verify semantic IDs and URLs are NOT modified by normalize()."""

    def _raw_df(self, **overrides: str) -> pl.DataFrame:
        base = {
            "event_id": "evt-001",
            "event_type": "product.observation",
            "schema_version": 1,
            "source": "test",
            "produced_at": datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc),
            "external_id": "prod-123",
            "name": "Product",
            "url": "https://example.com/p",
            "price": 10.0,
            "currency": "USD",
            "availability": "in_stock",
            "category": "cat",
            "collected_at": datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc),
        }
        base.update(overrides)
        return pl.DataFrame([base])

    def test_event_id_not_stripped(self) -> None:
        df = self._raw_df(event_id="  evt-with-spaces  ")
        result = normalize(df)
        assert result["event_id"][0] == "  evt-with-spaces  "

    def test_external_id_not_stripped(self) -> None:
        df = self._raw_df(external_id="  PROD-123  ")
        result = normalize(df)
        assert result["external_id"][0] == "  PROD-123  "

    def test_url_not_stripped(self) -> None:
        df = self._raw_df(url="  https://example.com/product  ")
        result = normalize(df)
        assert result["url"][0] == "  https://example.com/product  "

    def test_event_id_exact_value(self) -> None:
        df = self._raw_df(event_id="unique-id-42")
        result = normalize(df)
        assert result["event_id"][0] == "unique-id-42"

    def test_external_id_exact_value(self) -> None:
        df = self._raw_df(external_id="BB-98765")
        result = normalize(df)
        assert result["external_id"][0] == "BB-98765"


class TestWhitespaceStripping:
    """Verify that non-ID string fields are stripped."""

    def test_name_stripped(self) -> None:
        event = _make_event(name="  Widget Pro  ")
        result = normalize(_events_to_df(event))
        assert result["name"][0] == "Widget Pro"

    def test_category_stripped(self) -> None:
        event = _make_event(category="  home & garden  ")
        result = normalize(_events_to_df(event))
        assert result["category"][0] == "home & garden"

    def test_currency_stripped(self) -> None:
        event = _make_event(currency=" USD ")
        result = normalize(_events_to_df(event))
        assert result["currency"][0] == "USD"

    def test_source_stripped(self) -> None:
        event = _make_event(source="  bestbuy  ")
        result = normalize(_events_to_df(event))
        assert result["source"][0] == "bestbuy"

    def test_event_type_stripped(self) -> None:
        event = _make_event()
        df = _events_to_df(event)
        df = df.with_columns(pl.lit("  product.observation  ").alias("event_type"))
        result = normalize(df)
        assert result["event_type"][0] == "product.observation"


class TestRowCountPreservation:
    """Verify no silent row dropping."""

    def test_empty_input_returns_zero_rows(self) -> None:
        df = events_to_polars([])
        result = normalize(df)
        assert result.height == 0

    def test_single_row_preserved(self) -> None:
        result = normalize(_events_to_df(_make_event()))
        assert result.height == 1

    def test_multi_row_count_matches_input(self) -> None:
        events = [_make_event(event_id=f"evt-{i}") for i in range(10)]
        result = normalize(_events_to_df(*events))
        assert result.height == 10

    def test_rows_with_all_null_prices_preserved(self) -> None:
        events = [_make_event(event_id=f"evt-{i}", price=None) for i in range(5)]
        result = normalize(_events_to_df(*events))
        assert result.height == 5


class TestStableSchemaRegardlessOfRowOrder:
    """Verify the output schema is stable regardless of input row ordering."""

    def test_same_schema_different_input_order(self) -> None:
        events_a = [
            _make_event(event_id="evt-1", price=Decimal("10.00")),
            _make_event(event_id="evt-2", price=None),
        ]
        events_b = [
            _make_event(event_id="evt-2", price=None),
            _make_event(event_id="evt-1", price=Decimal("10.00")),
        ]

        result_a = normalize(_events_to_df(*events_a))
        result_b = normalize(_events_to_df(*events_b))

        assert result_a.schema == result_b.schema
        assert result_a.columns == result_b.columns

    def test_schema_stable_with_mixed_types(self) -> None:
        events = [
            _make_event(event_id="evt-1", price=Decimal("0.01")),
            _make_event(event_id="evt-2", price=None),
            _make_event(event_id="evt-3", price=Decimal("99999.99")),
        ]
        result = normalize(_events_to_df(*events))

        for col_name, expected_dtype in NORMALIZED_SCHEMA.items():
            assert result.schema[col_name] == expected_dtype


class TestSchemaVersionPreservation:
    """Verify schema_version is preserved as Int64."""

    def test_schema_version_value_preserved(self) -> None:
        event = _make_event()
        result = normalize(_events_to_df(event))
        assert result["schema_version"][0] == 1

    def test_schema_version_type_is_int64(self) -> None:
        event = _make_event()
        result = normalize(_events_to_df(event))
        assert result.schema["schema_version"] == pl.Int64


class TestEmptyInput:
    """Verify empty DataFrame handling."""

    def test_empty_dataframe_has_correct_schema(self) -> None:
        df = events_to_polars([])
        result = normalize(df)

        assert result.height == 0
        for col_name, expected_dtype in NORMALIZED_SCHEMA.items():
            assert result.schema[col_name] == expected_dtype

    def test_empty_dataframe_column_order(self) -> None:
        df = events_to_polars([])
        result = normalize(df)
        assert result.columns == list(NORMALIZED_SCHEMA.keys())
