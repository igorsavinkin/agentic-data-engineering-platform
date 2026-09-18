"""Unit tests for ingestion_health DAG structure (TASK-059).

Verifies the DAG file structure, scheduling semantics, and task
definitions without requiring Airflow to be installed.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAG_FILE = ROOT / "airflow" / "dags" / "ingestion_health_dag.py"


def _read_dag() -> str:
    return DAG_FILE.read_text()


class TestIngestionHealthDagStructure:
    def test_dag_file_exists(self) -> None:
        assert DAG_FILE.is_file()

    def test_dag_id_defined(self) -> None:
        content = _read_dag()
        assert 'dag_id="ingestion_health"' in content

    def test_schedule_interval_defined(self) -> None:
        content = _read_dag()
        assert "schedule=" in content or "schedule_interval=" in content

    def test_catchup_disabled(self) -> None:
        content = _read_dag()
        assert "catchup=False" in content

    def test_max_active_runs_defined(self) -> None:
        content = _read_dag()
        assert "max_active_runs=" in content

    def test_has_python_operator(self) -> None:
        content = _read_dag()
        assert "PythonOperator" in content

    def test_evaluate_task_defined(self) -> None:
        content = _read_dag()
        assert "evaluate_source_health" in content

    def test_imports_health_evaluation(self) -> None:
        content = _read_dag()
        assert "from libs.observability.health_evaluation import" in content

    def test_imports_health_persistence(self) -> None:
        content = _read_dag()
        assert "from libs.observability.health_persistence import" in content

    def test_has_retries_configured(self) -> None:
        content = _read_dag()
        assert "retries" in content

    def test_has_tags(self) -> None:
        content = _read_dag()
        assert "tags=" in content

    def test_uses_logical_date_for_replay(self) -> None:
        content = _read_dag()
        assert "logical_date" in content

    def test_queries_warehouse(self) -> None:
        content = _read_dag()
        assert "SELECT" in content
        assert "sources" in content
        assert "product_observations" in content

    def test_persists_results(self) -> None:
        content = _read_dag()
        assert "IngestionHealthResultWriter" in content
        assert "write_evaluations" in content

    def test_source_config_from_variable(self) -> None:
        content = _read_dag()
        assert "Variable.get" in content
        assert "ingestion_health_sources" in content

    def test_has_default_sources(self) -> None:
        content = _read_dag()
        assert "DEFAULT_SOURCES" in content
        assert "fake_store" in content
        assert "best_buy" in content
