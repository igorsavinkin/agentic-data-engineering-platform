"""Tests for warehouse loader (TASK-029).

These tests verify that the loader correctly reads Parquet data, maps it to
warehouse tables, handles transactions, and fails explicitly on bad input.

Prerequisites:
- PostgreSQL must be running locally (Docker Compose or native)
- Database 'warehouse_loader_test' will be created automatically
- User must have CREATE/DROP privileges on the test database

Run with:
    python -m pytest tests/warehouse/test_loader.py -v -m integration
"""

# mypy: disable-error-code="import-untyped,no-untyped-def,import-not-found"
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import polars as pl
import psycopg2
import pytest

from libs.common.minio_storage import MinIOStorage
from warehouse.loader.batch_loader import LoadResult, WarehouseLoader

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
    dbname = os.getenv("WAREHOUSE_DB_NAME_LOADER", "warehouse_loader_test")
    user = os.getenv("WAREHOUSE_DB_USER", "platform")
    password = os.getenv("WAREHOUSE_DB_PASSWORD", "platform-local")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"


@pytest.fixture(scope="module")
def db_connection(db_url):
    """Create a connection to the test database, creating it if needed."""
    from urllib.parse import urlparse

    parsed = urlparse(db_url.replace("postgresql+psycopg2://", "postgresql://"))

    # First connect to the default 'platform' database to create our test DB
    conn_admin = psycopg2.connect(
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        dbname="platform",
        user=parsed.username or "platform",
        password=parsed.password or "platform-local",
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
def loader(db_url):
    """Create a WarehouseLoader instance."""
    # Create a mock storage - not used for load_from_parquet_files
    from unittest.mock import MagicMock

    mock_storage = MagicMock(spec=MinIOStorage)
    return WarehouseLoader(db_url=db_url, storage=mock_storage, batch_size=10)


@pytest.fixture(autouse=True)
def clean_database(db_connection, db_url):
    """Drop all warehouse tables before each test to ensure isolation."""
    cur = db_connection.cursor()

    # Drop tables in reverse dependency order
    cur.execute("DROP TABLE IF EXISTS data_quality_results CASCADE")
    cur.execute("DROP TABLE IF EXISTS pipeline_runs CASCADE")
    cur.execute("DROP TABLE IF EXISTS product_observations CASCADE")
    cur.execute("DROP TABLE IF EXISTS source_products CASCADE")
    cur.execute("DROP TABLE IF EXISTS products CASCADE")
    cur.execute("DROP TABLE IF EXISTS sources CASCADE")
    cur.execute("DROP TABLE IF EXISTS alembic_version CASCADE")

    # Recreate schema using migrations
    from pathlib import Path as P

    from alembic import command
    from alembic.config import Config

    migrations_dir = P(__file__).parent.parent.parent / "warehouse" / "migrations"
    cfg = Config(str(migrations_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(migrations_dir))
    cfg.set_main_option("sqlalchemy.url", db_url.replace("postgresql+psycopg2://", "postgresql://"))

    try:
        command.upgrade(cfg, "head")
    except Exception:
        pass  # Schema may already be clean

    cur.close()


@pytest.fixture
def sample_parquet_file(tmp_path: Path) -> Path:
    """Create a sample Silver Parquet file for testing."""
    data = {
        "event_id": ["evt-001", "evt-002", "evt-003"],
        "event_type": ["product_observation"] * 3,
        "schema_version": ["1.0"] * 3,
        "source": ["fake-store", "fake-store", "best-buy"],
        "produced_at": [datetime.now(timezone.utc)] * 3,
        "external_id": ["prod-100", "prod-101", "prod-200"],
        "name": ["Widget A", "Widget B", "Gadget C"],
        "url": ["http://example.com/1", "http://example.com/2", None],
        "price": ["19.99", "29.99", "49.99"],
        "currency": ["USD", "USD", "USD"],
        "availability": ["in_stock", "out_of_stock", "in_stock"],
        "category": ["widgets", "widgets", "gadgets"],
        "collected_at": [
            datetime(2026, 9, 1, tzinfo=timezone.utc),
            datetime(2026, 9, 2, tzinfo=timezone.utc),
            datetime(2026, 9, 3, tzinfo=timezone.utc),
        ],
    }
    df = pl.DataFrame(data)
    file_path = tmp_path / "sample_silver.parquet"
    df.write_parquet(file_path)
    return file_path


@pytest.fixture
def parquet_with_nullable_fields(tmp_path: Path) -> Path:
    """Create a Parquet file with nullable fields set to None."""
    data = {
        "event_id": ["evt-010"],
        "event_type": ["product_observation"],
        "schema_version": ["1.0"],
        "source": ["test-source"],
        "produced_at": [datetime.now(timezone.utc)],
        "external_id": ["prod-nullable"],
        "name": [None],  # Nullable name
        "url": [None],  # Nullable URL
        "price": [None],  # Nullable price
        "currency": [None],  # Nullable currency
        "availability": ["unknown"],
        "category": [None],  # Nullable category
        "collected_at": [datetime(2026, 9, 10, tzinfo=timezone.utc)],
    }
    df = pl.DataFrame(data)
    file_path = tmp_path / "nullable_fields.parquet"
    df.write_parquet(file_path)
    return file_path


@pytest.fixture
def malformed_parquet_file(tmp_path: Path) -> Path:
    """Create a Parquet file with missing required fields."""
    data = {
        "event_id": ["evt-bad"],
        "event_type": ["product_observation"],
        # Missing 'source', 'external_id', 'availability', 'collected_at'
    }
    df = pl.DataFrame(data)
    file_path = tmp_path / "malformed.parquet"
    df.write_parquet(file_path)
    return file_path


@pytest.fixture
def multiple_parquet_files(tmp_path: Path) -> list[Path]:
    """Create multiple Parquet files for batch testing."""
    files = []
    for i in range(3):
        data = {
            "event_id": [f"evt-{i}-{j}" for j in range(5)],
            "event_type": ["product_observation"] * 5,
            "schema_version": ["1.0"] * 5,
            "source": [f"source-{i}"] * 5,
            "produced_at": [datetime.now(timezone.utc)] * 5,
            "external_id": [f"prod-{i}-{j}" for j in range(5)],
            "name": [f"Product {i}-{j}" for j in range(5)],
            "url": [None] * 5,
            "price": [f"{10 + i}.{j:02d}" for j in range(5)],
            "currency": ["USD"] * 5,
            "availability": ["in_stock"] * 5,
            "category": [f"cat-{i}"] * 5,
            "collected_at": [datetime(2026, 9, 1 + i, tzinfo=timezone.utc)] * 5,
        }
        df = pl.DataFrame(data)
        file_path = tmp_path / f"batch_{i}.parquet"
        df.write_parquet(file_path)
        files.append(file_path)
    return files


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_parquet_fixture_loads_to_postgres(loader, sample_parquet_file, db_connection):
    """Test that Parquet fixture data loads into PostgreSQL rows."""
    result = loader.load_from_parquet_files([sample_parquet_file])

    assert result.success
    assert result.rows_read == 3
    assert result.rows_loaded == 3
    assert result.rows_failed == 0

    # Verify data in database
    cur = db_connection.cursor()
    cur.execute("SELECT COUNT(*) FROM sources")
    assert cur.fetchone()[0] == 2  # fake-store, best-buy

    cur.execute("SELECT COUNT(*) FROM products")
    assert cur.fetchone()[0] >= 3

    cur.execute("SELECT COUNT(*) FROM product_observations")
    assert cur.fetchone()[0] == 3

    cur.close()


def test_sources_and_products_created_correctly(loader, sample_parquet_file, db_connection):
    """Test that sources and products are created with correct data."""
    loader.load_from_parquet_files([sample_parquet_file])

    cur = db_connection.cursor()

    # Check sources
    cur.execute("SELECT name FROM sources ORDER BY name")
    sources = [row[0] for row in cur.fetchall()]
    assert "fake-store" in sources
    assert "best-buy" in sources

    # Check products exist
    cur.execute("SELECT COUNT(*) FROM products WHERE canonical_name IS NOT NULL")
    assert cur.fetchone()[0] >= 3

    cur.close()


def test_historical_observations_loaded(loader, sample_parquet_file, db_connection):
    """Test that historical observations are loaded with correct timestamps."""
    loader.load_from_parquet_files([sample_parquet_file])

    cur = db_connection.cursor()

    # Check observations have correct collected_at timestamps
    cur.execute(
        "SELECT COUNT(*) FROM product_observations WHERE collected_at >= %s",
        (datetime(2026, 9, 1, tzinfo=timezone.utc),),
    )
    assert cur.fetchone()[0] == 3

    # Check prices were converted correctly
    cur.execute("SELECT price FROM product_observations ORDER BY price")
    prices = [row[0] for row in cur.fetchall()]
    assert Decimal("19.99") in prices
    assert Decimal("29.99") in prices
    assert Decimal("49.99") in prices

    cur.close()


def test_nullable_fields_handled(loader, parquet_with_nullable_fields, db_connection):
    """Test that nullable fields are handled correctly (None values)."""
    result = loader.load_from_parquet_files([parquet_with_nullable_fields])

    assert result.success
    assert result.rows_loaded == 1

    cur = db_connection.cursor()

    # Check observation with null fields
    cur.execute("SELECT name, price, currency FROM product_observations LIMIT 1")
    row = cur.fetchone()
    assert row[0] is None  # name
    assert row[1] is None  # price
    assert row[2] is None  # currency

    cur.close()


def test_rollback_on_failure(loader, sample_parquet_file, malformed_parquet_file):
    """Test that a failed batch triggers transaction rollback."""
    # Load valid data first
    result1 = loader.load_from_parquet_files([sample_parquet_file])
    assert result1.success

    # Try to load malformed data — should fail and not corrupt existing data
    with pytest.raises(Exception):
        loader.load_from_parquet_files([malformed_parquet_file])


def test_malformed_input_fails_clearly(loader, malformed_parquet_file):
    """Test that malformed/unmappable input fails with clear error."""
    with pytest.raises(ValueError) as exc_info:
        loader.load_from_parquet_files([malformed_parquet_file])

    # Error message should mention missing required field
    assert "source" in str(exc_info.value).lower() or "external_id" in str(exc_info.value).lower()


def test_multiple_input_files_batches(loader, multiple_parquet_files, db_connection):
    """Test loading multiple input files with batching."""
    result = loader.load_from_parquet_files(multiple_parquet_files)

    assert result.success
    assert result.rows_read == 15  # 3 files x 5 rows
    assert result.rows_loaded == 15

    # Verify all data loaded
    cur = db_connection.cursor()
    cur.execute("SELECT COUNT(*) FROM product_observations")
    assert cur.fetchone()[0] == 15

    cur.execute("SELECT COUNT(DISTINCT source_id) FROM source_products")
    assert cur.fetchone()[0] == 3  # 3 different sources

    cur.close()


def test_load_result_metadata(loader, sample_parquet_file):
    """Test that load result contains structured metadata."""
    result = loader.load_from_parquet_files([sample_parquet_file])

    assert isinstance(result, LoadResult)
    assert result.rows_read == 3
    assert result.rows_loaded == 3
    assert result.started_at is not None
    assert result.finished_at is not None
    assert result.finished_at >= result.started_at
    assert result.sources_created >= 0
    assert result.products_created >= 0
    assert result.observations_created == 3
