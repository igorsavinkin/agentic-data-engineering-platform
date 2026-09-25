"""Unit tests for consumer-lag collection and analysis (TASK-112)."""

from __future__ import annotations

from libs.load_test.lag_collector import (
    LagCollector,
    LagSample,
    _classify_growth,
)


class TestLagSample:
    def test_creation(self) -> None:
        s = LagSample(
            elapsed_sec=1.0,
            consumer_group="processor",
            topic="products.raw.v1",
            partition=0,
            lag=42,
        )
        assert s.elapsed_sec == 1.0
        assert s.consumer_group == "processor"
        assert s.topic == "products.raw.v1"
        assert s.partition == 0
        assert s.lag == 42

    def test_frozen(self) -> None:
        s = LagSample(elapsed_sec=0, consumer_group="g", topic="t", partition=0, lag=0)
        try:
            s.lag = 10  # type: ignore[misc]
        except AttributeError:
            pass
        else:
            raise AssertionError("LagSample should be frozen")


class TestClassifyGrowth:
    def test_stable_zero_lag(self) -> None:
        assert _classify_growth([0, 0, 0, 0]) == "stable"

    def test_stable_small_variation(self) -> None:
        assert _classify_growth([100, 105, 98, 102, 101, 99, 103, 100]) == "stable"

    def test_increasing(self) -> None:
        lags = [10, 12, 11, 13, 50, 80, 120, 200]
        assert _classify_growth(lags) == "increasing"

    def test_decreasing(self) -> None:
        lags = [200, 180, 150, 120, 50, 30, 20, 10]
        assert _classify_growth(lags) == "decreasing"

    def test_insufficient_data(self) -> None:
        assert _classify_growth([10, 20]) == "insufficient_data"
        assert _classify_growth([10]) == "insufficient_data"
        assert _classify_growth([]) == "insufficient_data"

    def test_increasing_from_zero(self) -> None:
        lags = [0, 0, 0, 0, 50, 100, 200, 500]
        assert _classify_growth(lags) == "increasing"


class TestLagCollector:
    def test_empty_collector(self) -> None:
        c = LagCollector()
        assert c.sample_count == 0
        assert c.get_summary() is None
        assert c.to_report_dict() is None
        assert c.get_time_series() == []

    def test_record_single_batch(self) -> None:
        c = LagCollector()
        samples = [
            LagSample(0.0, "proc", "t", 0, 10),
            LagSample(0.0, "proc", "t", 1, 20),
        ]
        c.record(samples)
        assert c.sample_count == 2

    def test_record_empty_batch_ignored(self) -> None:
        c = LagCollector()
        c.record([])
        assert c.sample_count == 0

    def test_record_multiple_batches(self) -> None:
        c = LagCollector()
        c.record([LagSample(0.0, "g", "t", 0, 10)])
        c.record([LagSample(5.0, "g", "t", 0, 50)])
        c.record([LagSample(10.0, "g", "t", 0, 100)])
        assert c.sample_count == 3

    def test_get_time_series(self) -> None:
        c = LagCollector()
        c.record([LagSample(1.5, "proc", "raw", 0, 42)])
        ts = c.get_time_series()
        assert len(ts) == 1
        assert ts[0] == {
            "elapsed_sec": 1.5,
            "consumer_group": "proc",
            "topic": "raw",
            "partition": 0,
            "lag": 42,
        }

    def test_summary_single_partition(self) -> None:
        c = LagCollector()
        c.record([LagSample(0.0, "g", "t", 0, 10)])
        c.record([LagSample(5.0, "g", "t", 0, 20)])
        c.record([LagSample(10.0, "g", "t", 0, 30)])
        c.record([LagSample(15.0, "g", "t", 0, 40)])

        summary = c.get_summary()
        assert summary is not None
        assert summary.total_samples == 4
        assert summary.max_observed_lag == 40

        p = summary.per_partition[0]
        assert p.consumer_group == "g"
        assert p.topic == "t"
        assert p.partition == 0
        assert p.sample_count == 4
        assert p.min_lag == 10
        assert p.max_lag == 40
        assert p.final_lag == 40
        assert p.mean_lag == 25.0

    def test_summary_multiple_partitions_sorted(self) -> None:
        c = LagCollector()
        c.record(
            [
                LagSample(0.0, "beta", "t", 1, 5),
                LagSample(0.0, "alpha", "t", 0, 10),
                LagSample(0.0, "alpha", "t", 1, 20),
            ]
        )
        c.record(
            [
                LagSample(5.0, "beta", "t", 1, 15),
                LagSample(5.0, "alpha", "t", 0, 10),
                LagSample(5.0, "alpha", "t", 1, 20),
            ]
        )
        c.record(
            [
                LagSample(10.0, "beta", "t", 1, 25),
                LagSample(10.0, "alpha", "t", 0, 10),
                LagSample(10.0, "alpha", "t", 1, 20),
            ]
        )
        c.record(
            [
                LagSample(15.0, "beta", "t", 1, 35),
                LagSample(15.0, "alpha", "t", 0, 10),
                LagSample(15.0, "alpha", "t", 1, 20),
            ]
        )

        summary = c.get_summary()
        assert summary is not None
        assert len(summary.per_partition) == 3
        keys = [(p.consumer_group, p.topic, p.partition) for p in summary.per_partition]
        assert keys == sorted(keys)

    def test_any_growing_flag(self) -> None:
        c = LagCollector()
        for i in range(8):
            c.record([LagSample(float(i), "g", "t", 0, 10 + i * 50)])

        summary = c.get_summary()
        assert summary is not None
        assert summary.any_growing is True

    def test_stable_lag_not_growing(self) -> None:
        c = LagCollector()
        for i in range(8):
            c.record([LagSample(float(i), "g", "t", 0, 100)])

        summary = c.get_summary()
        assert summary is not None
        assert summary.any_growing is False

    def test_to_report_dict_structure(self) -> None:
        c = LagCollector()
        c.record([LagSample(0.0, "g", "t", 0, 10)])
        c.record([LagSample(5.0, "g", "t", 0, 20)])
        c.record([LagSample(10.0, "g", "t", 0, 30)])
        c.record([LagSample(15.0, "g", "t", 0, 40)])

        report = c.to_report_dict()
        assert report is not None
        assert report["total_samples"] == 4
        assert report["max_observed_lag"] == 40
        assert "per_partition" in report
        assert "thresholds" in report
        assert report["thresholds"]["warning"] == 1000
        assert report["thresholds"]["critical"] == 10000

        pp = report["per_partition"][0]
        assert pp["consumer_group"] == "g"
        assert pp["min"] == 10
        assert pp["max"] == 40
        assert pp["final"] == 40
