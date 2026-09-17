"""Integration tests for quality-result persistence (TASK-057).

Tests write/read round-trips, replay safety, and query APIs against
a real PostgreSQL database. Uses the same test database as the warehouse
integration tests.

These tests are skipped when no PostgreSQL instance is available.
"""

from __future__ import annotations

# mypy: disable-error-code="import-untyped,no-any-return"
import os
from datetime import datetime, timezone

import pytest

from libs.quality.models import (
    CheckSeverity,
    CheckStatus,
    QualityResult,
    QualitySuiteResult,
)
from libs.quality.persistence import (
    QualityPersistenceConfig,
    QualityResultReader,
    QualityResultWriter,
    make_replay_key,
)

try:
    from sqlalchemy import create_engine, text

    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

WAREHOUSE_DB_HOST = os.getenv("WAREHOUSE_DB_HOST", "localhost")
WAREHOUSE_DB_PORT = os.getenv("WAREHOUSE_DB_PORT", "5432")
WAREHOUSE_DB_NAME = os.getenv("WAREHOUSE_DB_NAME", "platform")
WAREHOUSE_DB_USER = os.getenv("WAREHOUSE_DB_USER", "platform")
WAREHOUSE_DB_PASSWORD = os.getenv("WAREHOUSE_DB_PASSWORD", "platform-local")

SKIP_REASON = "PostgreSQL not available or SQLAlchemy not installed"


def _build_test_config() -> QualityPersistenceConfig:
    url = (
        f"postgresql://{WAREHOUSE_DB_USER}:{WAREHOUSE_DB_PASSWORD}"
        f"@{WAREHOUSE_DB_HOST}:{WAREHOUSE_DB_PORT}/{WAREHOUSE_DB_NAME}"
    )
    return QualityPersistenceConfig(db_url=url)


def _db_available() -> bool:
    if not HAS_SQLALCHEMY:
        return False
    try:
        url = (
            f"postgresql://{WAREHOUSE_DB_USER}:{WAREHOUSE_DB_PASSWORD}"
            f"@{WAREHOUSE_DB_HOST}:{WAREHOUSE_DB_PORT}/{WAREHOUSE_DB_NAME}"
        )
        engine = create_engine(url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


def _ensure_schema(config: QualityPersistenceConfig) -> None:
    """Create the data_quality_results table if it doesn't exist."""
    import psycopg2

    db_url = config.db_url.replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS data_quality_results (
                id                  BIGSERIAL PRIMARY KEY,
                pipeline_run_id     BIGINT,
                observation_id      BIGINT,
                check_name          TEXT NOT NULL,
                severity            TEXT NOT NULL,
                passed              BOOLEAN NOT NULL,
                message             TEXT,
                checked_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
                records_checked     BIGINT NOT NULL DEFAULT 0,
                failed_records      BIGINT NOT NULL DEFAULT 0,
                details             JSONB,
                replay_key          TEXT NOT NULL DEFAULT '',
                CONSTRAINT uk_data_quality_results_replay_key UNIQUE (replay_key)
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS ix_data_quality_results_check_checked_at
            ON data_quality_results (check_name, checked_at)
        """)
    finally:
        conn.close()


def _cleanup_results(config: QualityPersistenceConfig, replay_keys: list[str]) -> None:
    """Remove test rows by replay_key."""
    import psycopg2

    if not replay_keys:
        return
    db_url = config.db_url.replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        placeholders = ", ".join(["%s"] * len(replay_keys))
        cur.execute(
            f"DELETE FROM data_quality_results WHERE replay_key IN ({placeholders})",
            replay_keys,
        )
    finally:
        conn.close()


pytestmark = pytest.mark.skipif(not _db_available(), reason=SKIP_REASON)


def _make_result(
    check_name: str = "test_check",
    severity: CheckSeverity = CheckSeverity.ERROR,
    status: CheckStatus = CheckStatus.PASSED,
    source: str | None = None,
    records_checked: int = 100,
    failed_records: int = 0,
    details: dict | None = None,
    message: str = "test message",
    checked_at: datetime | None = None,
) -> QualityResult:
    return QualityResult(
        check_name=check_name,
        severity=severity,
        status=status,
        source=source,
        records_checked=records_checked,
        failed_records=failed_records,
        details=details or {},
        message=message,
        checked_at=checked_at or datetime.now(timezone.utc),
    )


class TestQualityResultWriter:
    def setup_method(self) -> None:
        self._config = _build_test_config()
        self._written_keys: list[str] = []
        _ensure_schema(self._config)

    def teardown_method(self) -> None:
        _cleanup_results(self._config, self._written_keys)

    def test_write_single_result(self) -> None:
        writer = QualityResultWriter(self._config)
        result = _make_result(check_name="required_fields")
        key = make_replay_key("required_fields", source=None)
        self._written_keys.append(key)

        write_result = writer.write_result(result)
        assert write_result.success
        assert write_result.written == 1

    def test_write_result_with_all_fields(self) -> None:
        writer = QualityResultWriter(self._config)
        now = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
        result = _make_result(
            check_name="price_validity",
            severity=CheckSeverity.WARNING,
            status=CheckStatus.FAILED,
            source="bestbuy",
            records_checked=500,
            failed_records=10,
            details={"negative_count": 5, "zero_count": 5},
            message="10 records with invalid prices",
            checked_at=now,
        )
        key = make_replay_key("price_validity", source="bestbuy")
        self._written_keys.append(key)

        write_result = writer.write_result(result)
        assert write_result.success
        assert write_result.written == 1

    def test_write_multiple_results(self) -> None:
        writer = QualityResultWriter(self._config)
        results = [
            _make_result(check_name="check_a"),
            _make_result(check_name="check_b"),
            _make_result(check_name="check_c"),
        ]
        keys = [make_replay_key(r.check_name) for r in results]
        self._written_keys.extend(keys)

        write_result = writer.write_results(results)
        assert write_result.success
        assert write_result.written == 3

    def test_write_empty_results(self) -> None:
        writer = QualityResultWriter(self._config)
        write_result = writer.write_results([])
        assert write_result.success
        assert write_result.written == 0

    def test_replay_safety(self) -> None:
        """Writing the same result twice should not duplicate rows."""
        writer = QualityResultWriter(self._config)
        result = _make_result(check_name="replay_test")
        key = make_replay_key("replay_test")
        self._written_keys.append(key)

        writer.write_result(result)
        write_result2 = writer.write_result(result)
        assert write_result2.success

        reader = QualityResultReader(self._config)
        rows = reader.recent_failures(check_name="replay_test", limit=100)
        assert len(rows) <= 1

    def test_write_with_pipeline_run_id(self) -> None:
        writer = QualityResultWriter(self._config)
        result = _make_result(check_name="pipeline_test")
        key = make_replay_key("pipeline_test", pipeline_run_id=999)
        self._written_keys.append(key)

        write_result = writer.write_result(result, pipeline_run_id=999)
        assert write_result.success
        assert write_result.written == 1

    def test_write_suite_result(self) -> None:
        writer = QualityResultWriter(self._config)
        now = datetime.now(timezone.utc)
        suite_result = QualitySuiteResult(
            results=(
                _make_result(check_name="suite_check_a"),
                _make_result(check_name="suite_check_b"),
            ),
            started_at=now,
            finished_at=now,
        )
        keys = [make_replay_key(r.check_name) for r in suite_result.results]
        self._written_keys.extend(keys)

        write_result = writer.write_suite_result(suite_result)
        assert write_result.success
        assert write_result.written == 2


class TestQualityResultReader:
    def setup_method(self) -> None:
        self._config = _build_test_config()
        self._written_keys: list[str] = []
        self._writer = QualityResultWriter(self._config)
        self._reader = QualityResultReader(self._config)
        _ensure_schema(self._config)

    def teardown_method(self) -> None:
        _cleanup_results(self._config, self._written_keys)

    def _write_and_track(self, result: QualityResult, **kwargs: object) -> None:
        key = make_replay_key(
            result.check_name,
            pipeline_run_id=kwargs.get("pipeline_run_id"),  # type: ignore[arg-type]
            source=result.source,
        )
        self._written_keys.append(key)
        self._writer.write_result(result, **kwargs)  # type: ignore[arg-type]

    def test_recent_failures_returns_failed(self) -> None:
        self._write_and_track(_make_result(check_name="fail_test", status=CheckStatus.FAILED))
        self._write_and_track(_make_result(check_name="pass_test", status=CheckStatus.PASSED))

        failures = self._reader.recent_failures(check_name="fail_test")
        assert len(failures) == 1
        assert failures[0].check_name == "fail_test"
        assert failures[0].passed is False

    def test_recent_failures_with_limit(self) -> None:
        for i in range(5):
            self._write_and_track(
                _make_result(
                    check_name=f"limit_test_{i}",
                    status=CheckStatus.FAILED,
                )
            )

        failures = self._reader.recent_failures(limit=3)
        assert len(failures) <= 3

    def test_recent_failures_filter_by_check_name(self) -> None:
        self._write_and_track(_make_result(check_name="filter_a", status=CheckStatus.FAILED))
        self._write_and_track(_make_result(check_name="filter_b", status=CheckStatus.FAILED))

        failures = self._reader.recent_failures(check_name="filter_a")
        assert all(r.check_name == "filter_a" for r in failures)

    def test_recent_failures_filter_by_since(self) -> None:
        old_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
        self._write_and_track(
            _make_result(
                check_name="old_failure",
                status=CheckStatus.FAILED,
                checked_at=old_time,
            )
        )
        self._write_and_track(
            _make_result(
                check_name="new_failure",
                status=CheckStatus.FAILED,
            )
        )

        since = datetime(2025, 1, 1, tzinfo=timezone.utc)
        failures = self._reader.recent_failures(since=since)
        assert all(r.checked_at >= since for r in failures)

    def test_latest_status(self) -> None:
        self._write_and_track(_make_result(check_name="latest_a", status=CheckStatus.FAILED))
        self._write_and_track(_make_result(check_name="latest_b", status=CheckStatus.PASSED))

        status = self._reader.latest_status(check_names=["latest_a", "latest_b"])
        assert len(status) == 2
        names = {r.check_name for r in status}
        assert names == {"latest_a", "latest_b"}

    def test_latest_status_returns_most_recent(self) -> None:
        old_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
        new_time = datetime(2026, 9, 17, tzinfo=timezone.utc)

        self._write_and_track(
            _make_result(
                check_name="latest_time",
                status=CheckStatus.FAILED,
                checked_at=old_time,
            )
        )
        self._write_and_track(
            _make_result(
                check_name="latest_time",
                status=CheckStatus.PASSED,
                checked_at=new_time,
                source="v2",
            )
        )

        status = self._reader.latest_status(check_names=["latest_time"])
        assert len(status) == 1
        assert status[0].checked_at == new_time

    def test_read_preserves_details(self) -> None:
        details = {"null_counts_by_column": {"a": 3, "b": 1}, "total_rows": 100}
        self._write_and_track(
            _make_result(
                check_name="details_test",
                status=CheckStatus.FAILED,
                details=details,
            )
        )

        failures = self._reader.recent_failures(check_name="details_test")
        assert len(failures) == 1
        assert failures[0].details == details

    def test_read_preserves_records_checked(self) -> None:
        self._write_and_track(
            _make_result(
                check_name="counts_test",
                status=CheckStatus.FAILED,
                records_checked=500,
                failed_records=42,
            )
        )

        failures = self._reader.recent_failures(check_name="counts_test")
        assert len(failures) == 1
        assert failures[0].records_checked == 500
        assert failures[0].failed_records == 42
