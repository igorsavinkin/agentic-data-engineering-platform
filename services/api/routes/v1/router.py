"""V1 API router — aggregates all versioned route modules."""

from __future__ import annotations

from fastapi import APIRouter

from services.api.routes.v1.analytics import router as analytics_router
from services.api.routes.v1.health import router as health_router
from services.api.routes.v1.metrics import router as metrics_router
from services.api.routes.v1.pipelines import router as pipelines_router
from services.api.routes.v1.products import router as products_router
from services.api.routes.v1.quality import router as quality_router

router = APIRouter()
router.include_router(health_router)
router.include_router(products_router)
router.include_router(analytics_router)
router.include_router(pipelines_router)
router.include_router(quality_router)
router.include_router(metrics_router)
