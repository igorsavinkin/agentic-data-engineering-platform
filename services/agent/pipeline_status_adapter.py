"""Concrete adapter bridging PipelineStatusRepository and KafkaMetrics to the agent tool.

Implements PipelineStatusProvider by delegating to the existing repository
and Kafka metrics layer, avoiding duplication of business logic.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class RepositoryPipelineStatusProvider:
    """Concrete PipelineStatusProvider backed by the API repository and Kafka metrics."""

    def __init__(
        self,
        repository: Any,
        lag_samples_fn: Callable[[], list[Any]] | None = None,
    ) -> None:
        self._repo = repository
        self._lag_samples_fn = lag_samples_fn

    def list_recent_runs(self, limit: int = 5) -> list[dict[str, Any]]:
        result = self._repo.list_pipeline_runs(page=1, page_size=limit)
        return [
            {
                "run_type": entry.run_type,
                "overall_status": entry.overall_status,
                "started_at": entry.started_at,
                "finished_at": entry.finished_at,
                "records_loaded": entry.records_loaded,
                "error_message": entry.error_message,
            }
            for entry in result.items
        ]

    def get_total_run_count(self) -> int:
        result = self._repo.list_pipeline_runs(page=1, page_size=1)
        return int(result.total)

    def list_source_health(self) -> list[dict[str, Any]]:
        result = self._repo.list_source_health()
        return [
            {
                "source_name": entry.source_name,
                "overall_status": entry.overall_status,
                "freshness_state": entry.freshness_state,
                "freshness_age_seconds": entry.freshness_age_seconds,
                "reasons": entry.reasons,
            }
            for entry in result.items
        ]

    def get_lag_samples(self) -> list[dict[str, Any]]:
        if self._lag_samples_fn is None:
            return []
        samples = self._lag_samples_fn()
        return [
            {
                "topic": s.topic,
                "partition": s.partition,
                "lag": s.lag,
            }
            for s in samples
        ]
