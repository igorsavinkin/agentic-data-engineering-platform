"""Concrete DatabaseConnection adapter backed by a SQLAlchemy session.

Implements the agent tool ``DatabaseConnection`` protocol using the
API session.  Read-only is enforced at two layers:

1. **Query level** — every call to :meth:`execute` passes through
   ``validate_read_only`` which rejects any write statement.
2. **Connection level** — for PostgreSQL sessions, ``SET TRANSACTION
   READ ONLY`` is issued at construction time so the database itself
   rejects writes within the request transaction.

Production deployments should additionally use a dedicated read-only
PostgreSQL role for the agent's database connection.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.agent.tools import validate_read_only


class SQLAlchemyDatabaseConnection:
    """Adapter from SQLAlchemy ``Session`` to the agent ``DatabaseConnection`` protocol.

    Read-only is enforced at the query level (``validate_read_only`` in
    ``execute``) and, for PostgreSQL, at the connection level via
    ``SET TRANSACTION READ ONLY`` issued during construction.
    """

    def __init__(self, session: Session, schema: str = "public") -> None:
        self._session = session
        self._schema = schema
        self._enforce_connection_read_only()

    def _enforce_connection_read_only(self) -> None:
        """Set the current transaction to read-only (PostgreSQL only).

        This is defense-in-depth; the primary enforcement is the
        ``validate_read_only`` guard in ``execute``.  Production should
        use a read-only PostgreSQL role for full connection-level safety.
        """
        try:
            dialect = self._session.bind.dialect.name if self._session.bind else ""
        except Exception:
            return
        if dialect == "postgresql":
            self._session.execute(text("SET TRANSACTION READ ONLY"))

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        error = validate_read_only(query)
        if error:
            raise ValueError(f"Read-only violation: {error}")
        result = self._session.execute(text(query))
        columns = list(result.keys())
        return [dict(zip(columns, row)) for row in result.fetchall()]

    def get_columns(self, schema: str, table: str) -> list[dict[str, Any]]:
        query = text(
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table "
            "ORDER BY ordinal_position"
        )
        rows = self._session.execute(query, {"schema": schema, "table": table}).fetchall()
        pk_cols = self._primary_key_columns(schema, table)
        return [
            {
                "name": row[0],
                "data_type": row[1],
                "is_nullable": row[2] == "YES",
                "is_primary_key": row[0] in pk_cols,
            }
            for row in rows
        ]

    def get_row_count(self, schema: str, table: str) -> int:
        safe_schema = schema.replace('"', "")
        safe_table = table.replace('"', "")
        query = text(f'SELECT COUNT(*) FROM "{safe_schema}"."{safe_table}"')
        return self._session.execute(query).scalar() or 0

    def list_tables(self, schema: str) -> list[str]:
        query = text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = :schema ORDER BY table_name"
        )
        rows = self._session.execute(query, {"schema": schema}).fetchall()
        return [row[0] for row in rows]

    def _primary_key_columns(self, schema: str, table: str) -> set[str]:
        query = text(
            "SELECT kcu.column_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name "
            "  AND tc.table_schema = kcu.table_schema "
            "WHERE tc.constraint_type = 'PRIMARY KEY' "
            "  AND tc.table_schema = :schema AND tc.table_name = :table"
        )
        rows = self._session.execute(query, {"schema": schema, "table": table}).fetchall()
        return {row[0] for row in rows}
