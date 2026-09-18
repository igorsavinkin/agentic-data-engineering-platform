"""FastAPI dependencies for the API service."""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def get_db_session(
    db: "Session | None" = None,
) -> Generator["Session", None, None]:
    """Yield a database session and ensure cleanup.

    The default implementation is overridden at application startup
    via ``app.dependency_overrides`` to use the real engine-backed
    session factory.  Tests can inject in-memory sessions the same way.
    """
    if db is None:
        raise RuntimeError("Database session factory not configured")
    try:
        yield db
    finally:
        db.close()


# Placeholder — replaced by the application factory with a real session
# factory bound to the configured engine.
_db_session_factory = get_db_session


def get_db() -> Generator["Session", None, None]:
    """FastAPI dependency that yields a database session."""
    yield from _db_session_factory()
