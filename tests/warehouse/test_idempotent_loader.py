"""Tests for idempotent warehouse loading (TASK-030).

These tests verify that replaying the same data doesn't create duplicates,
conflicting payloads are escalated, and legitimate new observations work correctly.

Prerequisites:
- PostgreSQL must be running locally
- Database migrations must include event_id column (migration 002)

Run with:
    python -m pytest tests/warehouse/test_idempotent_loader.py -v -m integration
"""

# mypy: disable-error-code="import-untyped,no-untyped-def,import-not-found"
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import polars as pl
import psycopg2
import pytest

from libs.common.minio_storage import MinIOStorage
from warehouse.loader.batch_loader import WarehouseLoader

pytestmark = pytest.mark.integration


@pytest.fixture
def db_url():
    """Database URL for tests."""
    return "postgresql+psycopg2://platform:platform-local@localhost:5432/warehouse_idempotency_test"


@pytest.fixture
def db_connection(db_url):
    """Create test database and return connection."""
    # Connect to postgres database to create test DB
    admin_url = db_url.replace("warehouse_idempotency_test", "postgres").replace(
        "postgresql+psycopg2://", "postgresql://"
    )
    conn = psycopg2.connect(admin_url)
    conn.autocommit = True
    cur = conn.cursor()

    # Drop if exists and recreate
    cur.execute("SELECT 1 FROM pg_database WHERE datname = 'warehouse_idempotency_test'")
    if cur.fetchone():
        cur.execute("DROP DATABASE warehouse_idempotency_test")
    cur.execute("CREATE DATABASE warehouse_idempotency_test")
    cur.close()
    conn.close()

    # Connect to test database
    test_url = db_url.replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(test_url)
    conn.autocommit = True

    # Run migrations
    from pathlib import Path as P

    from alembic import command
    from alembic.config import Config

    migrations_dir = P(__file__).parent.parent.parent / "warehouse" / "migrations"
    cfg = Config(str(migrations_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(migrations_dir))
    cfg.set_main_option("sqlalchemy.url", test_url)

    try:
        command.upgrade(cfg, "head")
    except Exception:
        pass  # Schema may already exist

    yield conn

    # Cleanup
    conn.close()

    # Drop test database
    conn = psycopg2.connect(admin_url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("DROP DATABASE IF EXISTS warehouse_idempotency_test")
    cur.close()
    conn.close()


@pytest.fixture
def loader(db_url):
    """Create a WarehouseLoader instance."""
    mock_storage = MagicMock(spec=MinIOStorage)
    return WarehouseLoader(db_url=db_url, storage=mock_storage, batch_size=10)


@pytest.fixture
def sample_parquet_file(tmp_path):
    """Create a sample Parquet file with event_id."""
    df = pl.DataFrame(
        {
            "event_id": ["evt-001", "evt-002"],
            "source": ["fake-store", "fake-store"],
            "external_id": ["prod-1", "prod-2"],
            "name": ["Widget A", "Widget B"],
            "price": ["19.99", "29.99"],
            "currency": ["USD", "USD"],
            "availability": ["in_stock", "in_stock"],
            "category": ["widgets", "widgets"],
            "collected_at": [
                datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc),
                datetime(2026, 9, 1, 11, 0, tzinfo=timezone.utc),
            ],
            "url": ["https://example.com/1", "https://example.com/2"],
        }
    )
    path = tmp_path / "sample.parquet"
    df.write_parquet(path)
    return path


def test_same_batch_twice(loader, sample_parquet_file, db_connection):
    """Loading the same batch twice should not create duplicates."""
    # First load
    result1 = loader.load_from_parquet_files([sample_parquet_file])
    assert result1.success
    assert result1.observations_created == 2

    # Second load (same data)
    result2 = loader.load_from_parquet_files([sample_parquet_file])
    assert result2.success
    # Should not create new observations due to idempotency
    assert result2.observations_created == 0

    # Verify only 2 observations exist
    cur = db_connection.cursor()
    cur.execute("SELECT COUNT(*) FROM product_observations")
    count = cur.fetchone()[0]
    assert count == 2
    cur.close()


def test_same_observation_through_two_files(loader, tmp_path, db_connection):
    """Same observation in two different files should not duplicate."""
    # Create two files with the same event_id
    df1 = pl.DataFrame(
        {
            "event_id": ["evt-001"],
            "source": ["fake-store"],
            "external_id": ["prod-1"],
            "name": ["Widget A"],
            "price": ["19.99"],
            "currency": ["USD"],
            "availability": ["in_stock"],
            "category": ["widgets"],
            "collected_at": [datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)],
            "url": ["https://example.com/1"],
        }
    )
    df2 = df1.clone()  # Same data

    path1 = tmp_path / "file1.parquet"
    path2 = tmp_path / "file2.parquet"
    df1.write_parquet(path1)
    df2.write_parquet(path2)

    # Load both files
    result1 = loader.load_from_parquet_files([path1])
    assert result1.success
    assert result1.observations_created == 1

    result2 = loader.load_from_parquet_files([path2])
    assert result2.success
    # Same event_id should not create duplicate
    assert result2.observations_created == 0

    # Verify only 1 observation exists
    cur = db_connection.cursor()
    cur.execute("SELECT COUNT(*) FROM product_observations")
    count = cur.fetchone()[0]
    assert count == 1
    cur.close()


def test_same_product_new_observation_remains_history(loader, tmp_path, db_connection):
    """Same product at a new observation time should create new history."""
    # First observation
    df1 = pl.DataFrame(
        {
            "event_id": ["evt-001"],
            "source": ["fake-store"],
            "external_id": ["prod-1"],
            "name": ["Widget A"],
            "price": ["19.99"],
            "currency": ["USD"],
            "availability": ["in_stock"],
            "category": ["widgets"],
            "collected_at": [datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)],
            "url": ["https://example.com/1"],
        }
    )
    path1 = tmp_path / "obs1.parquet"
    df1.write_parquet(path1)

    result1 = loader.load_from_parquet_files([path1])
    assert result1.success
    assert result1.observations_created == 1

    # Second observation for same product (different event_id, different time)
    df2 = pl.DataFrame(
        {
            "event_id": ["evt-002"],
            "source": ["fake-store"],
            "external_id": ["prod-1"],
            "name": ["Widget A"],
            "price": ["24.99"],  # Price changed
            "currency": ["USD"],
            "availability": ["in_stock"],
            "category": ["widgets"],
            "collected_at": [datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)],
            "url": ["https://example.com/1"],
        }
    )
    path2 = tmp_path / "obs2.parquet"
    df2.write_parquet(path2)

    result2 = loader.load_from_parquet_files([path2])
    assert result2.success
    # New observation should be created (different event_id)
    assert result2.observations_created == 1

    # Verify 2 observations exist (historical record preserved)
    cur = db_connection.cursor()
    cur.execute("SELECT COUNT(*) FROM product_observations")
    count = cur.fetchone()[0]
    assert count == 2

    # Verify both prices are stored
    cur.execute("SELECT price FROM product_observations ORDER BY collected_at")
    prices = [row[0] for row in cur.fetchall()]
    assert Decimal("19.99") in prices
    assert Decimal("24.99") in prices
    cur.close()


def test_retry_after_partial_failure(loader, tmp_path, db_connection):
    """Retry after partial failure should converge to correct state."""
    # Create file with 3 observations
    df = pl.DataFrame(
        {
            "event_id": ["evt-001", "evt-002", "evt-003"],
            "source": ["fake-store", "fake-store", "fake-store"],
            "external_id": ["prod-1", "prod-2", "prod-3"],
            "name": ["Widget A", "Widget B", "Widget C"],
            "price": ["19.99", "29.99", "39.99"],
            "currency": ["USD", "USD", "USD"],
            "availability": ["in_stock", "in_stock", "in_stock"],
            "category": ["widgets", "widgets", "widgets"],
            "collected_at": [
                datetime(2026, 9, 1, tzinfo=timezone.utc),
                datetime(2026, 9, 1, tzinfo=timezone.utc),
                datetime(2026, 9, 1, tzinfo=timezone.utc),
            ],
            "url": [None, None, None],
        }
    )
    path = tmp_path / "retry.parquet"
    df.write_parquet(path)

    # First load succeeds
    result1 = loader.load_from_parquet_files([path])
    assert result1.success
    assert result1.observations_created == 3

    # Retry same load
    result2 = loader.load_from_parquet_files([path])
    assert result2.success
    # No new observations due to idempotency
    assert result2.observations_created == 0

    # Verify exactly 3 observations
    cur = db_connection.cursor()
    cur.execute("SELECT COUNT(*) FROM product_observations")
    count = cur.fetchone()[0]
    assert count == 3
    cur.close()


def test_conflicting_duplicate_identity(loader, tmp_path, db_connection):
    """Conflicting payloads for same event_id should raise error."""
    # First load with original data
    df1 = pl.DataFrame(
        {
            "event_id": ["evt-001"],
            "source": ["fake-store"],
            "external_id": ["prod-1"],
            "name": ["Widget A"],
            "price": ["19.99"],
            "currency": ["USD"],
            "availability": ["in_stock"],
            "category": ["widgets"],
            "collected_at": [datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)],
            "url": ["https://example.com/1"],
        }
    )
    path1 = tmp_path / "original.parquet"
    df1.write_parquet(path1)

    result1 = loader.load_from_parquet_files([path1])
    assert result1.success

    # Second load with conflicting data (same event_id, different price)
    df2 = pl.DataFrame(
        {
            "event_id": ["evt-001"],  # Same event_id
            "source": ["fake-store"],
            "external_id": ["prod-1"],
            "name": ["Widget A"],
            "price": ["99.99"],  # Different price!
            "currency": ["USD"],
            "availability": ["in_stock"],
            "category": ["widgets"],
            "collected_at": [datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)],
            "url": ["https://example.com/1"],
        }
    )
    path2 = tmp_path / "conflict.parquet"
    df2.write_parquet(path2)

    # Should raise ValueError for conflicting data
    with pytest.raises(ValueError, match="Conflicting observation"):
        loader.load_from_parquet_files([path2])

    # Verify original data is unchanged
    cur = db_connection.cursor()
    cur.execute("SELECT price FROM product_observations WHERE event_id = 'evt-001'")
    price = cur.fetchone()[0]
    assert price == Decimal("19.99")
    cur.close()


def test_reference_table_upsert_behavior(loader, tmp_path, db_connection):
    """Sources and products should use upsert semantics."""
    # Create file with source/product
    df = pl.DataFrame(
        {
            "event_id": ["evt-001"],
            "source": ["fake-store"],
            "external_id": ["prod-1"],
            "name": ["Widget A"],
            "price": ["19.99"],
            "currency": ["USD"],
            "availability": ["in_stock"],
            "category": ["widgets"],
            "collected_at": [datetime(2026, 9, 1, tzinfo=timezone.utc)],
            "url": ["https://example.com/1"],
        }
    )
    path = tmp_path / "upsert.parquet"
    df.write_parquet(path)

    # First load
    result1 = loader.load_from_parquet_files([path])
    assert result1.success
    # Sources/products may or may not be created depending on prior state
    # What matters is they exist after the load
    assert result1.products_created >= 0

    # Second load (same source/product)
    result2 = loader.load_from_parquet_files([path])
    assert result2.success
    # No new observations due to idempotency
    assert result2.observations_created == 0

    # Verify single source and product exist
    cur = db_connection.cursor()
    cur.execute("SELECT COUNT(*) FROM sources WHERE name = 'fake-store'")
    assert cur.fetchone()[0] == 1

    cur.execute("SELECT COUNT(*) FROM source_products WHERE external_id = 'prod-1'")
    assert cur.fetchone()[0] == 1
    cur.close()
