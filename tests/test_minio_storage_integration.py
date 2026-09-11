"""Integration tests for MinIO object-storage client (TASK-020).

These tests exercise the real MinIO container from ``docker-compose.yml``
through the ``MinIOStorage`` client.  They start a dedicated Compose project
with alternate host ports so they never disturb a developer stack.

Run with::

    pytest -m integration tests/test_minio_storage_integration.py
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
from collections.abc import Iterator

import pytest

pytestmark = pytest.mark.integration

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPOSE_FILE = os.path.join(ROOT, "docker-compose.yml")

PROJECT = "ai-data-platform-minio-it"
# Alternate host ports so the test stack can run alongside a developer stack.
# Fixed credentials are local-only test fixtures, not real secrets.
STACK_ENV = {
    "KAFKA_HOST_PORT": "19092",
    "MINIO_HOST_PORT": "19000",
    "MINIO_CONSOLE_HOST_PORT": "19001",
    "POSTGRES_HOST_PORT": "15432",
    "PLATFORM_NETWORK_NAME": "ai-data-platform-it",
    "MINIO_ROOT_USER": "it-admin",
    "MINIO_ROOT_PASSWORD": "it-admin-secret",
}
MINIO_PORT = int(STACK_ENV["MINIO_HOST_PORT"])
MINIO_ENDPOINT = f"http://127.0.0.1:{MINIO_PORT}"
MINIO_ACCESS_KEY = STACK_ENV["MINIO_ROOT_USER"]
MINIO_SECRET_KEY = STACK_ENV["MINIO_ROOT_PASSWORD"]


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
        ["docker", "compose", "-f", COMPOSE_FILE, "-p", PROJECT, *args],
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


def _wait_for_minio(timeout: float = 30.0) -> None:
    """Block until the MinIO API port accepts connections."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", MINIO_PORT), timeout=2):
                return
        except OSError:
            time.sleep(0.5)
    pytest.fail(f"MinIO did not become reachable on port {MINIO_PORT}")


@pytest.fixture(scope="module")
def stack() -> Iterator[None]:
    if not _docker_available():
        pytest.skip("Docker daemon not available")
    _compose("down", "--volumes", "--remove-orphans", check=False)
    _compose("up", "-d", "--wait", "minio")
    _wait_for_minio()
    yield
    _compose("down", "--volumes", "--remove-orphans", check=False)


@pytest.fixture()
def storage(stack: None) -> Iterator:
    from libs.common.minio_storage import MinIOSettings, MinIOStorage

    settings = MinIOSettings(
        app_environment="development",
        minio_endpoint=MINIO_ENDPOINT,
        minio_access_key=MINIO_ACCESS_KEY,
        minio_secret_key=MINIO_SECRET_KEY,
        minio_bucket_bronze="it-bronze",
        minio_bucket_silver="it-silver",
    )
    client = MinIOStorage(settings)
    client.ensure_all_buckets()
    yield client
    client.close()


def test_health_check_passes(storage: object) -> None:
    from libs.common.minio_storage import MinIOStorage

    client: MinIOStorage = storage  # type: ignore[assignment]
    status = client.check_health()
    assert status.healthy
    assert status.detail == "ok"


def test_ensure_bucket_is_idempotent(storage: object) -> None:
    from libs.common.minio_storage import MinIOStorage

    client: MinIOStorage = storage  # type: ignore[assignment]
    client.ensure_bucket("it-bronze")
    client.ensure_bucket("it-bronze")
    client.ensure_all_buckets()


def test_put_get_round_trip(storage: object) -> None:
    from libs.common.minio_storage import MinIOStorage

    client: MinIOStorage = storage  # type: ignore[assignment]
    payload = json.dumps({"source": "integration-test", "value": 42}).encode()
    key = "integration/round-trip/test.json"

    client.put_object("it-bronze", key, payload)
    assert client.object_exists("it-bronze", key)

    fetched = client.get_object("it-bronze", key)
    assert fetched == payload


def test_get_missing_object_raises_key_error(storage: object) -> None:
    from libs.common.minio_storage import MinIOStorage

    client: MinIOStorage = storage  # type: ignore[assignment]
    with pytest.raises(KeyError, match="Object not found"):
        client.get_object("it-bronze", "does-not-exist-key")


def test_object_exists_returns_false_for_missing(storage: object) -> None:
    from libs.common.minio_storage import MinIOStorage

    client: MinIOStorage = storage  # type: ignore[assignment]
    assert not client.object_exists("it-bronze", "no-such-object-key")


def test_overwrite_replaces_content(storage: object) -> None:
    from libs.common.minio_storage import MinIOStorage

    client: MinIOStorage = storage  # type: ignore[assignment]
    key = "integration/overwrite/test.bin"
    client.put_object("it-bronze", key, b"version-1")
    client.put_object("it-bronze", key, b"version-2")
    assert client.get_object("it-bronze", key) == b"version-2"
