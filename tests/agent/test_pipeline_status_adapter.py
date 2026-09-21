"""Tests for the concrete pipeline status adapter (TASK-095)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from services.agent.pipeline_status_adapter import RepositoryPipelineStatusProvider


class FakeRepo:
    """Minimal fake matching PipelineStatusRepository interface."""

    def __init__(self) -> None:
        self.run_result = MagicMock()
        self.run_result.items = []
        self.run_result.total = 0
        self.health_result = MagicMock()
        self.health_result.items = []

    def list_pipeline_runs(self, page: int = 1, page_size: int = 20, status: Any = None) -> Any:
        return self.run_result

    def list_source_health(self, source_name: Any = None, limit: int = 20) -> Any:
        return self.health_result


class TestRepositoryPipelineStatusProvider:
    def test_list_recent_runs(self) -> None:
        repo = FakeRepo()
        entry = MagicMock()
        entry.run_type = "ingestion"
        entry.overall_status = "healthy"
        entry.started_at = "2026-09-20T10:00:00"
        entry.finished_at = "2026-09-20T10:05:00"
        entry.records_loaded = 100
        entry.error_message = None
        repo.run_result.items = [entry]
        repo.run_result.total = 50

        provider = RepositoryPipelineStatusProvider(repo)
        runs = provider.list_recent_runs(limit=5)

        assert len(runs) == 1
        assert runs[0]["run_type"] == "ingestion"
        assert runs[0]["records_loaded"] == 100

    def test_get_total_run_count(self) -> None:
        repo = FakeRepo()
        repo.run_result.total = 42

        provider = RepositoryPipelineStatusProvider(repo)
        assert provider.get_total_run_count() == 42

    def test_list_source_health(self) -> None:
        repo = FakeRepo()
        entry = MagicMock()
        entry.source_name = "fake_store"
        entry.overall_status = "healthy"
        entry.freshness_state = "fresh"
        entry.freshness_age_seconds = 60.0
        entry.reasons = None
        repo.health_result.items = [entry]

        provider = RepositoryPipelineStatusProvider(repo)
        sources = provider.list_source_health()

        assert len(sources) == 1
        assert sources[0]["source_name"] == "fake_store"

    def test_get_lag_samples_with_fn(self) -> None:
        sample = MagicMock()
        sample.topic = "products.raw.v1"
        sample.partition = 0
        sample.lag = 15

        provider = RepositoryPipelineStatusProvider(FakeRepo(), lag_samples_fn=lambda: [sample])
        lag = provider.get_lag_samples()

        assert len(lag) == 1
        assert lag[0]["topic"] == "products.raw.v1"
        assert lag[0]["lag"] == 15

    def test_get_lag_samples_without_fn(self) -> None:
        provider = RepositoryPipelineStatusProvider(FakeRepo())
        assert provider.get_lag_samples() == []
