"""Shared fixtures for API service tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from services.api.app import create_app
from services.api.config import DatabaseSettings
from services.api.dependencies import get_db


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """In-memory SQLite session for hermetic tests."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session: Session) -> TestClient:
    """TestClient with the DB dependency overridden to in-memory SQLite."""
    app = create_app(db_settings=DatabaseSettings(url="sqlite://"))

    def _override() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    return TestClient(app)
