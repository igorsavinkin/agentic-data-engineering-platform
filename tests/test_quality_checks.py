"""Tests for libs.quality.checks — concrete quality-check implementations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import polars as pl

from libs.quality.checks import (
    AllowedValuesCheck,
    DuplicateCheck,
    FreshnessCheck,
    PriceValidityCheck,
    RequiredFieldsCheck,
)
from libs.quality.models import CheckSeverity, CheckStatus


def _sample_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "event_id": ["e1", "e2", "e3"],
            "source": ["fake_store", "fake_store", "best_buy"],
            "price": [10.0, 20.0, 30.0],
            "availability": ["in_stock", "out_of_stock", "preorder"],
            "category": ["electronics", "books", "electronics"],
            "collected_at": [
                datetime(2026, 9, 17, 10, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 9, 17, 10, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 9, 17, 10, 0, 0, tzinfo=timezone.utc),
            ],
        }
    )


class TestRequiredFieldsCheck:
    def test_all_present(self) -> None:
        df = _sample_df()
        check = RequiredFieldsCheck(columns=["event_id", "source", "price"])
        result = check.run(df)
        assert result.status == CheckStatus.PASSED
        assert result.failed_records == 0
        assert result.records_checked == 3

    def test_null_detected(self) -> None:
        df = _sample_df().with_columns(pl.Series("source", ["fake_store", None, "best_buy"]))
        check = RequiredFieldsCheck(columns=["event_id", "source"])
        result = check.run(df)
        assert result.status == CheckStatus.FAILED
        assert result.failed_records == 1
        assert "source" in result.details["null_counts_by_column"]

    def test_multiple_null_columns(self) -> None:
        df = pl.DataFrame(
            {
                "a": [None, "x", None],
                "b": ["y", None, "z"],
            }
        )
        check = RequiredFieldsCheck(columns=["a", "b"])
        result = check.run(df)
        assert result.status == CheckStatus.FAILED
        assert result.details["null_counts_by_column"]["a"] == 2
        assert result.details["null_counts_by_column"]["b"] == 1
        assert result.failed_records == 3

    def test_missing_column(self) -> None:
        df = _sample_df()
        check = RequiredFieldsCheck(columns=["nonexistent"])
        result = check.run(df)
        assert result.status == CheckStatus.FAILED
        assert "nonexistent" in result.details["missing_columns"]

    def test_empty_dataframe(self) -> None:
        df = pl.DataFrame({"a": pl.Series([], dtype=pl.Utf8)})
        check = RequiredFieldsCheck(columns=["a"])
        result = check.run(df)
        assert result.status == CheckStatus.PASSED
        assert result.records_checked == 0

    def test_custom_severity(self) -> None:
        df = _sample_df().with_columns(pl.Series("source", [None, None, None]))
        check = RequiredFieldsCheck(columns=["source"], severity=CheckSeverity.WARNING)
        result = check.run(df)
        assert result.severity == CheckSeverity.WARNING


class TestPriceValidityCheck:
    def test_all_valid(self) -> None:
        df = _sample_df()
        check = PriceValidityCheck()
        result = check.run(df)
        assert result.status == CheckStatus.PASSED

    def test_negative_price(self) -> None:
        df = _sample_df().with_columns(pl.Series("price", [10.0, -5.0, 30.0]))
        check = PriceValidityCheck()
        result = check.run(df)
        assert result.status == CheckStatus.FAILED
        assert result.failed_records == 1
        assert result.details["below_min_count"] == 1

    def test_null_price_ignored(self) -> None:
        df = _sample_df().with_columns(pl.Series("price", [10.0, None, 30.0], dtype=pl.Float64))
        check = PriceValidityCheck()
        result = check.run(df)
        assert result.status == CheckStatus.PASSED

    def test_max_price(self) -> None:
        df = _sample_df()
        check = PriceValidityCheck(max_price=25.0)
        result = check.run(df)
        assert result.status == CheckStatus.FAILED
        assert result.failed_records == 1
        assert result.details["above_max_count"] == 1

    def test_missing_column(self) -> None:
        df = pl.DataFrame({"other": [1, 2, 3]})
        check = PriceValidityCheck()
        result = check.run(df)
        assert result.status == CheckStatus.FAILED
        assert result.details["missing_column"] == "price"

    def test_empty_dataframe(self) -> None:
        df = pl.DataFrame({"price": pl.Series([], dtype=pl.Float64)})
        check = PriceValidityCheck()
        result = check.run(df)
        assert result.status == CheckStatus.PASSED

    def test_custom_column(self) -> None:
        df = pl.DataFrame({"amount": [10.0, -1.0, 5.0]})
        check = PriceValidityCheck(price_column="amount")
        result = check.run(df)
        assert result.status == CheckStatus.FAILED
        assert result.failed_records == 1


class TestAllowedValuesCheck:
    def test_all_allowed(self) -> None:
        df = _sample_df()
        check = AllowedValuesCheck(
            column="availability",
            allowed_values=frozenset({"in_stock", "out_of_stock", "preorder", "unknown"}),
        )
        result = check.run(df)
        assert result.status == CheckStatus.PASSED

    def test_disallowed_value(self) -> None:
        df = _sample_df().with_columns(
            pl.Series("availability", ["in_stock", "discontinued", "preorder"])
        )
        check = AllowedValuesCheck(
            column="availability",
            allowed_values=frozenset({"in_stock", "out_of_stock", "preorder", "unknown"}),
        )
        result = check.run(df)
        assert result.status == CheckStatus.FAILED
        assert result.failed_records == 1
        assert "discontinued" in result.details["disallowed_values_found"]

    def test_missing_column(self) -> None:
        df = _sample_df()
        check = AllowedValuesCheck(column="nonexistent", allowed_values=frozenset({"a", "b"}))
        result = check.run(df)
        assert result.status == CheckStatus.FAILED
        assert result.details["missing_column"] == "nonexistent"

    def test_empty_dataframe(self) -> None:
        df = pl.DataFrame({"col": pl.Series([], dtype=pl.Utf8)})
        check = AllowedValuesCheck(column="col", allowed_values=frozenset({"a"}))
        result = check.run(df)
        assert result.status == CheckStatus.PASSED

    def test_custom_name(self) -> None:
        df = _sample_df()
        check = AllowedValuesCheck(
            column="availability",
            allowed_values=frozenset({"in_stock"}),
            name="avail_enum",
        )
        result = check.run(df)
        assert result.check_name == "avail_enum"


class TestDuplicateCheck:
    def test_no_duplicates(self) -> None:
        df = _sample_df()
        check = DuplicateCheck(key_columns=["event_id"])
        result = check.run(df)
        assert result.status == CheckStatus.PASSED
        assert result.details["duplicate_rows"] == 0

    def test_exact_duplicates(self) -> None:
        df = pl.DataFrame(
            {
                "event_id": ["e1", "e1", "e2"],
                "value": [1, 1, 2],
            }
        )
        check = DuplicateCheck(key_columns=["event_id"])
        result = check.run(df)
        assert result.status == CheckStatus.FAILED
        assert result.details["duplicate_rows"] == 1
        assert result.details["unique_keys"] == 2
        assert result.details["keys_with_duplicates"] == 1

    def test_composite_key(self) -> None:
        df = pl.DataFrame(
            {
                "source": ["a", "a", "b"],
                "external_id": ["1", "1", "2"],
                "value": [10, 10, 20],
            }
        )
        check = DuplicateCheck(key_columns=["source", "external_id"])
        result = check.run(df)
        assert result.status == CheckStatus.FAILED
        assert result.details["duplicate_rows"] == 1

    def test_within_threshold(self) -> None:
        df = pl.DataFrame(
            {
                "event_id": ["e1", "e1", "e2", "e3", "e4"],
                "value": [1, 1, 2, 3, 4],
            }
        )
        check = DuplicateCheck(key_columns=["event_id"], max_duplicate_rate=0.25)
        result = check.run(df)
        assert result.status == CheckStatus.PASSED

    def test_missing_key_column(self) -> None:
        df = _sample_df()
        check = DuplicateCheck(key_columns=["nonexistent"])
        result = check.run(df)
        assert result.status == CheckStatus.FAILED
        assert "nonexistent" in result.details["missing_columns"]

    def test_empty_dataframe(self) -> None:
        df = pl.DataFrame({"event_id": pl.Series([], dtype=pl.Utf8)})
        check = DuplicateCheck(key_columns=["event_id"])
        result = check.run(df)
        assert result.status == CheckStatus.PASSED

    def test_duplicate_rate_calculation(self) -> None:
        df = pl.DataFrame({"event_id": ["e1", "e1", "e1", "e2"], "v": [1, 1, 1, 2]})
        check = DuplicateCheck(key_columns=["event_id"])
        result = check.run(df)
        assert result.details["duplicate_rate"] == 0.5
        assert result.details["total_records"] == 4
        assert result.details["unique_keys"] == 2


class TestFreshnessCheck:
    def test_fresh_data(self) -> None:
        now = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
        df = pl.DataFrame(
            {
                "collected_at": [
                    now - timedelta(minutes=5),
                    now - timedelta(minutes=10),
                ]
            }
        )
        check = FreshnessCheck(max_age_seconds=3600.0, reference_time=now)
        result = check.run(df)
        assert result.status == CheckStatus.PASSED
        assert result.details["age_seconds"] < 3600.0

    def test_stale_data(self) -> None:
        now = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
        df = pl.DataFrame(
            {
                "collected_at": [
                    now - timedelta(hours=2),
                    now - timedelta(hours=3),
                ]
            }
        )
        check = FreshnessCheck(max_age_seconds=3600.0, reference_time=now)
        result = check.run(df)
        assert result.status == CheckStatus.FAILED
        assert result.details["age_seconds"] > 3600.0

    def test_empty_dataframe(self) -> None:
        df = pl.DataFrame(
            {"collected_at": pl.Series([], dtype=pl.Datetime(time_unit="us", time_zone="UTC"))}
        )
        check = FreshnessCheck(max_age_seconds=3600.0)
        result = check.run(df)
        assert result.status == CheckStatus.FAILED
        assert result.details["reason"] == "no_records"

    def test_missing_column(self) -> None:
        df = pl.DataFrame({"other": [1, 2, 3]})
        check = FreshnessCheck()
        result = check.run(df)
        assert result.status == CheckStatus.FAILED
        assert result.details["missing_column"] == "collected_at"

    def test_all_null_timestamps(self) -> None:
        df = pl.DataFrame(
            {"collected_at": [None, None], "value": [1, 2]},
            schema={
                "collected_at": pl.Datetime(time_unit="us", time_zone="UTC"),
                "value": pl.Int64,
            },
        )
        check = FreshnessCheck(max_age_seconds=3600.0)
        result = check.run(df)
        assert result.status == CheckStatus.FAILED
        assert result.details["reason"] == "all_null_timestamps"

    def test_source_propagated(self) -> None:
        now = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
        df = pl.DataFrame({"collected_at": [now - timedelta(minutes=1)]})
        check = FreshnessCheck(max_age_seconds=3600.0, source="fake_store", reference_time=now)
        result = check.run(df)
        assert result.source == "fake_store"

    def test_custom_timestamp_column(self) -> None:
        now = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
        df = pl.DataFrame({"observed_at": [now - timedelta(seconds=10)]})
        check = FreshnessCheck(
            timestamp_column="observed_at",
            max_age_seconds=3600.0,
            reference_time=now,
        )
        result = check.run(df)
        assert result.status == CheckStatus.PASSED
