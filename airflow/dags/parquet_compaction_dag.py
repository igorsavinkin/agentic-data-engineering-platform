"""parquet_compaction DAG (TASK-061).

Scheduled DAG that compacts small Parquet files in the data lake while
preserving records, schema, and partition semantics. Validates
replacement before source removal and handles replay/partial failure
safely.

The DAG is a thin orchestration layer — all compaction logic lives in
``libs.compaction.compactor``.

Compaction configuration is read from the Airflow Variable
``parquet_compaction_config`` (JSON). When the Variable is absent,
default thresholds are used.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from airflow.models import Variable
from airflow.operators.python import PythonOperator

from airflow import DAG
from libs.common.minio_storage import MinIOSettings, MinIOStorage
from libs.compaction.compactor import CompactionConfig, ParquetCompactor

logger = logging.getLogger(__name__)

DEFAULT_SOURCES: list[str] = ["fake_store", "best_buy"]
DEFAULT_LAYERS: list[str] = ["bronze"]


def _get_compaction_config() -> CompactionConfig:
    """Build compaction config from Airflow Variable or defaults."""
    try:
        raw = Variable.get("parquet_compaction_config", default_var=None)
        if raw is None:
            return CompactionConfig()
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(parsed, dict):
            return CompactionConfig(
                min_files_to_compact=parsed.get("min_files_to_compact", 5),
                max_source_file_bytes=parsed.get("max_source_file_bytes", 10 * 1024 * 1024),
            )
    except (json.JSONDecodeError, TypeError):
        logger.warning("invalid_compaction_config_variable")
    return CompactionConfig()


def _get_sources() -> list[str]:
    """Get list of sources to compact from Airflow Variable or defaults."""
    try:
        raw = Variable.get("parquet_compaction_sources", default_var=None)
        if raw is None:
            return DEFAULT_SOURCES
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, TypeError):
        logger.warning("invalid_compaction_sources_variable")
    return DEFAULT_SOURCES


def _compact_sources(**context: object) -> dict[str, object]:
    """Compact eligible partitions for configured sources.

    Called by the PythonOperator. Iterates over configured layers and
    sources, discovering and compacting eligible partitions.
    """
    logical_date = context["logical_date"]
    if isinstance(logical_date, datetime):
        logical_date_str = logical_date.strftime("%Y-%m-%dT%H:%M:%S")
    else:
        logical_date_str = str(logical_date)

    config = _get_compaction_config()
    sources = _get_sources()
    settings = MinIOSettings()
    storage = MinIOStorage(settings)

    all_results = []
    total_compacted = 0
    total_bytes_freed = 0
    errors: list[str] = []

    try:
        for layer in DEFAULT_LAYERS:
            bucket = settings.minio_bucket_bronze if layer == "bronze" else layer
            compactor = ParquetCompactor(storage, bucket=bucket, config=config)
            for source in sources:
                results = compactor.compact_all(layer=layer, source=source)
                for r in results:
                    result_dict = {
                        "partition": r.partition_prefix,
                        "source_files": r.source_files,
                        "compacted": r.compacted,
                        "records": r.records_before,
                        "bytes_freed": r.bytes_freed,
                        "errors": r.errors,
                    }
                    all_results.append(result_dict)
                    if r.compacted:
                        total_compacted += 1
                        total_bytes_freed += r.bytes_freed
                    errors.extend(r.errors)
    finally:
        storage.close()

    summary = {
        "logical_date": logical_date_str,
        "partitions_examined": len(all_results),
        "partitions_compacted": total_compacted,
        "bytes_freed": total_bytes_freed,
        "errors": errors,
        "results": all_results,
    }

    logger.info("parquet_compaction_complete", extra=summary)

    if errors:
        raise ValueError(f"Compaction completed with {len(errors)} error(s)")

    return summary


with DAG(
    dag_id="parquet_compaction",
    description="Compact small Parquet files in the data lake (TASK-061)",
    schedule=timedelta(hours=6),
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    tags=["compaction", "parquet", "maintenance"],
    default_args={
        "owner": "data-platform",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
) as dag:
    compact = PythonOperator(
        task_id="compact_partitions",
        python_callable=_compact_sources,
    )
