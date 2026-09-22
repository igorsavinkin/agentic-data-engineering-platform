"""Tests for the load-test runner (TASK-108)."""

from __future__ import annotations

import os
import tempfile
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
