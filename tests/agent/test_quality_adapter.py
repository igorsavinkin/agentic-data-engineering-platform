"""Tests for the concrete data quality adapter (TASK-096)."""

from __future__ import annotations

from unittest.mock import MagicMock

from services.agent.quality_adapter import RepositoryDataQualityProvider


class FakeRepo:
    """Minimal fake matching DataQualityRepository interface."""

    def __init__(self) -> None:
        self.check_result = MagicMock()
        self.check_result.items = []
        self.summary_result = MagicMock()
        self.summary_result.items = []
        self.list_quality_checks = MagicMock(return_value=self.check_result)
        self.list_quality_summary = MagicMock(return_value=self.summary_result)


class TestRepositoryDataQualityProvider:
    def test_list_recent_checks(self) -> None:
        repo = FakeRepo()
        entry = MagicMock()
        entry.check_name = "required_fields"
        entry.severity = "error"
        entry.passed = True
        entry.message = "All fields present"
        entry.checked_at = "2026-09-20T10:00:00"
        entry.records_checked = 500
        entry.failed_records = 0
        entry.details = None
        repo.check_result.items = [entry]

        provider = RepositoryDataQualityProvider(repo)
        checks = provider.list_recent_checks(limit=5)

        assert len(checks) == 1
        assert checks[0]["check_name"] == "required_fields"
        assert checks[0]["passed"] is True

    def test_list_recent_checks_with_filter(self) -> None:
        repo = FakeRepo()
        provider = RepositoryDataQualityProvider(repo)
        provider.list_recent_checks(limit=3, check_name="freshness")
        repo.list_quality_checks.assert_called_with(page=1, page_size=3, check_name="freshness")

    def test_get_quality_summary(self) -> None:
        repo = FakeRepo()
        entry = MagicMock()
        entry.check_name = "price_validity"
        entry.total_runs = 20
        entry.passed_runs = 18
        entry.failed_runs = 2
        entry.last_checked_at = "2026-09-20T10:00:00"
        entry.severity = "error"
        repo.summary_result.items = [entry]

        provider = RepositoryDataQualityProvider(repo)
        summary = provider.get_quality_summary()

        assert len(summary) == 1
        assert summary[0]["check_name"] == "price_validity"
        assert summary[0]["failed_runs"] == 2

    def test_empty_results(self) -> None:
        provider = RepositoryDataQualityProvider(FakeRepo())
        assert provider.list_recent_checks() == []
        assert provider.get_quality_summary() == []
