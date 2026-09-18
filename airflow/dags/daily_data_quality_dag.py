"""daily_data_quality DAG (TASK-060).

Scheduled DAG that runs data quality checks against recent warehouse
observations and persists results to the ``data_quality_results`` table.

The DAG is a thin orchestration layer — all check logic lives in
``libs.quality.checks`` and persistence in ``libs.quality.persistence``.

Check configuration is read from the Airflow Variable
``daily_data_quality_checks`` (JSON). When the Variable is absent, a
default set of checks with standard thresholds is used.

Idempotency: the persistence layer uses ``replay_key`` with
``ON CONFLICT DO NOTHING``, so rerunning the same logical interval
does not duplicate results.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import polars as pl
import psycopg2
from airflow.models import Variable
from airflow.operators.python import PythonOperator

from airflow import DAG
from libs.quality.checks import (
    DuplicateCheck,
    FreshnessCheck,
    PriceValidityCheck,
    RequiredFieldsCheck,
)
from libs.quality.models import CheckSeverity, QualityCheck
from libs.quality.persistence import (
    QualityPersistenceConfig,
    QualityResultWriter,
)
from libs.quality.runner import run_checks

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS: list[str] = [
    "source_name",
    "product_id",
    "price",
    "collected_at",
]

DEFAULT_CHECKS: dict[str, dict[str, object]] = {
    "required_fields": {
        "type": "required_fields",
        "columns": REQUIRED_COLUMNS,
    },
    "price_validity": {
        "type": "price_validity",
        "min_price": 0.0,
    },
    "freshness": {
        "type": "freshness",
        "max_age_seconds": 86400.0,
    },
    "duplicates": {
        "type": "duplicates",
        "key_columns": ["source_name", "product_id"],
    },
}


def _build_checks(check_config: dict[str, dict[str, object]]) -> list[QualityCheck]:
    """Instantiate quality checks from a configuration dict."""
    checks: list[QualityCheck] = []
    for _name, spec in check_config.items():
        check_type = spec.get("type", "")
        severity = CheckSeverity(spec["severity"]) if "severity" in spec else None
        kwargs = {k: v for k, v in spec.items() if k not in ("type", "severity")}
        if severity is not None:
            kwargs["severity"] = severity

        if check_type == "required_fields":
            checks.append(RequiredFieldsCheck(**kwargs))
        elif check_type == "price_validity":
            checks.append(PriceValidityCheck(**kwargs))
        elif check_type == "freshness":
            checks.append(FreshnessCheck(**kwargs))
        elif check_type == "duplicates":
            checks.append(DuplicateCheck(**kwargs))
        else:
            logger.warning("unknown_check_type_skipped", extra={"type": check_type})
    return checks


def _get_check_config() -> dict[str, dict[str, object]]:
    """Build check config from Airflow Variable or defaults."""
    try:
        raw = Variable.get("daily_data_quality_checks", default_var=None)
        if raw is None:
            return DEFAULT_CHECKS
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, TypeError):
        logger.warning("invalid_data_quality_checks_variable")
    return DEFAULT_CHECKS


def _query_observations(db_url: str, lookback_hours: int = 24) -> pl.DataFrame:
    """Load recent product observations from the warehouse.

    Returns a Polars DataFrame suitable for quality check execution.
    """
    plain_url = db_url.replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(plain_url)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT s.name AS source_name,
                   p.sku AS product_id,
                   po.price,
                   po.currency,
                   po.availability,
                   po.collected_at
            FROM product_observations po
            JOIN source_products sp ON sp.id = po.source_product_id
            JOIN sources s ON s.id = sp.source_id
            JOIN products p ON p.id = sp.product_id
            WHERE po.collected_at >= now() - make_interval(hours => %s)
            ORDER BY po.collected_at DESC
            LIMIT 100000
            """,
            (lookback_hours,),
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
                "product_id": pl.Series([], dtype=pl.Utf8),
                "price": pl.Series([], dtype=pl.Float64),
                "currency": pl.Series([], dtype=pl.Utf8),
                "availability": pl.Series([], dtype=pl.Utf8),
                "collected_at": pl.Series([], dtype=pl.Datetime),
            }
        )

    data = {col: [row[i] for row in rows] for i, col in enumerate(columns)}
    return pl.DataFrame(data)


def _run_quality_checks(**context: object) -> dict[str, object]:
    """Execute quality checks and persist results.

    Called by the PythonOperator. Uses the Airflow logical date for
    replay-safe persistence.
    """
    logical_date = context["logical_date"]
    if isinstance(logical_date, datetime):
        logical_date_str = logical_date.strftime("%Y-%m-%dT%H:%M:%S")
    else:
        logical_date_str = str(logical_date)

    check_config = _get_check_config()
    checks = _build_checks(check_config)

    db_config = QualityPersistenceConfig.from_env()

    try:
        df = _query_observations(db_config.db_url)
    except Exception:
        logger.warning("warehouse_query_failed_using_empty_frame")
        df = pl.DataFrame(
            {
                "source_name": pl.Series([], dtype=pl.Utf8),
                "product_id": pl.Series([], dtype=pl.Utf8),
                "price": pl.Series([], dtype=pl.Float64),
                "collected_at": pl.Series([], dtype=pl.Datetime),
            }
        )

    suite_result = run_checks(df, checks, suite_name="daily_data_quality")

    writer = QualityResultWriter(db_config)
    write_result = writer.write_suite_result(suite_result)

    results_summary = {
        "total_checks": suite_result.total_checks,
        "passed_checks": suite_result.passed_checks,
        "failed_checks": suite_result.failed_checks,
        "written": write_result.written,
        "skipped": write_result.skipped,
        "errors": write_result.errors,
        "logical_date": logical_date_str,
        "has_errors": suite_result.has_errors,
    }

    logger.info(
        "daily_data_quality_complete",
        extra=results_summary,
    )

    if suite_result.has_errors:
        raise ValueError(f"Quality checks failed with {suite_result.failed_checks} error(s)")

    return results_summary


with DAG(
    dag_id="daily_data_quality",
    description="Run data quality checks and persist results (TASK-060)",
    schedule=timedelta(days=1),
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    tags=["quality", "data-quality", "observability"],
    default_args={
        "owner": "data-platform",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
) as dag:
    run_quality = PythonOperator(
        task_id="run_quality_checks",
        python_callable=_run_quality_checks,
    )
