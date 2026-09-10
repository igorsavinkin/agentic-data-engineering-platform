"""Unit tests for data-quality validation.

These tests verify that ``validate()`` deterministically splits a normalized
DataFrame into valid and invalid records with full diagnostic context.
Coverage per TASK-015 requirements:

- missing required field
- invalid price (negative)
- invalid timestamp (null)
- invalid availability
- unsupported schema version
- multiple simultaneous failures
- valid record path
- diagnostic context preserved
- empty input
- row count preservation (no silent drops)
"""

from __future__ import annotations

from datetime import datetime, timezone

import polars as pl
import pytest

from services.processor.data_validation import validate
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


class TestValidRecordPath:
    """A fully valid record passes through unchanged."""

    def test_single_valid_record(self) -> None:
        result = validate(_make_df(_valid_row()))
        assert result.valid_count == 1
        assert result.invalid_count == 0
        assert result.total_count == 1

    def test_valid_record_preserves_all_fields(self) -> None:
        row = _valid_row(event_id="evt-42", source="bestbuy", price=149.99)
        result = validate(_make_df(row))
        assert result.valid["event_id"][0] == "evt-42"
        assert result.valid["source"][0] == "bestbuy"
        assert result.valid["price"][0] == pytest.approx(149.99)

    def test_multiple_valid_records(self) -> None:
        rows = [_valid_row(event_id=f"evt-{i}") for i in range(5)]
        result = validate(_make_df(*rows))
        assert result.valid_count == 5
        assert result.invalid_count == 0

    def test_null_price_is_valid(self) -> None:
        """Null price is allowed (source may not provide a price)."""
        result = validate(_make_df(_valid_row(price=None)))
        assert result.valid_count == 1
        assert result.invalid_count == 0

    def test_valid_schema_has_no_errors_column(self) -> None:
        result = validate(_make_df(_valid_row()))
        assert "_validation_errors" not in result.valid.columns


class TestMissingRequiredField:
    """Rows with null required fields are flagged."""

    def test_null_event_id(self) -> None:
        row = _valid_row()
        row["event_id"] = None
        result = validate(_make_df(row))
        assert result.invalid_count == 1
        assert "null_required:event_id" in result.invalid["_validation_errors"][0]

    def test_null_source(self) -> None:
        row = _valid_row()
        row["source"] = None
        result = validate(_make_df(row))
        assert result.invalid_count == 1
        assert "null_required:source" in result.invalid["_validation_errors"][0]

    def test_null_external_id(self) -> None:
        row = _valid_row()
        row["external_id"] = None
        result = validate(_make_df(row))
        assert result.invalid_count == 1
        assert "null_required:external_id" in result.invalid["_validation_errors"][0]

    def test_null_name(self) -> None:
        row = _valid_row()
        row["name"] = None
        result = validate(_make_df(row))
        assert result.invalid_count == 1
        assert "null_required:name" in result.invalid["_validation_errors"][0]

    def test_null_url(self) -> None:
        row = _valid_row()
        row["url"] = None
        result = validate(_make_df(row))
        assert result.invalid_count == 1
        assert "null_required:url" in result.invalid["_validation_errors"][0]

    def test_null_currency(self) -> None:
        row = _valid_row()
        row["currency"] = None
        result = validate(_make_df(row))
        assert result.invalid_count == 1
        assert "null_required:currency" in result.invalid["_validation_errors"][0]

    def test_null_availability(self) -> None:
        row = _valid_row()
        row["availability"] = None
        result = validate(_make_df(row))
        assert result.invalid_count == 1
        assert "null_required:availability" in result.invalid["_validation_errors"][0]

    def test_null_category(self) -> None:
        row = _valid_row()
        row["category"] = None
        result = validate(_make_df(row))
        assert result.invalid_count == 1
        assert "null_required:category" in result.invalid["_validation_errors"][0]


class TestInvalidPrice:
    """Price semantics: negative prices are rejected."""

    def test_negative_price(self) -> None:
        result = validate(_make_df(_valid_row(price=-10.0)))
        assert result.invalid_count == 1
        assert "negative_price" in result.invalid["_validation_errors"][0]

    def test_zero_price_is_valid(self) -> None:
        """Zero is a valid price (free product)."""
        result = validate(_make_df(_valid_row(price=0.0)))
        assert result.valid_count == 1
        assert result.invalid_count == 0

    def test_positive_price_is_valid(self) -> None:
        result = validate(_make_df(_valid_row(price=0.01)))
        assert result.valid_count == 1

    def test_null_price_is_valid(self) -> None:
        result = validate(_make_df(_valid_row(price=None)))
        assert result.valid_count == 1


class TestInvalidTimestamp:
    """Null timestamps are rejected."""

    def test_null_produced_at(self) -> None:
        row = _valid_row()
        row["produced_at"] = None
        result = validate(_make_df(row))
        assert result.invalid_count == 1
        assert "null_required:produced_at" in result.invalid["_validation_errors"][0]

    def test_null_collected_at(self) -> None:
        row = _valid_row()
        row["collected_at"] = None
        result = validate(_make_df(row))
        assert result.invalid_count == 1
        assert "null_required:collected_at" in result.invalid["_validation_errors"][0]

    def test_both_timestamps_null(self) -> None:
        row = _valid_row()
        row["produced_at"] = None
        row["collected_at"] = None
        result = validate(_make_df(row))
        errors = result.invalid["_validation_errors"][0]
        assert "null_required:produced_at" in errors
        assert "null_required:collected_at" in errors


class TestInvalidAvailability:
    """Non-canonical availability values are rejected."""

    def test_invalid_availability_value(self) -> None:
        result = validate(_make_df(_valid_row(availability="discontinued")))
        assert result.invalid_count == 1
        assert "invalid_availability" in result.invalid["_validation_errors"][0]

    def test_empty_string_availability(self) -> None:
        result = validate(_make_df(_valid_row(availability="")))
        assert result.invalid_count == 1
        assert "invalid_availability" in result.invalid["_validation_errors"][0]

    @pytest.mark.parametrize(
        "avail",
        ["in_stock", "out_of_stock", "preorder", "unknown"],
    )
    def test_all_valid_availability_values(self, avail: str) -> None:
        result = validate(_make_df(_valid_row(availability=avail)))
        assert result.valid_count == 1


class TestUnsupportedSchemaVersion:
    """Schema versions outside SUPPORTED_SCHEMA_VERSIONS are rejected."""

    def test_unsupported_schema_version(self) -> None:
        result = validate(_make_df(_valid_row(schema_version=99)))
        assert result.invalid_count == 1
        assert "unsupported_schema_version" in result.invalid["_validation_errors"][0]

    def test_zero_schema_version(self) -> None:
        result = validate(_make_df(_valid_row(schema_version=0)))
        assert result.invalid_count == 1
        assert "unsupported_schema_version" in result.invalid["_validation_errors"][0]

    def test_supported_schema_version(self) -> None:
        result = validate(_make_df(_valid_row(schema_version=1)))
        assert result.valid_count == 1


class TestInvalidCurrency:
    """Currency must match three uppercase ASCII letters."""

    def test_lowercase_currency(self) -> None:
        result = validate(_make_df(_valid_row(currency="eur")))
        assert result.invalid_count == 1
        assert "invalid_currency_format" in result.invalid["_validation_errors"][0]

    def test_too_long_currency(self) -> None:
        result = validate(_make_df(_valid_row(currency="EURO")))
        assert result.invalid_count == 1
        assert "invalid_currency_format" in result.invalid["_validation_errors"][0]

    def test_numeric_currency(self) -> None:
        result = validate(_make_df(_valid_row(currency="123")))
        assert result.invalid_count == 1
        assert "invalid_currency_format" in result.invalid["_validation_errors"][0]

    def test_valid_currency(self) -> None:
        for code in ["USD", "EUR", "GBP", "JPY"]:
            result = validate(_make_df(_valid_row(currency=code)))
            assert result.valid_count == 1, f"Currency {code} should be valid"


class TestMultipleSimultaneousFailures:
    """Rows with multiple violations report all of them."""

    def test_multiple_errors_collected(self) -> None:
        row = _valid_row()
        row["price"] = -5.0
        row["availability"] = "discontinued"
        row["schema_version"] = 99
        result = validate(_make_df(row))
        assert result.invalid_count == 1
        errors = result.invalid["_validation_errors"][0]
        assert "negative_price" in errors
        assert "invalid_availability" in errors
        assert "unsupported_schema_version" in errors

    def test_null_fields_and_bad_values(self) -> None:
        row = _valid_row()
        row["source"] = None
        row["price"] = -1.0
        row["currency"] = "bad"
        result = validate(_make_df(row))
        assert result.invalid_count == 1
        errors = result.invalid["_validation_errors"][0]
        assert "null_required:source" in errors
        assert "negative_price" in errors
        assert "invalid_currency_format" in errors

    def test_fully_invalid_row(self) -> None:
        """A row that fails every rule still produces exactly one invalid row."""
        row = _valid_row()
        row["event_id"] = None
        row["source"] = None
        row["external_id"] = None
        row["name"] = None
        row["url"] = None
        row["price"] = -100.0
        row["currency"] = "xx"
        row["availability"] = "bad"
        row["category"] = None
        row["schema_version"] = 0
        row["produced_at"] = None
        row["collected_at"] = None
        result = validate(_make_df(row))
        assert result.invalid_count == 1
        assert result.valid_count == 0
        errors = result.invalid["_validation_errors"][0]
        assert errors.count(";") >= 5


class TestDiagnosticContextPreserved:
    """Invalid records retain identity fields for diagnostics."""

    def test_event_id_preserved_in_invalid(self) -> None:
        row = _valid_row(event_id="evt-diag-42")
        row["price"] = -1.0
        result = validate(_make_df(row))
        assert result.invalid["event_id"][0] == "evt-diag-42"

    def test_source_preserved_in_invalid(self) -> None:
        row = _valid_row(source="bestbuy")
        row["availability"] = "bad"
        result = validate(_make_df(row))
        assert result.invalid["source"][0] == "bestbuy"

    def test_external_id_preserved_in_invalid(self) -> None:
        row = _valid_row(external_id="BB-98765")
        row["schema_version"] = 99
        result = validate(_make_df(row))
        assert result.invalid["external_id"][0] == "BB-98765"

    def test_invalid_record_has_all_original_columns(self) -> None:
        row = _valid_row()
        row["price"] = -1.0
        result = validate(_make_df(row))
        for col in NORMALIZED_SCHEMA:
            assert col in result.invalid.columns


class TestRowCountPreservation:
    """No record is silently dropped."""

    def test_all_valid_preserves_count(self) -> None:
        rows = [_valid_row(event_id=f"evt-{i}") for i in range(10)]
        result = validate(_make_df(*rows))
        assert result.total_count == 10
        assert result.valid_count == 10

    def test_all_invalid_preserves_count(self) -> None:
        rows = []
        for i in range(5):
            row = _valid_row(event_id=f"evt-{i}")
            row["price"] = -1.0
            rows.append(row)
        result = validate(_make_df(*rows))
        assert result.total_count == 5
        assert result.invalid_count == 5

    def test_mixed_preserves_count(self) -> None:
        rows = [
            _valid_row(event_id="evt-1"),
            _valid_row(event_id="evt-2", price=-1.0),
            _valid_row(event_id="evt-3"),
            _valid_row(event_id="evt-4", availability="bad"),
            _valid_row(event_id="evt-5"),
        ]
        result = validate(_make_df(*rows))
        assert result.total_count == 5
        assert result.valid_count == 3
        assert result.invalid_count == 2


class TestEmptyInput:
    """Empty DataFrame produces empty valid and invalid results."""

    def test_empty_dataframe(self) -> None:
        df = pl.DataFrame(schema=NORMALIZED_SCHEMA)
        result = validate(df)
        assert result.valid_count == 0
        assert result.invalid_count == 0
        assert result.total_count == 0

    def test_empty_valid_schema(self) -> None:
        df = pl.DataFrame(schema=NORMALIZED_SCHEMA)
        result = validate(df)
        for col, dtype in NORMALIZED_SCHEMA.items():
            assert result.valid.schema[col] == dtype


class TestValidationResultInterface:
    """Verify the ValidationResult dataclass contract."""

    def test_counts_match_dataframes(self) -> None:
        rows = [
            _valid_row(event_id="evt-1"),
            _valid_row(event_id="evt-2", price=-1.0),
        ]
        result = validate(_make_df(*rows))
        assert result.valid_count == result.valid.height
        assert result.invalid_count == result.invalid.height

    def test_total_count_property(self) -> None:
        rows = [_valid_row(event_id=f"evt-{i}") for i in range(7)]
        result = validate(_make_df(*rows))
        assert result.total_count == 7

    def test_invalid_has_errors_column(self) -> None:
        row = _valid_row()
        row["price"] = -1.0
        result = validate(_make_df(row))
        assert "_validation_errors" in result.invalid.columns

    def test_valid_has_no_errors_column(self) -> None:
        result = validate(_make_df(_valid_row()))
        assert "_validation_errors" not in result.valid.columns
