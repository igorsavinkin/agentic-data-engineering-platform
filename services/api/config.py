"""Typed configuration for the API service."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DatabaseSettings:
    """PostgreSQL connection settings for the serving warehouse.

    Reads ``WAREHOUSE_DB_*`` environment variables, matching the convention
    used by the warehouse loader, quality persistence, and metrics modules.

    The ``url`` attribute holds the full connection URL.  It is computed
    from individual fields in :meth:`from_env` or may be passed directly
    (useful for tests that point at SQLite).
    """

    url: str = "postgresql://postgres@localhost:5432/warehouse"

    @classmethod
    def from_env(cls) -> DatabaseSettings:
        host = os.getenv("WAREHOUSE_DB_HOST", "localhost")
        port = os.getenv("WAREHOUSE_DB_PORT", "5432")
        name = os.getenv("WAREHOUSE_DB_NAME", "warehouse")
        user = os.getenv("WAREHOUSE_DB_USER", "postgres")
        password = os.getenv("WAREHOUSE_DB_PASSWORD", "")

        if password:
            url = f"postgresql://{user}:{password}@{host}:{port}/{name}"
        else:
            url = f"postgresql://{user}@{host}:{port}/{name}"
        return cls(url=url)


@dataclass(frozen=True)
class APISettings:
    """Server binding and runtime settings for the API service."""

    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    @classmethod
    def from_env(cls) -> APISettings:
        return cls(
            host=os.getenv("APP_API_HOST", "0.0.0.0"),
            port=int(os.getenv("APP_API_PORT", "8000")),
            debug=os.getenv("APP_DEBUG", "").lower() in {"1", "true", "yes"},
        )
