"""Tests for build_daily_metrics DAG structure (TASK-062)."""

from __future__ import annotations

import ast
from pathlib import Path

DAG_PATH = Path(__file__).parent.parent / "airflow" / "dags" / "build_daily_metrics_dag.py"


class TestDAGFileStructure:
    def test_dag_file_exists(self) -> None:
        assert DAG_PATH.exists()

    def test_dag_file_is_valid_python(self) -> None:
        source = DAG_PATH.read_text()
        tree = ast.parse(source)
        assert tree is not None


class TestDAGImports:
    def test_imports_calculator(self) -> None:
        source = DAG_PATH.read_text()
        assert "from libs.metrics" in source

    def test_imports_persistence(self) -> None:
        source = DAG_PATH.read_text()
        assert "MetricsResultWriter" in source

    def test_imports_airflow_dag(self) -> None:
        source = DAG_PATH.read_text()
        assert "from airflow import DAG" in source

    def test_imports_python_operator(self) -> None:
        source = DAG_PATH.read_text()
        assert "from airflow.operators.python import PythonOperator" in source


class TestDAGConfiguration:
    def test_dag_id(self) -> None:
        source = DAG_PATH.read_text()
        assert 'dag_id="build_daily_metrics"' in source

    def test_schedule(self) -> None:
        source = DAG_PATH.read_text()
        assert "timedelta(days=1)" in source

    def test_catchup_disabled(self) -> None:
        source = DAG_PATH.read_text()
        assert "catchup=False" in source

    def test_max_active_runs(self) -> None:
        source = DAG_PATH.read_text()
        assert "max_active_runs=1" in source

    def test_has_python_operator(self) -> None:
        source = DAG_PATH.read_text()
        assert "PythonOperator" in source

    def test_task_id(self) -> None:
        source = DAG_PATH.read_text()
        assert 'task_id="compute_daily_metrics"' in source

    def test_retries_configured(self) -> None:
        source = DAG_PATH.read_text()
        assert '"retries": 2' in source

    def test_tags(self) -> None:
        source = DAG_PATH.read_text()
        assert '"metrics"' in source
        assert '"analytics"' in source

    def test_owner(self) -> None:
        source = DAG_PATH.read_text()
        assert '"owner": "data-platform"' in source


class TestDAGLogic:
    def test_uses_logical_date(self) -> None:
        source = DAG_PATH.read_text()
        assert "logical_date" in source

    def test_uses_calculator(self) -> None:
        source = DAG_PATH.read_text()
        assert "DailyMetricsCalculator" in source

    def test_uses_data_interval(self) -> None:
        source = DAG_PATH.read_text()
        assert "metric_date" in source

    def test_raises_on_errors(self) -> None:
        source = DAG_PATH.read_text()
        assert "raise" in source

    def test_queries_observations(self) -> None:
        source = DAG_PATH.read_text()
        assert "product_observations" in source
