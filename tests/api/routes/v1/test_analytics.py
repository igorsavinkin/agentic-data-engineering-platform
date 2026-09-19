"""Tests for price analytics endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from services.api.models import Product, ProductObservation, Source, SourceProduct

_NOW = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)


def _ts(days_ago: int) -> datetime:
    return _NOW - timedelta(days=days_ago)


def _seed_data(db: Session) -> None:
    """Insert test data: 2 sources, 2 products, multiple observations."""
    src1 = Source(id=1, name="fake_store", description="Fake Store API")
    src1.created_at = _ts(60)
    src1.updated_at = _ts(60)
    src2 = Source(id=2, name="best_buy", description="Best Buy API")
    src2.created_at = _ts(60)
    src2.updated_at = _ts(60)
    db.add_all([src1, src2])

    p1 = Product(id=1, canonical_name="Widget A", category="widgets")
    p1.created_at = _ts(60)
    p1.updated_at = _ts(60)
    p2 = Product(id=2, canonical_name="Gadget B", category="gadgets")
    p2.created_at = _ts(60)
    p2.updated_at = _ts(60)
    db.add_all([p1, p2])

    sp1 = SourceProduct(id=1, source_id=1, product_id=1, external_id="FS-001")
    sp1.created_at = _ts(60)
    sp1.updated_at = _ts(60)
    sp2 = SourceProduct(id=2, source_id=1, product_id=2, external_id="FS-002")
    sp2.created_at = _ts(60)
    sp2.updated_at = _ts(60)
    sp3 = SourceProduct(id=3, source_id=2, product_id=1, external_id="BB-100")
    sp3.created_at = _ts(60)
    sp3.updated_at = _ts(60)
    db.add_all([sp1, sp2, sp3])

    obs = [
        ProductObservation(
            id=1,
            source_product_id=1,
            name="Widget A",
            price=Decimal("10.00"),
            currency="USD",
            availability="in_stock",
            collected_at=_ts(20),
            ingested_at=_ts(20),
            event_id="evt-001",
        ),
        ProductObservation(
            id=2,
            source_product_id=1,
            name="Widget A",
            price=Decimal("12.00"),
            currency="USD",
            availability="in_stock",
            collected_at=_ts(10),
            ingested_at=_ts(10),
            event_id="evt-002",
        ),
        ProductObservation(
            id=3,
            source_product_id=1,
            name="Widget A",
            price=Decimal("15.00"),
            currency="USD",
            availability="in_stock",
            collected_at=_ts(5),
            ingested_at=_ts(5),
            event_id="evt-003",
        ),
        ProductObservation(
            id=4,
            source_product_id=2,
            name="Gadget B",
            price=Decimal("50.00"),
            currency="USD",
            availability="in_stock",
            collected_at=_ts(15),
            ingested_at=_ts(15),
            event_id="evt-004",
        ),
        ProductObservation(
            id=5,
            source_product_id=2,
            name="Gadget B",
            price=Decimal("45.00"),
            currency="USD",
            availability="in_stock",
            collected_at=_ts(5),
            ingested_at=_ts(5),
            event_id="evt-005",
        ),
        ProductObservation(
            id=6,
            source_product_id=3,
            name="Widget A (BB)",
            price=Decimal("11.00"),
            currency="USD",
            availability="in_stock",
            collected_at=_ts(8),
            ingested_at=_ts(8),
            event_id="evt-006",
        ),
    ]
    db.add_all(obs)
    db.commit()


@pytest.fixture()
def seeded_client(client: TestClient, db_session: Session) -> TestClient:
    _seed_data(db_session)
    return client


class TestPriceChanges:
    def test_empty(self, client: TestClient) -> None:
        response = client.get("/api/v1/analytics/price-changes")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_returns_all_changes(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/analytics/price-changes")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 6
        assert len(body["items"]) == 6

    def test_pagination(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/analytics/price-changes?page=1&page_size=2")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 6
        assert len(body["items"]) == 2
        assert body["page"] == 1
        assert body["page_size"] == 2

    def test_filter_by_source_product(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/analytics/price-changes?source_product_id=1")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert all(item["source_product_id"] == 1 for item in body["items"])

    def test_price_change_computed(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/analytics/price-changes?source_product_id=1")
        body = response.json()
        items_by_id = {item["observation_id"]: item for item in body["items"]}
        second_obs = items_by_id[2]
        assert second_obs["prev_price"] == pytest.approx(10.00)
        assert second_obs["price_change_absolute"] == pytest.approx(2.00)
        assert second_obs["price_change_percent"] == pytest.approx(20.0)

    def test_first_observation_has_no_change(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/analytics/price-changes?source_product_id=1")
        body = response.json()
        items_by_id = {item["observation_id"]: item for item in body["items"]}
        first_obs = items_by_id[1]
        assert first_obs["prev_price"] is None
        assert first_obs["price_change_absolute"] is None
        assert first_obs["price_change_percent"] is None

    def test_invalid_page(self, client: TestClient) -> None:
        response = client.get("/api/v1/analytics/price-changes?page=0")
        assert response.status_code == 422

    def test_invalid_page_size(self, client: TestClient) -> None:
        response = client.get("/api/v1/analytics/price-changes?page_size=200")
        assert response.status_code == 422


class TestPriceMovers:
    def test_empty(self, client: TestClient) -> None:
        response = client.get("/api/v1/analytics/price-movers")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []

    def test_returns_movers(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/analytics/price-movers?days_back=30")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) >= 1
        for item in body["items"]:
            assert "source_product_id" in item
            assert "first_price" in item
            assert "last_price" in item
            assert "price_change_percent" in item
            assert "observation_count" in item
            assert item["observation_count"] >= 2

    def test_limit(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/analytics/price-movers?limit=1&days_back=30")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) <= 1

    def test_source_filter(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/analytics/price-movers?source_id=1&days_back=30")
        assert response.status_code == 200
        body = response.json()
        for item in body["items"]:
            assert item["source_name"] == "fake_store"

    def test_invalid_days_back(self, client: TestClient) -> None:
        response = client.get("/api/v1/analytics/price-movers?days_back=0")
        assert response.status_code == 422

    def test_invalid_limit(self, client: TestClient) -> None:
        response = client.get("/api/v1/analytics/price-movers?limit=0")
        assert response.status_code == 422


class TestPriceStatistics:
    def test_empty(self, client: TestClient) -> None:
        response = client.get("/api/v1/analytics/price-statistics")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []

    def test_returns_source_stats(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/analytics/price-statistics?days_back=30")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 2
        source_names = {item["source_name"] for item in body["items"]}
        assert "fake_store" in source_names
        assert "best_buy" in source_names

    def test_statistics_values(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/analytics/price-statistics?days_back=30")
        body = response.json()
        by_name = {item["source_name"]: item for item in body["items"]}
        fs = by_name["fake_store"]
        assert fs["observation_count"] == 5
        assert fs["min_price"] == pytest.approx(10.00)
        assert fs["max_price"] == pytest.approx(50.00)
        assert fs["avg_price"] is not None

    def test_invalid_days_back(self, client: TestClient) -> None:
        response = client.get("/api/v1/analytics/price-statistics?days_back=0")
        assert response.status_code == 422
