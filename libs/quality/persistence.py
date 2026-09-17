"""Quality-result persistence — write/read APIs for PostgreSQL warehouse.

Persists TASK-056 ``QualityResult`` objects into the ``data_quality_results``
warehouse table with replay-safe identity and provides query APIs for
recent failures and latest-status lookups.

Design decisions (TASK-057):
    - Replay key is deterministic: ``check_name:pipeline_run_id:obs_id:source``.
      Re-inserting the same result is a no-op via ``ON CONFLICT DO NOTHING``.
    - Uses psycopg2 directly, consistent with ``WarehouseLoader``.
    - Reader provides targeted queries, not a general-purpose ORM.
    - No Airflow dependency — pure application-layer persistence.
"""

from __future__ import annotations

# mypy: disable-error-code="import-untyped,no-any-return"
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import psycopg2
from psycopg2.extras import execute_batch

from libs.quality.models import (
    QualityResult,
    QualitySuiteResult,
)

logger = logging.getLogger(__name__)


def make_replay_key(
    check_name: str,
    pipeline_run_id: int | None = None,
    observation_id: int | None = None,
    source: str | None = None,
) -> str:
    """Build a deterministic replay key for idempotent writes.

    The key combines the check identity with its scoping context. Two
    results with the same key represent the same logical check execution
    and should not be duplicated.
    """
    parts = [
        check_name,
        str(pipeline_run_id) if pipeline_run_id is not None else "_",
        str(observation_id) if observation_id is not None else "_",
        source or "_",
    ]
    return ":".join(parts)


@dataclass(frozen=True)
class QualityPersistenceConfig:
    """Database connection configuration for quality persistence.

    Uses the same ``WAREHOUSE_DB_*`` environment variables as the
    warehouse loader and migrations.
    """

    db_url: str

    @classmethod
    def from_env(cls) -> QualityPersistenceConfig:
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
class WriteResult:
    """Outcome of a persistence write operation."""

    written: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors


class QualityResultWriter:
    """Write quality results to the ``data_quality_results`` warehouse table.

    Supports replay-safe writes via ``replay_key`` — re-inserting the same
    result is a no-op.

    Parameters
    ----------
    config:
        Database connection configuration.
    """

    def __init__(self, config: QualityPersistenceConfig) -> None:
        self._db_url = config.db_url

    def write_result(
        self,
        result: QualityResult,
        *,
        pipeline_run_id: int | None = None,
        observation_id: int | None = None,
    ) -> WriteResult:
        """Persist a single quality result."""
        return self.write_results(
            [result],
            pipeline_run_id=pipeline_run_id,
            observation_id=observation_id,
        )

    def write_suite_result(
        self,
        suite_result: QualitySuiteResult,
        *,
        pipeline_run_id: int | None = None,
    ) -> WriteResult:
        """Persist all results from a quality suite execution."""
        return self.write_results(
            list(suite_result.results),
            pipeline_run_id=pipeline_run_id,
        )

    def write_results(
        self,
        results: list[QualityResult],
        *,
        pipeline_run_id: int | None = None,
        observation_id: int | None = None,
    ) -> WriteResult:
        """Persist multiple quality results in a single transaction.

        Uses ``ON CONFLICT (replay_key) DO NOTHING`` for replay safety.

        Parameters
        ----------
        results:
            Quality results to persist.
        pipeline_run_id:
            Optional pipeline run FK for traceability.
        observation_id:
            Optional observation FK, shared across all results.
        """
        if not results:
            return WriteResult()

        write_result = WriteResult()
        db_url = self._db_url.replace("postgresql+psycopg2://", "postgresql://")
        conn = psycopg2.connect(db_url)
        conn.autocommit = False

        try:
            cur = conn.cursor()

            values = []
            for r in results:
                replay_key = make_replay_key(
                    check_name=r.check_name,
                    pipeline_run_id=pipeline_run_id,
                    observation_id=observation_id,
                    source=r.source,
                )
                values.append(
                    (
                        pipeline_run_id,
                        observation_id,
                        r.check_name,
                        r.severity.value,
                        r.passed,
                        r.message or None,
                        r.checked_at,
                        r.records_checked,
                        r.failed_records,
                        json.dumps(r.details) if r.details else None,
                        replay_key,
                    )
                )

            execute_batch(
                cur,
                """
                INSERT INTO data_quality_results
                    (pipeline_run_id, observation_id, check_name, severity,
                     passed, message, checked_at, records_checked,
                     failed_records, details, replay_key)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (replay_key) DO NOTHING
                """,
                values,
            )

            conn.commit()
            write_result.written = len(values)
            logger.info(
                "quality_results_written",
                extra={"count": len(values), "pipeline_run_id": pipeline_run_id},
            )

        except Exception as exc:
            conn.rollback()
            write_result.errors.append(str(exc))
            logger.error("quality_results_write_failed", extra={"error": str(exc)})
            raise
        finally:
            conn.close()

        return write_result


@dataclass(frozen=True)
class QualityResultRow:
    """A row read back from the ``data_quality_results`` table."""

    id: int
    check_name: str
    severity: str
    passed: bool
    message: str | None
    checked_at: datetime
    records_checked: int
    failed_records: int
    details: dict[str, Any] | None
    pipeline_run_id: int | None
    observation_id: int | None
    replay_key: str


class QualityResultReader:
    """Read quality results from the warehouse.

    Provides targeted queries for common analytical patterns:
    - Recent failures (checks that failed, ordered by recency)
    - Latest status per check (most recent result for each check name)

    Parameters
    ----------
    config:
        Database connection configuration.
    """

    def __init__(self, config: QualityPersistenceConfig) -> None:
        self._db_url = config.db_url

    def _connect(self) -> Any:
        db_url = self._db_url.replace("postgresql+psycopg2://", "postgresql://")
        return psycopg2.connect(db_url)

    def recent_failures(
        self,
        *,
        limit: int = 50,
        check_name: str | None = None,
        pipeline_run_id: int | None = None,
        since: datetime | None = None,
    ) -> list[QualityResultRow]:
        """Return recent failed quality checks, newest first.

        Parameters
        ----------
        limit:
            Maximum number of rows to return.
        check_name:
            Filter to a specific check name.
        pipeline_run_id:
            Filter to a specific pipeline run.
        since:
            Only return failures after this timestamp.
        """
        conditions = ["passed = FALSE"]
        params: list[Any] = []

        if check_name is not None:
            conditions.append("check_name = %s")
            params.append(check_name)
        if pipeline_run_id is not None:
            conditions.append("pipeline_run_id = %s")
            params.append(pipeline_run_id)
        if since is not None:
            conditions.append("checked_at >= %s")
            params.append(since)

        where = " AND ".join(conditions)
        params.append(limit)

        query = f"""
            SELECT id, check_name, severity, passed, message, checked_at,
                   records_checked, failed_records, details,
                   pipeline_run_id, observation_id, replay_key
            FROM data_quality_results
            WHERE {where}
            ORDER BY checked_at DESC
            LIMIT %s
        """

        return self._execute_query(query, params)

    def latest_status(
        self,
        *,
        check_names: list[str] | None = None,
    ) -> list[QualityResultRow]:
        """Return the most recent result for each check name.

        Uses ``DISTINCT ON (check_name)`` to get the latest row per check.

        Parameters
        ----------
        check_names:
            Filter to specific check names. None returns all checks.
        """
        conditions: list[str] = []
        params: list[Any] = []

        if check_names is not None:
            conditions.append("check_name = ANY(%s)")
            params.append(check_names)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
            SELECT DISTINCT ON (check_name)
                id, check_name, severity, passed, message, checked_at,
                records_checked, failed_records, details,
                pipeline_run_id, observation_id, replay_key
            FROM data_quality_results
            {where}
            ORDER BY check_name, checked_at DESC
        """

        return self._execute_query(query, params)

    def _execute_query(self, query: str, params: list[Any]) -> list[QualityResultRow]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(query, params)
            rows = cur.fetchall()
            return [self._map_row(row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def _map_row(row: tuple[Any, ...]) -> QualityResultRow:
        details = row[8]
        if isinstance(details, str):
            details = json.loads(details)
        return QualityResultRow(
            id=row[0],
            check_name=row[1],
            severity=row[2],
            passed=row[3],
            message=row[4],
            checked_at=row[5],
            records_checked=row[6],
            failed_records=row[7],
            details=details,
            pipeline_run_id=row[9],
            observation_id=row[10],
            replay_key=row[11],
        )
