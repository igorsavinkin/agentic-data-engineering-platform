"""Concrete adapter bridging DataQualityRepository to the agent tool.

Implements DataQualityProvider by delegating to the existing repository,
avoiding duplication of business logic.
"""

from __future__ import annotations

from typing import Any, Optional


class RepositoryDataQualityProvider:
    """Concrete DataQualityProvider backed by the API quality repository."""

    def __init__(self, repository: Any) -> None:
        self._repo = repository

    def list_recent_checks(
        self, limit: int = 10, check_name: Optional[str] = None
    ) -> list[dict[str, Any]]:
        result = self._repo.list_quality_checks(page=1, page_size=limit, check_name=check_name)
        return [
            {
                "check_name": entry.check_name,
                "severity": entry.severity,
                "passed": entry.passed,
                "message": entry.message,
                "checked_at": entry.checked_at,
                "records_checked": entry.records_checked,
                "failed_records": entry.failed_records,
                "details": entry.details,
            }
            for entry in result.items
        ]

    def get_quality_summary(self) -> list[dict[str, Any]]:
        result = self._repo.list_quality_summary()
        return [
            {
                "check_name": entry.check_name,
                "total_runs": entry.total_runs,
                "passed_runs": entry.passed_runs,
                "failed_runs": entry.failed_runs,
                "last_checked_at": entry.last_checked_at,
                "severity": entry.severity,
            }
            for entry in result.items
        ]
