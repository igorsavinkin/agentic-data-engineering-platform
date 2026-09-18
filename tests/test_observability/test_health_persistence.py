"""Unit tests for ingestion health persistence (TASK-059)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from libs.observability.health_assessment import (
    FreshnessState,
    SourceDegradationState,
    SourceHealthAssessment,
)
from libs.observability.health_evaluation import IngestionHealthEvaluation
from libs.observability.health_persistence import (
    HealthPersistenceConfig,
    HealthWriteResult,
    IngestionHealthResultWriter,
    make_health_replay_key,
)

FIXED_NOW = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)


def _make_evaluation(
    source_name: str = "fake_store",
    state: SourceDegradationState = SourceDegradationState.HEALTHY,
    freshness_state: FreshnessState = FreshnessState.FRESH,
) -> IngestionHealthEvaluation:
    assessment = SourceHealthAssessment(
        state=state,
        reasons=["test reason"],
        source=source_name,
        assessed_at=FIXED_NOW,
        signals={"total_fetches": 10},
    )
    return IngestionHealthEvaluation(
        source_name=source_name,
        assessment=assessment,
        freshness_state=freshness_state,
        freshness_age_seconds=1800.0,
    )


class TestMakeHealthReplayKey:
    def test_deterministic(self) -> None:
        key1 = make_health_replay_key("fake_store", "2026-09-18T12:00:00")
        key2 = make_health_replay_key("fake_store", "2026-09-18T12:00:00")
        assert key1 == key2

    def test_different_sources_different_keys(self) -> None:
        key1 = make_health_replay_key("fake_store", "2026-09-18T12:00:00")
        key2 = make_health_replay_key("best_buy", "2026-09-18T12:00:00")
        assert key1 != key2

    def test_different_dates_different_keys(self) -> None:
        key1 = make_health_replay_key("fake_store", "2026-09-18T12:00:00")
        key2 = make_health_replay_key("fake_store", "2026-09-18T13:00:00")
        assert key1 != key2

    def test_format(self) -> None:
        key = make_health_replay_key("fake_store", "2026-09-18T12:00:00")
        assert key == "fake_store:2026-09-18T12:00:00"


class TestHealthPersistenceConfig:
    @patch.dict(
        "os.environ",
        {
            "WAREHOUSE_DB_HOST": "testhost",
            "WAREHOUSE_DB_PORT": "5433",
            "WAREHOUSE_DB_NAME": "testdb",
            "WAREHOUSE_DB_USER": "testuser",
            "WAREHOUSE_DB_PASSWORD": "testpass",
        },
    )
    def test_from_env(self) -> None:
        config = HealthPersistenceConfig.from_env()
        assert "testhost" in config.db_url
        assert "5433" in config.db_url
        assert "testdb" in config.db_url


class TestIngestionHealthResultWriter:
    @patch("libs.observability.health_persistence.psycopg2")
    def test_write_evaluations_empty(self, mock_psycopg2: MagicMock) -> None:
        config = HealthPersistenceConfig(db_url="postgresql://test")
        writer = IngestionHealthResultWriter(config)

        result = writer.write_evaluations([], logical_date="2026-09-18T12:00:00")

        assert result.written == 0
        assert result.success
        mock_psycopg2.connect.assert_not_called()

    @patch("libs.observability.health_persistence.execute_batch")
    @patch("libs.observability.health_persistence.psycopg2")
    def test_write_evaluations_success(
        self, mock_psycopg2: MagicMock, mock_execute_batch: MagicMock
    ) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        config = HealthPersistenceConfig(db_url="postgresql://test")
        writer = IngestionHealthResultWriter(config)

        evaluations = [
            _make_evaluation("fake_store"),
            _make_evaluation("best_buy"),
        ]

        result = writer.write_evaluations(evaluations, logical_date="2026-09-18T12:00:00")

        assert result.written == 2
        assert result.success
        mock_psycopg2.connect.assert_called_once()
        mock_execute_batch.assert_called_once()
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch("libs.observability.health_persistence.psycopg2")
    def test_write_evaluations_rolls_back_on_error(self, mock_psycopg2: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        with patch(
            "libs.observability.health_persistence.execute_batch",
            side_effect=Exception("db error"),
        ):
            config = HealthPersistenceConfig(db_url="postgresql://test")
            writer = IngestionHealthResultWriter(config)

            try:
                writer.write_evaluations([_make_evaluation()], logical_date="2026-09-18T12:00:00")
            except Exception:
                pass

            mock_conn.rollback.assert_called_once()
            mock_conn.close.assert_called_once()


class TestHealthWriteResult:
    def test_success_when_no_errors(self) -> None:
        result = HealthWriteResult(written=5, skipped=2)
        assert result.success

    def test_failure_when_errors(self) -> None:
        result = HealthWriteResult(written=0, errors=["db error"])
        assert not result.success
