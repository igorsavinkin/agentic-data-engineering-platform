"""Tests for PostgreSQL warehouse schema (TASK-027).

These tests verify that the schema can be created, constraints exist,
FK behavior works correctly, and data types are appropriate.

Prerequisites:
- PostgreSQL must be running locally (Docker Compose or native)
- Database 'warehouse_test' must exist
- User must have CREATE/DROP privileges on the test database

Run with:
    python -m pytest tests/warehouse/test_postgresql_schema.py -v -m integration
"""

import os
from pathlib import Path

import psycopg2
import pytest

# Mark all tests in this module as integration tests (require PostgreSQL)
pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db_connection():
    """Create a connection to the test database."""
    conn = psycopg2.connect(
        host=os.getenv("WAREHOUSE_DB_HOST", "localhost"),
        port=int(os.getenv("WAREHOUSE_DB_PORT", "5432")),
        dbname=os.getenv("WAREHOUSE_DB_NAME", "warehouse_test"),
        user=os.getenv("WAREHOUSE_DB_USER", "postgres"),
        password=os.getenv("WAREHOUSE_DB_PASSWORD", "postgres"),
    )
    conn.autocommit = True
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def schema_sql():
    """Read the schema SQL file."""
    schema_path = Path(__file__).parent.parent.parent / "warehouse" / "schema" / "init.sql"
    return schema_path.read_text()


@pytest.fixture(autouse=True)
def clean_schema(db_connection, schema_sql):
    """Drop all tables before each test and recreate from scratch."""
    cur = db_connection.cursor()

    # Drop tables in reverse dependency order
    cur.execute("DROP TABLE IF EXISTS data_quality_results CASCADE")
    cur.execute("DROP TABLE IF EXISTS pipeline_runs CASCADE")
    cur.execute("DROP TABLE IF EXISTS product_observations CASCADE")
    cur.execute("DROP TABLE IF EXISTS source_products CASCADE")
    cur.execute("DROP TABLE IF EXISTS products CASCADE")
    cur.execute("DROP TABLE IF EXISTS sources CASCADE")

    # Recreate schema
    cur.execute(schema_sql)
    cur.close()

    yield


# ---------------------------------------------------------------------------
# Test: Schema can be created
# ---------------------------------------------------------------------------


def test_schema_can_be_created(db_connection):
    """Verify that the schema SQL executes without errors."""
    cur = db_connection.cursor()

    # If we got here via the fixture, schema was already created successfully.
    # Verify tables exist by querying information_schema.
    cur.execute(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """
    )
    tables = {row[0] for row in cur.fetchall()}
    expected_tables = {
        "sources",
        "products",
        "source_products",
        "product_observations",
        "pipeline_runs",
        "data_quality_results",
    }
    assert tables == expected_tables, f"Expected tables {expected_tables}, got {tables}"
    cur.close()


# ---------------------------------------------------------------------------
# Test: Required constraints exist
# ---------------------------------------------------------------------------


def test_primary_keys_exist(db_connection):
    """Verify that all tables have primary keys."""
    cur = db_connection.cursor()

    cur.execute(
        """
        SELECT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
        WHERE tc.constraint_type = 'PRIMARY KEY'
        AND tc.table_schema = 'public'
        ORDER BY tc.table_name
        """
    )
    pk_columns = {row[0]: row[1] for row in cur.fetchall()}

    assert pk_columns.get("sources") == "id"
    assert pk_columns.get("products") == "id"
    assert pk_columns.get("source_products") == "id"
    assert pk_columns.get("product_observations") == "id"
    assert pk_columns.get("pipeline_runs") == "id"
    assert pk_columns.get("data_quality_results") == "id"

    cur.close()


def test_unique_constraints_exist(db_connection):
    """Verify unique constraints on sources.name and source_products(source_id, external_id)."""
    cur = db_connection.cursor()

    # Check sources.name uniqueness
    cur.execute(
        """
        SELECT constraint_name FROM information_schema.table_constraints
        WHERE constraint_type = 'UNIQUE'
        AND table_name = 'sources'
        AND table_schema = 'public'
        """
    )
    source_unique = cur.fetchall()
    assert len(source_unique) > 0, "sources table should have a UNIQUE constraint on name"

    # Check source_products composite uniqueness
    cur.execute(
        """
        SELECT constraint_name FROM information_schema.table_constraints
        WHERE constraint_type = 'UNIQUE'
        AND table_name = 'source_products'
        AND table_schema = 'public'
        """
    )
    sp_unique = cur.fetchall()
    assert len(sp_unique) > 0, "source_products should have a UNIQUE constraint"

    cur.close()


def test_check_constraints_exist(db_connection):
    """Verify CHECK constraints on product_observations.price."""
    cur = db_connection.cursor()

    cur.execute(
        """
        SELECT cc.constraint_name, cc.check_clause
        FROM information_schema.check_constraints cc
        JOIN information_schema.table_constraints tc
            ON cc.constraint_name = tc.constraint_name
        WHERE tc.table_name = 'product_observations'
        AND tc.table_schema = 'public'
        """
    )
    checks = cur.fetchall()
    assert len(checks) > 0, "product_observations should have CHECK constraints"

    # Verify price non-negative check exists
    check_clauses = [c[1] for c in checks]
    has_price_check = any("price" in clause.lower() for clause in check_clauses)
    assert has_price_check, "Should have a CHECK constraint on price"

    cur.close()


# ---------------------------------------------------------------------------
# Test: FK behavior
# ---------------------------------------------------------------------------


def test_fk_sources_to_source_products(db_connection):
    """Verify FK from source_products.source_id to sources.id prevents orphan rows."""
    cur = db_connection.cursor()

    # Insert a valid source
    cur.execute("INSERT INTO sources (name) VALUES ('test_source') RETURNING id")
    source_id = cur.fetchone()[0]

    # Insert a product
    cur.execute("INSERT INTO products (canonical_name) VALUES ('Test Product') RETURNING id")
    product_id = cur.fetchone()[0]

    # This should succeed (valid FK)
    cur.execute(
        "INSERT INTO source_products (source_id, product_id, external_id) VALUES (%s, %s, 'ext-001')",
        (source_id, product_id),
    )

    # Try to insert with invalid source_id — should fail
    with pytest.raises(psycopg2.errors.ForeignKeyViolation):
        cur.execute(
            "INSERT INTO source_products (source_id, product_id, external_id) VALUES (99999, %s, 'ext-002')",
            (product_id,),
        )

    cur.close()


def test_fk_cascade_delete_products(db_connection):
    """Verify that deleting a product cascades to source_products."""
    cur = db_connection.cursor()

    # Create source and product
    cur.execute("INSERT INTO sources (name) VALUES ('test_source') RETURNING id")
    source_id = cur.fetchone()[0]

    cur.execute("INSERT INTO products (canonical_name) VALUES ('Test Product') RETURNING id")
    product_id = cur.fetchone()[0]

    # Create source_product mapping
    cur.execute(
        "INSERT INTO source_products (source_id, product_id, external_id) VALUES (%s, %s, 'ext-001')",
        (source_id, product_id),
    )

    # Delete the product — should cascade to source_products
    cur.execute("DELETE FROM products WHERE id = %s", (product_id,))

    # Verify source_products row is gone
    cur.execute("SELECT COUNT(*) FROM source_products WHERE product_id = %s", (product_id,))
    count = cur.fetchone()[0]
    assert count == 0, "source_products row should be deleted when product is deleted"

    cur.close()


def test_fk_restrict_delete_sources(db_connection):
    """Verify that deleting a source with existing source_products fails."""
    cur = db_connection.cursor()

    # Create source and product
    cur.execute("INSERT INTO sources (name) VALUES ('test_source') RETURNING id")
    source_id = cur.fetchone()[0]

    cur.execute("INSERT INTO products (canonical_name) VALUES ('Test Product') RETURNING id")
    product_id = cur.fetchone()[0]

    # Create source_product mapping
    cur.execute(
        "INSERT INTO source_products (source_id, product_id, external_id) VALUES (%s, %s, 'ext-001')",
        (source_id, product_id),
    )

    # Try to delete the source — should fail due to RESTRICT
    with pytest.raises(psycopg2.errors.ForeignKeyViolation):
        cur.execute("DELETE FROM sources WHERE id = %s", (source_id,))

    cur.close()


# ---------------------------------------------------------------------------
# Test: Duplicate logical keys rejected
# ---------------------------------------------------------------------------


def test_duplicate_source_external_id_rejected(db_connection):
    """Verify that duplicate (source_id, external_id) pairs are rejected."""
    cur = db_connection.cursor()

    # Create source and product
    cur.execute("INSERT INTO sources (name) VALUES ('test_source') RETURNING id")
    source_id = cur.fetchone()[0]

    cur.execute("INSERT INTO products (canonical_name) VALUES ('Test Product') RETURNING id")
    product_id = cur.fetchone()[0]

    # First insert should succeed
    cur.execute(
        "INSERT INTO source_products (source_id, product_id, external_id) VALUES (%s, %s, 'ext-001')",
        (source_id, product_id),
    )

    # Second insert with same (source_id, external_id) should fail
    with pytest.raises(psycopg2.errors.UniqueViolation):
        cur.execute(
            "INSERT INTO source_products (source_id, product_id, external_id) VALUES (%s, %s, 'ext-001')",
            (source_id, product_id),
        )

    cur.close()


def test_duplicate_source_name_rejected(db_connection):
    """Verify that duplicate source names are rejected."""
    cur = db_connection.cursor()

    # First insert should succeed
    cur.execute("INSERT INTO sources (name) VALUES ('bestbuy')")

    # Second insert with same name should fail
    with pytest.raises(psycopg2.errors.UniqueViolation):
        cur.execute("INSERT INTO sources (name) VALUES ('bestbuy')")

    cur.close()


# ---------------------------------------------------------------------------
# Test: Multiple historical observations allowed
# ---------------------------------------------------------------------------


def test_multiple_observations_per_source_product(db_connection):
    """Verify that multiple observations can exist for one source_product."""
    cur = db_connection.cursor()

    # Create source, product, and source_product
    cur.execute("INSERT INTO sources (name) VALUES ('test_source') RETURNING id")
    source_id = cur.fetchone()[0]

    cur.execute("INSERT INTO products (canonical_name) VALUES ('Test Product') RETURNING id")
    product_id = cur.fetchone()[0]

    cur.execute(
        "INSERT INTO source_products (source_id, product_id, external_id) VALUES (%s, %s, 'ext-001') RETURNING id",
        (source_id, product_id),
    )
    source_product_id = cur.fetchone()[0]

    # Insert multiple observations
    cur.execute(
        """
        INSERT INTO product_observations (source_product_id, name, price, currency, availability, collected_at)
        VALUES
            (%s, 'Product v1', 10.00, 'USD', 'in_stock', '2026-09-01 10:00:00+00'),
            (%s, 'Product v2', 12.50, 'USD', 'in_stock', '2026-09-02 10:00:00+00'),
            (%s, 'Product v3', 9.99, 'USD', 'out_of_stock', '2026-09-03 10:00:00+00')
        """,
        (source_product_id, source_product_id, source_product_id),
    )

    # Verify all three observations exist
    cur.execute(
        "SELECT COUNT(*) FROM product_observations WHERE source_product_id = %s",
        (source_product_id,),
    )
    count = cur.fetchone()[0]
    assert count == 3, f"Expected 3 observations, got {count}"

    cur.close()


# ---------------------------------------------------------------------------
# Test: Price/timestamp types verified
# ---------------------------------------------------------------------------


def test_price_is_numeric_not_float(db_connection):
    """Verify that price column uses NUMERIC type, not FLOAT/DOUBLE PRECISION."""
    cur = db_connection.cursor()

    cur.execute(
        """
        SELECT data_type, numeric_precision, numeric_scale
        FROM information_schema.columns
        WHERE table_name = 'product_observations'
        AND column_name = 'price'
        AND table_schema = 'public'
        """
    )
    row = cur.fetchone()
    assert row is not None, "price column should exist"

    data_type = row[0]
    assert data_type == "numeric", f"price should be NUMERIC, got {data_type}"

    cur.close()


def test_timestamps_are_timestamptz(db_connection):
    """Verify that timestamp columns use TIMESTAMPTZ."""
    cur = db_connection.cursor()

    timestamp_columns = ["collected_at", "ingested_at", "created_at", "updated_at"]

    for col in timestamp_columns:
        cur.execute(
            """
            SELECT data_type FROM information_schema.columns
            WHERE table_name IN ('product_observations', 'sources', 'products', 'source_products', 'pipeline_runs')
            AND column_name = %s
            AND table_schema = 'public'
            """,
            (col,),
        )
        row = cur.fetchone()
        if row:
            data_type = row[0]
            assert data_type == "timestamp with time zone", (
                f"{col} should be TIMESTAMPTZ, got {data_type}"
            )

    cur.close()


def test_negative_price_rejected(db_connection):
    """Verify that negative prices are rejected by CHECK constraint."""
    cur = db_connection.cursor()

    # Create source, product, and source_product
    cur.execute("INSERT INTO sources (name) VALUES ('test_source') RETURNING id")
    source_id = cur.fetchone()[0]

    cur.execute("INSERT INTO products (canonical_name) VALUES ('Test Product') RETURNING id")
    product_id = cur.fetchone()[0]

    cur.execute(
        "INSERT INTO source_products (source_id, product_id, external_id) VALUES (%s, %s, 'ext-001') RETURNING id",
        (source_id, product_id),
    )
    source_product_id = cur.fetchone()[0]

    # Try to insert negative price — should fail
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            """
            INSERT INTO product_observations (source_product_id, name, price, currency, availability, collected_at)
            VALUES (%s, 'Bad Product', -5.00, 'USD', 'in_stock', '2026-09-01 10:00:00+00')
            """,
            (source_product_id,),
        )

    cur.close()


def test_null_price_allowed(db_connection):
    """Verify that NULL prices are allowed (e.g., free items or missing data)."""
    cur = db_connection.cursor()

    # Create source, product, and source_product
    cur.execute("INSERT INTO sources (name) VALUES ('test_source') RETURNING id")
    source_id = cur.fetchone()[0]

    cur.execute("INSERT INTO products (canonical_name) VALUES ('Test Product') RETURNING id")
    product_id = cur.fetchone()[0]

    cur.execute(
        "INSERT INTO source_products (source_id, product_id, external_id) VALUES (%s, %s, 'ext-001') RETURNING id",
        (source_id, product_id),
    )
    source_product_id = cur.fetchone()[0]

    # Insert observation with NULL price — should succeed
    cur.execute(
        """
        INSERT INTO product_observations (source_product_id, name, price, currency, availability, collected_at)
        VALUES (%s, 'Free Product', NULL, 'USD', 'in_stock', '2026-09-01 10:00:00+00')
        """,
        (source_product_id,),
    )

    # Verify it was inserted
    cur.execute(
        "SELECT price FROM product_observations WHERE source_product_id = %s AND name = 'Free Product'",
        (source_product_id,),
    )
    row = cur.fetchone()
    assert row is not None
    assert row[0] is None

    cur.close()
