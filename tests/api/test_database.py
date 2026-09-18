"""Tests for database engine and session factory."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.api.database import create_db_engine, create_session_factory


def test_create_engine_sqlite() -> None:
    engine = create_db_engine("sqlite://")
    assert engine is not None
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1


def test_create_session_factory() -> None:
    engine = create_db_engine("sqlite://")
    factory = create_session_factory(engine)
    session = factory()
    assert isinstance(session, Session)
    session.close()
