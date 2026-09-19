"""Application factory for the API service."""

from __future__ import annotations

import logging
from collections.abc import Generator

from fastapi import FastAPI
from sqlalchemy.orm import Session

from services.api.config import DatabaseSettings
from services.api.database import create_db_engine, create_session_factory
from services.api.dependencies import get_db
from services.api.errors import register_exception_handlers
from services.api.routes.v1.metrics import metrics_middleware
from services.api.routes.v1.router import router as v1_router

logger = logging.getLogger(__name__)


def create_app(
    db_settings: DatabaseSettings | None = None,
) -> FastAPI:
    """Build and configure the FastAPI application.

    *db_settings* defaults to :meth:`DatabaseSettings.from_env`.
    """
    if db_settings is None:
        db_settings = DatabaseSettings.from_env()

    engine = create_db_engine(db_settings.url)
    session_factory = create_session_factory(engine)

    def _db_session() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = FastAPI(
        title="AI Data Platform API",
        description="Synchronous HTTP access to serving and analytics data.",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    from libs.observability.otel_config import OTelSettings, setup_opentelemetry

    setup_opentelemetry(OTelSettings(service_name="api"))

    @app.middleware("http")
    async def _prometheus_middleware(request, call_next):  # type: ignore[no-untyped-def]
        return await metrics_middleware(request, call_next)

    app.dependency_overrides[get_db] = _db_session

    register_exception_handlers(app)
    app.include_router(v1_router, prefix="/api/v1")

    return app
