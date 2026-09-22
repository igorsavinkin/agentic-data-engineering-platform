"""Tests for the load-test report module (TASK-108)."""

from __future__ import annotations

import json
import os
import tempfile

from libs.load_test.report import build_report, write_report


def test_build_report_structure() -> None:
    settings = {"target_events_per_sec": 100.0, "duration_sec": 30.0}
    metrics = {
        "produced_count": 3000,
        "error_count": 0,
        "throughput_events_per_sec": 99.5,
        "duration_sec": 30.1,
        "latency_ms": {"min": 1.0, "p50": 2.0, "max": 10.0},
        "resource": {"peak_rss_mb": 50.0, "total_cpu_sec": 5.0},
    }

    report = build_report(settings, metrics, run_id="test-run-123")

    assert report["run_id"] == "test-run-123"
    assert report["configuration"] == settings
    assert report["results"] == metrics
    assert "timestamp" in report
    assert "environment" in report
    assert "python_version" in report["environment"]
    assert "platform" in report["environment"]


def test_write_report_creates_file() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "nested", "report.json")
        report = {"run_id": "abc", "data": "test"}

        result = write_report(report, path)

        assert result.exists()
        content = json.loads(result.read_text(encoding="utf-8"))
        assert content["run_id"] == "abc"


def test_write_report_is_valid_json() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "report.json")
        report = build_report(
            {"rate": 100},
            {"count": 50},
            run_id="json-test",
        )

        write_report(report, path)

        with open(path, encoding="utf-8") as f:
            parsed = json.load(f)
        assert parsed["run_id"] == "json-test"
