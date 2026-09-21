"""Read-only SQL and dataset metadata agent tools (TASK-094).

Tools enforce read-only constraints at the query level: DDL, DML,
and any non-SELECT statements are rejected before execution.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from pydantic import BaseModel


class SQLResult(BaseModel):
    """Structured result from a read-only SQL query."""

    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int


class ToolResponse(BaseModel):
    """Generic tool response envelope."""

    success: bool
    data: Any = None
    error: str | None = None


class ColumnMetadata(BaseModel):
    """Metadata for a single database column."""

    name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool = False


class TableMetadata(BaseModel):
    """Metadata for a database table."""

    schema_name: str
    table_name: str
    columns: list[ColumnMetadata]
    row_count: int | None = None


class DatasetMetadataResult(BaseModel):
    """Result from a dataset metadata query."""

    tables: list[TableMetadata]


_BLOCKED_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE"
    r"|EXEC|EXECUTE|CALL|MERGE|REPLACE|LOAD|INTO)\b",
    re.IGNORECASE,
)

_SIDEEFFECT_FUNCTIONS = re.compile(
    r"\b(setval|nextval|currval|lo_from_bytea|lo_creat|lo_unlink"
    r"|dblink_exec|pg_notify|pg_terminate_backend|pg_cancel_backend"
    r"|set_config|pg_reload_conf)\b\s*\(",
    re.IGNORECASE,
)


class DatabaseConnection(Protocol):
    """Protocol for database connections used by agent tools."""

    def execute(
        self, query: str, params: tuple[Any, ...] | None = None
    ) -> list[dict[str, Any]]: ...
    def get_columns(self, schema: str, table: str) -> list[dict[str, Any]]: ...
    def get_row_count(self, schema: str, table: str) -> int: ...
    def list_tables(self, schema: str) -> list[str]: ...


def validate_read_only(query: str) -> str | None:
    """Validate that a SQL query is read-only.

    Returns None if the query is safe, or an error message if blocked.
    """
    stripped = query.strip()
    if not stripped:
        return "Empty query"

    if not stripped.upper().startswith("SELECT") and not stripped.upper().startswith("WITH"):
        return "Only SELECT and WITH (CTE) queries are allowed"

    if ";" in stripped.rstrip(";"):
        return "Multiple statements are not allowed"

    match = _BLOCKED_KEYWORDS.search(stripped)
    if match:
        return f"Blocked keyword found: {match.group(0).upper()}"

    side_effect = _SIDEEFFECT_FUNCTIONS.search(stripped)
    if side_effect:
        return f"Side-effecting function not allowed: {side_effect.group(1).upper()}"

    return None


def execute_read_only_sql(query: str, db: DatabaseConnection) -> ToolResponse:
    """Execute a read-only SQL query and return structured results."""
    error = validate_read_only(query)
    if error:
        return ToolResponse(success=False, error=error)

    try:
        rows = db.execute(query)
        columns = list(rows[0].keys()) if rows else []
        result = SQLResult(columns=columns, rows=rows, row_count=len(rows))
        return ToolResponse(success=True, data=result.model_dump())
    except Exception as e:
        return ToolResponse(success=False, error=str(e))


def get_dataset_metadata(
    db: DatabaseConnection,
    schema: str = "public",
    table_names: list[str] | None = None,
) -> ToolResponse:
    """Retrieve dataset metadata: table schemas, row counts, column info."""
    try:
        if table_names is None:
            table_names = db.list_tables(schema)

        tables: list[TableMetadata] = []
        for tname in table_names:
            raw_columns = db.get_columns(schema, tname)
            columns = [
                ColumnMetadata(
                    name=c["name"],
                    data_type=c["data_type"],
                    is_nullable=c.get("is_nullable", True),
                    is_primary_key=c.get("is_primary_key", False),
                )
                for c in raw_columns
            ]
            row_count = db.get_row_count(schema, tname)
            tables.append(
                TableMetadata(
                    schema_name=schema,
                    table_name=tname,
                    columns=columns,
                    row_count=row_count,
                )
            )

        result = DatasetMetadataResult(tables=tables)
        return ToolResponse(success=True, data=result.model_dump())
    except Exception as e:
        return ToolResponse(success=False, error=str(e))
