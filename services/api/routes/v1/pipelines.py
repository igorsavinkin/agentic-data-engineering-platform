"""Pipeline status endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from services.api.dependencies import get_db
from services.api.repositories.pipeline_status import PipelineStatusRepository
from services.api.schemas import (
    PipelineRunListResponse,
    PipelineRunResponse,
    SourceHealthListResponse,
    SourceHealthResponse,
)

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


@router.get("", response_model=PipelineRunListResponse)
def list_pipeline_runs(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page (max 100)"),
    status: Optional[str] = Query(
        default=None, description="Filter by raw pipeline status (running, success, failed)"
    ),
    db: Session = Depends(get_db),
) -> PipelineRunListResponse:
    """Return paginated pipeline runs with derived overall status."""
    repo = PipelineStatusRepository(db)
    result = repo.list_pipeline_runs(page=page, page_size=page_size, status=status)
    return PipelineRunListResponse(
        items=[
            PipelineRunResponse(
                id=item.id,
                run_type=item.run_type,
                status=item.status,
                overall_status=item.overall_status,
                started_at=item.started_at,
                finished_at=item.finished_at,
                records_loaded=item.records_loaded,
                error_message=item.error_message,
            )
            for item in result.items
        ],
        total=result.total,
        page=page,
        page_size=page_size,
    )


@router.get("/source-health", response_model=SourceHealthListResponse)
def list_source_health(
    source_name: Optional[str] = Query(default=None, description="Filter by source name"),
    limit: int = Query(default=20, ge=1, le=100, description="Max results (default 20)"),
    db: Session = Depends(get_db),
) -> SourceHealthListResponse:
    """Return latest health assessment per source."""
    repo = PipelineStatusRepository(db)
    result = repo.list_source_health(source_name=source_name, limit=limit)
    return SourceHealthListResponse(
        items=[
            SourceHealthResponse(
                source_name=item.source_name,
                overall_status=item.overall_status,
                degradation_state=item.degradation_state,
                freshness_state=item.freshness_state,
                freshness_age_seconds=item.freshness_age_seconds,
                assessed_at=item.assessed_at,
                reasons=item.reasons,
            )
            for item in result.items
        ]
    )


@router.get("/{run_id}", response_model=PipelineRunResponse)
def get_pipeline_run(
    run_id: int,
    db: Session = Depends(get_db),
) -> PipelineRunResponse:
    """Return a single pipeline run by ID."""
    repo = PipelineStatusRepository(db)
    entry = repo.get_pipeline_run(run_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return PipelineRunResponse(
        id=entry.id,
        run_type=entry.run_type,
        status=entry.status,
        overall_status=entry.overall_status,
        started_at=entry.started_at,
        finished_at=entry.finished_at,
        records_loaded=entry.records_loaded,
        error_message=entry.error_message,
    )
