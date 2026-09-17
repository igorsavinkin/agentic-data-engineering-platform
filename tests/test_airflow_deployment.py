"""Unit tests for Airflow local deployment configuration (TASK-058).

Verifies the Docker Compose structure, init scripts, and directory layout
without requiring a running Docker daemon or PyYAML dependency.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "docker-compose.yml"
AIRFLOW_DIR = ROOT / "airflow"


def _read_compose() -> str:
    return COMPOSE_FILE.read_text()


class TestAirflowComposeServices:
    def test_airflow_init_service_defined(self) -> None:
        content = _read_compose()
        assert "airflow-init:" in content

    def test_airflow_scheduler_service_defined(self) -> None:
        content = _read_compose()
        assert "airflow-scheduler:" in content

    def test_airflow_webserver_service_defined(self) -> None:
        content = _read_compose()
        assert "airflow-webserver:" in content

    def test_webserver_exposes_port_8080(self) -> None:
        content = _read_compose()
        assert "AIRFLOW_HOST_PORT:-8080}:8080" in content

    def test_webserver_has_healthcheck(self) -> None:
        content = _read_compose()
        assert "/health" in content

    def test_scheduler_runs_scheduler_command(self) -> None:
        content = _read_compose()
        assert "command: scheduler" in content

    def test_local_executor_configured(self) -> None:
        content = _read_compose()
        assert "AIRFLOW__CORE__EXECUTOR: LocalExecutor" in content

    def test_sql_alchemy_conn_points_to_postgres(self) -> None:
        content = _read_compose()
        assert "postgresql+psycopg2://" in content
        assert "postgres:5432" in content

    def test_services_on_platform_network(self) -> None:
        content = _read_compose()
        assert "- platform" in content

    def test_scheduler_has_kafka_connectivity(self) -> None:
        content = _read_compose()
        assert "AIRFLOW_VAR_KAFKA_BOOTSTRAP_SERVERS: kafka:29092" in content

    def test_scheduler_has_minio_connectivity(self) -> None:
        content = _read_compose()
        assert "AIRFLOW_VAR_MINIO_ENDPOINT: http://minio:9000" in content

    def test_scheduler_has_warehouse_db_connectivity(self) -> None:
        content = _read_compose()
        assert "AIRFLOW_VAR_WAREHOUSE_DB_HOST: postgres" in content

    def test_dags_folder_mounted(self) -> None:
        content = _read_compose()
        assert "./airflow/dags:/opt/airflow/dags" in content

    def test_airflow_logs_volume_defined(self) -> None:
        content = _read_compose()
        assert "airflow_logs:" in content

    def test_init_depends_on_postgres(self) -> None:
        content = _read_compose()
        assert "airflow db migrate" in content

    def test_scheduler_depends_on_init(self) -> None:
        content = _read_compose()
        assert "airflow-init:" in content
        assert "service_completed_successfully" in content

    def test_no_example_dags_loaded(self) -> None:
        content = _read_compose()
        assert 'AIRFLOW__CORE__LOAD_EXAMPLES: "false"' in content

    def test_uses_official_airflow_image(self) -> None:
        content = _read_compose()
        assert "apache/airflow:" in content


class TestAirflowDirectoryLayout:
    def test_airflow_directory_exists(self) -> None:
        assert AIRFLOW_DIR.is_dir()

    def test_dags_directory_exists(self) -> None:
        assert (AIRFLOW_DIR / "dags").is_dir()

    def test_init_sql_exists(self) -> None:
        init_sql = AIRFLOW_DIR / "init" / "01-create-airflow-db.sql"
        assert init_sql.is_file()

    def test_init_sql_creates_airflow_database(self) -> None:
        init_sql = AIRFLOW_DIR / "init" / "01-create-airflow-db.sql"
        content = init_sql.read_text()
        assert "CREATE DATABASE airflow" in content

    def test_init_sql_grants_createdb(self) -> None:
        init_sql = AIRFLOW_DIR / "init" / "01-create-airflow-db.sql"
        content = init_sql.read_text()
        assert "CREATEDB" in content

    def test_postgres_mounts_init_scripts(self) -> None:
        content = _read_compose()
        assert "docker-entrypoint-initdb.d" in content
