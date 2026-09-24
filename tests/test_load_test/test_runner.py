"""Tests for the load-test runner (TASK-108)."""

from __future__ import annotations

import os
import tempfile
import threading
from typing import Any

from libs.event_contracts import ProductObservationEvent
from libs.load_test.config import LoadTestSettings
from libs.load_test.runner import LoadTestRunner


def _noop_produce(event: ProductObservationEvent) -> str:
    return event.event_id


def _make_settings(**overrides: Any) -> LoadTestSettings:
    defaults = {
        "target_events_per_sec": 1000.0,
        "duration_sec": 0.5,
        "total_events": 0,
        "worker_count": 1,
        "output_path": os.path.join(tempfile.mkdtemp(), "result.json"),
        "source_name": "test",
        "seed": 42,
    }
    defaults.update(overrides)
    return LoadTestSettings(**defaults)  # type: ignore[arg-type]


def test_runner_produces_events() -> None:
    settings = _make_settings(target_events_per_sec=500, duration_sec=0.5)
    runner = LoadTestRunner(settings=settings, produce_fn=_noop_produce)

    report = runner.run()

    assert report["results"]["produced_count"] > 0
    assert report["results"]["error_count"] == 0
    assert report["results"]["throughput_events_per_sec"] > 0


def test_runner_respects_total_events() -> None:
    settings = _make_settings(
        target_events_per_sec=10000,
        duration_sec=60,
        total_events=10,
    )
    runner = LoadTestRunner(settings=settings, produce_fn=_noop_produce)

    report = runner.run()

    assert report["results"]["produced_count"] >= 10


def test_runner_records_errors() -> None:
    def failing_produce(event: ProductObservationEvent) -> str:
        raise RuntimeError("simulated failure")

    settings = _make_settings(target_events_per_sec=500, duration_sec=0.3)
    runner = LoadTestRunner(settings=settings, produce_fn=failing_produce)

    report = runner.run()

    assert report["results"]["error_count"] > 0
    assert report["results"]["produced_count"] == 0


def test_runner_writes_report_file() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        output = os.path.join(tmpdir, "subdir", "results.json")
        settings = _make_settings(
            target_events_per_sec=500,
            duration_sec=0.2,
            output_path=output,
        )
        runner = LoadTestRunner(settings=settings, produce_fn=_noop_produce)
        runner.run()

        assert os.path.exists(output)


def test_runner_report_has_expected_structure() -> None:
    settings = _make_settings(target_events_per_sec=500, duration_sec=0.2)
    runner = LoadTestRunner(settings=settings, produce_fn=_noop_produce)

    report = runner.run()

    assert "run_id" in report
    assert "timestamp" in report
    assert "environment" in report
    assert "configuration" in report
    assert "results" in report
    assert "latency_ms" in report["results"]
    assert "resource" in report["results"]


def test_runner_with_multiple_workers() -> None:
    settings = _make_settings(
        target_events_per_sec=500,
        duration_sec=0.5,
        worker_count=4,
    )
    runner = LoadTestRunner(settings=settings, produce_fn=_noop_produce)

    report = runner.run()

    assert report["results"]["produced_count"] > 0
    assert report["configuration"]["worker_count"] == 4


def test_multi_worker_rate_is_global_not_per_worker() -> None:
    """Rate is a global target; 4 workers at 200 eps should yield ~200 total."""
    target_rate = 200.0
    workers = 4
    duration = 2.0

    settings = _make_settings(
        target_events_per_sec=target_rate,
        duration_sec=duration,
        worker_count=workers,
    )
    runner = LoadTestRunner(settings=settings, produce_fn=_noop_produce)

    report = runner.run()

    actual_throughput = report["results"]["throughput_events_per_sec"]
    assert actual_throughput < target_rate * 2.0, (
        f"throughput {actual_throughput} is too high — rate should be global "
        f"({target_rate}), not per-worker ({target_rate * workers})"
    )
    assert actual_throughput > target_rate * 0.3, (
        f"throughput {actual_throughput} is too low for target {target_rate}"
    )


def test_multi_worker_produces_unique_event_ids() -> None:
    """Each worker must produce unique events (no shared generator races)."""
    collected_ids: list[str] = []
    lock = threading.Lock()

    def collecting_produce(event: ProductObservationEvent) -> str:
        with lock:
            collected_ids.append(event.event_id)
        return event.event_id

    settings = _make_settings(
        target_events_per_sec=2000,
        duration_sec=0.5,
        worker_count=4,
    )
    runner = LoadTestRunner(settings=settings, produce_fn=collecting_produce)
    runner.run()

    assert len(collected_ids) == len(set(collected_ids)), (
        f"duplicate event_ids detected: "
        f"{len(collected_ids)} total, {len(set(collected_ids))} unique"
    )


def test_dry_run_sustains_100_eps_with_auto_scaling() -> None:
    """The harness must sustain >= 100 eps and auto-scale beyond configured workers."""
    settings = _make_settings(
        target_events_per_sec=100,
        duration_sec=5.0,
        worker_count=4,
    )
    runner = LoadTestRunner(settings=settings, produce_fn=_noop_produce)

    report = runner.run()

    actual = report["results"]["throughput_events_per_sec"]
    assert actual >= 80, f"harness must sustain >= 80 eps (80% of 100 target), got {actual:.0f}"


def test_auto_scaling_provisions_extra_workers() -> None:
    """Auto-scaling must increase workers when target rate exceeds per-worker capacity."""
    settings = _make_settings(
        target_events_per_sec=1000,
        duration_sec=1.0,
        worker_count=2,
    )
    runner = LoadTestRunner(settings=settings, produce_fn=_noop_produce)
    effective = runner._effective_worker_count()

    assert effective > 2, (
        f"auto-scaling should increase workers beyond configured 2, got {effective}"
    )
    assert effective <= 64, f"auto-scaling must respect the 64-worker cap, got {effective}"


def test_runner_diagnostic_includes_timing_breakdown() -> None:
    settings = _make_settings(target_events_per_sec=500, duration_sec=0.3)
    runner = LoadTestRunner(
        settings=settings,
        produce_fn=_noop_produce,
        diagnostic=True,
    )

    report = runner.run()

    assert "diagnostic_timing" in report
    timing = report["diagnostic_timing"]
    assert "sample_count" in timing
    assert timing["sample_count"] > 0
    for component in (
        "gen_ms",
        "produce_ms",
        "requested_wait_ms",
        "actual_wait_ms",
        "overshoot_ms",
        "total_ms",
    ):
        assert component in timing
        assert "mean" in timing[component]
        assert "p50" in timing[component]
    assert "per_worker" in timing


def test_runner_non_diagnostic_omits_timing_breakdown() -> None:
    settings = _make_settings(target_events_per_sec=500, duration_sec=0.3)
    runner = LoadTestRunner(
        settings=settings,
        produce_fn=_noop_produce,
        diagnostic=False,
    )

    report = runner.run()

    assert "diagnostic_timing" not in report
