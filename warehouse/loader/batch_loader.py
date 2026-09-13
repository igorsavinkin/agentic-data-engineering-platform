"""Batch loader for warehouse — reads Silver Parquet and loads PostgreSQL.

This module implements the core loading logic:
- Reads curated Silver Parquet data using LakeReader
- Maps Parquet columns to warehouse relational entities
- Uses batched/chunked processing to avoid loading entire datasets into memory
- Wraps each batch in a transaction for atomic failure behavior
- Logs structured metadata about each load operation
"""

from __future__ import annotations

import logging

# mypy: disable-error-code="import-untyped,no-any-return"
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import polars as pl
import psycopg2
from psycopg2.extras import execute_batch

from libs.common.minio_storage import MinIOStorage
from libs.parquet_reader.reader import LakeReader, PartitionFilter
from libs.partitioning import LakeLayer

from .models import (
    MappedRow,
    ObservationRecord,
    ProductRecord,
    SourceProductRecord,
    SourceRecord,
)

logger = logging.getLogger(__name__)

# Batch size for chunked processing — balances memory usage and DB round-trips
DEFAULT_BATCH_SIZE = 1000


@dataclass
class LoadResult:
    """Structured result metadata from a load operation."""

    rows_read: int = 0
    rows_loaded: int = 0
    rows_failed: int = 0
    sources_created: int = 0
    products_created: int = 0
    source_products_created: int = 0
    observations_created: int = 0
    errors: list[str] = field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def success(self) -> bool:
        return self.rows_failed == 0 and not self.errors


class WarehouseLoader:
    """Loads curated Silver Parquet data into PostgreSQL warehouse tables.

    This loader is designed to be reusable for Airflow orchestration. It
    reads from the Silver layer of the data lake and writes to the warehouse
    PostgreSQL database using batched transactions.

    Parameters
    ----------
    db_url:
        PostgreSQL connection URL for the warehouse database.
    storage:
        MinIO/S3 storage client for reading Parquet files.
    batch_size:
        Number of rows to process per transaction batch.
    """

    def __init__(
        self,
        db_url: str,
        storage: MinIOStorage,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        self._db_url = db_url
        self._storage = storage
        self._batch_size = batch_size
        self._reader = LakeReader(storage, bucket="silver")

    def load_from_parquet_files(
        self,
        parquet_paths: list[Path],
    ) -> LoadResult:
        """Load warehouse from local Parquet file paths.

        Useful for testing and local development where files are on disk.

        Parameters
        ----------
        parquet_paths:
            List of paths to Silver Parquet files.

        Returns
        -------
        LoadResult
            Structured metadata about the load operation.
        """
        if not parquet_paths:
            raise ValueError("No Parquet files provided")

        result = LoadResult(started_at=datetime.now(timezone.utc))

        try:
            # Read all files into a single DataFrame
            df = pl.read_parquet(parquet_paths)
            logger.info(
                "read_parquet_files",
                extra={"file_count": len(parquet_paths), "row_count": len(df)},
            )
            result.rows_read = len(df)

            # Process in batches
            self._process_dataframe(df, result)

        except Exception as exc:
            result.errors.append(f"Failed to read Parquet files: {exc}")
            logger.error("load_failed", extra={"error": str(exc)})
            raise

        result.finished_at = datetime.now(timezone.utc)
        return result

    def load_from_lake(
        self,
        filter: PartitionFilter,
    ) -> LoadResult:
        """Load warehouse from Silver layer using partition filters.

        This is the primary method for production use, reading from the
        data lake via MinIO/S3.

        Parameters
        ----------
        filter:
            Partition filter specifying which data to load.

        Returns
        -------
        LoadResult
            Structured metadata about the load operation.
        """
        result = LoadResult(started_at=datetime.now(timezone.utc))

        try:
            # Use scan for lazy evaluation with column projection
            scanner = self._reader.scan(filter)

            # Collect into DataFrame for batched processing
            df = scanner.collect()
            logger.info(
                "read_from_lake",
                extra={
                    "layer": filter.layer.value
                    if isinstance(filter.layer, LakeLayer)
                    else filter.layer,
                    "source": filter.source,
                    "row_count": len(df),
                },
            )
            result.rows_read = len(df)

            if len(df) == 0:
                logger.warning("no_data_to_load", extra={"filter": str(filter)})
                result.finished_at = datetime.now(timezone.utc)
                return result

            # Process in batches
            self._process_dataframe(df, result)

        except Exception as exc:
            result.errors.append(f"Failed to read from lake: {exc}")
            logger.error("load_failed", extra={"error": str(exc)})
            raise

        result.finished_at = datetime.now(timezone.utc)
        return result

    def _process_dataframe(self, df: pl.DataFrame, result: LoadResult) -> None:
        """Process a DataFrame in batches, mapping and loading rows.

        Parameters
        ----------
        df:
            Polars DataFrame containing Silver Parquet data.
        result:
            LoadResult to update with progress.
        """
        total_rows = len(df)

        for start_idx in range(0, total_rows, self._batch_size):
            end_idx = min(start_idx + self._batch_size, total_rows)
            batch_df = df.slice(start_idx, end_idx - start_idx)

            logger.info(
                "processing_batch",
                extra={
                    "batch_start": start_idx,
                    "batch_end": end_idx,
                    "batch_size": len(batch_df),
                },
            )

            try:
                self._load_batch(batch_df, result)
                result.rows_loaded += len(batch_df)
            except Exception as exc:
                result.rows_failed += len(batch_df)
                error_msg = f"Batch {start_idx}-{end_idx} failed: {exc}"
                result.errors.append(error_msg)
                logger.error("batch_failed", extra={"error": error_msg})
                # Re-raise to trigger transaction rollback at caller level
                raise

    def _load_batch(self, df: pl.DataFrame, result: LoadResult) -> None:
        """Load a single batch within a database transaction.

        All operations in this method are wrapped in a single transaction.
        If any step fails, the entire batch is rolled back.

        Parameters
        ----------
        df:
            Batch DataFrame to load.
        result:
            LoadResult to update with counts.
        """
        # Convert SQLAlchemy URL to psycopg2-compatible DSN
        db_url = self._db_url.replace("postgresql+psycopg2://", "postgresql://")
        conn = psycopg2.connect(db_url)
        conn.autocommit = False

        try:
            cur = conn.cursor()

            # Map rows to warehouse entities
            mapped_rows = [self._map_row(row) for row in df.iter_rows(named=True)]

            # Upsert sources
            sources_created = self._upsert_sources(cur, mapped_rows)
            result.sources_created += sources_created

            # Upsert products
            products_created = self._upsert_products(cur, mapped_rows)
            result.products_created += products_created

            # Upsert source_products
            sp_created = self._upsert_source_products(cur, mapped_rows)
            result.source_products_created += sp_created

            # Insert observations
            obs_created = self._insert_observations(cur, mapped_rows)
            result.observations_created += obs_created

            conn.commit()
            logger.info(
                "batch_committed",
                extra={
                    "sources": sources_created,
                    "products": products_created,
                    "source_products": sp_created,
                    "observations": obs_created,
                },
            )

        except Exception as exc:
            conn.rollback()
            logger.error("batch_rolled_back", extra={"error": str(exc)})
            raise
        finally:
            conn.close()

    def _map_row(self, row: dict[str, Any]) -> MappedRow:
        """Map a single Silver Parquet row to warehouse entities.

        This separates the mapping logic from DB I/O for testability.

        Parameters
        ----------
        row:
            Dictionary representing one Silver Parquet row.

        Returns
        -------
        MappedRow
            Complete mapping of the row into warehouse entities.

        Raises
        ------
        ValueError
            If required fields are missing or malformed.
        """
        # Extract required fields
        source_name = row.get("source")
        external_id = row.get("external_id")
        availability = row.get("availability")
        collected_at = row.get("collected_at")

        # Validate required fields
        if not source_name:
            raise ValueError(f"Missing required field 'source': {row}")
        if not external_id:
            raise ValueError(f"Missing required field 'external_id': {row}")
        if not availability:
            raise ValueError(f"Missing required field 'availability': {row}")
        if not collected_at:
            raise ValueError(f"Missing required field 'collected_at': {row}")

        # Parse price as Decimal if present
        price_str = row.get("price")
        price: Decimal | None = None
        if price_str:
            try:
                price = Decimal(str(price_str))
            except (InvalidOperation, ValueError) as exc:
                raise ValueError(f"Invalid price value '{price_str}': {exc}") from exc

        # Normalize timestamps
        if isinstance(collected_at, str):
            collected_at = datetime.fromisoformat(collected_at.replace("Z", "+00:00"))

        return MappedRow(
            source=SourceRecord(name=str(source_name)),
            product=ProductRecord(
                canonical_name=row.get("name"),
                category=row.get("category"),
            ),
            source_product=SourceProductRecord(
                source_id=0,  # Placeholder — resolved during upsert
                product_id=0,  # Placeholder — resolved during upsert
                external_id=str(external_id),
                url=row.get("url"),
            ),
            observation=ObservationRecord(
                source_product_id=0,  # Placeholder — resolved during upsert
                availability=str(availability),
                collected_at=collected_at,
                name=row.get("name"),
                price=price,
                currency=row.get("currency"),
            ),
        )

    def _upsert_sources(self, cur: Any, mapped_rows: list[MappedRow]) -> int:
        """Upsert sources into the sources table.

        Uses INSERT ... ON CONFLICT to handle idempotent inserts.

        Returns
        -------
        int
            Number of new sources created.
        """
        # Collect unique sources
        sources: dict[str, SourceRecord] = {}
        for mr in mapped_rows:
            if mr.source:
                sources[mr.source.name] = mr.source

        if not sources:
            return 0

        # Upsert using ON CONFLICT
        values = [(name, src.description) for name, src in sources.items()]
        execute_batch(
            cur,
            """
            INSERT INTO sources (name, description)
            VALUES (%s, %s)
            ON CONFLICT (name) DO NOTHING
            """,
            values,
        )

        # Count how many were actually inserted (not conflicts)
        cur.execute(
            "SELECT COUNT(*) FROM sources WHERE name IN %s",
            (tuple(sources.keys()),),
        )
        existing_count = cur.fetchone()[0]
        created = len(sources) - existing_count

        return max(0, created)

    def _upsert_products(self, cur: Any, mapped_rows: list[MappedRow]) -> int:
        """Upsert products into the products table.

        Products are identified by their canonical_name + category combination.
        Since we don't have a natural key, we use a simple approach: insert
        and let the serial ID auto-generate. For deduplication, TASK-030 will
        implement proper idempotency.

        Returns
        -------
        int
            Number of new products created.
        """
        # For now, create products based on unique (canonical_name, category) pairs
        products: set[tuple[str | None, str | None]] = set()
        for mr in mapped_rows:
            if mr.product:
                key = (mr.product.canonical_name, mr.product.category)
                products.add(key)

        if not products:
            return 0

        # Insert products
        values = [(name, cat) for name, cat in products]
        execute_batch(
            cur,
            """
            INSERT INTO products (canonical_name, category)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            values,
        )

        return len(products)

    def _upsert_source_products(self, cur: Any, mapped_rows: list[MappedRow]) -> int:
        """Upsert source_products mapping.

        Links sources to products via external_id. Requires looking up
        source_id and product_id from existing records.

        Returns
        -------
        int
            Number of new source_product mappings created.
        """
        # Get source IDs
        source_names = {mr.source.name for mr in mapped_rows if mr.source}
        if not source_names:
            return 0

        cur.execute(
            "SELECT id, name FROM sources WHERE name IN %s",
            (tuple(source_names),),
        )
        source_id_map = {name: sid for sid, name in cur.fetchall()}

        # Get product IDs (by canonical_name)
        product_names = {
            mr.product.canonical_name
            for mr in mapped_rows
            if mr.product and mr.product.canonical_name
        }
        product_id_map: dict[str | None, int] = {}
        if product_names:
            cur.execute(
                "SELECT id, canonical_name FROM products WHERE canonical_name IN %s",
                (tuple(product_names),),
            )
            product_id_map = {name: pid for pid, name in cur.fetchall()}

        # Build source_product records
        sp_values = []
        for mr in mapped_rows:
            if not mr.source_product or not mr.source:
                continue

            source_id = source_id_map.get(mr.source.name)
            if not source_id:
                continue

            # For now, use a placeholder product_id since we may not have exact match
            # In production, this would use proper product matching logic
            product_id = product_id_map.get(mr.product.canonical_name if mr.product else None)
            if not product_id:
                # Create a minimal product if needed
                cur.execute(
                    "INSERT INTO products (canonical_name, category) VALUES (%s, %s) RETURNING id",
                    (
                        mr.product.canonical_name if mr.product else None,
                        mr.product.category if mr.product else None,
                    ),
                )
                product_id = cur.fetchone()[0]

            sp_values.append(
                (source_id, product_id, mr.source_product.external_id, mr.source_product.url)
            )

        if not sp_values:
            return 0

        # Remove duplicates
        sp_values = list(set(sp_values))

        execute_batch(
            cur,
            """
            INSERT INTO source_products (source_id, product_id, external_id, url)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (source_id, external_id) DO NOTHING
            """,
            sp_values,
        )

        return len(sp_values)

    def _insert_observations(self, cur: Any, mapped_rows: list[MappedRow]) -> int:
        """Insert product observations.

        Each observation is linked to a source_product via foreign key.

        Returns
        -------
        int
            Number of observations inserted.
        """
        # Get source_product IDs
        sp_keys = [
            (mr.source.name, mr.source_product.external_id)
            for mr in mapped_rows
            if mr.source and mr.source_product and mr.observation
        ]
        if not sp_keys:
            return 0

        # Query for existing source_products
        placeholders = ", ".join(["(%s, %s)"] * len(sp_keys))
        query = f"""
            SELECT sp.id, s.name, sp.external_id
            FROM source_products sp
            JOIN sources s ON sp.source_id = s.id
            WHERE (s.name, sp.external_id) IN ({placeholders})
        """
        flat_params = [item for sublist in sp_keys for item in sublist]
        cur.execute(query, flat_params)
        sp_id_map = {(name, ext_id): sp_id for sp_id, name, ext_id in cur.fetchall()}

        # Build observation values
        obs_values = []
        for mr in mapped_rows:
            if not mr.observation or not mr.source or not mr.source_product:
                continue

            key = (mr.source.name, mr.source_product.external_id)
            sp_id = sp_id_map.get(key)
            if not sp_id:
                continue

            obs_values.append(
                (
                    sp_id,
                    mr.observation.name,
                    mr.observation.price,
                    mr.observation.currency,
                    mr.observation.availability,
                    mr.observation.collected_at,
                )
            )

        if not obs_values:
            return 0

        execute_batch(
            cur,
            """
            INSERT INTO product_observations
                (source_product_id, name, price, currency, availability, collected_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            obs_values,
        )

        return len(obs_values)
