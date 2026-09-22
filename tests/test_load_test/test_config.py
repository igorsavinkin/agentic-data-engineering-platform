"""Tests for the load-test configuration (TASK-108)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from libs.load_test.config import LoadTestSettings


def test_default_settings() -> None:
    settings = LoadTestSettings()
    assert settings.target_events_per_sec == 100.0
    assert settings.duration_sec == 30.0
    assert settings.total_events == 0
    assert settings.worker_count == 1
    assert settings.source_name == "load-test"
    assert settings.seed == 42
    assert settings.output_path == "load_test_results.json"


def test_custom_settings() -> None:
    settings = LoadTestSettings(
        target_events_per_sec=500.0,
        duration_sec=60.0,
        total_events=1000,
        worker_count=4,
        source_name="custom",
        seed=99,
    )
    assert settings.target_events_per_sec == 500.0
    assert settings.duration_sec == 60.0
    assert settings.total_events == 1000
    assert settings.worker_count == 4
    assert settings.source_name == "custom"
    assert settings.seed == 99


def test_rejects_zero_rate() -> None:
    with pytest.raises(ValidationError):
        LoadTestSettings(target_events_per_sec=0)


def test_rejects_negative_rate() -> None:
    with pytest.raises(ValidationError):
        LoadTestSettings(target_events_per_sec=-10)


def test_rejects_zero_duration() -> None:
    with pytest.raises(ValidationError):
        LoadTestSettings(duration_sec=0)


def test_rejects_negative_total_events() -> None:
    with pytest.raises(ValidationError):
        LoadTestSettings(total_events=-1)


def test_rejects_zero_workers() -> None:
    with pytest.raises(ValidationError):
        LoadTestSettings(worker_count=0)


def test_rejects_too_many_workers() -> None:
    with pytest.raises(ValidationError):
        LoadTestSettings(worker_count=100)
