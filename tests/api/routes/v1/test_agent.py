"""Tests for the agent ask endpoint."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from services.api.models import (
    DataQualityResult,
    IngestionHealthResult,
    PipelineRun,
)

_NOW = datetime.now(timezone.utc)


def _ts(days_ago: int, hours_ago: int = 0) -> datetime:
    return _NOW - timedelta(days=days_ago, hours=hours_ago)


def _seed_data(db: Session) -> None:
    db.add_all(
        [
            PipelineRun(
                id=1,
                run_type="full_load",
                status="success",
                started_at=_ts(1),
                finished_at=_ts(1, hours_ago=-1),
                records_loaded=500,
                error_message=None,
            ),
            PipelineRun(
                id=2,
                run_type="incremental",
                status="failed",
                started_at=_ts(0, hours_ago=-2),
                finished_at=_ts(0, hours_ago=-1),
                records_loaded=0,
                error_message="Connection timeout",
            ),
        ]
    )
    db.add_all(
        [
            IngestionHealthResult(
                id=1,
                source_name="fake_store",
                state="healthy",
                freshness_state="fresh",
                reasons=None,
                signals=None,
                freshness_age_seconds=300.0,
                assessed_at=_ts(0, hours_ago=-1),
                evaluated_at=_ts(0, hours_ago=-1),
                logical_date="2026-09-21",
                replay_key="fs-2026-09-21",
            ),
            IngestionHealthResult(
                id=2,
                source_name="best_buy",
                state="unreachable",
                freshness_state="stale",
                reasons={"http_code": 503},
                signals=None,
                freshness_age_seconds=86400.0,
                assessed_at=_ts(0, hours_ago=-2),
                evaluated_at=_ts(0, hours_ago=-2),
                logical_date="2026-09-21",
                replay_key="bb-2026-09-21",
            ),
        ]
    )
    db.add_all(
        [
            DataQualityResult(
                id=1,
                check_name="null_check",
                severity="error",
                passed=True,
                message=None,
                checked_at=_ts(0, hours_ago=-1),
                records_checked=500,
                failed_records=0,
                pipeline_run_id=1,
                observation_id=None,
                details=None,
            ),
            DataQualityResult(
                id=2,
                check_name="schema_validation",
                severity="warning",
                passed=False,
                message="Unexpected column type",
                checked_at=_ts(0, hours_ago=-2),
                records_checked=500,
                failed_records=10,
                pipeline_run_id=1,
                observation_id=None,
                details=None,
            ),
        ]
    )
    db.commit()


@pytest.fixture()
def seeded_client(client: TestClient, db_session: Session) -> TestClient:
    _seed_data(db_session)
    return client


class TestAgentAsk:
    def test_pipeline_status_question(self, seeded_client: TestClient) -> None:
        response = seeded_client.post(
            "/api/v1/agent/ask",
            json={"question": "What is the pipeline status?"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["intent"] == "pipeline_status"
        assert isinstance(body["answer"], str)
        assert len(body["answer"]) > 0
        assert isinstance(body["confidence"], float)
        assert 0.0 <= body["confidence"] <= 1.0

    def test_data_quality_question(self, seeded_client: TestClient) -> None:
        response = seeded_client.post(
            "/api/v1/agent/ask",
            json={"question": "Show me data quality checks"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["intent"] == "data_quality"
        assert body["status"] == "ok"

    def test_source_health_question(self, seeded_client: TestClient) -> None:
        response = seeded_client.post(
            "/api/v1/agent/ask",
            json={"question": "Which sources have freshness problems?"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["intent"] == "source_health"
        assert body["status"] == "ok"

    def test_general_intent_fallback(self, seeded_client: TestClient) -> None:
        response = seeded_client.post(
            "/api/v1/agent/ask",
            json={"question": "What is the meaning of life?"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["intent"] == "general"
        assert "rephrase" in body["answer"].lower() or "help" in body["answer"].lower()

    def test_empty_question_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/agent/ask",
            json={"question": ""},
        )
        assert response.status_code == 422

    def test_missing_question_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/agent/ask",
            json={},
        )
        assert response.status_code == 422

    def test_whitespace_question_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/agent/ask",
            json={"question": "   "},
        )
        assert response.status_code == 422

    def test_response_sources_list(self, seeded_client: TestClient) -> None:
        response = seeded_client.post(
            "/api/v1/agent/ask",
            json={"question": "What is the pipeline status?"},
        )
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["sources"], list)

    def test_no_db_data_still_works(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/agent/ask",
            json={"question": "What is the pipeline status?"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["intent"] == "pipeline_status"
        assert body["status"] == "ok"
