"""Tests for the load-test metrics collector (TASK-108)."""

from __future__ import annotations

from libs.load_test.metrics_collector import MetricsCollector, _compute_percentiles


def test_empty_summary() -> None:
    mc = MetricsCollector()
    mc.mark_start()
    mc.mark_end()
    summary = mc.get_summary()

    assert summary["produced_count"] == 0
    assert summary["error_count"] == 0
    assert summary["throughput_events_per_sec"] == 0.0
    assert summary["latency_ms"]["min"] == 0.0
    assert summary["latency_ms"]["p50"] == 0.0


def test_record_latency_increments_count() -> None:
    mc = MetricsCollector()
    mc.mark_start()
    mc.record_latency("evt-1", 5.0)
    mc.record_latency("evt-2", 10.0)
    mc.mark_end()

    summary = mc.get_summary()
    assert summary["produced_count"] == 2
    assert summary["error_count"] == 0


def test_record_error_increments_count() -> None:
    mc = MetricsCollector()
    mc.mark_start()
    mc.record_error()
    mc.record_error()
    mc.record_error()
    mc.mark_end()

    summary = mc.get_summary()
    assert summary["error_count"] == 3


def test_throughput_calculation() -> None:
    mc = MetricsCollector()
    mc.mark_start()
    for i in range(100):
        mc.record_latency(f"evt-{i}", 1.0)
    mc.mark_end()

    summary = mc.get_summary()
    assert summary["produced_count"] == 100
    assert summary["throughput_events_per_sec"] > 0


def test_latency_percentiles() -> None:
    mc = MetricsCollector()
    mc.mark_start()
    for i in range(100):
        mc.record_latency(f"evt-{i}", float(i + 1))
    mc.mark_end()

    summary = mc.get_summary()
    lat = summary["latency_ms"]
    assert lat["min"] == 1.0
    assert lat["max"] == 100.0
    assert lat["p50"] > 0
    assert lat["p90"] > lat["p50"]
    assert lat["p99"] >= lat["p90"]


def test_resource_snapshot_records() -> None:
    mc = MetricsCollector()
    mc.record_resource_snapshot()
    mc.record_resource_snapshot()
    summary = mc.get_summary()
    assert "resource" in summary
    assert "peak_rss_mb" in summary["resource"]
    assert "total_cpu_sec" in summary["resource"]


def test_compute_percentiles_empty() -> None:
    result = _compute_percentiles([])
    assert result["min"] == 0.0
    assert result["max"] == 0.0
    assert result["mean"] == 0.0


def test_compute_percentiles_single_value() -> None:
    result = _compute_percentiles([42.0])
    assert result["min"] == 42.0
    assert result["max"] == 42.0
    assert result["mean"] == 42.0
    assert result["p50"] == 42.0
    assert result["p99"] == 42.0


def test_compute_percentiles_sorted_input() -> None:
    values = list(range(1, 101))
    result = _compute_percentiles([float(v) for v in values])
    assert result["min"] == 1.0
    assert result["max"] == 100.0
    assert 49.0 <= result["p50"] <= 51.0


def test_concurrent_record_latency() -> None:
    """Lock-free record_latency must produce correct totals under concurrency."""
    import threading

    mc = MetricsCollector()
    mc.mark_start()
    num_threads = 8
    per_thread = 1000

    def _worker(start: int) -> None:
        for i in range(per_thread):
            mc.record_latency(f"evt-{start + i}", float(i))

    threads = [threading.Thread(target=_worker, args=(t * per_thread,)) for t in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    mc.mark_end()
    summary = mc.get_summary()
    assert summary["produced_count"] == num_threads * per_thread
    assert summary["error_count"] == 0
    assert len(summary["latency_ms"]) > 0


def test_diagnostic_records_iteration_timings() -> None:
    mc = MetricsCollector(diagnostic=True)
    mc.record_iteration_timing(
        worker_id=0,
        t_gen_ms=0.1,
        t_produce_ms=12.0,
        t_requested_wait_ms=17.9,
        t_actual_wait_ms=24.5,
        t_overshoot_ms=6.6,
        t_total_ms=37.0,
    )
    mc.record_iteration_timing(
        worker_id=1,
        t_gen_ms=0.2,
        t_produce_ms=13.0,
        t_requested_wait_ms=16.8,
        t_actual_wait_ms=23.0,
        t_overshoot_ms=6.2,
        t_total_ms=36.0,
    )

    breakdown = mc.get_timing_breakdown()
    assert breakdown is not None
    assert breakdown["sample_count"] == 2


def test_non_diagnostic_ignores_iteration_timings() -> None:
    mc = MetricsCollector(diagnostic=False)
    mc.record_iteration_timing(
        worker_id=0,
        t_gen_ms=0.1,
        t_produce_ms=12.0,
        t_requested_wait_ms=17.9,
        t_actual_wait_ms=24.5,
        t_overshoot_ms=6.6,
        t_total_ms=37.0,
    )

    assert mc.get_timing_breakdown() is None


def test_get_timing_breakdown_returns_none_when_disabled() -> None:
    mc = MetricsCollector(diagnostic=False)
    assert mc.get_timing_breakdown() is None


def test_get_timing_breakdown_returns_none_when_empty() -> None:
    mc = MetricsCollector(diagnostic=True)
    assert mc.get_timing_breakdown() is None


def test_get_timing_breakdown_structure() -> None:
    mc = MetricsCollector(diagnostic=True)
    for i in range(10):
        mc.record_iteration_timing(
            worker_id=i % 2,
            t_gen_ms=0.1 * (i + 1),
            t_produce_ms=10.0 + i,
            t_requested_wait_ms=20.0 - i,
            t_actual_wait_ms=25.0 - i,
            t_overshoot_ms=5.0,
            t_total_ms=35.0 + i,
        )

    breakdown = mc.get_timing_breakdown()
    assert breakdown is not None
    assert breakdown["sample_count"] == 10

    for component in (
        "gen_ms",
        "produce_ms",
        "requested_wait_ms",
        "actual_wait_ms",
        "overshoot_ms",
        "total_ms",
    ):
        assert component in breakdown
        stats = breakdown[component]
        assert "min" in stats
        assert "p50" in stats
        assert "p90" in stats
        assert "p95" in stats
        assert "p99" in stats
        assert "max" in stats
        assert "mean" in stats
        assert stats["min"] <= stats["p50"]
        assert stats["p50"] <= stats["p90"]
        assert stats["p90"] <= stats["p95"]
        assert stats["p95"] <= stats["p99"]
        assert stats["p99"] <= stats["max"]

    assert "per_worker" in breakdown
    assert "worker_0" in breakdown["per_worker"]
    assert "worker_1" in breakdown["per_worker"]
    assert breakdown["per_worker"]["worker_0"]["iterations"] == 5
    assert breakdown["per_worker"]["worker_1"]["iterations"] == 5


def test_get_timing_breakdown_percentiles_are_sorted() -> None:
    """Percentiles must be computed from sorted values, not insertion order."""
    mc = MetricsCollector(diagnostic=True)
    mc.record_iteration_timing(
        worker_id=0,
        t_gen_ms=100.0,
        t_produce_ms=1.0,
        t_requested_wait_ms=1.0,
        t_actual_wait_ms=1.0,
        t_overshoot_ms=0.0,
        t_total_ms=1.0,
    )
    mc.record_iteration_timing(
        worker_id=0,
        t_gen_ms=1.0,
        t_produce_ms=50.0,
        t_requested_wait_ms=1.0,
        t_actual_wait_ms=1.0,
        t_overshoot_ms=0.0,
        t_total_ms=1.0,
    )
    mc.record_iteration_timing(
        worker_id=0,
        t_gen_ms=50.0,
        t_produce_ms=100.0,
        t_requested_wait_ms=1.0,
        t_actual_wait_ms=1.0,
        t_overshoot_ms=0.0,
        t_total_ms=1.0,
    )
    mc.record_iteration_timing(
        worker_id=0,
        t_gen_ms=1.0,
        t_produce_ms=1.0,
        t_requested_wait_ms=1.0,
        t_actual_wait_ms=1.0,
        t_overshoot_ms=0.0,
        t_total_ms=1.0,
    )

    breakdown = mc.get_timing_breakdown()
    assert breakdown is not None

    gen = breakdown["gen_ms"]
    assert gen["min"] == 1.0
    assert gen["max"] == 100.0

    produce = breakdown["produce_ms"]
    assert produce["min"] == 1.0
    assert produce["max"] == 100.0
    assert produce["p50"] <= produce["p90"]
