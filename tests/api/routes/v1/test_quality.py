"""Tests for data quality endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from services.api.models import DataQualityResult

_NOW = datetime.now(timezone.utc)


def _ts(days_ago: int, hours_ago: int = 0) -> datetime:
    return _NOW - timedelta(days=days_ago, hours=hours_ago)


def _seed_quality(db: Session) -> None:
    results = [
        DataQualityResult(
            id=1,
            pipeline_run_id=1,
            observation_id=None,
            check_name="price_not_null",
            severity="error",
            passed=True,
            message="All prices present",
            checked_at=_ts(2),
            records_checked=100,
            failed_records=0,
            replay_key="q-001",
        ),
        DataQualityResult(
            id=2,
            pipeline_run_id=1,
            observation_id=None,
            check_name="price_not_null",
            severity="error",
            passed=False,
            message="5 missing prices",
            checked_at=_ts(1),
            records_checked=100,
            failed_records=5,
            replay_key="q-002",
        ),
        DataQualityResult(
            id=3,
            pipeline_run_id=2,
            observation_id=None,
            check_name="duplicate_external_id",
            severity="warning",
            passed=True,
            message=None,
            checked_at=_ts(1),
            records_checked=200,
            failed_records=0,
            replay_key="q-003",
        ),
        DataQualityResult(
            id=4,
            pipeline_run_id=None,
            observation_id=1,
            check_name="currency_valid",
            severity="info",
            passed=True,
            message="USD is valid",
            checked_at=_ts(0, hours_ago=-5),
            records_checked=50,
            failed_records=0,
            replay_key="q-004",
        ),
    ]
    db.add_all(results)
    db.commit()


@pytest.fixture()
def seeded_client(client: TestClient, db_session: Session) -> TestClient:
    _seed_quality(db_session)
    return client


class TestListQualityChecks:
    def test_empty(self, client: TestClient) -> None:
        response = client.get("/api/v1/quality")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_returns_all(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/quality")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 4
        assert len(body["items"]) == 4

    def test_pagination(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/quality?page=1&page_size=2")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 4
        assert len(body["items"]) == 2
        assert body["page"] == 1
        assert body["page_size"] == 2

    def test_filter_by_check_name(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/quality?check_name=price_not_null")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert all(item["check_name"] == "price_not_null" for item in body["items"])

    def test_filter_by_severity(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/quality?severity=warning")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["severity"] == "warning"

    def test_filter_by_passed(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/quality?passed=false")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["passed"] is False

    def test_filter_by_pipeline_run(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/quality?pipeline_run_id=1")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert all(item["pipeline_run_id"] == 1 for item in body["items"])

    def test_check_fields(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/quality?check_name=price_not_null&passed=false")
        body = response.json()
        item = body["items"][0]
        assert item["check_name"] == "price_not_null"
        assert item["severity"] == "error"
        assert item["passed"] is False
        assert item["failed_records"] == 5
        assert item["records_checked"] == 100
        assert item["message"] == "5 missing prices"

    def test_invalid_page(self, client: TestClient) -> None:
        response = client.get("/api/v1/quality?page=0")
        assert response.status_code == 422

    def test_invalid_page_size(self, client: TestClient) -> None:
        response = client.get("/api/v1/quality?page_size=200")
        assert response.status_code == 422


class TestQualitySummary:
    def test_empty(self, client: TestClient) -> None:
        response = client.get("/api/v1/quality/summary")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []

    def test_returns_summary(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/quality/summary")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 3
        by_name = {item["check_name"]: item for item in body["items"]}
        assert "price_not_null" in by_name
        assert "duplicate_external_id" in by_name
        assert "currency_valid" in by_name

    def test_summary_values(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/quality/summary")
        body = response.json()
        by_name = {item["check_name"]: item for item in body["items"]}
        price = by_name["price_not_null"]
        assert price["total_runs"] == 2
        assert price["passed_runs"] == 1
        assert price["failed_runs"] == 1
        assert price["severity"] == "error"

    def test_all_passed_summary(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/quality/summary")
        body = response.json()
        by_name = {item["check_name"]: item for item in body["items"]}
        dup = by_name["duplicate_external_id"]
        assert dup["total_runs"] == 1
        assert dup["passed_runs"] == 1
        assert dup["failed_runs"] == 0
