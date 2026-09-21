"""Read-only SQL, dataset metadata, and pipeline status agent tools.

Tools enforce read-only constraints at the query level: DDL, DML,
and any non-SELECT statements are rejected before execution.
Pipeline status tool aggregates from existing health/metrics endpoints.
"""

from __future__ import annotations

import re
from typing import Any, Optional, Protocol

from pydantic import BaseModel, Field


class SQLResult(BaseModel):
    """Structured result from a read-only SQL query."""

    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int


class ToolResponse(BaseModel):
    """Generic tool response envelope."""

    success: bool
    data: Any = None
    error: str | None = None


class ColumnMetadata(BaseModel):
    """Metadata for a single database column."""

    name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool = False


class TableMetadata(BaseModel):
    """Metadata for a database table."""

    schema_name: str
    table_name: str
    columns: list[ColumnMetadata]
    row_count: int | None = None


class DatasetMetadataResult(BaseModel):
    """Result from a dataset metadata query."""

    tables: list[TableMetadata]


_BLOCKED_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE"
    r"|EXEC|EXECUTE|CALL|MERGE|REPLACE|LOAD|INTO)\b",
    re.IGNORECASE,
)

_SIDEEFFECT_FUNCTIONS = re.compile(
    r"\b(setval|nextval|currval|lo_from_bytea|lo_creat|lo_unlink"
    r"|lo_import|lo_export|dblink_exec|dblink_connect"
    r"|pg_notify|pg_terminate_backend|pg_cancel_backend"
    r"|set_config|pg_reload_conf)\b\s*\(",
    re.IGNORECASE,
)


class DatabaseConnection(Protocol):
    """Protocol for database connections used by agent tools.

    Concrete implementations MUST enforce connection-level read-only access
    (e.g. ``default_transaction_read_only=on`` or a read-only PostgreSQL role).
    The query-level validation in this module is a defense-in-depth measure;
    the connection itself must prevent any write operation.
    """

    def execute(
        self, query: str, params: tuple[Any, ...] | None = None
    ) -> list[dict[str, Any]]: ...
    def get_columns(self, schema: str, table: str) -> list[dict[str, Any]]: ...
    def get_row_count(self, schema: str, table: str) -> int: ...
    def list_tables(self, schema: str) -> list[str]: ...


def validate_read_only(query: str) -> str | None:
    """Validate that a SQL query is read-only.

    Returns None if the query is safe, or an error message if blocked.
    """
    stripped = query.strip()
    if not stripped:
        return "Empty query"

    if not stripped.upper().startswith("SELECT") and not stripped.upper().startswith("WITH"):
        return "Only SELECT and WITH (CTE) queries are allowed"

    if ";" in stripped.rstrip(";"):
        return "Multiple statements are not allowed"

    match = _BLOCKED_KEYWORDS.search(stripped)
    if match:
        return f"Blocked keyword found: {match.group(0).upper()}"

    side_effect = _SIDEEFFECT_FUNCTIONS.search(stripped)
    if side_effect:
        return f"Side-effecting function not allowed: {side_effect.group(1).upper()}"

    return None


def execute_read_only_sql(query: str, db: DatabaseConnection) -> ToolResponse:
    """Execute a read-only SQL query and return structured results."""
    error = validate_read_only(query)
    if error:
        return ToolResponse(success=False, error=error)

    try:
        rows = db.execute(query)
        columns = list(rows[0].keys()) if rows else []
        result = SQLResult(columns=columns, rows=rows, row_count=len(rows))
        return ToolResponse(success=True, data=result.model_dump())
    except Exception as e:
        return ToolResponse(success=False, error=str(e))


def get_dataset_metadata(
    db: DatabaseConnection,
    schema: str = "public",
    table_names: list[str] | None = None,
) -> ToolResponse:
    """Retrieve dataset metadata: table schemas, row counts, column info."""
    try:
        if table_names is None:
            table_names = db.list_tables(schema)

        tables: list[TableMetadata] = []
        for tname in table_names:
            raw_columns = db.get_columns(schema, tname)
            columns = [
                ColumnMetadata(
                    name=c["name"],
                    data_type=c["data_type"],
                    is_nullable=c.get("is_nullable", True),
                    is_primary_key=c.get("is_primary_key", False),
                )
                for c in raw_columns
            ]
            row_count = db.get_row_count(schema, tname)
            tables.append(
                TableMetadata(
                    schema_name=schema,
                    table_name=tname,
                    columns=columns,
                    row_count=row_count,
                )
            )

        result = DatasetMetadataResult(tables=tables)
        return ToolResponse(success=True, data=result.model_dump())
    except Exception as e:
        return ToolResponse(success=False, error=str(e))


class PipelineRunSummary(BaseModel):
    """Summary of a single pipeline run for agent consumption."""

    run_type: str
    overall_status: str
    started_at: str
    finished_at: Optional[str] = None
    records_loaded: Optional[int] = None
    error_message: Optional[str] = None


class SourceHealthSummary(BaseModel):
    """Source health snapshot for agent consumption."""

    source_name: str
    overall_status: str
    freshness_state: str
    freshness_age_seconds: Optional[float] = None
    reasons: Optional[dict[str, Any]] = None


class PipelineAlert(BaseModel):
    """Active alert derived from failed runs or degraded sources."""

    alert_type: str
    severity: str
    message: str
    source: Optional[str] = None


class ConsumerLagSummary(BaseModel):
    """Kafka consumer lag aggregated across topics."""

    total_lag: int = 0
    topics: list[dict[str, Any]] = Field(default_factory=list)


class PipelineStatusResult(BaseModel):
    """Aggregated pipeline health status for agent reasoning."""

    overall_health: str
    recent_runs: list[PipelineRunSummary] = Field(default_factory=list)
    total_runs: int = 0
    source_health: list[SourceHealthSummary] = Field(default_factory=list)
    alerts: list[PipelineAlert] = Field(default_factory=list)
    consumer_lag: ConsumerLagSummary = Field(default_factory=ConsumerLagSummary)
    processing_rate: Optional[float] = None
    last_successful_write_at: Optional[str] = None


class PipelineStatusProvider(Protocol):
    """Protocol for pipeline status data access.

    Abstracts the repository and metrics layer so the agent tool can be
    tested without a live database or Kafka cluster.
    """

    def list_recent_runs(self, limit: int = 5) -> list[dict[str, Any]]: ...
    def get_total_run_count(self) -> int: ...
    def list_source_health(self) -> list[dict[str, Any]]: ...
    def get_lag_samples(self) -> list[dict[str, Any]]: ...


def get_pipeline_status(
    provider: PipelineStatusProvider,
    limit: int = 5,
) -> ToolResponse:
    """Report current pipeline health: recent runs, source status, lag, alerts."""
    try:
        recent_runs_raw = provider.list_recent_runs(limit=limit)
        total_runs = provider.get_total_run_count()
        source_health_raw = provider.list_source_health()
        lag_samples_raw = provider.get_lag_samples()

        recent_runs = [
            PipelineRunSummary(
                run_type=r["run_type"],
                overall_status=r["overall_status"],
                started_at=r["started_at"],
                finished_at=r.get("finished_at"),
                records_loaded=r.get("records_loaded"),
                error_message=r.get("error_message"),
            )
            for r in recent_runs_raw
        ]

        source_health = [
            SourceHealthSummary(
                source_name=s["source_name"],
                overall_status=s["overall_status"],
                freshness_state=s["freshness_state"],
                freshness_age_seconds=s.get("freshness_age_seconds"),
                reasons=s.get("reasons"),
            )
            for s in source_health_raw
        ]

        consumer_lag = _aggregate_lag(lag_samples_raw)
        processing_rate = _compute_processing_rate(recent_runs_raw)
        last_write = _last_successful_write(recent_runs_raw)

        alerts = _derive_alerts(recent_runs_raw, source_health_raw)

        overall_health = _derive_overall_pipeline_health(recent_runs_raw, source_health_raw)

        result = PipelineStatusResult(
            overall_health=overall_health,
            recent_runs=recent_runs,
            total_runs=total_runs,
            source_health=source_health,
            alerts=alerts,
            consumer_lag=consumer_lag,
            processing_rate=processing_rate,
            last_successful_write_at=last_write,
        )
        return ToolResponse(success=True, data=result.model_dump())
    except Exception as e:
        return ToolResponse(success=False, error=str(e))


def _aggregate_lag(lag_samples: list[dict[str, Any]]) -> ConsumerLagSummary:
    topic_lag: dict[str, int] = {}
    for s in lag_samples:
        topic = s.get("topic", "unknown")
        topic_lag[topic] = topic_lag.get(topic, 0) + int(s.get("lag") or 0)

    total = sum(topic_lag.values())
    topics = [{"topic": t, "lag": lag} for t, lag in sorted(topic_lag.items())]
    return ConsumerLagSummary(total_lag=total, topics=topics)


def _compute_processing_rate(runs: list[dict[str, Any]]) -> Optional[float]:
    completed = [
        r
        for r in runs
        if r.get("finished_at") and r.get("started_at") and r.get("records_loaded") is not None
    ]
    if not completed:
        return None

    total_records = 0
    total_seconds = 0.0
    for r in completed:
        try:
            from datetime import datetime

            start = datetime.fromisoformat(r["started_at"])
            end = datetime.fromisoformat(r["finished_at"])
            duration = (end - start).total_seconds()
            if duration > 0:
                total_records += r["records_loaded"]
                total_seconds += duration
        except (ValueError, TypeError):
            continue

    if total_seconds > 0:
        return round(total_records / total_seconds, 2)
    return None


def _last_successful_write(runs: list[dict[str, Any]]) -> Optional[str]:
    for r in runs:
        if r.get("overall_status") == "healthy" and r.get("finished_at"):
            return str(r["finished_at"])
    return None


def _derive_overall_pipeline_health(
    runs: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> str:
    if any(r.get("overall_status") == "failed" for r in runs):
        return "degraded"
    if any(s.get("overall_status") in ("degraded", "stale") for s in sources):
        return "degraded"
    if not runs:
        return "unknown"
    return "healthy"


def _derive_alerts(
    runs: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> list[PipelineAlert]:
    alerts: list[PipelineAlert] = []

    for r in runs:
        if r.get("overall_status") == "failed":
            error_msg = r.get("error_message", "Unknown error")
            alerts.append(
                PipelineAlert(
                    alert_type="pipeline_failure",
                    severity="high",
                    message=f"Pipeline run failed: {error_msg}",
                    source=r.get("run_type"),
                )
            )

    for s in sources:
        status = s.get("overall_status", "unknown")
        if status == "degraded":
            reasons = s.get("reasons")
            detail = (
                "; ".join(str(v) for v in reasons.values())
                if isinstance(reasons, dict)
                else "Degraded"
            )
            alerts.append(
                PipelineAlert(
                    alert_type="source_degraded",
                    severity="medium",
                    message=f"Source '{s['source_name']}' is degraded: {detail}",
                    source=s["source_name"],
                )
            )
        elif status == "stale":
            age = s.get("freshness_age_seconds")
            age_str = f"{age:.0f}s" if age is not None else "unknown age"
            alerts.append(
                PipelineAlert(
                    alert_type="source_stale",
                    severity="medium",
                    message=f"Source '{s['source_name']}' is stale ({age_str})",
                    source=s["source_name"],
                )
            )

    return alerts
