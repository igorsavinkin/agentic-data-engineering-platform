"""PostgreSQL failure engineering test (TASK-102).

Demonstrates the full failure lifecycle:

    Baseline -> Failure -> Detection (exception/log) -> Recovery -> No silent data loss

The PostgreSQL container is stopped (simulating a restart) to verify that:
- The warehouse loader raises a connection error (detection).
- The loader logs the failure (structured log assertion via caplog).
- After restart, the loader recovers and loads successfully.
- Re-loading the same data creates no duplicates (idempotent semantics).
- Committed data survives the restart intact.

Run with: pytest tests/warehouse/test_postgresql_failure.py -v -m integration
"""

# mypy: disable-error-code="import-untyped,no-untyped-def,import-not-found,no-any-return"
from __future__ import annotations

import logging
import os
import socket
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import polars as pl
import psycopg2
import pytest

from libs.common.minio_storage import MinIOStorage
from warehouse.loader.batch_loader import WarehouseLoader

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class ComposeContext:
    """Shared state for a single Docker Compose PostgreSQL lifecycle."""

    port: int
    env: dict[str, str]
    compose_cmd: list[str]


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.upper().startswith("APP_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("APP_ENVIRONMENT", "development")


@pytest.fixture
def compose_project() -> Iterator[ComposeContext]:
    """Start an isolated PostgreSQL container and yield its context.

    A single fixture owns the project name, env, port, and compose command
    so that stop/start always target the same container.
    """
    try:
        probe = subprocess.run(["docker", "info"], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("Docker daemon unavailable")
    if probe.returncode:
        pytest.skip("Docker daemon unavailable")

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    project = f"task102-test-{uuid4().hex[:10]}"
    env = os.environ.copy()
    env["COMPOSE_PROJECT_NAME"] = project
    env["PLATFORM_NETWORK_NAME"] = project
    env["POSTGRES_HOST_PORT"] = str(port)

    compose_file = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    compose_cmd = ["docker", "compose", "-f", str(compose_file)]

    try:
        result = subprocess.run(
            [*compose_cmd, "up", "-d", "--wait", "--wait-timeout", "120", "postgres"],
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
        assert result.returncode == 0, f"Failed to start PostgreSQL: {result.stderr}"
        _wait_for_postgres(port, timeout=30)
        yield ComposeContext(port=port, env=env, compose_cmd=compose_cmd)
    finally:
        subprocess.run(
            [*compose_cmd, "down", "--volumes", "--remove-orphans"],
            capture_output=True,
            check=True,
            timeout=60,
            env=env,
        )


def _wait_for_postgres(port: int, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            conn = psycopg2.connect(
                host="127.0.0.1",
                port=port,
                user="platform",
                password="platform-local",
                dbname="platform",
            )
            conn.close()
            return
        except psycopg2.OperationalError:
            time.sleep(0.5)
    raise TimeoutError(f"PostgreSQL did not become ready on port {port}")


def _stop_postgres(ctx: ComposeContext) -> None:
    subprocess.run(
        [*ctx.compose_cmd, "stop", "postgres"],
        capture_output=True,
        check=True,
        timeout=30,
        env=ctx.env,
    )


def _start_postgres(ctx: ComposeContext) -> None:
    subprocess.run(
        [*ctx.compose_cmd, "start", "postgres"],
        capture_output=True,
        check=True,
        timeout=120,
        env=ctx.env,
    )
    _wait_for_postgres(ctx.port, timeout=60)


@pytest.fixture
def test_db_url(compose_project: ComposeContext) -> Iterator[str]:
    port = compose_project.port
    admin_url = f"postgresql://platform:platform-local@127.0.0.1:{port}/postgres"
    db_name = f"warehouse_failure_test_{uuid4().hex[:8]}"

    conn = psycopg2.connect(admin_url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE {db_name}")
    cur.close()
    conn.close()

    test_url = f"postgresql://platform:platform-local@127.0.0.1:{port}/{db_name}"

    migrations_dir = Path(__file__).resolve().parents[2] / "warehouse" / "migrations"
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(migrations_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(migrations_dir))
    cfg.set_main_option("sqlalchemy.url", test_url)
    command.upgrade(cfg, "head")

    loader_url = test_url.replace("postgresql://", "postgresql+psycopg2://")
    yield loader_url

    _wait_for_postgres(port, timeout=30)
    conn = psycopg2.connect(admin_url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {db_name}")
    cur.close()
    conn.close()


@pytest.fixture
def loader(test_db_url: str) -> WarehouseLoader:
    mock_storage = MagicMock(spec=MinIOStorage)
    return WarehouseLoader(db_url=test_db_url, storage=mock_storage, batch_size=10)


@pytest.fixture
def query_url(test_db_url: str) -> str:
    return test_db_url.replace("postgresql+psycopg2://", "postgresql://")


def _make_parquet(tmp_path: Path, tag: str, count: int = 3) -> Path:
    event_ids = [f"evt-{tag}-{i}" for i in range(count)]
    df = pl.DataFrame(
        {
            "event_id": event_ids,
            "source": ["fake-store"] * count,
            "external_id": [f"prod-{tag}-{i}" for i in range(count)],
            "name": [f"Widget {tag}-{i}" for i in range(count)],
            "price": [f"{19.99 + i}" for i in range(count)],
            "currency": ["USD"] * count,
            "availability": ["in_stock"] * count,
            "category": ["widgets"] * count,
            "collected_at": [
                datetime(2026, 9, 1, 10 + i, tzinfo=timezone.utc) for i in range(count)
            ],
            "url": [f"https://example.com/{tag}/{i}" for i in range(count)],
        }
    )
    path = tmp_path / f"{tag}.parquet"
    df.write_parquet(path)
    return path


def _count_observations(query_url: str) -> int:
    conn = psycopg2.connect(query_url)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM product_observations")
        return cur.fetchone()[0]
    finally:
        conn.close()


def test_postgres_restart_no_duplicate_data(
    loader: WarehouseLoader,
    tmp_path: Path,
    query_url: str,
    compose_project: ComposeContext,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Full lifecycle: load -> stop -> fail -> restart -> idempotent reload."""
    batch1 = _make_parquet(tmp_path, "batch1", count=3)

    result1 = loader.load_from_parquet_files([batch1])
    assert result1.success
    assert result1.observations_created == 3
    assert _count_observations(query_url) == 3

    _stop_postgres(compose_project)

    batch2 = _make_parquet(tmp_path, "batch2", count=2)
    with caplog.at_level(logging.ERROR, logger="warehouse.loader.batch_loader"):
        with pytest.raises(psycopg2.OperationalError):
            loader.load_from_parquet_files([batch2])

    assert any(
        "batch_rolled_back" in record.message or "load_failed" in record.message
        for record in caplog.records
    ), "Loader must log the failure for detection"

    _start_postgres(compose_project)

    result2 = loader.load_from_parquet_files([batch2])
    assert result2.success
    assert result2.observations_created == 2

    result_replay = loader.load_from_parquet_files([batch1])
    assert result_replay.success
    assert result_replay.observations_created == 0

    total = _count_observations(query_url)
    assert total == 5, f"Expected 5 observations (3+2), got {total}"


def test_loader_connection_failure_detected(
    loader: WarehouseLoader,
    tmp_path: Path,
    compose_project: ComposeContext,
) -> None:
    """Stopping PostgreSQL causes the loader to raise OperationalError."""
    _stop_postgres(compose_project)

    batch = _make_parquet(tmp_path, "fail-detect", count=1)
    with pytest.raises(psycopg2.OperationalError):
        loader.load_from_parquet_files([batch])


def test_committed_data_survives_restart(
    loader: WarehouseLoader,
    tmp_path: Path,
    query_url: str,
    compose_project: ComposeContext,
) -> None:
    """Data committed before a restart is intact after recovery."""
    batch = _make_parquet(tmp_path, "survive", count=4)

    result = loader.load_from_parquet_files([batch])
    assert result.success
    assert result.observations_created == 4
    assert _count_observations(query_url) == 4

    _stop_postgres(compose_project)
    _start_postgres(compose_project)

    assert _count_observations(query_url) == 4

    conn = psycopg2.connect(query_url)
    try:
        cur = conn.cursor()
        cur.execute("SELECT event_id FROM product_observations ORDER BY event_id")
        event_ids = {row[0] for row in cur.fetchall()}
        expected = {f"evt-survive-{i}" for i in range(4)}
        assert event_ids == expected
        cur.close()
    finally:
        conn.close()


def test_idempotent_recovery_preserves_integrity(
    loader: WarehouseLoader,
    tmp_path: Path,
    query_url: str,
    compose_project: ComposeContext,
) -> None:
    """After failure and recovery, replaying loaded data creates no duplicates."""
    batch1 = _make_parquet(tmp_path, "integ-b1", count=2)
    batch2 = _make_parquet(tmp_path, "integ-b2", count=3)

    r1 = loader.load_from_parquet_files([batch1])
    assert r1.success
    assert r1.observations_created == 2

    _stop_postgres(compose_project)

    with pytest.raises(psycopg2.OperationalError):
        loader.load_from_parquet_files([batch2])

    _start_postgres(compose_project)

    r2 = loader.load_from_parquet_files([batch2])
    assert r2.success
    assert r2.observations_created == 3

    r1_replay = loader.load_from_parquet_files([batch1])
    assert r1_replay.observations_created == 0

    r2_replay = loader.load_from_parquet_files([batch2])
    assert r2_replay.observations_created == 0

    total = _count_observations(query_url)
    assert total == 5

    conn = psycopg2.connect(query_url)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sources WHERE name = 'fake-store'")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT COUNT(DISTINCT external_id) FROM source_products")
        assert cur.fetchone()[0] == 5
        cur.close()
    finally:
        conn.close()
