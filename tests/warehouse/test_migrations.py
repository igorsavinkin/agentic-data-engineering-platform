"""Tests for warehouse database migrations (TASK-028).

These tests verify that migrations can upgrade/downgrade, produce the correct
schema, handle reruns safely, and fail clearly on misconfiguration.

Prerequisites:
- PostgreSQL must be running locally (Docker Compose or native)
- Database 'warehouse_migration_test' must exist
- User must have CREATE/DROP privileges on the test database

Run with:
    python -m pytest tests/warehouse/test_migrations.py -v -m integration
"""

# mypy: disable-error-code="import-untyped,no-untyped-def,import-not-found"
import os
from pathlib import Path

import psycopg2
import pytest
from alembic import command
from alembic.config import Config

# Mark all tests in this module as integration tests (require PostgreSQL)
pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db_url():
    """Build database URL from environment variables."""
    host = os.getenv("WAREHOUSE_DB_HOST", "localhost")
    port = os.getenv("WAREHOUSE_DB_PORT", "5432")
    dbname = os.getenv("WAREHOUSE_DB_NAME_MIGRATION", "warehouse_migration_test")
    user = os.getenv("WAREHOUSE_DB_USER", "postgres")
    password = os.getenv("WAREHOUSE_DB_PASSWORD", "postgres")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"


@pytest.fixture(scope="module")
def db_connection(db_url):
    """Create a connection to the test database, creating it if needed."""
    from urllib.parse import urlparse

    parsed = urlparse(db_url.replace("postgresql+psycopg2://", "postgresql://"))

    # First connect to the default 'postgres' database to create our test DB
    conn_admin = psycopg2.connect(
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        dbname="postgres",  # Connect to default database
        user=parsed.username or "postgres",
        password=parsed.password or "",
    )
    conn_admin.autocommit = True
    cur_admin = conn_admin.cursor()

    # Create test database if it doesn't exist
    test_dbname = parsed.path.lstrip("/")
    cur_admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (test_dbname,))
    if not cur_admin.fetchone():
        cur_admin.execute(f"CREATE DATABASE {test_dbname}")

    cur_admin.close()
    conn_admin.close()

    # Now connect to the test database
    conn = psycopg2.connect(
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        dbname=test_dbname,
        user=parsed.username or "postgres",
        password=parsed.password or "",
    )
    conn.autocommit = True
    yield conn
    conn.close()


@pytest.fixture
def alembic_cfg(db_url):
    """Create Alembic configuration for testing."""
    migrations_dir = Path(__file__).parent.parent.parent / "warehouse" / "migrations"
    cfg = Config(str(migrations_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(migrations_dir))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


@pytest.fixture(autouse=True)
def clean_database(db_connection):
    """Drop all tables before each test to ensure isolation."""
    cur = db_connection.cursor()

    # Drop tables in reverse dependency order
    cur.execute("DROP TABLE IF EXISTS daily_metrics CASCADE")
    cur.execute("DROP TABLE IF EXISTS ingestion_health_results CASCADE")
    cur.execute("DROP TABLE IF EXISTS data_quality_results CASCADE")
    cur.execute("DROP TABLE IF EXISTS pipeline_runs CASCADE")
    cur.execute("DROP TABLE IF EXISTS product_observations CASCADE")
    cur.execute("DROP TABLE IF EXISTS source_products CASCADE")
    cur.execute("DROP TABLE IF EXISTS products CASCADE")
    cur.execute("DROP TABLE IF EXISTS sources CASCADE")
    cur.execute("DROP TABLE IF EXISTS alembic_version CASCADE")

    cur.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_migrate_empty_db_to_head(alembic_cfg):
    """Test upgrading an empty database to head/latest version."""
    command.upgrade(alembic_cfg, "head")

    # Version tracking is verified in test_migration_version_inspectable


def test_resulting_schema_matches_task027(db_connection, alembic_cfg):
    """Test that migration produces the same schema as TASK-027 init.sql."""
    # Run migration
    command.upgrade(alembic_cfg, "head")

    cur = db_connection.cursor()

    # Check all expected tables exist
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    tables = {row[0] for row in cur.fetchall()}

    expected_tables = {
        "sources",
        "products",
        "source_products",
        "product_observations",
        "pipeline_runs",
        "data_quality_results",
        "ingestion_health_results",
        "daily_metrics",
        "alembic_version",
    }
    assert expected_tables.issubset(tables), f"Missing tables: {expected_tables - tables}"

    # Check sources table structure
    cur.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'sources'
        ORDER BY ordinal_position
    """)
    columns = {row[0]: {"type": row[1], "nullable": row[2]} for row in cur.fetchall()}

    assert "id" in columns
    assert "name" in columns
    assert columns["name"]["type"] == "text"
    assert columns["name"]["nullable"] == "NO"  # NOT NULL

    # Check products table has BIGSERIAL (bigint) primary key
    cur.execute("""
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'products' AND column_name = 'id'
    """)
    assert cur.fetchone()[0] == "bigint"

    # Check product_observations has NUMERIC price
    cur.execute("""
        SELECT numeric_precision, numeric_scale
        FROM information_schema.columns
        WHERE table_name = 'product_observations' AND column_name = 'price'
    """)
    precision, scale = cur.fetchone()
    assert precision == 12
    assert scale == 2

    # Check timestamps are TIMESTAMPTZ
    cur.execute("""
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'sources' AND column_name = 'created_at'
    """)
    assert cur.fetchone()[0] == "timestamp with time zone"

    # Check foreign keys exist
    cur.execute("""
        SELECT tc.table_name, kcu.column_name, ccu.table_name AS foreign_table_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
    """)
    fk_info = {(row[0], row[1], row[2]) for row in cur.fetchall()}

    # Verify key FK relationships
    assert ("source_products", "source_id", "sources") in fk_info
    assert ("source_products", "product_id", "products") in fk_info
    assert ("product_observations", "source_product_id", "source_products") in fk_info

    cur.close()


def test_migration_version_inspectable(db_connection, alembic_cfg):
    """Test that migration version can be inspected after upgrade."""
    # Initially no version
    cur = db_connection.cursor()
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'alembic_version'
        )
    """)
    assert not cur.fetchone()[0]

    # Upgrade
    command.upgrade(alembic_cfg, "head")

    # Now version table should exist
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'alembic_version'
        )
    """)
    assert cur.fetchone()[0]

    # Check version value
    cur.execute("SELECT version_num FROM alembic_version")
    version = cur.fetchone()[0]
    assert version == "006"

    cur.close()


def test_downgrade_upgrade_cycle(db_connection, alembic_cfg):
    """Test downgrade and re-upgrade cycle."""
    # Upgrade to head
    command.upgrade(alembic_cfg, "head")

    # Verify tables exist
    cur = db_connection.cursor()
    cur.execute("""
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    """)
    table_count_after_upgrade = cur.fetchone()[0]
    assert table_count_after_upgrade >= 8  # Our 8 tables + alembic_version

    # Downgrade to base (remove all migrations)
    command.downgrade(alembic_cfg, "base")

    # Verify tables are gone
    cur.execute("""
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        AND table_name != 'alembic_version'
    """)
    table_count_after_downgrade = cur.fetchone()[0]
    assert table_count_after_downgrade == 0

    # Re-upgrade should work
    command.upgrade(alembic_cfg, "head")

    cur.execute("""
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    """)
    table_count_after_reupgrade = cur.fetchone()[0]
    assert table_count_after_reupgrade >= 8

    cur.close()


def test_rerun_is_safe(db_connection, alembic_cfg):
    """Test that running upgrade head multiple times is safe (idempotent)."""
    # First upgrade
    command.upgrade(alembic_cfg, "head")

    # Second upgrade should be safe (no-op)
    command.upgrade(alembic_cfg, "head")

    # Third upgrade should also be safe
    command.upgrade(alembic_cfg, "head")

    # Verify schema is still correct
    cur = db_connection.cursor()
    cur.execute("""
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    """)
    table_count = cur.fetchone()[0]
    assert table_count >= 8

    cur.close()


def test_misconfiguration_fails_clearly(monkeypatch):
    """Test that bad database configuration fails with clear error."""
    # Monkeypatch env vars to point to unreachable DB (bypasses env.py's URL building)
    monkeypatch.setenv("WAREHOUSE_DB_HOST", "localhost")
    monkeypatch.setenv("WAREHOUSE_DB_PORT", "9999")
    monkeypatch.setenv("WAREHOUSE_DB_NAME", "nonexistent_db_12345")
    monkeypatch.setenv("WAREHOUSE_DB_USER", "baduser_xyz")
    monkeypatch.setenv("WAREHOUSE_DB_PASSWORD", "badpass_xyz")

    # Use placeholder URL so env.py will build from our bad env vars
    migrations_dir = Path(__file__).parent.parent.parent / "warehouse" / "migrations"
    cfg = Config(str(migrations_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(migrations_dir))
    cfg.set_main_option("sqlalchemy.url", "driver://user:pass@localhost/dbname")  # placeholder

    with pytest.raises(Exception):
        command.upgrade(cfg, "head")


def test_migration_history(alembic_cfg):
    """Test that migration history is accessible."""
    from alembic.script import ScriptDirectory

    # Use ScriptDirectory to inspect available migrations directly
    script = ScriptDirectory.from_config(alembic_cfg)

    # Get all revisions
    revisions = list(script.walk_revisions())
    assert len(revisions) >= 1, "No migrations found in history"

    # Check our initial migration exists
    revision_ids = [rev.revision for rev in revisions]
    assert "001" in revision_ids, f"Expected '001' revision not found in {revision_ids}"


def test_stamp_version(db_connection, alembic_cfg):
    """Test stamping database to a specific version without running migrations."""
    # Stamp to version 001
    command.stamp(alembic_cfg, "001")

    # Verify version table exists and has correct version
    cur = db_connection.cursor()
    cur.execute("SELECT version_num FROM alembic_version")
    version = cur.fetchone()[0]
    assert version == "001"

    # Tables should NOT exist (stamp doesn't run migrations)
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'sources'
        )
    """)
    assert not cur.fetchone()[0]

    cur.close()
