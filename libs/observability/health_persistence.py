"""Ingestion health result persistence (TASK-059).

Writes and reads ``IngestionHealthEvaluation`` results to/from the
``ingestion_health_results`` warehouse table. Uses the same
``WAREHOUSE_DB_*`` environment variables and psycopg2 patterns as
``QualityResultWriter``.

Replay key is deterministic: ``source_name:logical_date``. Re-running
the same evaluation for the same logical interval is a no-op via
``ON CONFLICT (replay_key) DO NOTHING``.
"""

from __future__ import annotations

# mypy: disable-error-code="import-untyped,no-any-return"
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import psycopg2
from psycopg2.extras import execute_batch

from libs.observability.health_evaluation import IngestionHealthEvaluation

logger = logging.getLogger(__name__)


def make_health_replay_key(source_name: str, logical_date: str) -> str:
    """Build a deterministic replay key for idempotent health writes.

    The key combines the source identity with the logical evaluation
    date. Two evaluations with the same key represent the same logical
    check and should not be duplicated.
    """
    return f"{source_name}:{logical_date}"


@dataclass(frozen=True)
class HealthPersistenceConfig:
    """Database connection configuration for health persistence.

    Uses the same ``WAREHOUSE_DB_*`` environment variables as the
    warehouse loader and quality persistence.
    """

    db_url: str

    @classmethod
    def from_env(cls) -> HealthPersistenceConfig:
        """Build config from ``WAREHOUSE_DB_*`` environment variables."""
        import os

        host = os.getenv("WAREHOUSE_DB_HOST", "localhost")
        port = os.getenv("WAREHOUSE_DB_PORT", "5432")
        dbname = os.getenv("WAREHOUSE_DB_NAME", "warehouse")
        user = os.getenv("WAREHOUSE_DB_USER", "postgres")
        password = os.getenv("WAREHOUSE_DB_PASSWORD", "")
        url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
        return cls(db_url=url)


@dataclass
class HealthWriteResult:
    """Outcome of a health persistence write operation."""

    written: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors


class IngestionHealthResultWriter:
    """Write health evaluations to the ``ingestion_health_results`` table.

    Supports replay-safe writes via ``replay_key`` — re-inserting the
    same evaluation is a no-op.

    Parameters
    ----------
    config:
        Database connection configuration.
    """

    def __init__(self, config: HealthPersistenceConfig) -> None:
        self._db_url = config.db_url

    def write_evaluations(
        self,
        evaluations: list[IngestionHealthEvaluation],
        *,
        logical_date: str,
        evaluated_at: datetime | None = None,
    ) -> HealthWriteResult:
        """Persist multiple health evaluations in a single transaction.

        Uses ``ON CONFLICT (replay_key) DO NOTHING`` for replay safety.

        Parameters
        ----------
        evaluations:
            Health evaluations to persist.
        logical_date:
            The Airflow logical date string for this evaluation run.
        evaluated_at:
            When the evaluation was performed. Defaults to now().
        """
        if not evaluations:
            return HealthWriteResult()

        now = evaluated_at or datetime.now(timezone.utc)
        write_result = HealthWriteResult()
        db_url = self._db_url.replace("postgresql+psycopg2://", "postgresql://")
        conn = psycopg2.connect(db_url)
        conn.autocommit = False

        try:
            cur = conn.cursor()

            values = []
            for ev in evaluations:
                replay_key = make_health_replay_key(ev.source_name, logical_date)
                values.append(
                    (
                        ev.source_name,
                        ev.assessment.state.value,
                        ev.freshness_state.value,
                        json.dumps(ev.assessment.reasons),
                        json.dumps(ev.assessment.signals),
                        ev.freshness_age_seconds,
                        ev.assessment.assessed_at,
                        now,
                        logical_date,
                        replay_key,
                    )
                )

            execute_batch(
                cur,
                """
                INSERT INTO ingestion_health_results
                    (source_name, state, freshness_state, reasons, signals,
                     freshness_age_seconds, assessed_at, evaluated_at,
                     logical_date, replay_key)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (replay_key) DO NOTHING
                """,
                values,
            )

            conn.commit()
            write_result.written = len(values)
            logger.info(
                "ingestion_health_results_written",
                extra={
                    "count": len(values),
                    "logical_date": logical_date,
                },
            )

        except Exception as exc:
            conn.rollback()
            write_result.errors.append(str(exc))
            logger.error("ingestion_health_write_failed", extra={"error": str(exc)})
            raise
        finally:
            conn.close()

        return write_result


@dataclass(frozen=True)
class IngestionHealthResultRow:
    """A row read back from the ``ingestion_health_results`` table."""

    id: int
    source_name: str
    state: str
    freshness_state: str
    reasons: list[str]
    signals: dict[str, Any]
    freshness_age_seconds: float | None
    assessed_at: datetime
    evaluated_at: datetime
    logical_date: str
    replay_key: str


class IngestionHealthResultReader:
    """Read health evaluation results from the warehouse.

    Provides targeted queries for common analytical patterns:
    - Latest status per source
    - Recent evaluations for a source
    - Sources in degraded states

    Parameters
    ----------
    config:
        Database connection configuration.
    """

    def __init__(self, config: HealthPersistenceConfig) -> None:
        self._db_url = config.db_url

    def _connect(self) -> Any:
        db_url = self._db_url.replace("postgresql+psycopg2://", "postgresql://")
        return psycopg2.connect(db_url)

    def latest_per_source(self) -> list[IngestionHealthResultRow]:
        """Return the most recent evaluation for each source.

        Uses ``DISTINCT ON (source_name)`` to get the latest row per source.
        """
        query = """
            SELECT DISTINCT ON (source_name)
                id, source_name, state, freshness_state, reasons, signals,
                freshness_age_seconds, assessed_at, evaluated_at,
                logical_date, replay_key
            FROM ingestion_health_results
            ORDER BY source_name, assessed_at DESC
        """
        return self._execute_query(query, [])

    def recent_evaluations(
        self,
        *,
        source_name: str | None = None,
        limit: int = 50,
    ) -> list[IngestionHealthResultRow]:
        """Return recent evaluations, newest first.

        Parameters
        ----------
        source_name:
            Filter to a specific source. None returns all sources.
        limit:
            Maximum number of rows to return.
        """
        conditions: list[str] = []
        params: list[Any] = []

        if source_name is not None:
            conditions.append("source_name = %s")
            params.append(source_name)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        query = f"""
            SELECT id, source_name, state, freshness_state, reasons, signals,
                   freshness_age_seconds, assessed_at, evaluated_at,
                   logical_date, replay_key
            FROM ingestion_health_results
            {where}
            ORDER BY assessed_at DESC
            LIMIT %s
        """
        return self._execute_query(query, params)

    def degraded_sources(self) -> list[IngestionHealthResultRow]:
        """Return latest evaluations where sources are not HEALTHY."""
        query = """
            SELECT DISTINCT ON (source_name)
                id, source_name, state, freshness_state, reasons, signals,
                freshness_age_seconds, assessed_at, evaluated_at,
                logical_date, replay_key
            FROM ingestion_health_results
            ORDER BY source_name, assessed_at DESC
        """
        rows = self._execute_query(query, [])
        return [r for r in rows if r.state != "healthy"]

    def _execute_query(self, query: str, params: list[Any]) -> list[IngestionHealthResultRow]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(query, params)
            rows = cur.fetchall()
            return [self._map_row(row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def _map_row(row: tuple[Any, ...]) -> IngestionHealthResultRow:
        reasons = row[4]
        if isinstance(reasons, str):
            reasons = json.loads(reasons)
        signals = row[5]
        if isinstance(signals, str):
            signals = json.loads(signals)
        return IngestionHealthResultRow(
            id=row[0],
            source_name=row[1],
            state=row[2],
            freshness_state=row[3],
            reasons=reasons or [],
            signals=signals or {},
            freshness_age_seconds=row[6],
            assessed_at=row[7],
            evaluated_at=row[8],
            logical_date=row[9],
            replay_key=row[10],
        )
