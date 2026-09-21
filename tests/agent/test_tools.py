"""Tests for read-only SQL and dataset metadata agent tools (TASK-094)."""

from __future__ import annotations

from typing import Any

from services.agent.tools import (
    DatasetMetadataResult,
    SQLResult,
    TableMetadata,
    ToolResponse,
    execute_read_only_sql,
    get_dataset_metadata,
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
