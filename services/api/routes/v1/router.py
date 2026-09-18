"""V1 API router — aggregates all versioned route modules."""

from __future__ import annotations

from fastapi import APIRouter

from services.api.routes.v1.health import router as health_router

router = APIRouter()
router.include_router(health_router)
