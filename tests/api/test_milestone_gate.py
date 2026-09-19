"""FastAPI milestone gate — end-to-end integration test for the full API surface.

Seeds every table with deterministic data and verifies:
- All endpoints return correct data
- Pagination bounds are enforced
- Validation errors are consistent
- DB failures are handled gracefully
- OpenAPI schema is complete
- 404 responses follow the error contract
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from services.api.app import create_app
from services.api.config import DatabaseSettings
from services.api.dependencies import get_db
from services.api.models import (
    Base,
    DataQualityResult,
    IngestionHealthResult,
    PipelineRun,
    Product,
    ProductObservation,
    Source,
    SourceProduct,
)

NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
PAST = NOW - timedelta(days=10)
OLDER = NOW - timedelta(days=30)


@pytest.fixture()
def seeded_session() -> Generator[Session, None, None]:
    """In-memory SQLite session with deterministic seed data across all tables."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()

    src_a = Source(id=1, name="source_a", description="Source A", created_at=NOW, updated_at=NOW)
    src_b = Source(id=2, name="source_b", description="Source B", created_at=NOW, updated_at=NOW)
    session.add_all([src_a, src_b])

    prod_1 = Product(
        id=100, canonical_name="Widget", category="gadgets", created_at=NOW, updated_at=NOW
    )
    prod_2 = Product(
        id=200, canonical_name="Gizmo", category="gadgets", created_at=NOW, updated_at=NOW
    )
    prod_3 = Product(
        id=300, canonical_name="Thingamajig", category="tools", created_at=NOW, updated_at=NOW
    )
    session.add_all([prod_1, prod_2, prod_3])

    sp_1 = SourceProduct(
        id=10,
        source_id=1,
        product_id=100,
        external_id="EXT-A-1",
        url="https://a.com/1",
        created_at=NOW,
        updated_at=NOW,
    )
    sp_2 = SourceProduct(
        id=20,
        source_id=2,
        product_id=100,
        external_id="EXT-B-1",
        url="https://b.com/1",
        created_at=NOW,
        updated_at=NOW,
    )
    sp_3 = SourceProduct(
        id=30,
        source_id=1,
        product_id=200,
        external_id="EXT-A-2",
        url="https://a.com/2",
        created_at=NOW,
        updated_at=NOW,
    )
    session.add_all([sp_1, sp_2, sp_3])

    observations = [
        ProductObservation(
            id=1,
            source_product_id=10,
            name="Widget v1",
            price=Decimal("10.00"),
            currency="USD",
            availability="in_stock",
            collected_at=OLDER,
            ingested_at=OLDER,
            event_id="evt-001",
        ),
        ProductObservation(
            id=2,
            source_product_id=10,
            name="Widget v1",
            price=Decimal("12.00"),
            currency="USD",
            availability="in_stock",
            collected_at=PAST,
            ingested_at=PAST,
            event_id="evt-002",
        ),
        ProductObservation(
            id=3,
            source_product_id=10,
            name="Widget v1",
            price=Decimal("15.00"),
            currency="USD",
            availability="in_stock",
            collected_at=NOW,
            ingested_at=NOW,
            event_id="evt-003",
        ),
        ProductObservation(
            id=4,
            source_product_id=20,
            name="Widget",
            price=Decimal("11.00"),
            currency="EUR",
            availability="in_stock",
            collected_at=NOW,
            ingested_at=NOW,
            event_id="evt-004",
        ),
        ProductObservation(
            id=5,
            source_product_id=30,
            name="Gizmo",
            price=Decimal("25.00"),
            currency="USD",
            availability="out_of_stock",
            collected_at=NOW,
            ingested_at=NOW,
            event_id="evt-005",
        ),
    ]
    session.add_all(observations)

    pipeline_runs = [
        PipelineRun(
            id=1,
            run_type="full",
            status="success",
            started_at=PAST,
            finished_at=PAST + timedelta(hours=1),
            records_loaded=100,
            error_message=None,
        ),
        PipelineRun(
            id=2,
            run_type="incremental",
            status="failed",
            started_at=NOW - timedelta(hours=2),
            finished_at=NOW - timedelta(hours=1),
            records_loaded=0,
            error_message="Connection timeout",
        ),
        PipelineRun(
            id=3,
            run_type="incremental",
            status="running",
            started_at=NOW,
            finished_at=None,
            records_loaded=None,
            error_message=None,
        ),
    ]
    session.add_all(pipeline_runs)

    health_results = [
        IngestionHealthResult(
            id=1,
            source_name="source_a",
            state="healthy",
            freshness_state="fresh",
            reasons=None,
            signals=None,
            freshness_age_seconds=300.0,
            assessed_at=NOW,
            evaluated_at=NOW,
            logical_date="2025-06-15",
            replay_key="rk-001",
        ),
        IngestionHealthResult(
            id=2,
            source_name="source_b",
            state="unreachable",
            freshness_state="stale",
            reasons={"error": "connection refused"},
            signals=None,
            freshness_age_seconds=86400.0,
            assessed_at=NOW,
            evaluated_at=NOW,
            logical_date="2025-06-15",
            replay_key="rk-002",
        ),
    ]
    session.add_all(health_results)

    quality_results = [
        DataQualityResult(
            id=1,
            pipeline_run_id=1,
            observation_id=None,
            check_name="null_price",
            severity="warning",
            passed=True,
            message="All prices non-null",
            checked_at=NOW,
            records_checked=100,
            failed_records=0,
            details=None,
            replay_key="qk-001",
        ),
        DataQualityResult(
            id=2,
            pipeline_run_id=1,
            observation_id=None,
            check_name="duplicate_detection",
            severity="error",
            passed=False,
            message="Found 3 duplicates",
            checked_at=NOW,
            records_checked=100,
            failed_records=3,
            details={"duplicates": 3},
            replay_key="qk-002",
        ),
        DataQualityResult(
            id=3,
            pipeline_run_id=2,
            observation_id=None,
            check_name="null_price",
            severity="warning",
            passed=False,
            message="5 null prices found",
            checked_at=NOW,
            records_checked=50,
            failed_records=5,
            details=None,
            replay_key="qk-003",
        ),
    ]
    session.add_all(quality_results)

    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(seeded_session: Session) -> TestClient:
    """TestClient with the seeded DB session."""
    app = create_app(db_settings=DatabaseSettings(url="sqlite://"))

    def _override() -> Generator[Session, None, None]:
        try:
            yield seeded_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


@pytest.fixture()
def failing_client() -> TestClient:
    """TestClient where the DB session raises on every query."""
    app = create_app(db_settings=DatabaseSettings(url="sqlite://"))

    def _override() -> Generator[MagicMock, None, None]:
        mock_session = MagicMock()
        mock_session.execute.side_effect = RuntimeError("DB unreachable")
        yield mock_session

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


# ---------------------------------------------------------------------------
# OpenAPI / docs
# ---------------------------------------------------------------------------


class TestOpenAPIMilestone:
    def test_openapi_schema_lists_all_v1_paths(self, client: TestClient) -> None:
        resp = client.get("/api/openapi.json")
        assert resp.status_code == 200
        paths = resp.json()["paths"]
        expected = {
            "/api/v1/health",
            "/api/v1/ready",
            "/api/v1/products",
            "/api/v1/products/{product_id}",
            "/api/v1/products/{product_id}/history",
            "/api/v1/analytics/price-changes",
            "/api/v1/analytics/price-movers",
            "/api/v1/analytics/price-statistics",
            "/api/v1/pipelines",
            "/api/v1/pipelines/{run_id}",
            "/api/v1/pipelines/source-health",
            "/api/v1/quality",
            "/api/v1/quality/summary",
        }
        for path in expected:
            assert path in paths, f"Missing path: {path}"

    def test_docs_ui_available(self, client: TestClient) -> None:
        resp = client.get("/api/docs")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Health / readiness
# ---------------------------------------------------------------------------


class TestHealthMilestone:
    def test_health_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["service"] == "api"

    def test_readiness_returns_connected(self, client: TestClient) -> None:
        resp = client.get("/api/v1/ready")
        assert resp.status_code == 200
        assert resp.json()["database"] == "connected"

    def test_readiness_returns_503_on_db_failure(self, failing_client: TestClient) -> None:
        resp = failing_client.get("/api/v1/ready")
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"]["code"] == "SERVICE_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


class TestProductsMilestone:
    def test_list_products_returns_all(self, client: TestClient) -> None:
        resp = client.get("/api/v1/products")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert len(body["items"]) == 3

    def test_list_products_pagination(self, client: TestClient) -> None:
        resp = client.get("/api/v1/products?page=1&page_size=2")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2
        assert body["total"] == 3
        assert body["page"] == 1
        assert body["page_size"] == 2

    def test_list_products_beyond_range(self, client: TestClient) -> None:
        resp = client.get("/api/v1/products?page=999")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 3

    def test_product_detail(self, client: TestClient) -> None:
        resp = client.get("/api/v1/products/100")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 100
        assert body["canonical_name"] == "Widget"
        assert body["source_count"] == 2

    def test_product_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/v1/products/99999")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == "PRODUCT_NOT_FOUND"

    def test_product_history(self, client: TestClient) -> None:
        resp = client.get("/api/v1/products/100/history")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 4
        assert len(body["items"]) == 4

    def test_product_history_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/v1/products/99999/history")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


class TestAnalyticsMilestone:
    def test_price_changes(self, client: TestClient) -> None:
        resp = client.get("/api/v1/analytics/price-changes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1

    def test_price_changes_pagination(self, client: TestClient) -> None:
        resp = client.get("/api/v1/analytics/price-changes?page=1&page_size=1")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 1
        assert body["page"] == 1
        assert body["page_size"] == 1

    def test_price_movers(self, client: TestClient) -> None:
        resp = client.get("/api/v1/analytics/price-movers")
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body

    def test_price_statistics(self, client: TestClient) -> None:
        resp = client.get("/api/v1/analytics/price-statistics")
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert len(body["items"]) >= 1


# ---------------------------------------------------------------------------
# Pipelines
# ---------------------------------------------------------------------------


class TestPipelinesMilestone:
    def test_list_pipeline_runs(self, client: TestClient) -> None:
        resp = client.get("/api/v1/pipelines")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3

    def test_list_pipeline_runs_filter_status(self, client: TestClient) -> None:
        resp = client.get("/api/v1/pipelines?status=failed")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["status"] == "failed"

    def test_get_pipeline_run(self, client: TestClient) -> None:
        resp = client.get("/api/v1/pipelines/1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 1
        assert body["run_type"] == "full"

    def test_get_pipeline_run_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/v1/pipelines/99999")
        assert resp.status_code == 404

    def test_source_health(self, client: TestClient) -> None:
        resp = client.get("/api/v1/pipelines/source-health")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2

    def test_source_health_filter(self, client: TestClient) -> None:
        resp = client.get("/api/v1/pipelines/source-health?source_name=source_a")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["source_name"] == "source_a"


# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------


class TestQualityMilestone:
    def test_list_quality_checks(self, client: TestClient) -> None:
        resp = client.get("/api/v1/quality")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3

    def test_quality_filter_by_check_name(self, client: TestClient) -> None:
        resp = client.get("/api/v1/quality?check_name=null_price")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2

    def test_quality_filter_by_passed(self, client: TestClient) -> None:
        resp = client.get("/api/v1/quality?passed=false")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2

    def test_quality_summary(self, client: TestClient) -> None:
        resp = client.get("/api/v1/quality/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2
        names = {item["check_name"] for item in body["items"]}
        assert "null_price" in names
        assert "duplicate_detection" in names


# ---------------------------------------------------------------------------
# Validation / pagination bounds
# ---------------------------------------------------------------------------


class TestValidationBounds:
    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/products",
            "/api/v1/products/100/history",
            "/api/v1/analytics/price-changes",
            "/api/v1/pipelines",
            "/api/v1/quality",
        ],
    )
    def test_page_zero_rejected(self, client: TestClient, path: str) -> None:
        resp = client.get(f"{path}?page=0")
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/products",
            "/api/v1/products/100/history",
            "/api/v1/analytics/price-changes",
            "/api/v1/pipelines",
            "/api/v1/quality",
        ],
    )
    def test_page_size_zero_rejected(self, client: TestClient, path: str) -> None:
        resp = client.get(f"{path}?page_size=0")
        assert resp.status_code == 422

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/products",
            "/api/v1/products/100/history",
            "/api/v1/analytics/price-changes",
            "/api/v1/pipelines",
            "/api/v1/quality",
        ],
    )
    def test_page_size_over_limit_rejected(self, client: TestClient, path: str) -> None:
        resp = client.get(f"{path}?page_size=101")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Error contract
# ---------------------------------------------------------------------------


class TestErrorContract:
    def test_404_has_structured_error(self, client: TestClient) -> None:
        resp = client.get("/api/v1/products/99999")
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]

    def test_422_has_validation_error_code(self, client: TestClient) -> None:
        resp = client.get("/api/v1/products?page=-1")
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert "errors" in body["error"].get("detail", {})

    def test_db_failure_does_not_leak_internals(self, failing_client: TestClient) -> None:
        resp = failing_client.get("/api/v1/ready")
        assert resp.status_code == 503
        body = resp.json()
        assert "DB unreachable" not in body["error"]["message"]
        assert "Traceback" not in str(body)
