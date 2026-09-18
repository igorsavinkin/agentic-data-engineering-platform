"""Tests for daily_data_quality DAG structure (TASK-060)."""

from __future__ import annotations

import ast
from pathlib import Path

DAG_PATH = Path(__file__).parent.parent / "airflow" / "dags" / "daily_data_quality_dag.py"


class TestDAGFileStructure:
    def test_dag_file_exists(self) -> None:
        assert DAG_PATH.exists()

    def test_dag_file_is_valid_python(self) -> None:
        source = DAG_PATH.read_text()
        tree = ast.parse(source)
        assert tree is not None


class TestDAGImports:
    def test_imports_quality_checks(self) -> None:
        source = DAG_PATH.read_text()
        assert "from libs.quality.checks import" in source

    def test_imports_quality_runner(self) -> None:
        source = DAG_PATH.read_text()
        assert "from libs.quality.runner import" in source

    def test_imports_quality_persistence(self) -> None:
        source = DAG_PATH.read_text()
        assert "from libs.quality.persistence import" in source

    def test_imports_airflow_dag(self) -> None:
        source = DAG_PATH.read_text()
        assert "from airflow import DAG" in source

    def test_imports_python_operator(self) -> None:
        source = DAG_PATH.read_text()
        assert "from airflow.operators.python import PythonOperator" in source


class TestDAGConfiguration:
    def _get_dag_ast(self) -> ast.Module:
        source = DAG_PATH.read_text()
        return ast.parse(source)

    def test_dag_id(self) -> None:
        source = DAG_PATH.read_text()
        assert 'dag_id="daily_data_quality"' in source

    def test_daily_schedule(self) -> None:
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
        assert 'task_id="run_quality_checks"' in source

    def test_retries_configured(self) -> None:
        source = DAG_PATH.read_text()
        assert '"retries": 2' in source

    def test_tags(self) -> None:
        source = DAG_PATH.read_text()
        assert '"quality"' in source
        assert '"data-quality"' in source

    def test_owner(self) -> None:
        source = DAG_PATH.read_text()
        assert '"owner": "data-platform"' in source


class TestDAGLogic:
    def test_uses_logical_date(self) -> None:
        source = DAG_PATH.read_text()
        assert "logical_date" in source

    def test_uses_quality_persistence(self) -> None:
        source = DAG_PATH.read_text()
        assert "QualityResultWriter" in source

    def test_uses_run_checks(self) -> None:
        source = DAG_PATH.read_text()
        assert "run_checks" in source

    def test_uses_airflow_variable(self) -> None:
        source = DAG_PATH.read_text()
        assert "Variable.get" in source

    def test_has_default_checks(self) -> None:
        source = DAG_PATH.read_text()
        assert "DEFAULT_CHECKS" in source

    def test_queries_warehouse(self) -> None:
        source = DAG_PATH.read_text()
        assert "product_observations" in source

    def test_raises_on_errors(self) -> None:
        source = DAG_PATH.read_text()
        assert "has_errors" in source
        assert "raise" in source

    def test_builds_checks_function(self) -> None:
        source = DAG_PATH.read_text()
        assert "def _build_checks" in source

    def test_supports_required_fields_check(self) -> None:
        source = DAG_PATH.read_text()
        assert "RequiredFieldsCheck" in source

    def test_supports_price_validity_check(self) -> None:
        source = DAG_PATH.read_text()
        assert "PriceValidityCheck" in source

    def test_supports_freshness_check(self) -> None:
        source = DAG_PATH.read_text()
        assert "FreshnessCheck" in source

    def test_supports_duplicate_check(self) -> None:
        source = DAG_PATH.read_text()
        assert "DuplicateCheck" in source
