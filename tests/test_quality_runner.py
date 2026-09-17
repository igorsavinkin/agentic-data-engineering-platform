"""Tests for libs.quality.runner — suite runner."""

from __future__ import annotations

from datetime import datetime, timezone

import polars as pl

from libs.quality.checks import (
    AllowedValuesCheck,
    DuplicateCheck,
    FreshnessCheck,
    PriceValidityCheck,
    RequiredFieldsCheck,
)
from libs.quality.models import CheckStatus
from libs.quality.runner import QualitySuite, run_checks


def _sample_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "event_id": ["e1", "e2", "e3"],
            "source": ["fake_store", "fake_store", "best_buy"],
            "price": [10.0, 20.0, 30.0],
            "availability": ["in_stock", "out_of_stock", "preorder"],
            "collected_at": [
                datetime(2026, 9, 17, 10, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 9, 17, 10, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 9, 17, 10, 0, 0, tzinfo=timezone.utc),
            ],
        }
    )


class TestQualitySuite:
    def test_all_pass(self) -> None:
        df = _sample_df()
        suite = QualitySuite(
            name="test_suite",
            checks=[
                RequiredFieldsCheck(columns=["event_id", "source"]),
                PriceValidityCheck(),
            ],
        )
        result = suite.run(df)
        assert result.total_checks == 2
        assert result.passed_checks == 2
        assert result.failed_checks == 0
        assert result.has_errors is False

    def test_mixed_results(self) -> None:
        df = _sample_df().with_columns(pl.Series("price", [10.0, -5.0, 30.0]))
        suite = QualitySuite(
            name="test_suite",
            checks=[
                RequiredFieldsCheck(columns=["event_id"]),
                PriceValidityCheck(),
            ],
        )
        result = suite.run(df)
        assert result.total_checks == 2
        assert result.passed_checks == 1
        assert result.failed_checks == 1
        assert result.has_errors is True

    def test_checks_run_in_order(self) -> None:
        df = _sample_df()
        suite = QualitySuite(
            name="ordered",
            checks=[
                RequiredFieldsCheck(columns=["event_id"], name="first"),
                RequiredFieldsCheck(columns=["source"], name="second"),
                RequiredFieldsCheck(columns=["price"], name="third"),
            ],
        )
        result = suite.run(df)
        assert [r.check_name for r in result.results] == ["first", "second", "third"]

    def test_failing_check_does_not_stop_others(self) -> None:
        df = _sample_df().with_columns(pl.Series("price", [10.0, -5.0, 30.0]))
        suite = QualitySuite(
            name="resilient",
            checks=[
                PriceValidityCheck(),
                RequiredFieldsCheck(columns=["event_id"]),
            ],
        )
        result = suite.run(df)
        assert result.total_checks == 2
        assert result.results[0].status == CheckStatus.FAILED
        assert result.results[1].status == CheckStatus.PASSED


class TestRunChecks:
    def test_convenience_function(self) -> None:
        df = _sample_df()
        result = run_checks(
            df,
            [RequiredFieldsCheck(columns=["event_id"])],
            suite_name="convenience",
        )
        assert result.total_checks == 1
        assert result.passed_checks == 1

    def test_full_pipeline(self) -> None:
        now = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
        df = _sample_df()
        result = run_checks(
            df,
            [
                RequiredFieldsCheck(columns=["event_id", "source", "price"]),
                PriceValidityCheck(),
                AllowedValuesCheck(
                    column="availability",
                    allowed_values=frozenset({"in_stock", "out_of_stock", "preorder", "unknown"}),
                ),
                DuplicateCheck(key_columns=["event_id"]),
                FreshnessCheck(max_age_seconds=7200.0, reference_time=now),
            ],
            suite_name="full",
        )
        assert result.total_checks == 5
        assert result.passed_checks == 5
        assert result.has_errors is False

    def test_empty_dataframe_suite(self) -> None:
        df = pl.DataFrame(
            {
                "event_id": pl.Series([], dtype=pl.Utf8),
                "price": pl.Series([], dtype=pl.Float64),
            }
        )
        result = run_checks(
            df,
            [
                RequiredFieldsCheck(columns=["event_id"]),
                PriceValidityCheck(),
            ],
        )
        assert result.total_checks == 2
        assert result.passed_checks == 2
