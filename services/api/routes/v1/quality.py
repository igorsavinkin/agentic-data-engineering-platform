"""Data quality endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from services.api.dependencies import get_db
from services.api.repositories.quality import DataQualityRepository
from services.api.schemas import (
    QualityCheckListResponse,
    QualityCheckResponse,
    QualitySummaryListResponse,
    QualitySummaryResponse,
)

router = APIRouter(prefix="/quality", tags=["quality"])


@router.get("", response_model=QualityCheckListResponse)
def list_quality_checks(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page (max 100)"),
    check_name: Optional[str] = Query(default=None, description="Filter by check name"),
    severity: Optional[str] = Query(
        default=None, description="Filter by severity (info, warning, error)"
    ),
    passed: Optional[bool] = Query(default=None, description="Filter by pass/fail status"),
    pipeline_run_id: Optional[int] = Query(default=None, description="Filter by pipeline run ID"),
    from_date: Optional[datetime] = Query(
        default=None, description="Filter checks performed on or after this ISO timestamp"
    ),
    db: Session = Depends(get_db),
) -> QualityCheckListResponse:
    """Return paginated data quality check results."""
    repo = DataQualityRepository(db)
    result = repo.list_quality_checks(
        page=page,
        page_size=page_size,
        check_name=check_name,
        severity=severity,
        passed=passed,
        pipeline_run_id=pipeline_run_id,
        from_date=from_date,
    )
    return QualityCheckListResponse(
        items=[
            QualityCheckResponse(
                id=item.id,
                check_name=item.check_name,
                severity=item.severity,
                passed=item.passed,
                message=item.message,
                checked_at=item.checked_at,
                records_checked=item.records_checked,
                failed_records=item.failed_records,
                pipeline_run_id=item.pipeline_run_id,
                observation_id=item.observation_id,
                details=item.details,
            )
            for item in result.items
        ],
        total=result.total,
        page=page,
        page_size=page_size,
    )


@router.get("/summary", response_model=QualitySummaryListResponse)
def list_quality_summary(
    db: Session = Depends(get_db),
) -> QualitySummaryListResponse:
    """Return aggregate quality summary per check name."""
    repo = DataQualityRepository(db)
    result = repo.list_quality_summary()
    return QualitySummaryListResponse(
        items=[
            QualitySummaryResponse(
                check_name=item.check_name,
                total_runs=item.total_runs,
                passed_runs=item.passed_runs,
                failed_runs=item.failed_runs,
                last_checked_at=item.last_checked_at,
                severity=item.severity,
            )
            for item in result.items
        ]
    )
