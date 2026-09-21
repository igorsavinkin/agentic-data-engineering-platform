"""Pipeline status repository — read-only pipeline run and source health queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from services.api.models import IngestionHealthResult, PipelineRun

_DEGRADED_STATES = frozenset(
    {
        "unreachable",
        "rate_limited",
        "structurally_changed",
        "partially_parseable",
        "empty_result",
    }
)


def _derive_overall_status(
    state: str,
    freshness_state: str,
) -> str:
    if freshness_state == "stale":
        return "stale"
    if state == "healthy" and freshness_state == "fresh":
        return "healthy"
    if state in _DEGRADED_STATES:
        return "degraded"
    if state == "stale":
        return "stale"
    return "unknown"


def _derive_pipeline_status(status: str) -> str:
    if status == "failed":
        return "failed"
    if status in ("running", "success"):
        return "healthy"
    return "unknown"


@dataclass(frozen=True)
class PipelineRunEntry:
    """Single pipeline run with derived status."""

    id: int
    run_type: str
    status: str
    overall_status: str
    started_at: str
    finished_at: Optional[str]
    records_loaded: Optional[int]
    error_message: Optional[str]


@dataclass(frozen=True)
class PipelineRunResult:
    """Paginated pipeline run list."""

    items: list[PipelineRunEntry]
    total: int


@dataclass(frozen=True)
class SourceHealthEntry:
    """Latest health assessment for a single source."""

    source_name: str
    overall_status: str
    degradation_state: str
    freshness_state: str
    freshness_age_seconds: Optional[float]
    assessed_at: str
    reasons: Optional[dict[str, Any]]
    signals: Optional[dict[str, Any]] = None


@dataclass(frozen=True)
class SourceHealthResult:
    """List of source health entries."""

    items: list[SourceHealthEntry]


class PipelineStatusRepository:
    """Read-only queries for pipeline runs and source health."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_pipeline_runs(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
    ) -> PipelineRunResult:
        q = select(PipelineRun)
        if status is not None:
            q = q.where(PipelineRun.status == status)

        total = self._session.execute(select(func.count()).select_from(q.subquery())).scalar() or 0

        offset = (page - 1) * page_size
        rows = (
            self._session.execute(
                q.order_by(desc(PipelineRun.started_at)).offset(offset).limit(page_size)
            )
            .scalars()
            .all()
        )

        items = [
            PipelineRunEntry(
                id=row.id,
                run_type=row.run_type,
                status=row.status,
                overall_status=_derive_pipeline_status(row.status),
                started_at=row.started_at.isoformat(),
                finished_at=row.finished_at.isoformat() if row.finished_at else None,
                records_loaded=row.records_loaded,
                error_message=row.error_message,
            )
            for row in rows
        ]
        return PipelineRunResult(items=items, total=total)

    def get_pipeline_run(self, run_id: int) -> Optional[PipelineRunEntry]:
        row = self._session.execute(
            select(PipelineRun).where(PipelineRun.id == run_id)
        ).scalar_one_or_none()
        if row is None:
            return None
        return PipelineRunEntry(
            id=row.id,
            run_type=row.run_type,
            status=row.status,
            overall_status=_derive_pipeline_status(row.status),
            started_at=row.started_at.isoformat(),
            finished_at=row.finished_at.isoformat() if row.finished_at else None,
            records_loaded=row.records_loaded,
            error_message=row.error_message,
        )

    def list_source_health(
        self,
        source_name: Optional[str] = None,
        limit: int = 20,
    ) -> SourceHealthResult:
        q = select(IngestionHealthResult)
        if source_name is not None:
            q = q.where(IngestionHealthResult.source_name == source_name)

        rows = (
            self._session.execute(
                q.order_by(
                    IngestionHealthResult.source_name,
                    desc(IngestionHealthResult.assessed_at),
                ).limit(limit * 10)
            )
            .scalars()
            .all()
        )

        seen: set[str] = set()
        items: list[SourceHealthEntry] = []
        for row in rows:
            if row.source_name in seen:
                continue
            seen.add(row.source_name)
            items.append(
                SourceHealthEntry(
                    source_name=row.source_name,
                    overall_status=_derive_overall_status(row.state, row.freshness_state),
                    degradation_state=row.state,
                    freshness_state=row.freshness_state,
                    freshness_age_seconds=row.freshness_age_seconds,
                    assessed_at=row.assessed_at.isoformat(),
                    reasons=row.reasons,
                    signals=row.signals,
                )
            )
            if len(items) >= limit:
                break

        return SourceHealthResult(items=items)
