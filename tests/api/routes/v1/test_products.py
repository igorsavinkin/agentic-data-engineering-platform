"""Tests for product list and detail endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from services.api.models import Product, ProductObservation, Source, SourceProduct


def _seed_data(db: Session) -> None:
    """Insert test data: 2 sources, 3 products, observations."""
    src1 = Source(id=1, name="fake_store", description="Fake Store API")
    src1.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    src1.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    src2 = Source(id=2, name="best_buy", description="Best Buy API")
    src2.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    src2.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    db.add_all([src1, src2])

    p1 = Product(id=1, canonical_name="Widget A", category="widgets")
    p1.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    p1.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    p2 = Product(id=2, canonical_name="Gadget B", category="gadgets")
    p2.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    p2.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    p3 = Product(id=3, canonical_name="Widget C", category="widgets")
    p3.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    p3.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    db.add_all([p1, p2, p3])

    sp1 = SourceProduct(id=1, source_id=1, product_id=1, external_id="FS-001")
    sp1.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    sp1.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    sp2 = SourceProduct(id=2, source_id=1, product_id=2, external_id="FS-002")
    sp2.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    sp2.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    sp3 = SourceProduct(id=3, source_id=2, product_id=1, external_id="BB-100")
    sp3.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    sp3.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    sp4 = SourceProduct(id=4, source_id=1, product_id=3, external_id="FS-003")
    sp4.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    sp4.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    db.add_all([sp1, sp2, sp3, sp4])

    obs1 = ProductObservation(
        id=1,
        source_product_id=1,
        name="Widget A",
        price=Decimal("9.99"),
        currency="USD",
        availability="in_stock",
        collected_at=datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc),
        ingested_at=datetime(2025, 6, 1, 12, 5, tzinfo=timezone.utc),
        event_id="evt-001",
    )
    obs2 = ProductObservation(
        id=2,
        source_product_id=1,
        name="Widget A",
        price=Decimal("10.99"),
        currency="USD",
        availability="in_stock",
        collected_at=datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc),
        ingested_at=datetime(2025, 6, 15, 12, 5, tzinfo=timezone.utc),
        event_id="evt-002",
    )
    obs3 = ProductObservation(
        id=3,
        source_product_id=2,
        name="Gadget B",
        price=Decimal("24.50"),
        currency="USD",
        availability="out_of_stock",
        collected_at=datetime(2025, 6, 10, 10, 0, tzinfo=timezone.utc),
        ingested_at=datetime(2025, 6, 10, 10, 5, tzinfo=timezone.utc),
        event_id="evt-003",
    )
    obs4 = ProductObservation(
        id=4,
        source_product_id=3,
        name="Widget A (BB)",
        price=Decimal("11.00"),
        currency="USD",
        availability="in_stock",
        collected_at=datetime(2025, 6, 20, 8, 0, tzinfo=timezone.utc),
        ingested_at=datetime(2025, 6, 20, 8, 5, tzinfo=timezone.utc),
        event_id="evt-004",
    )
    obs5 = ProductObservation(
        id=5,
        source_product_id=4,
        name="Widget C",
        price=Decimal("5.00"),
        currency="USD",
        availability="in_stock",
        collected_at=datetime(2025, 6, 5, 9, 0, tzinfo=timezone.utc),
        ingested_at=datetime(2025, 6, 5, 9, 5, tzinfo=timezone.utc),
        event_id="evt-005",
    )
    db.add_all([obs1, obs2, obs3, obs4, obs5])
    db.commit()


@pytest.fixture()
def seeded_client(client: TestClient, db_session: Session) -> TestClient:
    """Client with seeded product data."""
    _seed_data(db_session)
    return client


class TestProductList:
    def test_empty_list(self, client: TestClient) -> None:
        response = client.get("/api/v1/products")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["page"] == 1
        assert body["page_size"] == 20

    def test_list_returns_all_products(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/products")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert len(body["items"]) == 3
        ids = [item["id"] for item in body["items"]]
        assert ids == [1, 2, 3]

    def test_list_pagination(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/products?page=1&page_size=2")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert len(body["items"]) == 2
        assert body["page"] == 1
        assert body["page_size"] == 2

        response2 = seeded_client.get("/api/v1/products?page=2&page_size=2")
        body2 = response2.json()
        assert len(body2["items"]) == 1
        assert body2["page"] == 2

    def test_list_filter_by_category(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/products?category=widgets")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert all(item["category"] == "widgets" for item in body["items"])

    def test_list_filter_by_source(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/products?source=best_buy")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == 1

    def test_list_invalid_page(self, client: TestClient) -> None:
        response = client.get("/api/v1/products?page=0")
        assert response.status_code == 422

    def test_list_invalid_page_size(self, client: TestClient) -> None:
        response = client.get("/api/v1/products?page_size=200")
        assert response.status_code == 422

    def test_list_latest_observation(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/products?page_size=1")
        body = response.json()
        item = body["items"][0]
        assert item["id"] == 1
        assert item["latest_price"] == pytest.approx(11.00)
        assert item["latest_name"] == "Widget A (BB)"

    def test_list_validation_error_format(self, client: TestClient) -> None:
        response = client.get("/api/v1/products?page=0")
        assert response.status_code == 422
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] == "VALIDATION_ERROR"


class TestProductDetail:
    def test_get_existing_product(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/products/1")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == 1
        assert body["canonical_name"] == "Widget A"
        assert body["category"] == "widgets"
        assert body["source_count"] == 2
        assert body["latest_price"] == pytest.approx(11.00)
        assert body["latest_source"] == "best_buy"

    def test_get_product_not_found(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/products/999")
        assert response.status_code == 404
        body = response.json()
        assert body["error"]["code"] == "PRODUCT_NOT_FOUND"

    def test_get_product_404_format(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/products/999")
        body = response.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]

    def test_get_product_single_source(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/products/2")
        assert response.status_code == 200
        body = response.json()
        assert body["source_count"] == 1
        assert body["latest_price"] == pytest.approx(24.50)
        assert body["latest_availability"] == "out_of_stock"


class TestProductObservations:
    def test_list_observations_for_product(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/products/1/history")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert len(body["items"]) == 3
        assert body["page"] == 1
        assert body["page_size"] == 20
        collected_dates = [item["collected_at"] for item in body["items"]]
        assert collected_dates == sorted(collected_dates, reverse=True)

    def test_observations_source_traceability(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/products/1/history")
        body = response.json()
        sources = {item["source"] for item in body["items"]}
        assert "fake_store" in sources
        assert "best_buy" in sources

    def test_observations_pagination(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/products/1/history?page=1&page_size=2")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert len(body["items"]) == 2

        response2 = seeded_client.get("/api/v1/products/1/history?page=2&page_size=2")
        body2 = response2.json()
        assert len(body2["items"]) == 1

    def test_observations_date_filter_from(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/products/1/history?from_date=2025-06-10T00:00:00Z")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        for item in body["items"]:
            assert item["collected_at"] >= "2025-06-10"

    def test_observations_date_filter_to(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/products/1/history?to_date=2025-06-10T00:00:00Z")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == 1

    def test_observations_date_filter_range(self, seeded_client: TestClient) -> None:
        response = seeded_client.get(
            "/api/v1/products/1/history?from_date=2025-06-01T00:00:00Z&to_date=2025-06-15T23:59:59Z"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2

    def test_observations_product_not_found(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/products/999/history")
        assert response.status_code == 404
        body = response.json()
        assert body["error"]["code"] == "PRODUCT_NOT_FOUND"

    def test_observations_invalid_page(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/products/1/history?page=0")
        assert response.status_code == 422

    def test_observations_single_product(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/products/2/history")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == 3
        assert body["items"][0]["source"] == "fake_store"
        assert body["items"][0]["price"] == pytest.approx(24.50)
        assert body["items"][0]["availability"] == "out_of_stock"
