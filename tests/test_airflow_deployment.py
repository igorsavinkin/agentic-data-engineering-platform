"""Unit tests for Airflow local deployment configuration (TASK-058).

Verifies the Docker Compose structure, init scripts, and directory layout
without requiring a running Docker daemon.
"""

from __future__ import annotations

from pathlib import Path

# mypy: disable-error-code="import-untyped"
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "docker-compose.yml"
AIRFLOW_DIR = ROOT / "airflow"


def _load_compose() -> dict:
    with open(COMPOSE_FILE) as f:
        return yaml.safe_load(f)  # type: ignore[no-any-return]


class TestAirflowComposeServices:
    def test_airflow_init_service_exists(self) -> None:
        compose = _load_compose()
        assert "airflow-init" in compose["services"]

    def test_airflow_scheduler_service_exists(self) -> None:
        compose = _load_compose()
        assert "airflow-scheduler" in compose["services"]

    def test_airflow_webserver_service_exists(self) -> None:
        compose = _load_compose()
        assert "airflow-webserver" in compose["services"]

    def test_webserver_exposes_port(self) -> None:
        compose = _load_compose()
        webserver = compose["services"]["airflow-webserver"]
        ports = webserver.get("ports", [])
        assert any("8080" in str(p) for p in ports)

    def test_webserver_has_healthcheck(self) -> None:
        compose = _load_compose()
        webserver = compose["services"]["airflow-webserver"]
        assert "healthcheck" in webserver

    def test_scheduler_runs_scheduler_command(self) -> None:
        compose = _load_compose()
        scheduler = compose["services"]["airflow-scheduler"]
        assert scheduler.get("command") == "scheduler"

    def test_all_services_use_local_executor(self) -> None:
        compose = _load_compose()
        for name in ("airflow-init", "airflow-scheduler", "airflow-webserver"):
            env = compose["services"][name].get("environment", {})
            assert env.get("AIRFLOW__CORE__EXECUTOR") == "LocalExecutor"

    def test_all_services_connect_to_postgres(self) -> None:
        compose = _load_compose()
        for name in ("airflow-init", "airflow-scheduler", "airflow-webserver"):
            env = compose["services"][name].get("environment", {})
            conn = env.get("AIRFLOW__DATABASE__SQL_ALCHEMY_CONN", "")
            assert "postgres" in conn

    def test_all_services_on_platform_network(self) -> None:
        compose = _load_compose()
        for name in ("airflow-init", "airflow-scheduler", "airflow-webserver"):
            networks = compose["services"][name].get("networks", [])
            assert "platform" in networks

    def test_scheduler_has_platform_connectivity_vars(self) -> None:
        compose = _load_compose()
        env = compose["services"]["airflow-scheduler"].get("environment", {})
        assert "AIRFLOW_VAR_KAFKA_BOOTSTRAP_SERVERS" in env
        assert "AIRFLOW_VAR_MINIO_ENDPOINT" in env
        assert "AIRFLOW_VAR_WAREHOUSE_DB_HOST" in env

    def test_dags_folder_mounted(self) -> None:
        compose = _load_compose()
        for name in ("airflow-scheduler", "airflow-webserver"):
            volumes = compose["services"][name].get("volumes", [])
            assert any("dags" in str(v) for v in volumes)

    def test_airflow_logs_volume_defined(self) -> None:
        compose = _load_compose()
        volumes = compose.get("volumes", {})
        assert "airflow_logs" in volumes

    def test_init_depends_on_postgres_healthy(self) -> None:
        compose = _load_compose()
        depends = compose["services"]["airflow-init"].get("depends_on", {})
        assert "postgres" in depends

    def test_scheduler_depends_on_init(self) -> None:
        compose = _load_compose()
        depends = compose["services"]["airflow-scheduler"].get("depends_on", {})
        assert "airflow-init" in depends


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
        compose = _load_compose()
        volumes = compose["services"]["postgres"].get("volumes", [])
        assert any("docker-entrypoint-initdb.d" in str(v) for v in volumes)

    def test_no_example_dags_loaded(self) -> None:
        compose = _load_compose()
        for name in ("airflow-init", "airflow-scheduler", "airflow-webserver"):
            env = compose["services"][name].get("environment", {})
            assert env.get("AIRFLOW__CORE__LOAD_EXAMPLES") == "false"
