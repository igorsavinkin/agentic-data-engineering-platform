"""Tests for RepositorySourceHealthProvider adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
from unittest.mock import MagicMock

from services.agent.source_health_adapter import RepositorySourceHealthProvider


@dataclass(frozen=True)
class FakeSourceHealthEntry:
    source_name: str
    overall_status: str
    degradation_state: str
    freshness_state: str
    freshness_age_seconds: Optional[float]
    assessed_at: str
    reasons: Optional[dict[str, Any]]
    signals: Optional[dict[str, Any]] = None


@dataclass(frozen=True)
class FakeSourceHealthResult:
    items: list[FakeSourceHealthEntry]


class TestRepositorySourceHealthProvider:
    def setup_method(self) -> None:
        self.entries = [
            FakeSourceHealthEntry(
                source_name="api_a",
                overall_status="healthy",
                degradation_state="healthy",
                freshness_state="fresh",
                freshness_age_seconds=60.0,
                assessed_at="2026-09-21T10:00:00",
                reasons=None,
                signals={"success_ratio": 1.0},
            ),
            FakeSourceHealthEntry(
                source_name="api_b",
                overall_status="degraded",
                degradation_state="unreachable",
                freshness_state="fresh",
                freshness_age_seconds=10.0,
                assessed_at="2026-09-21T10:00:00",
                reasons={"detail": "Connection refused"},
                signals={"success_ratio": 0.0, "failed_fetches": 5},
            ),
        ]
        self.result = FakeSourceHealthResult(items=self.entries)

    def test_list_source_health_returns_dicts(self) -> None:
        repo = MagicMock()
        repo.list_source_health = MagicMock(return_value=self.result)

        provider = RepositorySourceHealthProvider(repo)
        result = provider.list_source_health()

        assert len(result) == 2
        assert result[0]["source_name"] == "api_a"
        assert result[0]["degradation_state"] == "healthy"
        assert result[0]["signals"]["success_ratio"] == 1.0
        assert result[1]["source_name"] == "api_b"
        assert result[1]["degradation_state"] == "unreachable"
        assert result[1]["signals"]["failed_fetches"] == 5

    def test_passes_source_name_filter(self) -> None:
        repo = MagicMock()
        repo.list_source_health = MagicMock(return_value=self.result)

        provider = RepositorySourceHealthProvider(repo)
        provider.list_source_health(source_name="api_a")

        repo.list_source_health.assert_called_once_with(source_name="api_a")

    def test_empty_result(self) -> None:
        repo = MagicMock()
        repo.list_source_health = MagicMock(return_value=FakeSourceHealthResult(items=[]))

        provider = RepositorySourceHealthProvider(repo)
        result = provider.list_source_health()

        assert result == []

    def test_surfaces_none_signals(self) -> None:
        entry = FakeSourceHealthEntry(
            source_name="api_c",
            overall_status="stale",
            degradation_state="healthy",
            freshness_state="stale",
            freshness_age_seconds=7200.0,
            assessed_at="2026-09-21T08:00:00",
            reasons=None,
            signals=None,
        )
        repo = MagicMock()
        repo.list_source_health = MagicMock(return_value=FakeSourceHealthResult(items=[entry]))

        provider = RepositorySourceHealthProvider(repo)
        result = provider.list_source_health()

        assert result[0]["signals"] is None
        assert result[0]["freshness_age_seconds"] == 7200.0
