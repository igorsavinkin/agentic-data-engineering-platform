"""Database engine and session factory for the API service.

Uses SQLAlchemy 2.0 synchronous patterns with connection pooling.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def create_db_engine(db_url: str, **kwargs: object) -> Engine:
    """Create a SQLAlchemy engine for the serving database.

    Connection pooling is configured with sensible defaults for a web
    service.  Pool parameters are only applied for non-SQLite URLs, since
    SQLite uses ``SingletonThreadPool`` which rejects them.
    Extra *kwargs* override the defaults (useful for tests).
    """
    if db_url.startswith("sqlite"):
        return create_engine(db_url, **kwargs)

    defaults: dict[str, object] = {
        "pool_size": 5,
        "max_overflow": 10,
        "pool_recycle": 1800,
    }
    defaults.update(kwargs)
    return create_engine(db_url, **defaults)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to *engine*."""
    return sessionmaker(bind=engine, expire_on_commit=False)
