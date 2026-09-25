"""Unit tests for end-to-end latency collection and analysis (TASK-113)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from libs.load_test.latency_collector import (
    EndToEndSample,
    LatencyCollector,
    ProduceRecord,
    _compute_percentiles,
)


class TestProduceRecord:
    def test_creation(self) -> None:
        now = datetime.now(timezone.utc)
        r = ProduceRecord(event_id="abc-1", produce_time=now)
        assert r.event_id == "abc-1"
        assert r.produce_time == now

    def test_frozen(self) -> None:
        r = ProduceRecord(event_id="x", produce_time=datetime.now(timezone.utc))
        try:
            r.event_id = "y"  # type: ignore[misc]
        except AttributeError:
            pass
        else:
            raise AssertionError("ProduceRecord should be frozen")


class TestEndToEndSample:
    def test_creation(self) -> None:
        t0 = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 25, 12, 0, 5, tzinfo=timezone.utc)
        s = EndToEndSample(
            event_id="e1",
            latency_ms=5000.0,
            produce_time=t0,
            arrival_time=t1,
        )
        assert s.event_id == "e1"
        assert s.latency_ms == 5000.0
        assert s.produce_time == t0
        assert s.arrival_time == t1

    def test_frozen(self) -> None:
        t0 = datetime.now(timezone.utc)
        s = EndToEndSample(event_id="e", latency_ms=1.0, produce_time=t0, arrival_time=t0)
        try:
            s.latency_ms = 2.0  # type: ignore[misc]
        except AttributeError:
            pass
        else:
            raise AssertionError("EndToEndSample should be frozen")


class TestLatencyCollector:
    def test_empty_report(self) -> None:
        c = LatencyCollector()
        assert c.to_report_dict() is None
        assert c.produced_count == 0
        assert c.resolved_count == 0
        assert c.pending_count == 0

    def test_record_produce(self) -> None:
        c = LatencyCollector()
        t0 = datetime.now(timezone.utc)
        c.record_produce("e1", t0)
        c.record_produce("e2", t0)
        assert c.produced_count == 2
        assert c.pending_count == 2
        assert c.resolved_count == 0

    def test_record_pg_arrivals_computes_latency(self) -> None:
        c = LatencyCollector()
        t0 = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 25, 12, 0, 2, tzinfo=timezone.utc)

        c.record_produce("e1", t0)
        c.record_produce("e2", t0)

        new_samples = c.record_pg_arrivals(["e1"], t1)
        assert len(new_samples) == 1
        assert new_samples[0].event_id == "e1"
        assert abs(new_samples[0].latency_ms - 2000.0) < 0.001
        assert c.resolved_count == 1
        assert c.pending_count == 1

    def test_duplicate_arrivals_ignored(self) -> None:
        c = LatencyCollector()
        t0 = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 25, 12, 0, 1, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 25, 12, 0, 5, tzinfo=timezone.utc)

        c.record_produce("e1", t0)
        c.record_pg_arrivals(["e1"], t1)

        new_samples = c.record_pg_arrivals(["e1"], t2)
        assert len(new_samples) == 0
        assert c.resolved_count == 1

    def test_unknown_event_ids_ignored(self) -> None:
        c = LatencyCollector()
        t0 = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 25, 12, 0, 1, tzinfo=timezone.utc)

        c.record_produce("e1", t0)
        new_samples = c.record_pg_arrivals(["e1", "unknown-1"], t1)
        assert len(new_samples) == 1
        assert new_samples[0].event_id == "e1"

    def test_get_pending_event_ids(self) -> None:
        c = LatencyCollector()
        t0 = datetime.now(timezone.utc)
        c.record_produce("e1", t0)
        c.record_produce("e2", t0)
        c.record_produce("e3", t0)

        pending = c.get_pending_event_ids()
        assert sorted(pending) == ["e1", "e2", "e3"]

        c.record_pg_arrivals(["e2"], t0)
        pending = c.get_pending_event_ids()
        assert sorted(pending) == ["e1", "e3"]

    def test_get_samples(self) -> None:
        c = LatencyCollector()
        t0 = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 25, 12, 0, 1, tzinfo=timezone.utc)

        c.record_produce("e1", t0)
        c.record_produce("e2", t0)
        c.record_pg_arrivals(["e1", "e2"], t1)

        samples = c.get_samples()
        assert len(samples) == 2
        event_ids = {s.event_id for s in samples}
        assert event_ids == {"e1", "e2"}

    def test_report_with_data(self) -> None:
        c = LatencyCollector()
        base = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)

        for i in range(10):
            c.record_produce(f"e{i}", base + timedelta(milliseconds=i))

        arrival = base + timedelta(seconds=5)
        c.record_pg_arrivals([f"e{i}" for i in range(10)], arrival)

        report = c.to_report_dict()
        assert report is not None
        assert report["total_produced"] == 10
        assert report["total_resolved"] == 10
        assert report["unresolved"] == 0
        assert report["sample_count"] == 10
        assert "latency_ms" in report
        assert "p50" in report["latency_ms"]
        assert "p95" in report["latency_ms"]
        assert "p99" in report["latency_ms"]

    def test_report_partial_resolution(self) -> None:
        c = LatencyCollector()
        t0 = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 25, 12, 0, 1, tzinfo=timezone.utc)

        c.record_produce("e1", t0)
        c.record_produce("e2", t0)
        c.record_produce("e3", t0)
        c.record_pg_arrivals(["e1"], t1)

        report = c.to_report_dict()
        assert report is not None
        assert report["total_produced"] == 3
        assert report["total_resolved"] == 1
        assert report["unresolved"] == 2
        assert report["sample_count"] == 1


class TestComputePercentiles:
    def test_empty(self) -> None:
        result = _compute_percentiles([])
        assert result["min"] == 0.0
        assert result["mean"] == 0.0

    def test_single_value(self) -> None:
        result = _compute_percentiles([42.0])
        assert result["min"] == 42.0
        assert result["max"] == 42.0
        assert result["mean"] == 42.0
        assert result["p50"] == 42.0

    def test_multiple_values(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        result = _compute_percentiles(values)
        assert result["min"] == 1.0
        assert result["max"] == 10.0
        assert result["mean"] == 5.5
        assert result["p50"] == 5.5

    def test_latency_distribution(self) -> None:
        values = sorted([100.0, 200.0, 300.0, 500.0, 1000.0, 5000.0])
        result = _compute_percentiles(values)
        assert result["min"] == 100.0
        assert result["max"] == 5000.0
        assert result["p95"] > result["p50"]
