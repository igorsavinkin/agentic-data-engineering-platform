"""Unit tests for KafkaMetrics lag tracking (TASK-088)."""

from __future__ import annotations

import time

from libs.observability.kafka_metrics import KafkaMetrics, LagSample


class TestLagSample:
    def test_lag_sample_creation(self) -> None:
        sample = LagSample(topic="test.topic", partition=0, lag=100)
        assert sample.topic == "test.topic"
        assert sample.partition == 0
        assert sample.lag == 100
        assert sample.sampled_at > 0

    def test_lag_sample_age_seconds(self) -> None:
        sample = LagSample(topic="test.topic", partition=0, lag=100)
        time.sleep(0.01)
        age = sample.age_seconds()
        assert age >= 0.01
        assert age < 1.0

    def test_lag_sample_custom_timestamp(self) -> None:
        custom_time = time.monotonic() - 10.0
        sample = LagSample(topic="test.topic", partition=0, lag=100, sampled_at=custom_time)
        assert sample.sampled_at == custom_time
        assert sample.age_seconds() >= 10.0


class TestKafkaMetricsLag:
    def test_initial_lag_snapshot_empty(self) -> None:
        metrics = KafkaMetrics()
        assert metrics.lag_snapshot() == []

    def test_update_lag(self) -> None:
        metrics = KafkaMetrics()
        samples = [
            LagSample(topic="topic1", partition=0, lag=10),
            LagSample(topic="topic1", partition=1, lag=20),
        ]
        metrics.update_lag(samples)
        result = metrics.lag_snapshot()
        assert len(result) == 2
        assert result[0].topic == "topic1"
        assert result[0].partition == 0
        assert result[0].lag == 10
        assert result[1].partition == 1
        assert result[1].lag == 20

    def test_update_lag_replaces_previous(self) -> None:
        metrics = KafkaMetrics()
        metrics.update_lag([LagSample(topic="t1", partition=0, lag=10)])
        metrics.update_lag([LagSample(topic="t2", partition=0, lag=20)])
        result = metrics.lag_snapshot()
        assert len(result) == 1
        assert result[0].topic == "t2"
        assert result[0].lag == 20

    def test_lag_snapshot_returns_copy(self) -> None:
        metrics = KafkaMetrics()
        samples = [LagSample(topic="t1", partition=0, lag=10)]
        metrics.update_lag(samples)
        snapshot1 = metrics.lag_snapshot()
        snapshot2 = metrics.lag_snapshot()
        assert snapshot1 is not snapshot2
        assert snapshot1 == snapshot2

    def test_clear_stale_lag_removes_old_samples(self) -> None:
        metrics = KafkaMetrics()
        old_time = time.monotonic() - 120.0
        old_sample = LagSample(topic="old", partition=0, lag=100, sampled_at=old_time)
        fresh_sample = LagSample(topic="fresh", partition=0, lag=50)
        metrics.update_lag([old_sample, fresh_sample])

        removed = metrics.clear_stale_lag(max_age_seconds=60.0)
        assert removed == 1

        result = metrics.lag_snapshot()
        assert len(result) == 1
        assert result[0].topic == "fresh"

    def test_clear_stale_lag_keeps_fresh_samples(self) -> None:
        metrics = KafkaMetrics()
        samples = [
            LagSample(topic="t1", partition=0, lag=10),
            LagSample(topic="t1", partition=1, lag=20),
        ]
        metrics.update_lag(samples)

        removed = metrics.clear_stale_lag(max_age_seconds=60.0)
        assert removed == 0

        result = metrics.lag_snapshot()
        assert len(result) == 2

    def test_clear_stale_lag_empty_list(self) -> None:
        metrics = KafkaMetrics()
        removed = metrics.clear_stale_lag(max_age_seconds=60.0)
        assert removed == 0
