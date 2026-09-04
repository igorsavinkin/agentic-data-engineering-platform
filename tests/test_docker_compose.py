"""Integration tests for the local Docker Compose stack (TASK-004).

These tests exercise the real infrastructure: they start Kafka, MinIO, and
PostgreSQL from ``docker-compose.yml`` under a dedicated Compose project with
alternate host ports and their own volumes, so they never disturb a stack a
developer may already be running. They require the Docker daemon and skip
cleanly when it is unavailable.

Run with::

    pytest -m integration
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "docker-compose.yml"

PROJECT = "ai-data-platform-it"
# Alternate host ports and network name so the test stack can run alongside a
# developer stack started from the documented procedure. Fixed MinIO
# credentials make the tests independent of any values a developer may have
# set in .env; they are local-only test fixtures, not real secrets.
STACK_ENV = {
    "KAFKA_HOST_PORT": "19092",
    "MINIO_HOST_PORT": "19000",
    "MINIO_CONSOLE_HOST_PORT": "19001",
    "POSTGRES_HOST_PORT": "15432",
    "PLATFORM_NETWORK_NAME": "ai-data-platform-it",
    "MINIO_ROOT_USER": "it-admin",
    "MINIO_ROOT_PASSWORD": "it-admin-secret",
}
SERVICES = ("kafka", "minio", "postgres")
MINIO_ALIAS = "it"


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def _compose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, **STACK_ENV}
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "-p", PROJECT, *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=600,
    )
    if check and result.returncode != 0:
        pytest.fail(
            f"docker compose {' '.join(args)} failed "
            f"with exit code {result.returncode}:\n{result.stderr.strip()}",
            pytrace=False,
        )
    return result


def _parse_ps(output: str) -> list[dict[str, str]]:
    # Recent Compose versions emit a JSON array; older ones emit JSON lines.
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        parsed = [json.loads(line) for line in output.splitlines() if line.strip()]
    if isinstance(parsed, dict):
        parsed = [parsed]
    return parsed  # type: ignore[no-any-return]


@pytest.fixture(scope="session")
def stack() -> Iterator[None]:
    if not _docker_available():
        pytest.skip("Docker daemon not available")
    # Clear leftovers from an aborted previous run; -p scopes this to the test
    # project only, never to a developer's stack.
    _compose("down", "--volumes", "--remove-orphans", check=False)
    _compose("up", "-d", "--wait")
    yield
    _compose("down", "--volumes", "--remove-orphans", check=False)


def test_all_services_report_healthy(stack: None) -> None:
    statuses = {
        item.get("Service"): item.get("Health")
        for item in _parse_ps(_compose("ps", "--format", "json").stdout)
    }
    assert set(statuses) == set(SERVICES)
    for service in SERVICES:
        assert statuses[service] == "healthy", f"{service} is not healthy"


def test_kafka_is_reachable_from_host(stack: None) -> None:
    with socket.create_connection(("127.0.0.1", 19092), timeout=10):
        pass


def test_kafka_answers_api_calls(stack: None) -> None:
    # In-container clients must use the internal listener (kafka:29092): the
    # host listener advertises localhost:<host port>, which does not exist
    # inside the container.
    _compose(
        "exec",
        "-T",
        "kafka",
        "/opt/kafka/bin/kafka-topics.sh",
        "--bootstrap-server",
        "kafka:29092",
        "--list",
    )


def test_minio_is_reachable_from_host(stack: None) -> None:
    with urllib.request.urlopen("http://127.0.0.1:19000/minio/health/live", timeout=10) as response:
        assert response.status == 200
    with socket.create_connection(("127.0.0.1", 19001), timeout=10):
        pass


def test_postgres_is_reachable_from_host(stack: None) -> None:
    with socket.create_connection(("127.0.0.1", 15432), timeout=10):
        pass


def test_postgres_accepts_queries(stack: None) -> None:
    result = _compose("exec", "-T", "postgres", "pg_isready")
    assert "accepting connections" in result.stdout


def test_data_survives_a_full_stack_restart(stack: None) -> None:
    # Seed one durable artifact per service.
    _compose(
        "exec",
        "-T",
        "kafka",
        "/opt/kafka/bin/kafka-topics.sh",
        "--bootstrap-server",
        "kafka:29092",
        "--create",
        "--topic",
        "platform-restart-check",
        "--partitions",
        "1",
        "--replication-factor",
        "1",
    )

    # Configure a dedicated mc alias with the test stack's fixed credentials.
    _compose(
        "exec",
        "-T",
        "minio",
        "mc",
        "alias",
        "set",
        MINIO_ALIAS,
        "http://localhost:9000",
        STACK_ENV["MINIO_ROOT_USER"],
        STACK_ENV["MINIO_ROOT_PASSWORD"],
    )
    _compose("exec", "-T", "minio", "mc", "mb", f"{MINIO_ALIAS}/platform-restart-check")

    _compose(
        "exec",
        "-T",
        "postgres",
        "sh",
        "-c",
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 '
        '-c "CREATE TABLE platform_restart_check (id integer); '
        'INSERT INTO platform_restart_check VALUES (42);"',
    )

    _compose("restart")
    _compose("up", "-d", "--wait")

    topics = _compose(
        "exec",
        "-T",
        "kafka",
        "/opt/kafka/bin/kafka-topics.sh",
        "--bootstrap-server",
        "kafka:29092",
        "--list",
    ).stdout
    assert "platform-restart-check" in topics

    _compose("exec", "-T", "minio", "mc", "stat", f"{MINIO_ALIAS}/platform-restart-check")

    query = _compose(
        "exec",
        "-T",
        "postgres",
        "sh",
        "-c",
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -A '
        '-c "SELECT id FROM platform_restart_check;"',
    ).stdout
    assert query.strip() == "42"
