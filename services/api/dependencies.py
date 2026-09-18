"""FastAPI dependencies for the API service."""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def get_db() -> Generator["Session", None, None]:
    """FastAPI dependency that yields a database session.

    Overridden at application startup by the app factory to use the
    real engine-backed session factory.  Tests inject in-memory sessions
    the same way via ``app.dependency_overrides``.
    """
    raise RuntimeError("Database session factory not configured")
