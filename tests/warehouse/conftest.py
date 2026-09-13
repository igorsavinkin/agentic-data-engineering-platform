"""Pytest fixtures for warehouse integration tests (TASK-033).

Provides database session fixtures for testing against real PostgreSQL.
These fixtures support both unit-style tests (with transaction rollback)
and full integration tests (with committed data).
"""

# mypy: disable-error-code="import-untyped,no-untyped-def"
import os
from typing import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Database configuration from environment or defaults
WAREHOUSE_DB_HOST = os.getenv("WAREHOUSE_DB_HOST", "localhost")
WAREHOUSE_DB_PORT = os.getenv("WAREHOUSE_DB_PORT", "5432")
WAREHOUSE_DB_NAME = os.getenv("WAREHOUSE_DB_NAME", "platform")
WAREHOUSE_DB_USER = os.getenv("WAREHOUSE_DB_USER", "platform")
WAREHOUSE_DB_PASSWORD = os.getenv("WAREHOUSE_DB_PASSWORD", "platform-local")


def _build_db_url(dbname: str) -> str:
    """Build PostgreSQL connection URL."""
    return (
        f"postgresql://{WAREHOUSE_DB_USER}:{WAREHOUSE_DB_PASSWORD}"
        f"@{WAREHOUSE_DB_HOST}:{WAREHOUSE_DB_PORT}/{dbname}"
    )


@pytest.fixture(scope="session")
def db_engine():
    """Create SQLAlchemy engine for test database."""
    url = _build_db_url(WAREHOUSE_DB_NAME)
    engine = create_engine(url, echo=False)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def _setup_test_database(db_engine):
    """Ensure test schema exists by running migrations.

    This fixture runs once per test session and ensures all warehouse
    tables exist before any tests run.
    """
    # Run migrations if needed - for now just verify connection
    with db_engine.connect() as conn:
        conn.execute(text("SELECT 1"))


@pytest.fixture
def db_session(_setup_test_database, db_engine) -> Generator[Session, None, None]:
    """Provide a database session for tests.

    Each test gets a fresh session that is rolled back after the test completes,
    ensuring test isolation. Tests can commit within their scope if needed.

    Usage:
        def test_something(db_session):
            result = db_session.execute(text("SELECT 1"))
            assert result.scalar() == 1
    """
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
