"""build_daily_metrics DAG (TASK-062).

Scheduled DAG that computes daily analytical metrics from product
observations and persists them to the ``daily_metrics`` table.

The DAG is a thin orchestration layer — all computation logic lives in
``libs.metrics.calculator`` and persistence in ``libs.metrics.persistence``.

Uses the Airflow logical date (= data_interval_start) as the metric date.
For schedule=timedelta(days=1), a run with logical_date=D covers [D, D+1).

Idempotency: the persistence layer uses ``replay_key`` with
``ON CONFLICT DO NOTHING``, so rerunning the same logical interval
does not duplicate metrics.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import polars as pl
import psycopg2
from airflow.operators.python import PythonOperator

from airflow import DAG
from libs.metrics.calculator import DailyMetricsCalculator
from libs.metrics.persistence import (
    MetricsPersistenceConfig,
    MetricsResultWriter,
)

logger = logging.getLogger(__name__)


def _query_observations(db_url: str, metric_date: str) -> pl.DataFrame:
    """Load observations for a specific date from the warehouse.

    Returns a Polars DataFrame suitable for metrics computation.
    """
    plain_url = db_url.replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(plain_url)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT s.name AS source_name,
                   p.id AS product_id,
                   po.price,
                   po.availability,
                   po.collected_at
            FROM product_observations po
            JOIN source_products sp ON sp.id = po.source_product_id
            JOIN sources s ON s.id = sp.source_id
            JOIN products p ON p.id = sp.product_id
            WHERE po.collected_at AT TIME ZONE 'UTC' >= %s::date
              AND po.collected_at AT TIME ZONE 'UTC' < (%s::date + interval '1 day')
            ORDER BY po.collected_at
            """,
            (metric_date, metric_date),
        )
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        cur.close()
    finally:
        conn.close()

    if not rows:
        return pl.DataFrame(
            {
                "source_name": pl.Series([], dtype=pl.Utf8),
                "product_id": pl.Series([], dtype=pl.Int64),
                "price": pl.Series([], dtype=pl.Float64),
                "availability": pl.Series([], dtype=pl.Utf8),
                "collected_at": pl.Series([], dtype=pl.Datetime),
            }
        )

    data = {col: [row[i] for row in rows] for i, col in enumerate(columns)}
    return pl.DataFrame(data)


def _build_daily_metrics(**context: object) -> dict[str, object]:
    """Compute and persist daily metrics.

    Called by the PythonOperator. Uses the Airflow logical date (= data_interval_start)
    as the metric date.
    """
    logical_date = context["logical_date"]
    if isinstance(logical_date, datetime):
        logical_date_str = logical_date.strftime("%Y-%m-%dT%H:%M:%S")
        metric_date = logical_date.strftime("%Y-%m-%d")
    else:
        logical_date_str = str(logical_date)
        metric_date = str(logical_date)

    config = MetricsPersistenceConfig.from_env()

    df = _query_observations(config.db_url, metric_date)

    from datetime import date as date_type

    target = date_type.fromisoformat(metric_date)
    calculator = DailyMetricsCalculator(target)
    metrics_result = calculator.compute(df)

    writer = MetricsResultWriter(config)
    write_result = writer.write_metrics(metrics_result.metrics, logical_date=logical_date_str)

    summary = {
        "metric_date": metric_date,
        "logical_date": logical_date_str,
        "observations_processed": metrics_result.observation_count,
        "metrics_computed": len(metrics_result.metrics),
        "metrics_written": write_result.written,
        "errors": metrics_result.errors + write_result.errors,
    }

    logger.info("build_daily_metrics_complete", extra=summary)

    if metrics_result.errors:
        raise ValueError(f"Metrics computation failed: {metrics_result.errors}")

    return summary


with DAG(
    dag_id="build_daily_metrics",
    description="Compute daily analytical metrics from product observations (TASK-062)",
    schedule=timedelta(days=1),
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    tags=["metrics", "analytics", "gold"],
    default_args={
        "owner": "data-platform",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
) as dag:
    build_metrics = PythonOperator(
        task_id="compute_daily_metrics",
        python_callable=_build_daily_metrics,
    )
