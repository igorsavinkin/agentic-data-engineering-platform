"""Health and readiness endpoints.

``GET /health`` is a liveness probe — always returns 200 without checking
dependencies.

``GET /ready`` is a readiness probe — verifies database connectivity and
returns 503 when the database is unreachable.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.api.dependencies import get_db
from services.api.errors import APIError
from services.api.schemas import HealthStatus, ReadinessStatus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

_API_VERSION = "0.1.0"


@router.get("/health", response_model=HealthStatus)
def health() -> HealthStatus:
    """Liveness probe — always returns 200."""
    return HealthStatus(status="healthy", service="api", version=_API_VERSION)


@router.get("/ready", response_model=ReadinessStatus)
def readiness(db: Session = Depends(get_db)) -> ReadinessStatus:
    """Readiness probe — checks database connectivity."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.warning("Readiness check failed: database unreachable")
        raise APIError(
            status_code=503,
            error_code="SERVICE_UNAVAILABLE",
            message="Service not ready",
            detail={
                "status": "not_ready",
                "service": "api",
                "version": _API_VERSION,
                "database": "disconnected",
            },
        )

    return ReadinessStatus(
        status="ready",
        service="api",
        version=_API_VERSION,
        database="connected",
    )
