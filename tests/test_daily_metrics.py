"""Tests for DailyMetricsCalculator (TASK-062)."""

from __future__ import annotations

from datetime import date, datetime

import polars as pl

from libs.metrics.calculator import (
    DailyMetric,
    DailyMetricsCalculator,
    DailyMetricsResult,
)


def _make_observations(n: int = 10) -> pl.DataFrame:
    """Create a sample observations DataFrame."""
    sources = ["fake_store"] * (n // 2) + ["best_buy"] * (n - n // 2)
    product_ids = list(range(1, n + 1))
    prices = [10.0 + i for i in range(n)]
    availabilities = ["in_stock"] * (n // 2) + ["out_of_stock"] * (n - n // 2)
    collected = [datetime(2026, 9, 18, 10, i) for i in range(n)]

    return pl.DataFrame(
        {
            "source_name": sources,
            "product_id": product_ids,
            "price": prices,
            "availability": availabilities,
            "collected_at": collected,
        }
    )


class TestDailyMetric:
    def test_replay_key_no_dimension(self) -> None:
        m = DailyMetric(
            metric_date=date(2026, 9, 18),
            metric_name="observation_count",
            dimension="",
            value=42.0,
        )
        assert m.replay_key == "observation_count:2026-09-18:_"

    def test_replay_key_with_dimension(self) -> None:
        m = DailyMetric(
            metric_date=date(2026, 9, 18),
            metric_name="source_observation_count",
            dimension="fake_store",
            value=5.0,
        )
        assert m.replay_key == "source_observation_count:2026-09-18:fake_store"


class TestDailyMetricsResult:
    def test_success_when_no_errors(self) -> None:
        result = DailyMetricsResult()
        assert result.success

    def test_failure_when_errors(self) -> None:
        result = DailyMetricsResult(errors=["oops"])
        assert not result.success


class TestDailyMetricsCalculator:
    def test_empty_dataframe(self) -> None:
        df = pl.DataFrame(
            {
                "source_name": pl.Series([], dtype=pl.Utf8),
                "product_id": pl.Series([], dtype=pl.Int64),
                "price": pl.Series([], dtype=pl.Float64),
                "availability": pl.Series([], dtype=pl.Utf8),
                "collected_at": pl.Series([], dtype=pl.Datetime),
            }
        )
        calc = DailyMetricsCalculator(date(2026, 9, 18))
        result = calc.compute(df)
        assert result.success
        assert result.observation_count == 0
        assert len(result.metrics) == 0

    def test_observation_count(self) -> None:
        df = _make_observations(10)
        calc = DailyMetricsCalculator(date(2026, 9, 18))
        result = calc.compute(df)
        obs_count = [m for m in result.metrics if m.metric_name == "observation_count"]
        assert len(obs_count) == 1
        assert obs_count[0].value == 10.0

    def test_unique_products(self) -> None:
        df = _make_observations(10)
        calc = DailyMetricsCalculator(date(2026, 9, 18))
        result = calc.compute(df)
        unique = [m for m in result.metrics if m.metric_name == "unique_products"]
        assert len(unique) == 1
        assert unique[0].value == 10.0

    def test_avg_price(self) -> None:
        df = _make_observations(10)
        calc = DailyMetricsCalculator(date(2026, 9, 18))
        result = calc.compute(df)
        avg = [m for m in result.metrics if m.metric_name == "avg_price"]
        assert len(avg) == 1
        expected_avg = sum(10.0 + i for i in range(10)) / 10
        assert abs(avg[0].value - expected_avg) < 0.01

    def test_avg_price_all_null(self) -> None:
        df = pl.DataFrame(
            {
                "source_name": ["a", "b"],
                "product_id": [1, 2],
                "price": [None, None],
                "availability": ["in_stock", "in_stock"],
                "collected_at": [datetime(2026, 9, 18), datetime(2026, 9, 18)],
            },
            schema={
                "source_name": pl.Utf8,
                "product_id": pl.Int64,
                "price": pl.Float64,
                "availability": pl.Utf8,
                "collected_at": pl.Datetime,
            },
        )
        calc = DailyMetricsCalculator(date(2026, 9, 18))
        result = calc.compute(df)
        avg = [m for m in result.metrics if m.metric_name == "avg_price"]
        assert len(avg) == 1
        assert avg[0].value == 0.0

    def test_availability_distribution(self) -> None:
        df = _make_observations(10)
        calc = DailyMetricsCalculator(date(2026, 9, 18))
        result = calc.compute(df)
        in_stock = [m for m in result.metrics if m.metric_name == "availability_in_stock"]
        out_stock = [m for m in result.metrics if m.metric_name == "availability_out_of_stock"]
        assert len(in_stock) == 1
        assert len(out_stock) == 1
        assert in_stock[0].value == 5.0
        assert out_stock[0].value == 5.0

    def test_source_observation_count(self) -> None:
        df = _make_observations(10)
        calc = DailyMetricsCalculator(date(2026, 9, 18))
        result = calc.compute(df)
        source_counts = [m for m in result.metrics if m.metric_name == "source_observation_count"]
        assert len(source_counts) == 2
        sources = {m.dimension for m in source_counts}
        assert "fake_store" in sources
        assert "best_buy" in sources

    def test_total_metric_count(self) -> None:
        df = _make_observations(10)
        calc = DailyMetricsCalculator(date(2026, 9, 18))
        result = calc.compute(df)
        assert result.success
        # observation_count + unique_products + avg_price + 2 availability + 2 source counts
        assert len(result.metrics) == 7

    def test_metric_date_is_set(self) -> None:
        df = _make_observations(5)
        calc = DailyMetricsCalculator(date(2026, 9, 18))
        result = calc.compute(df)
        for m in result.metrics:
            assert m.metric_date == date(2026, 9, 18)

    def test_missing_price_column(self) -> None:
        df = pl.DataFrame(
            {
                "source_name": ["a"],
                "product_id": [1],
                "availability": ["in_stock"],
                "collected_at": [datetime(2026, 9, 18)],
            }
        )
        calc = DailyMetricsCalculator(date(2026, 9, 18))
        result = calc.compute(df)
        assert result.success
        avg = [m for m in result.metrics if m.metric_name == "avg_price"]
        assert len(avg) == 0
