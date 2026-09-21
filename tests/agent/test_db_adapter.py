"""Tests for SQLAlchemyDatabaseConnection adapter.

Tests cover read-only enforcement (the security-critical behavior) and
basic query execution.  The ``list_tables``, ``get_columns``, and
``_primary_key_columns`` methods use PostgreSQL ``information_schema``
queries and require an integration test against a real PostgreSQL.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from services.agent.db_adapter import SQLAlchemyDatabaseConnection


@pytest.fixture()
def sqlite_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE products (  id INTEGER PRIMARY KEY,  name TEXT NOT NULL,  price REAL)"
            )
        )
        conn.execute(text("INSERT INTO products VALUES (1, 'Widget', 9.99)"))
        conn.execute(text("INSERT INTO products VALUES (2, 'Gadget', 19.99)"))
        conn.commit()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def conn(sqlite_session: Session) -> SQLAlchemyDatabaseConnection:
    return SQLAlchemyDatabaseConnection(sqlite_session)


class TestExecute:
    def test_select_returns_dicts(self, conn: SQLAlchemyDatabaseConnection) -> None:
        rows = conn.execute("SELECT id, name FROM products ORDER BY id")
        assert len(rows) == 2
        assert rows[0] == {"id": 1, "name": "Widget"}
        assert rows[1] == {"id": 2, "name": "Gadget"}

    def test_rejects_insert(self, conn: SQLAlchemyDatabaseConnection) -> None:
        with pytest.raises(ValueError, match="Read-only violation"):
            conn.execute("INSERT INTO products VALUES (3, 'Doohickey', 29.99)")

    def test_rejects_delete(self, conn: SQLAlchemyDatabaseConnection) -> None:
        with pytest.raises(ValueError, match="Read-only violation"):
            conn.execute("DELETE FROM products")

    def test_rejects_drop(self, conn: SQLAlchemyDatabaseConnection) -> None:
        with pytest.raises(ValueError, match="Read-only violation"):
            conn.execute("DROP TABLE products")

    def test_rejects_update(self, conn: SQLAlchemyDatabaseConnection) -> None:
        with pytest.raises(ValueError, match="Read-only violation"):
            conn.execute("UPDATE products SET price = 0")

    def test_rejects_empty_query(self, conn: SQLAlchemyDatabaseConnection) -> None:
        with pytest.raises(ValueError, match="Read-only violation"):
            conn.execute("")

    def test_rejects_multiple_statements(self, conn: SQLAlchemyDatabaseConnection) -> None:
        with pytest.raises(ValueError, match="Read-only violation"):
            conn.execute("SELECT 1; DROP TABLE products")

    def test_allows_cte(self, conn: SQLAlchemyDatabaseConnection) -> None:
        rows = conn.execute(
            "WITH expensive AS (SELECT * FROM products WHERE price > 10) SELECT * FROM expensive"
        )
        assert len(rows) == 1
        assert rows[0]["name"] == "Gadget"


class TestGetRowCount:
    def test_returns_count(self, conn: SQLAlchemyDatabaseConnection) -> None:
        count = conn.get_row_count("main", "products")
        assert count == 2
