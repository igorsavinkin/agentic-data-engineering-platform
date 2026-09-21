"""Concrete adapter bridging PipelineStatusRepository to the source health agent tool.

Implements SourceHealthProvider by delegating to the existing repository,
avoiding duplication of business logic.
"""

from __future__ import annotations

from typing import Any, Optional


class RepositorySourceHealthProvider:
    """Concrete SourceHealthProvider backed by the API repository."""

    def __init__(self, repository: Any) -> None:
        self._repo = repository

    def list_source_health(self, source_name: Optional[str] = None) -> list[dict[str, Any]]:
        result = self._repo.list_source_health(source_name=source_name)
        return [
            {
                "source_name": entry.source_name,
                "overall_status": entry.overall_status,
                "degradation_state": entry.degradation_state,
                "freshness_state": entry.freshness_state,
                "freshness_age_seconds": entry.freshness_age_seconds,
                "assessed_at": entry.assessed_at,
                "reasons": entry.reasons,
                "signals": entry.signals,
            }
            for entry in result.items
        ]
