"""High-level Parquet read utilities for Bronze/Silver data lake layers.

This module provides:
- ``PartitionFilter``: structured filter specification for partition pruning
- ``LakeReader``: unified reader API supporting filtered reads with column projection

The reader is designed to be reusable by downstream components (Airflow DAGs,
warehouse loaders, FastAPI endpoints) while remaining strictly read-only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import polars as pl

from libs.common.minio_storage import MinIOStorage
from libs.parquet_reader.scanner import LazyScanner, PartitionInfo, list_partitions
from libs.partitioning import LakeLayer

logger = logging.getLogger(__name__)


@dataclass
class PartitionFilter:
    """Structured filter for partition discovery and reading.

    All fields are optional — omitting a field means "match all".

    Parameters
    ----------
    layer:
        Target lake layer (bronze or silver).
    source:
        Optional source name filter (e.g., "fake-store").
    start_date:
        Inclusive start date for temporal range.
    end_date:
        Inclusive end date for temporal range.
    columns:
        Optional column projection — only these columns will be read.
    """

    layer: LakeLayer | str = LakeLayer.BRONZE
    source: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    columns: list[str] | None = None

    def __post_init__(self) -> None:
        if isinstance(self.layer, str):
            self.layer = LakeLayer(self.layer)


class LakeReader:
    """Unified reader for partitioned Bronze/Silver Parquet datasets.

    Provides high-level methods for discovering partitions and reading data
    with automatic partition pruning and column projection.

    This reader is strictly read-only and does not modify the data lake.

    Parameters
    ----------
    storage:
        Initialized MinIO/S3 storage client.
    bucket:
        Bucket containing the data lake layers. Defaults to "bronze" but
        can be overridden per-read via the filter.

    Examples
    --------
    >>> reader = LakeReader(storage, bucket="bronze")
    >>> # Read all fake-store data from September 2026
    >>> df = reader.read(
    ...     PartitionFilter(
    ...         layer=LakeLayer.BRONZE,
    ...         source="fake-store",
    ...         start_date=date(2026, 9, 1),
    ...         end_date=date(2026, 9, 30),
    ...         columns=["event_id", "external_id", "price"],
    ...     )
    ... )
    """

    def __init__(
        self,
        storage: MinIOStorage,
        bucket: str = "bronze",
    ) -> None:
        self._storage = storage
        self._bucket = bucket

    def discover_partitions(
        self,
        layer: LakeLayer | str = LakeLayer.BRONZE,
        source: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[PartitionInfo]:
        """Discover available partitions matching the given filters.

        Parameters
        ----------
        layer:
            Target layer (bronze or silver).
        source:
            Optional source filter.
        start_date:
            Inclusive start date.
        end_date:
            Inclusive end date.

        Returns
        -------
        list[PartitionInfo]
            Sorted list of matching partitions with metadata.
        """
        return list_partitions(
            self._storage,
            self._bucket,
            layer,
            source,
            start_date,
            end_date,
        )

    def read(
        self,
        filter: PartitionFilter,
        bucket: str | None = None,
    ) -> pl.DataFrame:
        """Read Parquet data matching the filter into a DataFrame.

        This method performs partition pruning, column projection, and
        returns a materialized DataFrame. For large datasets, prefer
        ``scan()`` which returns a lazy frame.

        Parameters
        ----------
        filter:
            Partition and column filter specification.
        bucket:
            Optional bucket override. Defaults to the reader's bucket.

        Returns
        -------
        pl.DataFrame
            Materialized result. Empty DataFrame if no data matches.

        Raises
        ------
        ValueError
            If the filter is invalid (e.g., start_date > end_date).
        """
        target_bucket = bucket or self._bucket
        scanner = self._create_scanner(filter, target_bucket)

        try:
            return scanner.collect()
        except (ValueError, FileNotFoundError, OSError) as exc:
            # No files found or files don't exist on disk — return empty DataFrame
            logger.warning(
                "no_data_for_filter",
                extra={
                    "layer": filter.layer.value
                    if isinstance(filter.layer, LakeLayer)
                    else filter.layer,
                    "source": filter.source,
                    "date_range": f"{filter.start_date}..{filter.end_date}",
                    "error": str(exc),
                },
            )
            return self._empty_frame(filter)

    def scan(
        self,
        filter: PartitionFilter,
        bucket: str | None = None,
    ) -> pl.LazyFrame:
        """Create a lazy scan for the filtered partitions.

        Use this for large datasets where you want to apply additional
        filters or aggregations before materialization. Polars will push
        down predicates and projections where supported.

        Parameters
        ----------
        filter:
            Partition and column filter specification.
        bucket:
            Optional bucket override.

        Returns
        -------
        pl.LazyFrame
            Lazy frame ready for further transformation.

        Raises
        ------
        ValueError
            If no files match the filter criteria.
        """
        target_bucket = bucket or self._bucket
        scanner = self._create_scanner(filter, target_bucket)
        return scanner.scan()

    def _create_scanner(
        self,
        filter: PartitionFilter,
        bucket: str,
    ) -> LazyScanner:
        """Create a LazyScanner from a PartitionFilter."""
        return LazyScanner(
            storage=self._storage,
            bucket=bucket,
            layer=filter.layer,
            source=filter.source,
            start_date=filter.start_date,
            end_date=filter.end_date,
            columns=filter.columns,
        )

    def _empty_frame(self, filter: PartitionFilter) -> pl.DataFrame:
        """Return an empty DataFrame with the expected column structure.

        When no data matches the filter, we return an empty frame rather
        than raising an error, so callers can handle the "no data" case
        gracefully without special-casing.
        """
        if filter.columns:
            return pl.DataFrame(schema={col: pl.Utf8 for col in filter.columns})
        # Return completely empty frame
        return pl.DataFrame()

    def health_check(self) -> bool:
        """Check if the underlying storage is reachable."""
        status = self._storage.check_health()
        return status.healthy
