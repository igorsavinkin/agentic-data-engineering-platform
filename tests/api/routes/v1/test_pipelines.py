"""Tests for pipeline status endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from services.api.models import (
    IngestionHealthResult,
    PipelineRun,
)

_NOW = datetime.now(timezone.utc)


def _ts(days_ago: int, hours_ago: int = 0) -> datetime:
    return _NOW - timedelta(days=days_ago, hours=hours_ago)


def _seed_pipeline_runs(db: Session) -> None:
    runs = [
        PipelineRun(
            id=1,
            run_type="full_load",
            status="success",
            started_at=_ts(5),
            finished_at=_ts(5, hours_ago=-1),
            records_loaded=1000,
            error_message=None,
        ),
        PipelineRun(
            id=2,
            run_type="incremental",
            status="running",
            started_at=_ts(0, hours_ago=-2),
            finished_at=None,
            records_loaded=None,
            error_message=None,
        ),
        PipelineRun(
            id=3,
            run_type="incremental",
            status="failed",
            started_at=_ts(1),
            finished_at=_ts(1, hours_ago=-1),
            records_loaded=0,
            error_message="Connection timeout",
        ),
    ]
    db.add_all(runs)
    db.commit()


def _seed_health_results(db: Session) -> None:
    results = [
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
            logical_date="2026-09-19",
            replay_key="fs-2026-09-19",
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
            logical_date="2026-09-19",
            replay_key="bb-2026-09-19",
        ),
        IngestionHealthResult(
            id=3,
            source_name="fake_store",
            state="healthy",
            freshness_state="fresh",
            reasons=None,
            signals=None,
            freshness_age_seconds=600.0,
            assessed_at=_ts(1, hours_ago=-1),
            evaluated_at=_ts(1, hours_ago=-1),
            logical_date="2026-09-18",
            replay_key="fs-2026-09-18",
        ),
    ]
    db.add_all(results)
    db.commit()


@pytest.fixture()
def seeded_client(client: TestClient, db_session: Session) -> TestClient:
    _seed_pipeline_runs(db_session)
    _seed_health_results(db_session)
    return client


class TestListPipelineRuns:
    def test_empty(self, client: TestClient) -> None:
        response = client.get("/api/v1/pipelines")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_returns_all_runs(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/pipelines")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert len(body["items"]) == 3

    def test_pagination(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/pipelines?page=1&page_size=2")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert len(body["items"]) == 2
        assert body["page"] == 1
        assert body["page_size"] == 2

    def test_status_filter(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/pipelines?status=failed")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["status"] == "failed"
        assert body["items"][0]["overall_status"] == "failed"

    def test_overall_status_mapping(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/pipelines")
        body = response.json()
        by_id = {item["id"]: item for item in body["items"]}
        assert by_id[1]["overall_status"] == "healthy"
        assert by_id[2]["overall_status"] == "healthy"
        assert by_id[3]["overall_status"] == "failed"

    def test_invalid_page(self, client: TestClient) -> None:
        response = client.get("/api/v1/pipelines?page=0")
        assert response.status_code == 422

    def test_invalid_page_size(self, client: TestClient) -> None:
        response = client.get("/api/v1/pipelines?page_size=200")
        assert response.status_code == 422


class TestGetPipelineRun:
    def test_not_found(self, client: TestClient) -> None:
        response = client.get("/api/v1/pipelines/999")
        assert response.status_code == 404

    def test_returns_run(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/pipelines/1")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == 1
        assert body["run_type"] == "full_load"
        assert body["status"] == "success"
        assert body["overall_status"] == "healthy"
        assert body["records_loaded"] == 1000
        assert body["error_message"] is None

    def test_failed_run(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/pipelines/3")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "failed"
        assert body["overall_status"] == "failed"
        assert body["error_message"] == "Connection timeout"


class TestSourceHealth:
    def test_empty(self, client: TestClient) -> None:
        response = client.get("/api/v1/pipelines/source-health")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []

    def test_returns_latest_per_source(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/pipelines/source-health")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 2
        by_name = {item["source_name"]: item for item in body["items"]}
        assert "fake_store" in by_name
        assert "best_buy" in by_name

    def test_status_mapping_healthy(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/pipelines/source-health")
        body = response.json()
        by_name = {item["source_name"]: item for item in body["items"]}
        fs = by_name["fake_store"]
        assert fs["overall_status"] == "healthy"
        assert fs["degradation_state"] == "healthy"
        assert fs["freshness_state"] == "fresh"

    def test_status_mapping_stale(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/pipelines/source-health")
        body = response.json()
        by_name = {item["source_name"]: item for item in body["items"]}
        bb = by_name["best_buy"]
        assert bb["overall_status"] == "stale"
        assert bb["freshness_state"] == "stale"

    def test_source_filter(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/pipelines/source-health?source_name=fake_store")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["source_name"] == "fake_store"

    def test_limit(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/pipelines/source-health?limit=1")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) <= 1

    def test_invalid_limit(self, client: TestClient) -> None:
        response = client.get("/api/v1/pipelines/source-health?limit=0")
        assert response.status_code == 422
