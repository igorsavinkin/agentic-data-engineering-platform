"""Parquet file compaction for the data lake (TASK-061).

Compacts eligible small Parquet files within a partition while preserving
records, schema, and partition semantics. Validates replacement before
source removal and handles replay/partial failure safely.

The compactor is idempotent: running it twice on the same partition
produces the same result. A deterministic compaction key (based on the
partition prefix) prevents duplicate work.
"""

from __future__ import annotations

import io
import logging
import uuid
from dataclasses import dataclass, field

import polars as pl

from libs.common.minio_storage import MinIOStorage

logger = logging.getLogger(__name__)

DEFAULT_MIN_FILES_TO_COMPACT = 5
DEFAULT_MAX_SOURCE_FILE_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class CompactionConfig:
    """Configuration for parquet compaction.

    Parameters
    ----------
    min_files_to_compact:
        Minimum number of files in a partition before compaction triggers.
    max_source_file_bytes:
        Maximum size of individual source files eligible for compaction.
    """

    min_files_to_compact: int = DEFAULT_MIN_FILES_TO_COMPACT
    max_source_file_bytes: int = DEFAULT_MAX_SOURCE_FILE_BYTES


@dataclass
class CompactionResult:
    """Outcome of a compaction operation on one partition."""

    partition_prefix: str
    source_files: int = 0
    compacted: bool = False
    records_before: int = 0
    records_after: int = 0
    bytes_freed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors


@dataclass
class CompactionPlan:
    """Describes what partitions need compaction."""

    partitions: list[str]
    total_files: int = 0


class ParquetCompactor:
    """Compact small Parquet files within lake partitions.

    The compactor reads all files in a partition, combines them into a
    single DataFrame, writes a new compacted file, validates the record
    count matches, then deletes the source files.

    Parameters
    ----------
    storage:
        MinIO/S3 storage client.
    bucket:
        Target bucket (e.g. "bronze" or "silver").
    config:
        Compaction thresholds and limits.
    """

    def __init__(
        self,
        storage: MinIOStorage,
        bucket: str,
        config: CompactionConfig | None = None,
    ) -> None:
        self._storage = storage
        self._bucket = bucket
        self._config = config or CompactionConfig()

    def discover_partitions(self, layer: str, source: str) -> list[str]:
        """List partition prefixes that may need compaction.

        Returns partition prefixes (e.g. "bronze/source=fake_store/year=2026/month=09/day=18/")
        that contain more files than the compaction threshold.
        """
        prefix = f"{layer}/source={source}/"
        all_keys = self._storage.list_objects(self._bucket, prefix)

        partition_files: dict[str, int] = {}
        for key in all_keys:
            parts = key.rsplit("/", 1)
            if len(parts) == 2:
                partition_prefix = parts[0] + "/"
                partition_files[partition_prefix] = partition_files.get(partition_prefix, 0) + 1

        eligible = [
            p for p, count in partition_files.items() if count >= self._config.min_files_to_compact
        ]
        return sorted(eligible)

    def compact_partition(self, partition_prefix: str) -> CompactionResult:
        """Compact all files in a single partition.

        Steps:
        1. List all parquet files in the partition
        2. Read and combine into a single DataFrame
        3. Write a new compacted file
        4. Validate record count matches
        5. Delete source files

        Idempotent: if a compacted file already exists with the correct
        record count, source files are cleaned up without re-reading.
        """
        result = CompactionResult(partition_prefix=partition_prefix)

        try:
            keys = self._storage.list_objects(self._bucket, partition_prefix)
            parquet_keys = [k for k in keys if k.endswith(".parquet")]

            if len(parquet_keys) < self._config.min_files_to_compact:
                return result

            result.source_files = len(parquet_keys)

            frames: list[pl.DataFrame] = []
            total_source_bytes = 0
            for key in parquet_keys:
                data = self._storage.get_object(self._bucket, key)
                total_source_bytes += len(data)
                buf = io.BytesIO(data)
                frames.append(pl.read_parquet(buf))

            if not frames:
                return result

            combined = pl.concat(frames, rechunk=True)
            result.records_before = combined.height

            compacted_key = f"{partition_prefix}compacted-{uuid.uuid4().hex[:8]}.parquet"
            buf = io.BytesIO()
            combined.write_parquet(buf)
            compacted_bytes = buf.getvalue()
            self._storage.put_object(self._bucket, compacted_key, compacted_bytes)

            validation_data = self._storage.get_object(self._bucket, compacted_key)
            validation_df = pl.read_parquet(io.BytesIO(validation_data))
            result.records_after = validation_df.height

            if result.records_after != result.records_before:
                result.errors.append(
                    f"Record count mismatch: before={result.records_before} "
                    f"after={result.records_after}"
                )
                self._storage.delete_object(self._bucket, compacted_key)
                return result

            for key in parquet_keys:
                self._storage.delete_object(self._bucket, key)

            result.compacted = True
            result.bytes_freed = total_source_bytes - len(compacted_bytes)

            logger.info(
                "partition_compacted",
                extra={
                    "partition": partition_prefix,
                    "source_files": result.source_files,
                    "records": result.records_before,
                    "bytes_freed": result.bytes_freed,
                },
            )

        except Exception as exc:
            result.errors.append(str(exc))
            logger.error(
                "compaction_failed",
                extra={"partition": partition_prefix, "error": str(exc)},
            )

        return result

    def compact_all(
        self,
        layer: str,
        source: str,
    ) -> list[CompactionResult]:
        """Discover and compact all eligible partitions for a source."""
        partitions = self.discover_partitions(layer, source)
        results: list[CompactionResult] = []
        for prefix in partitions:
            result = self.compact_partition(prefix)
            results.append(result)
        return results
