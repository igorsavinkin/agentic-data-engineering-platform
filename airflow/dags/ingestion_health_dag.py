"""ingestion_health DAG (TASK-059).

Scheduled DAG that evaluates configured source health using existing
health/freshness/degradation semantics and persists results to the
warehouse ``ingestion_health_results`` table.

The DAG is a thin orchestration layer — all business logic lives in
``libs.observability.health_evaluation`` and
``libs.observability.health_persistence``.

Source configuration is read from the Airflow Variable
``ingestion_health_sources`` (JSON). When the Variable is absent, a
default set of sources with default thresholds is used.

Idempotency: each evaluation run uses the Airflow logical date as part
of the replay key, so rerunning the same logical interval is a no-op.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from airflow.models import Variable
from airflow.operators.python import PythonOperator

from airflow import DAG
from libs.observability.health_assessment import SourceHealthConfig
from libs.observability.health_evaluation import (
    IngestionHealthEvaluator,
    SourceHealthEvaluationConfig,
    SourceObservation,
)
from libs.observability.health_persistence import (
    HealthPersistenceConfig,
    IngestionHealthResultWriter,
)

logger = logging.getLogger(__name__)

DEFAULT_SOURCES: dict[str, dict[str, float | int | None]] = {
    "fake_store": {},
    "best_buy": {},
}


def _get_source_config() -> SourceHealthEvaluationConfig:
    """Build evaluation config from Airflow Variable or defaults."""
    try:
        raw = Variable.get("ingestion_health_sources", default_var=None)
        if raw is None:
            source_thresholds = DEFAULT_SOURCES
        else:
            source_thresholds = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        logger.warning("invalid_ingestion_health_sources_variable", extra={"raw": raw})
        source_thresholds = DEFAULT_SOURCES

    configs: dict[str, SourceHealthConfig] = {}
    for name, thresholds in source_thresholds.items():
        if isinstance(thresholds, dict):
            configs[name] = SourceHealthConfig(
                min_success_ratio=thresholds.get("min_success_ratio", 0.5),
                max_malformed_ratio=thresholds.get("max_malformed_ratio", 0.5),
                max_empty_fetches=thresholds.get("max_empty_fetches", 3),
                max_freshness_age_seconds=thresholds.get("max_freshness_age_seconds"),
                min_expected_records=thresholds.get("min_expected_records"),
            )
        else:
            configs[name] = SourceHealthConfig()

    return SourceHealthEvaluationConfig(source_configs=configs)


def _query_source_observations(db_url: str) -> list[SourceObservation]:
    """Query warehouse for latest observation data per source.

    Returns one ``SourceObservation`` per registered source. Sources
    with no observations still appear (with None timestamps) so the
    evaluator can report NEVER_COLLECTED freshness.
    """
    import psycopg2

    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT s.name,
                   MAX(po.collected_at) AS last_observation_at,
                   COUNT(po.id) AS total_observations
            FROM sources s
            LEFT JOIN source_products sp ON sp.source_id = s.id
            LEFT JOIN product_observations po ON po.source_product_id = sp.id
            GROUP BY s.name
            ORDER BY s.name
        """)
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    return [
        SourceObservation(
            source_name=row[0],
            last_observation_at=row[1],
            total_observations=row[2] or 0,
        )
        for row in rows
    ]


def _evaluate_and_persist(**context: object) -> dict[str, object]:
    """Evaluate source health and persist results.

    Called by the PythonOperator. Uses the Airflow logical date for
    replay-safe persistence.
    """
    logical_date = context["logical_date"]
    if isinstance(logical_date, datetime):
        logical_date_str = logical_date.strftime("%Y-%m-%dT%H:%M:%S")
    else:
        logical_date_str = str(logical_date)

    config = _get_source_config()
    evaluator = IngestionHealthEvaluator(evaluation_config=config)

    db_config = HealthPersistenceConfig.from_env()

    try:
        observations = _query_source_observations(db_config.db_url)
    except Exception:
        logger.warning("warehouse_query_failed_using_configured_sources")
        observations = [SourceObservation(source_name=name) for name in config.source_configs]

    if not observations:
        observations = [
            SourceObservation(source_name=name)
            for name in (list(config.source_configs.keys()) or list(DEFAULT_SOURCES.keys()))
        ]

    evaluations = evaluator.evaluate_all(observations)

    writer = IngestionHealthResultWriter(db_config)
    write_result = writer.write_evaluations(
        evaluations,
        logical_date=logical_date_str,
    )

    results_summary = {
        "evaluated": len(evaluations),
        "written": write_result.written,
        "errors": write_result.errors,
        "evaluations": [ev.to_dict() for ev in evaluations],
    }

    logger.info(
        "ingestion_health_evaluation_complete",
        extra=results_summary,
    )

    return results_summary


with DAG(
    dag_id="ingestion_health",
    description="Evaluate source ingestion health and persist results (TASK-059)",
    schedule=timedelta(minutes=15),
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    tags=["health", "ingestion", "observability"],
    default_args={
        "owner": "data-platform",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
) as dag:
    evaluate_health = PythonOperator(
        task_id="evaluate_source_health",
        python_callable=_evaluate_and_persist,
    )
