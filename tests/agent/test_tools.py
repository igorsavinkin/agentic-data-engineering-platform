"""Tests for read-only SQL, dataset metadata, and pipeline status agent tools."""

from __future__ import annotations

from typing import Any

from services.agent.tools import (
    DatasetMetadataResult,
    PipelineAlert,
    PipelineRunSummary,
    PipelineStatusResult,
    SourceHealthSummary,
    SQLResult,
    TableMetadata,
    ToolResponse,
    _aggregate_lag,
    _compute_processing_rate,
    _derive_alerts,
    _derive_overall_pipeline_health,
    _last_successful_write,
    execute_read_only_sql,
    get_dataset_metadata,
    get_pipeline_status,
    validate_read_only,
)


class FakeDatabaseConnection:
    """Deterministic in-memory database connection for testing."""

    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        tables: list[str] | None = None,
        columns: list[dict[str, Any]] | None = None,
        row_count: int = 0,
        raise_on_execute: Exception | None = None,
    ) -> None:
        self._rows = rows or []
        self._tables = tables or []
        self._columns = columns or []
        self._row_count = row_count
        self._raise_on_execute = raise_on_execute
        self.last_query: str | None = None

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        if self._raise_on_execute:
            raise self._raise_on_execute
        self.last_query = query
        return self._rows

    def get_columns(self, schema: str, table: str) -> list[dict[str, Any]]:
        return self._columns

    def get_row_count(self, schema: str, table: str) -> int:
        return self._row_count

    def list_tables(self, schema: str) -> list[str]:
        return self._tables


# --- validate_read_only ---


class TestValidateReadOnly:
    def test_select_allowed(self) -> None:
        assert validate_read_only("SELECT 1") is None

    def test_select_lowercase_allowed(self) -> None:
        assert validate_read_only("select * from products") is None

    def test_with_cte_allowed(self) -> None:
        assert validate_read_only("WITH cte AS (SELECT 1) SELECT * FROM cte") is None

    def test_with_leading_whitespace(self) -> None:
        assert validate_read_only("  SELECT 1") is None

    def test_empty_query_rejected(self) -> None:
        assert validate_read_only("") == "Empty query"

    def test_whitespace_only_rejected(self) -> None:
        assert validate_read_only("   ") == "Empty query"

    def test_insert_rejected(self) -> None:
        result = validate_read_only("INSERT INTO t VALUES (1)")
        assert result is not None
        assert "SELECT" in result

    def test_update_rejected(self) -> None:
        result = validate_read_only("UPDATE t SET x = 1")
        assert result is not None
        assert "SELECT" in result

    def test_delete_rejected(self) -> None:
        result = validate_read_only("DELETE FROM t")
        assert result is not None
        assert "SELECT" in result

    def test_drop_rejected(self) -> None:
        result = validate_read_only("DROP TABLE t")
        assert result is not None
        assert "SELECT" in result

    def test_create_rejected(self) -> None:
        result = validate_read_only("CREATE TABLE t (id INT)")
        assert result is not None
        assert "SELECT" in result

    def test_alter_rejected(self) -> None:
        result = validate_read_only("ALTER TABLE t ADD COLUMN x INT")
        assert result is not None
        assert "SELECT" in result

    def test_truncate_rejected(self) -> None:
        result = validate_read_only("TRUNCATE TABLE t")
        assert result is not None
        assert "SELECT" in result

    def test_grant_rejected(self) -> None:
        result = validate_read_only("GRANT SELECT ON t TO user1")
        assert result is not None
        assert "SELECT" in result

    def test_revoke_rejected(self) -> None:
        result = validate_read_only("REVOKE SELECT ON t FROM user1")
        assert result is not None
        assert "SELECT" in result

    def test_exec_rejected(self) -> None:
        result = validate_read_only("EXEC sp_help")
        assert result is not None
        assert "SELECT" in result

    def test_execute_rejected(self) -> None:
        result = validate_read_only("EXECUTE sp_help")
        assert result is not None
        assert "SELECT" in result

    def test_merge_rejected(self) -> None:
        result = validate_read_only("MERGE INTO t USING s ON t.id = s.id")
        assert result is not None
        assert "SELECT" in result

    def test_non_select_start_rejected(self) -> None:
        result = validate_read_only("SHOW TABLES")
        assert result is not None
        assert "SELECT" in result

    def test_blocked_keyword_inside_select(self) -> None:
        result = validate_read_only("SELECT * FROM t WHERE name = 'DELETE'")
        assert result is not None
        assert "DELETE" in result

    def test_select_with_insert_keyword_in_string(self) -> None:
        result = validate_read_only("SELECT * FROM t WHERE action = 'INSERT'")
        assert result is not None
        assert "INSERT" in result

    def test_select_with_drop_keyword_in_string(self) -> None:
        result = validate_read_only("SELECT * FROM t WHERE type = 'DROP'")
        assert result is not None
        assert "DROP" in result

    def test_select_into_rejected(self) -> None:
        result = validate_read_only("SELECT * INTO new_table FROM products")
        assert result is not None
        assert "INTO" in result

    def test_side_effecting_function_rejected(self) -> None:
        result = validate_read_only("SELECT setval('seq', 1)")
        assert result is not None
        assert "SETVAL" in result

    def test_nextval_rejected(self) -> None:
        result = validate_read_only("SELECT nextval('my_seq')")
        assert result is not None
        assert "NEXTVAL" in result

    def test_lo_import_rejected(self) -> None:
        result = validate_read_only("SELECT lo_import('/etc/passwd')")
        assert result is not None
        assert "LO_IMPORT" in result

    def test_lo_export_rejected(self) -> None:
        result = validate_read_only("SELECT lo_export(12345, '/tmp/out')")
        assert result is not None
        assert "LO_EXPORT" in result

    def test_dblink_connect_rejected(self) -> None:
        result = validate_read_only("SELECT dblink_connect('host=evil.com')")
        assert result is not None
        assert "DBLINK_CONNECT" in result

    def test_multi_statement_rejected(self) -> None:
        result = validate_read_only("SELECT 1; SELECT 2")
        assert result is not None
        assert "Multiple" in result

    def test_trailing_semicolon_allowed(self) -> None:
        assert validate_read_only("SELECT 1;") is None


# --- execute_read_only_sql ---


class TestExecuteReadOnlySql:
    def test_successful_query(self) -> None:
        rows = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        db = FakeDatabaseConnection(rows=rows)
        response = execute_read_only_sql("SELECT id, name FROM users", db)

        assert response.success is True
        assert response.error is None
        assert response.data is not None
        result = SQLResult(**response.data)
        assert result.columns == ["id", "name"]
        assert result.row_count == 2
        assert result.rows == rows

    def test_empty_result(self) -> None:
        db = FakeDatabaseConnection(rows=[])
        response = execute_read_only_sql("SELECT 1 WHERE false", db)

        assert response.success is True
        result = SQLResult(**response.data)
        assert result.columns == []
        assert result.row_count == 0

    def test_validation_failure(self) -> None:
        db = FakeDatabaseConnection()
        response = execute_read_only_sql("DELETE FROM users", db)

        assert response.success is False
        assert response.data is None
        assert response.error is not None

    def test_database_error(self) -> None:
        db = FakeDatabaseConnection(raise_on_execute=RuntimeError("connection lost"))
        response = execute_read_only_sql("SELECT 1", db)

        assert response.success is False
        assert response.error is not None
        assert "connection lost" in response.error

    def test_query_passed_to_db(self) -> None:
        db = FakeDatabaseConnection(rows=[{"x": 1}])
        execute_read_only_sql("SELECT x FROM t", db)
        assert db.last_query == "SELECT x FROM t"


# --- get_dataset_metadata ---


class TestGetDatasetMetadata:
    def test_explicit_table_names(self) -> None:
        columns = [
            {"name": "id", "data_type": "integer", "is_nullable": False, "is_primary_key": True},
            {"name": "name", "data_type": "varchar", "is_nullable": True},
        ]
        db = FakeDatabaseConnection(columns=columns, row_count=42)

        response = get_dataset_metadata(db, schema="public", table_names=["products"])

        assert response.success is True
        result = DatasetMetadataResult(**response.data)
        assert len(result.tables) == 1
        table = result.tables[0]
        assert table.schema_name == "public"
        assert table.table_name == "products"
        assert table.row_count == 42
        assert len(table.columns) == 2
        assert table.columns[0].name == "id"
        assert table.columns[0].is_primary_key is True
        assert table.columns[1].is_nullable is True

    def test_auto_discover_tables(self) -> None:
        columns = [{"name": "id", "data_type": "integer", "is_nullable": False}]
        db = FakeDatabaseConnection(tables=["orders", "items"], columns=columns, row_count=10)

        response = get_dataset_metadata(db, schema="sales")

        assert response.success is True
        result = DatasetMetadataResult(**response.data)
        assert len(result.tables) == 2
        assert result.tables[0].table_name == "orders"
        assert result.tables[1].table_name == "items"

    def test_default_schema(self) -> None:
        db = FakeDatabaseConnection(tables=[], columns=[])
        response = get_dataset_metadata(db)

        assert response.success is True
        result = DatasetMetadataResult(**response.data)
        assert result.tables == []

    def test_column_defaults(self) -> None:
        columns = [{"name": "x", "data_type": "text"}]
        db = FakeDatabaseConnection(columns=columns, row_count=0)

        response = get_dataset_metadata(db, table_names=["t"])

        assert response.success is True
        result = DatasetMetadataResult(**response.data)
        col = result.tables[0].columns[0]
        assert col.is_nullable is True
        assert col.is_primary_key is False

    def test_database_error(self) -> None:
        db = FakeDatabaseConnection()
        db.list_tables = lambda schema: (_ for _ in ()).throw(RuntimeError("db down"))  # type: ignore[method-assign]

        response = get_dataset_metadata(db)

        assert response.success is False
        assert response.error is not None
        assert "db down" in response.error

    def test_multiple_tables(self) -> None:
        columns_a = [{"name": "id", "data_type": "integer", "is_nullable": False}]
        columns_b = [{"name": "name", "data_type": "varchar", "is_nullable": True}]

        class MultiFakeDb:
            def execute(self, query: str, params: Any = None) -> list[dict[str, Any]]:
                return []

            def get_columns(self, schema: str, table: str) -> list[dict[str, Any]]:
                if table == "a":
                    return columns_a
                return columns_b

            def get_row_count(self, schema: str, table: str) -> int:
                return 5 if table == "a" else 10

            def list_tables(self, schema: str) -> list[str]:
                return ["a", "b"]

        response = get_dataset_metadata(MultiFakeDb())

        assert response.success is True
        result = DatasetMetadataResult(**response.data)
        assert len(result.tables) == 2
        assert result.tables[0].columns[0].name == "id"
        assert result.tables[1].columns[0].name == "name"
        assert result.tables[0].row_count == 5
        assert result.tables[1].row_count == 10


# --- Model tests ---


class TestModels:
    def test_sql_result_serialization(self) -> None:
        result = SQLResult(columns=["a"], rows=[{"a": 1}], row_count=1)
        dumped = result.model_dump()
        assert dumped["columns"] == ["a"]
        assert dumped["row_count"] == 1

    def test_tool_response_error(self) -> None:
        resp = ToolResponse(success=False, error="boom")
        assert resp.data is None
        assert resp.error == "boom"

    def test_table_metadata_optional_row_count(self) -> None:
        table = TableMetadata(schema_name="s", table_name="t", columns=[])
        assert table.row_count is None


# --- Pipeline status tool tests (TASK-095) ---


class FakePipelineStatusProvider:
    """Deterministic in-memory pipeline status provider for testing."""

    def __init__(
        self,
        runs: list[dict[str, Any]] | None = None,
        total_runs: int = 0,
        sources: list[dict[str, Any]] | None = None,
        lag_samples: list[dict[str, Any]] | None = None,
        raise_on_runs: Exception | None = None,
    ) -> None:
        self._runs = runs if runs is not None else []
        self._total_runs = total_runs
        self._sources = sources if sources is not None else []
        self._lag_samples = lag_samples if lag_samples is not None else []
        self._raise_on_runs = raise_on_runs
        self.last_limit: int | None = None

    def list_recent_runs(self, limit: int = 5) -> list[dict[str, Any]]:
        if self._raise_on_runs:
            raise self._raise_on_runs
        self.last_limit = limit
        return self._runs

    def get_total_run_count(self) -> int:
        return self._total_runs

    def list_source_health(self) -> list[dict[str, Any]]:
        return self._sources

    def get_lag_samples(self) -> list[dict[str, Any]]:
        return self._lag_samples


class TestGetPipelineStatus:
    def test_healthy_pipeline(self) -> None:
        runs = [
            {
                "run_type": "ingestion",
                "overall_status": "healthy",
                "started_at": "2026-09-20T10:00:00",
                "finished_at": "2026-09-20T10:05:00",
                "records_loaded": 100,
                "error_message": None,
            }
        ]
        sources = [
            {
                "source_name": "fake_store",
                "overall_status": "healthy",
                "freshness_state": "fresh",
                "freshness_age_seconds": 60.0,
                "reasons": None,
            }
        ]
        provider = FakePipelineStatusProvider(runs=runs, total_runs=50, sources=sources)

        response = get_pipeline_status(provider)

        assert response.success is True
        assert response.error is None
        result = PipelineStatusResult(**response.data)
        assert result.overall_health == "healthy"
        assert result.total_runs == 50
        assert len(result.recent_runs) == 1
        assert result.recent_runs[0].run_type == "ingestion"
        assert result.recent_runs[0].records_loaded == 100
        assert len(result.source_health) == 1
        assert result.source_health[0].overall_status == "healthy"
        assert result.alerts == []

    def test_degraded_pipeline_with_failure(self) -> None:
        runs = [
            {
                "run_type": "ingestion",
                "overall_status": "failed",
                "started_at": "2026-09-20T10:00:00",
                "finished_at": None,
                "records_loaded": None,
                "error_message": "Kafka connection timeout",
            }
        ]
        provider = FakePipelineStatusProvider(runs=runs, total_runs=10)

        response = get_pipeline_status(provider)

        assert response.success is True
        result = PipelineStatusResult(**response.data)
        assert result.overall_health == "degraded"
        assert len(result.alerts) == 1
        alert = result.alerts[0]
        assert alert.alert_type == "pipeline_failure"
        assert alert.severity == "high"
        assert "Kafka connection timeout" in alert.message

    def test_degraded_source_alerts(self) -> None:
        runs = [
            {
                "run_type": "ingestion",
                "overall_status": "healthy",
                "started_at": "2026-09-20T10:00:00",
                "finished_at": "2026-09-20T10:05:00",
                "records_loaded": 50,
                "error_message": None,
            }
        ]
        sources = [
            {
                "source_name": "ebay",
                "overall_status": "degraded",
                "freshness_state": "stale",
                "freshness_age_seconds": 7200.0,
                "reasons": {"malformed_ratio": "0.3 exceeds threshold"},
            }
        ]
        provider = FakePipelineStatusProvider(runs=runs, total_runs=20, sources=sources)

        response = get_pipeline_status(provider)

        assert response.success is True
        result = PipelineStatusResult(**response.data)
        assert result.overall_health == "degraded"
        assert len(result.alerts) == 1
        assert result.alerts[0].alert_type == "source_degraded"
        assert result.alerts[0].source == "ebay"
        assert "0.3 exceeds threshold" in result.alerts[0].message

    def test_stale_source_alerts(self) -> None:
        runs = [
            {
                "run_type": "ingestion",
                "overall_status": "healthy",
                "started_at": "2026-09-20T10:00:00",
                "finished_at": "2026-09-20T10:05:00",
                "records_loaded": 50,
                "error_message": None,
            }
        ]
        sources = [
            {
                "source_name": "best_buy",
                "overall_status": "stale",
                "freshness_state": "stale",
                "freshness_age_seconds": 86400.0,
                "reasons": None,
            }
        ]
        provider = FakePipelineStatusProvider(runs=runs, total_runs=15, sources=sources)

        response = get_pipeline_status(provider)

        assert response.success is True
        result = PipelineStatusResult(**response.data)
        assert result.overall_health == "degraded"
        assert len(result.alerts) == 1
        assert result.alerts[0].alert_type == "source_stale"
        assert "86400" in result.alerts[0].message

    def test_empty_pipeline_unknown(self) -> None:
        provider = FakePipelineStatusProvider(runs=[], total_runs=0, sources=[])

        response = get_pipeline_status(provider)

        assert response.success is True
        result = PipelineStatusResult(**response.data)
        assert result.overall_health == "unknown"
        assert result.recent_runs == []
        assert result.source_health == []
        assert result.alerts == []

    def test_limit_passed_to_provider(self) -> None:
        provider = FakePipelineStatusProvider()
        get_pipeline_status(provider, limit=3)
        assert provider.last_limit == 3

    def test_provider_error(self) -> None:
        provider = FakePipelineStatusProvider(raise_on_runs=RuntimeError("db connection lost"))

        response = get_pipeline_status(provider)

        assert response.success is False
        assert response.error is not None
        assert "db connection lost" in response.error

    def test_multiple_alerts(self) -> None:
        runs = [
            {
                "run_type": "ingestion",
                "overall_status": "failed",
                "started_at": "2026-09-20T10:00:00",
                "finished_at": None,
                "records_loaded": None,
                "error_message": "timeout",
            },
            {
                "run_type": "warehouse",
                "overall_status": "healthy",
                "started_at": "2026-09-20T09:00:00",
                "finished_at": "2026-09-20T09:30:00",
                "records_loaded": 500,
                "error_message": None,
            },
        ]
        sources = [
            {
                "source_name": "fake_store",
                "overall_status": "degraded",
                "freshness_state": "fresh",
                "freshness_age_seconds": 30.0,
                "reasons": {"empty_fetches": "3 consecutive"},
            },
            {
                "source_name": "best_buy",
                "overall_status": "stale",
                "freshness_state": "stale",
                "freshness_age_seconds": 500.0,
                "reasons": None,
            },
        ]
        provider = FakePipelineStatusProvider(runs=runs, total_runs=30, sources=sources)

        response = get_pipeline_status(provider)

        result = PipelineStatusResult(**response.data)
        assert len(result.alerts) == 3
        alert_types = {a.alert_type for a in result.alerts}
        assert alert_types == {"pipeline_failure", "source_degraded", "source_stale"}


class TestDeriveOverallPipelineHealth:
    def test_healthy_with_successful_runs(self) -> None:
        runs = [{"overall_status": "healthy"}]
        sources = [{"overall_status": "healthy"}]
        assert _derive_overall_pipeline_health(runs, sources) == "healthy"

    def test_degraded_on_failed_run(self) -> None:
        runs = [{"overall_status": "failed"}]
        sources = [{"overall_status": "healthy"}]
        assert _derive_overall_pipeline_health(runs, sources) == "degraded"

    def test_degraded_on_degraded_source(self) -> None:
        runs = [{"overall_status": "healthy"}]
        sources = [{"overall_status": "degraded"}]
        assert _derive_overall_pipeline_health(runs, sources) == "degraded"

    def test_degraded_on_stale_source(self) -> None:
        runs = [{"overall_status": "healthy"}]
        sources = [{"overall_status": "stale"}]
        assert _derive_overall_pipeline_health(runs, sources) == "degraded"

    def test_unknown_when_no_runs(self) -> None:
        assert _derive_overall_pipeline_health([], []) == "unknown"


class TestDeriveAlerts:
    def test_no_alerts_when_healthy(self) -> None:
        runs = [{"overall_status": "healthy", "error_message": None}]
        sources = [{"overall_status": "healthy", "source_name": "x"}]
        assert _derive_alerts(runs, sources) == []

    def test_pipeline_failure_alert(self) -> None:
        runs = [
            {
                "overall_status": "failed",
                "error_message": "OOM",
                "run_type": "ingestion",
            }
        ]
        alerts = _derive_alerts(runs, [])
        assert len(alerts) == 1
        assert alerts[0].alert_type == "pipeline_failure"
        assert alerts[0].severity == "high"
        assert alerts[0].source == "ingestion"

    def test_source_degraded_alert_with_reasons(self) -> None:
        sources = [
            {
                "overall_status": "degraded",
                "source_name": "ebay",
                "reasons": {"key": "value"},
            }
        ]
        alerts = _derive_alerts([], sources)
        assert len(alerts) == 1
        assert alerts[0].alert_type == "source_degraded"
        assert alerts[0].severity == "medium"

    def test_source_stale_alert(self) -> None:
        sources = [
            {
                "overall_status": "stale",
                "source_name": "best_buy",
                "freshness_age_seconds": 3600.0,
            }
        ]
        alerts = _derive_alerts([], sources)
        assert len(alerts) == 1
        assert alerts[0].alert_type == "source_stale"
        assert "3600" in alerts[0].message

    def test_stale_source_unknown_age(self) -> None:
        sources = [
            {
                "overall_status": "stale",
                "source_name": "src",
                "freshness_age_seconds": None,
            }
        ]
        alerts = _derive_alerts([], sources)
        assert "unknown age" in alerts[0].message


class TestPipelineStatusModels:
    def test_pipeline_run_summary(self) -> None:
        run = PipelineRunSummary(
            run_type="ingestion",
            overall_status="healthy",
            started_at="2026-09-20T10:00:00",
        )
        assert run.finished_at is None
        assert run.records_loaded is None
        assert run.error_message is None

    def test_source_health_summary(self) -> None:
        src = SourceHealthSummary(
            source_name="fake_store",
            overall_status="healthy",
            freshness_state="fresh",
        )
        assert src.freshness_age_seconds is None
        assert src.reasons is None

    def test_pipeline_alert(self) -> None:
        alert = PipelineAlert(
            alert_type="pipeline_failure",
            severity="high",
            message="test",
        )
        assert alert.source is None

    def test_pipeline_status_result_serialization(self) -> None:
        result = PipelineStatusResult(
            overall_health="healthy",
            recent_runs=[
                PipelineRunSummary(
                    run_type="ingestion",
                    overall_status="healthy",
                    started_at="2026-09-20T10:00:00",
                    records_loaded=100,
                )
            ],
            total_runs=50,
            source_health=[
                SourceHealthSummary(
                    source_name="fake_store",
                    overall_status="healthy",
                    freshness_state="fresh",
                    freshness_age_seconds=60.0,
                )
            ],
            alerts=[],
        )
        dumped = result.model_dump()
        assert dumped["overall_health"] == "healthy"
        assert dumped["total_runs"] == 50
        assert len(dumped["recent_runs"]) == 1
        assert len(dumped["source_health"]) == 1


class TestConsumerLag:
    def test_lag_aggregated_by_topic(self) -> None:
        samples = [
            {"topic": "products.raw.v1", "partition": 0, "lag": 10},
            {"topic": "products.raw.v1", "partition": 1, "lag": 20},
            {"topic": "products.normalized.v1", "partition": 0, "lag": 5},
        ]
        result = _aggregate_lag(samples)
        assert result.total_lag == 35
        assert len(result.topics) == 2
        assert result.topics[0]["topic"] == "products.normalized.v1"
        assert result.topics[0]["lag"] == 5
        assert result.topics[1]["topic"] == "products.raw.v1"
        assert result.topics[1]["lag"] == 30

    def test_empty_lag(self) -> None:
        result = _aggregate_lag([])
        assert result.total_lag == 0
        assert result.topics == []

    def test_lag_in_pipeline_status(self) -> None:
        runs = [
            {
                "run_type": "ingestion",
                "overall_status": "healthy",
                "started_at": "2026-09-20T10:00:00",
                "finished_at": "2026-09-20T10:05:00",
                "records_loaded": 100,
                "error_message": None,
            }
        ]
        lag = [{"topic": "t1", "partition": 0, "lag": 42}]
        provider = FakePipelineStatusProvider(runs=runs, total_runs=10, lag_samples=lag)

        response = get_pipeline_status(provider)

        result = PipelineStatusResult(**response.data)
        assert result.consumer_lag.total_lag == 42
        assert len(result.consumer_lag.topics) == 1


class TestProcessingRate:
    def test_rate_from_completed_runs(self) -> None:
        runs = [
            {
                "started_at": "2026-09-20T10:00:00",
                "finished_at": "2026-09-20T10:05:00",
                "records_loaded": 300,
            }
        ]
        rate = _compute_processing_rate(runs)
        assert rate == 1.0

    def test_rate_none_when_no_completed_runs(self) -> None:
        runs = [{"started_at": "2026-09-20T10:00:00", "finished_at": None, "records_loaded": None}]
        assert _compute_processing_rate(runs) is None

    def test_rate_in_pipeline_status(self) -> None:
        runs = [
            {
                "run_type": "ingestion",
                "overall_status": "healthy",
                "started_at": "2026-09-20T10:00:00",
                "finished_at": "2026-09-20T10:02:00",
                "records_loaded": 600,
                "error_message": None,
            }
        ]
        provider = FakePipelineStatusProvider(runs=runs, total_runs=5)

        response = get_pipeline_status(provider)

        result = PipelineStatusResult(**response.data)
        assert result.processing_rate == 5.0


class TestLastSuccessfulWrite:
    def test_last_write_from_healthy_run(self) -> None:
        runs = [
            {"overall_status": "healthy", "finished_at": "2026-09-20T10:05:00"},
            {"overall_status": "failed", "finished_at": None},
        ]
        assert _last_successful_write(runs) == "2026-09-20T10:05:00"

    def test_last_write_none_when_no_success(self) -> None:
        runs = [{"overall_status": "failed", "finished_at": None}]
        assert _last_successful_write(runs) is None

    def test_last_write_in_pipeline_status(self) -> None:
        runs = [
            {
                "run_type": "ingestion",
                "overall_status": "healthy",
                "started_at": "2026-09-20T10:00:00",
                "finished_at": "2026-09-20T10:05:00",
                "records_loaded": 100,
                "error_message": None,
            }
        ]
        provider = FakePipelineStatusProvider(runs=runs, total_runs=10)

        response = get_pipeline_status(provider)

        result = PipelineStatusResult(**response.data)
        assert result.last_successful_write_at == "2026-09-20T10:05:00"
