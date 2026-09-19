"""Data quality repository — read-only quality result queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Integer, desc, func, select
from sqlalchemy.orm import Session

from services.api.models import DataQualityResult


@dataclass(frozen=True)
class QualityCheckEntry:
    """Single data quality check result."""

    id: int
    check_name: str
    severity: str
    passed: bool
    message: Optional[str]
    checked_at: str
    records_checked: int
    failed_records: int
    pipeline_run_id: Optional[int]
    observation_id: Optional[int]
    details: Optional[dict[str, Any]]


@dataclass(frozen=True)
class QualityCheckResult:
    """Paginated quality check list."""

    items: list[QualityCheckEntry]
    total: int


@dataclass(frozen=True)
class QualitySummaryEntry:
    """Aggregate quality summary per check name."""

    check_name: str
    total_runs: int
    passed_runs: int
    failed_runs: int
    last_checked_at: str
    severity: str


@dataclass(frozen=True)
class QualitySummaryResult:
    """Quality summary list."""

    items: list[QualitySummaryEntry]


class DataQualityRepository:
    """Read-only queries for data quality results."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_quality_checks(
        self,
        page: int = 1,
        page_size: int = 20,
        check_name: Optional[str] = None,
        severity: Optional[str] = None,
        passed: Optional[bool] = None,
        pipeline_run_id: Optional[int] = None,
        from_date: Optional[datetime] = None,
    ) -> QualityCheckResult:
        q = select(DataQualityResult)
        if check_name is not None:
            q = q.where(DataQualityResult.check_name == check_name)
        if severity is not None:
            q = q.where(DataQualityResult.severity == severity)
        if passed is not None:
            q = q.where(DataQualityResult.passed == passed)
        if pipeline_run_id is not None:
            q = q.where(DataQualityResult.pipeline_run_id == pipeline_run_id)
        if from_date is not None:
            q = q.where(DataQualityResult.checked_at >= from_date)

        total = self._session.execute(select(func.count()).select_from(q.subquery())).scalar() or 0

        offset = (page - 1) * page_size
        rows = (
            self._session.execute(
                q.order_by(desc(DataQualityResult.checked_at)).offset(offset).limit(page_size)
            )
            .scalars()
            .all()
        )

        items = [
            QualityCheckEntry(
                id=row.id,
                check_name=row.check_name,
                severity=row.severity,
                passed=row.passed,
                message=row.message,
                checked_at=row.checked_at.isoformat(),
                records_checked=row.records_checked,
                failed_records=row.failed_records,
                pipeline_run_id=row.pipeline_run_id,
                observation_id=row.observation_id,
                details=row.details,
            )
            for row in rows
        ]
        return QualityCheckResult(items=items, total=total)

    def list_quality_summary(self) -> QualitySummaryResult:
        passed_count = func.sum(func.cast(DataQualityResult.passed, Integer))

        rows = self._session.execute(
            select(
                DataQualityResult.check_name,
                func.max(DataQualityResult.severity).label("severity"),
                func.count().label("total_runs"),
                passed_count.label("passed_runs"),
                func.max(DataQualityResult.checked_at).label("last_checked_at"),
            )
            .group_by(DataQualityResult.check_name)
            .order_by(DataQualityResult.check_name)
        ).all()

        items = [
            QualitySummaryEntry(
                check_name=row.check_name,
                total_runs=row.total_runs,
                passed_runs=row.passed_runs,
                failed_runs=row.total_runs - row.passed_runs,
                last_checked_at=row.last_checked_at.isoformat(),
                severity=row.severity,
            )
            for row in rows
        ]
        return QualitySummaryResult(items=items)
