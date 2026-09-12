"""Partition discovery and lazy scanning utilities for Parquet data lake.

This module provides:
- ``list_partitions``: discover available partition directories in Bronze/Silver
- ``LazyScanner``: Polars-based lazy scanner with predicate/projection pushdown
  for efficient columnar reads without materializing full datasets in memory.

Both utilities work with the canonical partition layout:

    <layer>/source=<source>/year=<YYYY>/month=<MM>/day=<DD>/*.parquet
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

import polars as pl

from libs.common.minio_storage import MinIOStorage
from libs.partitioning import LakeLayer

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class PartitionInfo:
    """Metadata about a discovered partition directory."""

    layer: str
    source: str
    year: int
    month: int
    day: int
    file_count: int = 0
    prefix: str = ""  # S3/MinIO key prefix for this partition


def _parse_partition_prefix(prefix: str) -> PartitionInfo | None:
    """Parse a partition prefix into structured metadata.

    Expected format: <layer>/source=<source>/year=<YYYY>/month=<MM>/day=<DD>/

    Returns None if the prefix doesn't match the expected pattern.
    """
    parts = prefix.rstrip("/").split("/")
    if len(parts) != 5:
        return None

    layer_str, source_part, year_part, month_part, day_part = parts

    # Validate structure
    if not source_part.startswith("source="):
        return None
    if not year_part.startswith("year="):
        return None
    if not month_part.startswith("month="):
        return None
    if not day_part.startswith("day="):
        return None

    try:
        year = int(year_part.split("=", 1)[1])
        month = int(month_part.split("=", 1)[1])
        day = int(day_part.split("=", 1)[1])
    except ValueError:
        return None

    source = source_part.split("=", 1)[1]

    return PartitionInfo(
        layer=layer_str,
        source=source,
        year=year,
        month=month,
        day=day,
        prefix=prefix,
    )


def list_partitions(
    storage: MinIOStorage,
    bucket: str,
    layer: LakeLayer | str = LakeLayer.BRONZE,
    source: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[PartitionInfo]:
    """Discover partition directories matching the given filters.

    Parameters
    ----------
    storage:
        Initialized MinIO/S3 storage client.
    bucket:
        Bucket containing the data lake layers (e.g., "bronze", "silver").
    layer:
        Target layer — ``bronze`` or ``silver``.
    source:
        Optional source filter (e.g., "fake-store"). If None, all sources.
    start_date:
        Optional inclusive start date for temporal filtering.
    end_date:
        Optional inclusive end date for temporal filtering.

    Returns
    -------
    list[PartitionInfo]
        Sorted list of matching partitions with file counts.

    Examples
    --------
    >>> # List all bronze partitions for fake-store in September 2026
    >>> partitions = list_partitions(
    ...     storage, "bronze", LakeLayer.BRONZE,
    ...     source="fake-store",
    ...     start_date=date(2026, 9, 1),
    ...     end_date=date(2026, 9, 30),
    ... )
    """
    layer_value = layer.value if isinstance(layer, LakeLayer) else layer
    prefix = f"{layer_value}/"

    if source is not None:
        prefix += f"source={source}/"

    logger.info(
        "listing_partitions",
        extra={"bucket": bucket, "prefix": prefix},
    )

    # List objects to discover partition structure
    objects = storage.list_objects(bucket, prefix=prefix)

    # Extract unique partition prefixes
    partition_prefixes: set[str] = set()
    for obj_key in objects:
        # Extract partition directory: everything up to and including day=<DD>/
        parts = obj_key.split("/")
        if len(parts) >= 5:
            # Reconstruct partition prefix
            partition_prefix = "/".join(parts[:5]) + "/"
            partition_prefixes.add(partition_prefix)

    # Parse and filter partitions
    result: list[PartitionInfo] = []
    for pp in sorted(partition_prefixes):
        info = _parse_partition_prefix(pp)
        if info is None:
            continue

        # Apply date filters
        part_date = date(info.year, info.month, info.day)
        if start_date is not None and part_date < start_date:
            continue
        if end_date is not None and part_date > end_date:
            continue

        # Count files in partition
        file_count = sum(1 for k in objects if k.startswith(pp) and k.endswith(".parquet"))
        info.file_count = file_count
        result.append(info)

    logger.info(
        "partitions_discovered",
        extra={"count": len(result), "bucket": bucket, "layer": layer_value},
    )
    return result


class LazyScanner:
    """Lazy Polars scanner for partitioned Parquet datasets.

    Uses Polars ``scan_parquet`` for lazy evaluation with automatic
    predicate and projection pushdown where supported by the Parquet engine.

    This avoids materializing large datasets in Python memory and lets
    Polars optimize the read plan.

    Parameters
    ----------
    storage:
        Initialized MinIO/S3 storage client.
    bucket:
        Bucket containing the data.
    layer:
        Target layer (``bronze`` or ``silver``).
    source:
        Optional source filter for partition pruning.
    start_date:
        Optional inclusive start date for temporal filtering.
    end_date:
        Optional inclusive end date for temporal filtering.
    columns:
        Optional list of column names to project. If None, all columns.
    """

    def __init__(
        self,
        storage: MinIOStorage,
        bucket: str,
        layer: LakeLayer | str = LakeLayer.BRONZE,
        source: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        columns: list[str] | None = None,
    ) -> None:
        self._storage = storage
        self._bucket = bucket
        self._layer = layer.value if isinstance(layer, LakeLayer) else layer
        self._source = source
        self._start_date = start_date
        self._end_date = end_date
        self._columns = columns
        self._lazy_frame: pl.LazyFrame | None = None

    def _discover_files(self) -> list[str]:
        """Discover Parquet files matching the scan criteria.

        Returns local file paths or S3 URIs that Polars can read.
        For MinIO, we download to temporary locations or use direct reads.
        """
        partitions = list_partitions(
            self._storage,
            self._bucket,
            self._layer,
            self._source,
            self._start_date,
            self._end_date,
        )

        if not partitions:
            logger.warning(
                "no_partitions_found",
                extra={
                    "bucket": self._bucket,
                    "layer": self._layer,
                    "source": self._source,
                },
            )
            return []

        # Collect all parquet files from matching partitions
        files: list[str] = []
        for part in partitions:
            prefix = part.prefix
            objects = self._storage.list_objects(self._bucket, prefix=prefix)
            parquet_files = [k for k in objects if k.endswith(".parquet")]
            files.extend(parquet_files)

        logger.info(
            "files_discovered_for_scan",
            extra={"file_count": len(files), "partition_count": len(partitions)},
        )
        return files

    def scan(self) -> pl.LazyFrame:
        """Build a lazy DataFrame for the matching partitions.

        The returned LazyFrame supports further filtering and column selection
        before materialization. Polars will push down predicates and projections
        where possible.

        Returns
        -------
        pl.LazyFrame
            Lazy frame ready for further transformation or collection.

        Raises
        ------
        ValueError
            If no files match the scan criteria.
        """
        if self._lazy_frame is not None:
            return self._lazy_frame

        files = self._discover_files()
        if not files:
            raise ValueError(
                f"No Parquet files found for layer={self._layer}, "
                f"source={self._source}, "
                f"date_range=({self._start_date}, {self._end_date})"
            )

        # Use parallel scan for multiple files
        lf = pl.scan_parquet(files)

        # Apply column projection after scan (Polars will push it down)
        if self._columns:
            lf = lf.select(self._columns)

        self._lazy_frame = lf
        logger.info(
            "lazy_scan_created",
            extra={
                "file_count": len(files),
                "columns": self._columns,
                "layer": self._layer,
            },
        )
        return lf

    def collect(self) -> pl.DataFrame:
        """Execute the lazy scan and return a materialized DataFrame.

        This triggers actual I/O and computation. Use with caution on
        large datasets — prefer ``scan()`` followed by selective filtering.

        Returns
        -------
        pl.DataFrame
            Materialized result of the scan.
        """
        lf = self.scan()
        return lf.collect()

    def count(self) -> int:
        """Return the number of rows matching the scan criteria.

        More efficient than ``collect()`` because it only counts rows
        without materializing column data.
        """
        lf = self.scan()
        return lf.select(pl.len()).collect().item()  # type: ignore[no-any-return]
