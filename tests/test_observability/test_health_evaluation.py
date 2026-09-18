"""Unit tests for ingestion health evaluation (TASK-059)."""

from __future__ import annotations

from datetime import datetime, timezone

from libs.observability.health_assessment import (
    FreshnessState,
    SourceDegradationState,
    SourceHealthConfig,
)
from libs.observability.health_evaluation import (
    IngestionHealthEvaluator,
    SourceHealthEvaluationConfig,
    SourceObservation,
)

FIXED_NOW = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)


def _fixed_clock() -> datetime:
    return FIXED_NOW


class TestSourceObservation:
    def test_defaults(self) -> None:
        obs = SourceObservation(source_name="test_source")
        assert obs.source_name == "test_source"
        assert obs.last_observation_at is None
        assert obs.total_observations == 0
        assert obs.recent_fetch_outcomes == []


class TestIngestionHealthEvaluator:
    def test_evaluate_source_no_data(self) -> None:
        evaluator = IngestionHealthEvaluator(clock=_fixed_clock)
        obs = SourceObservation(source_name="fake_store")

        result = evaluator.evaluate_source(obs)

        assert result.source_name == "fake_store"
        assert result.assessment.state == SourceDegradationState.HEALTHY
        assert result.freshness_state == FreshnessState.NEVER_COLLECTED
        assert result.freshness_age_seconds is None

    def test_evaluate_source_fresh(self) -> None:
        config = SourceHealthEvaluationConfig(
            source_configs={
                "fake_store": SourceHealthConfig(max_freshness_age_seconds=3600),
            }
        )
        evaluator = IngestionHealthEvaluator(evaluation_config=config, clock=_fixed_clock)

        obs = SourceObservation(
            source_name="fake_store",
            last_observation_at=datetime(2026, 9, 18, 11, 30, 0, tzinfo=timezone.utc),
            total_observations=100,
        )

        result = evaluator.evaluate_source(obs)

        assert result.freshness_state == FreshnessState.FRESH
        assert result.freshness_age_seconds == 1800.0
        assert result.assessment.state == SourceDegradationState.HEALTHY

    def test_evaluate_source_stale(self) -> None:
        config = SourceHealthEvaluationConfig(
            source_configs={
                "fake_store": SourceHealthConfig(max_freshness_age_seconds=3600),
            }
        )
        evaluator = IngestionHealthEvaluator(evaluation_config=config, clock=_fixed_clock)

        obs = SourceObservation(
            source_name="fake_store",
            last_observation_at=datetime(2026, 9, 18, 10, 0, 0, tzinfo=timezone.utc),
            total_observations=100,
            recent_fetch_outcomes=[
                {"success": True, "events_emitted": 10, "total_records": 10},
            ],
        )

        result = evaluator.evaluate_source(obs)

        assert result.freshness_state == FreshnessState.STALE
        assert result.freshness_age_seconds == 7200.0
        assert result.assessment.state == SourceDegradationState.STALE

    def test_evaluate_source_with_failed_fetches(self) -> None:
        config = SourceHealthEvaluationConfig(
            source_configs={
                "best_buy": SourceHealthConfig(min_success_ratio=0.5),
            }
        )
        evaluator = IngestionHealthEvaluator(evaluation_config=config, clock=_fixed_clock)

        obs = SourceObservation(
            source_name="best_buy",
            recent_fetch_outcomes=[
                {"success": True, "events_emitted": 10, "total_records": 10},
                {"success": False, "failure_reason": "connection timeout"},
                {"success": False, "failure_reason": "connection timeout"},
                {"success": False, "failure_reason": "connection timeout"},
            ],
        )

        result = evaluator.evaluate_source(obs)

        assert result.assessment.state == SourceDegradationState.UNREACHABLE

    def test_evaluate_source_with_empty_fetches(self) -> None:
        config = SourceHealthEvaluationConfig(
            source_configs={
                "fake_store": SourceHealthConfig(max_empty_fetches=2),
            }
        )
        evaluator = IngestionHealthEvaluator(evaluation_config=config, clock=_fixed_clock)

        obs = SourceObservation(
            source_name="fake_store",
            recent_fetch_outcomes=[
                {"success": True, "events_emitted": 0, "total_records": 0},
                {"success": True, "events_emitted": 0, "total_records": 0},
                {"success": True, "events_emitted": 0, "total_records": 0},
            ],
        )

        result = evaluator.evaluate_source(obs)

        assert result.assessment.state == SourceDegradationState.EMPTY_RESULT

    def test_evaluate_all(self) -> None:
        evaluator = IngestionHealthEvaluator(clock=_fixed_clock)
        observations = [
            SourceObservation(source_name="fake_store"),
            SourceObservation(source_name="best_buy"),
        ]

        results = evaluator.evaluate_all(observations)

        assert len(results) == 2
        assert results[0].source_name == "fake_store"
        assert results[1].source_name == "best_buy"

    def test_evaluate_uses_default_config_for_unknown_source(self) -> None:
        config = SourceHealthEvaluationConfig(
            source_configs={
                "fake_store": SourceHealthConfig(max_freshness_age_seconds=3600),
            },
            default_config=SourceHealthConfig(max_freshness_age_seconds=7200),
        )
        evaluator = IngestionHealthEvaluator(evaluation_config=config, clock=_fixed_clock)

        obs = SourceObservation(
            source_name="unknown_source",
            last_observation_at=datetime(2026, 9, 18, 9, 0, 0, tzinfo=timezone.utc),
        )

        result = evaluator.evaluate_source(obs)

        assert result.freshness_age_seconds == 10800.0
        assert result.freshness_state == FreshnessState.STALE


class TestIngestionHealthEvaluation:
    def test_to_dict(self) -> None:
        evaluator = IngestionHealthEvaluator(clock=_fixed_clock)
        obs = SourceObservation(source_name="fake_store")
        result = evaluator.evaluate_source(obs)

        d = result.to_dict()

        assert d["source_name"] == "fake_store"
        assert d["state"] == "healthy"
        assert d["freshness_state"] == "never_collected"
        assert isinstance(d["reasons"], list)
        assert isinstance(d["signals"], dict)
        assert d["freshness_age_seconds"] is None
        assert "assessed_at" in d
