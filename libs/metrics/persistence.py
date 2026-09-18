"""Daily metrics persistence — write API for PostgreSQL warehouse.

Persists computed daily metrics into the ``daily_metrics`` warehouse table
with replay-safe identity. Uses ``ON CONFLICT DO NOTHING`` on the
``replay_key`` unique constraint.

Design decisions (TASK-062):
    - Replay key is deterministic: ``metric_name:metric_date:dimension``.
    - Uses psycopg2 directly, consistent with other persistence modules.
    - No Airflow dependency — pure application-layer persistence.
"""

from __future__ import annotations

# mypy: disable-error-code="import-untyped,no-any-return"
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import execute_batch

from libs.metrics.calculator import DailyMetric

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MetricsPersistenceConfig:
    """Database connection configuration for metrics persistence."""

    db_url: str

    @classmethod
    def from_env(cls) -> MetricsPersistenceConfig:
        """Build config from ``WAREHOUSE_DB_*`` environment variables."""
        host = os.getenv("WAREHOUSE_DB_HOST", "localhost")
        port = os.getenv("WAREHOUSE_DB_PORT", "5432")
        dbname = os.getenv("WAREHOUSE_DB_NAME", "warehouse")
        user = os.getenv("WAREHOUSE_DB_USER", "postgres")
        password = os.getenv("WAREHOUSE_DB_PASSWORD", "")
        url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
        return cls(db_url=url)


@dataclass
class MetricsWriteResult:
    """Outcome of a metrics persistence write operation."""

    written: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors


class MetricsResultWriter:
    """Write daily metrics to the ``daily_metrics`` warehouse table.

    Uses ``ON CONFLICT (replay_key) DO NOTHING`` for replay safety.

    Parameters
    ----------
    config:
        Database connection configuration.
    """

    def __init__(self, config: MetricsPersistenceConfig) -> None:
        self._db_url = config.db_url

    def write_metrics(
        self,
        metrics: list[DailyMetric],
        *,
        logical_date: str,
    ) -> MetricsWriteResult:
        """Persist daily metrics in a single transaction.

        Parameters
        ----------
        metrics:
            Metric values to persist.
        logical_date:
            Airflow logical date for traceability.
        """
        if not metrics:
            return MetricsWriteResult()

        write_result = MetricsWriteResult()
        db_url = self._db_url.replace("postgresql+psycopg2://", "postgresql://")
        conn = psycopg2.connect(db_url)
        conn.autocommit = False

        try:
            cur = conn.cursor()
            computed_at = datetime.now(timezone.utc)

            values = []
            for m in metrics:
                values.append(
                    (
                        m.metric_date,
                        m.metric_name,
                        m.dimension,
                        m.value,
                        computed_at,
                        logical_date,
                        m.replay_key,
                    )
                )

            execute_batch(
                cur,
                """
                INSERT INTO daily_metrics
                    (metric_date, metric_name, dimension, value,
                     computed_at, logical_date, replay_key)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (replay_key) DO NOTHING
                """,
                values,
            )

            conn.commit()
            write_result.written = len(values)
            logger.info(
                "daily_metrics_written",
                extra={"count": len(values), "logical_date": logical_date},
            )

        except Exception as exc:
            conn.rollback()
            write_result.errors.append(str(exc))
            logger.error("daily_metrics_write_failed", extra={"error": str(exc)})
            raise
        finally:
            conn.close()

        return write_result
