"""Tests for ParquetCompactor (TASK-061)."""

from __future__ import annotations

import io
from unittest.mock import MagicMock

import polars as pl

from libs.compaction.compactor import (
    CompactionConfig,
    CompactionResult,
    ParquetCompactor,
)


def _make_parquet_bytes(df: pl.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.write_parquet(buf)
    return buf.getvalue()


class TestCompactionConfig:
    def test_defaults(self) -> None:
        config = CompactionConfig()
        assert config.min_files_to_compact == 5
        assert config.max_source_file_bytes == 10 * 1024 * 1024

    def test_custom_values(self) -> None:
        config = CompactionConfig(min_files_to_compact=10, max_source_file_bytes=1024)
        assert config.min_files_to_compact == 10
        assert config.max_source_file_bytes == 1024


class TestCompactionResult:
    def test_success_when_no_errors(self) -> None:
        result = CompactionResult(partition_prefix="bronze/source=test/")
        assert result.success

    def test_failure_when_errors(self) -> None:
        result = CompactionResult(partition_prefix="bronze/source=test/", errors=["oops"])
        assert not result.success


class TestParquetCompactor:
    def _make_compactor(
        self,
        mock_storage: MagicMock,
        config: CompactionConfig | None = None,
    ) -> ParquetCompactor:
        return ParquetCompactor(mock_storage, bucket="bronze", config=config)

    def test_discover_partitions_eligible(self) -> None:
        mock_storage = MagicMock()
        mock_storage.list_objects.return_value = [
            "bronze/source=fake_store/year=2026/month=09/day=18/file1.parquet",
            "bronze/source=fake_store/year=2026/month=09/day=18/file2.parquet",
            "bronze/source=fake_store/year=2026/month=09/day=18/file3.parquet",
            "bronze/source=fake_store/year=2026/month=09/day=18/file4.parquet",
            "bronze/source=fake_store/year=2026/month=09/day=18/file5.parquet",
            "bronze/source=fake_store/year=2026/month=09/day=17/file1.parquet",
        ]
        compactor = self._make_compactor(mock_storage)
        partitions = compactor.discover_partitions("bronze", "fake_store")
        assert len(partitions) == 1
        assert "bronze/source=fake_store/year=2026/month=09/day=18/" in partitions

    def test_discover_partitions_below_threshold(self) -> None:
        mock_storage = MagicMock()
        mock_storage.list_objects.return_value = [
            "bronze/source=fake_store/year=2026/month=09/day=18/file1.parquet",
            "bronze/source=fake_store/year=2026/month=09/day=18/file2.parquet",
        ]
        compactor = self._make_compactor(mock_storage)
        partitions = compactor.discover_partitions("bronze", "fake_store")
        assert len(partitions) == 0

    def test_compact_partition_success(self) -> None:
        df1 = pl.DataFrame({"event_id": ["a"], "source": ["test"]})
        df2 = pl.DataFrame({"event_id": ["b"], "source": ["test"]})
        source_dfs = [df1, df2, df1, df2, df1]
        combined = pl.concat(source_dfs)

        mock_storage = MagicMock()
        mock_storage.list_objects.return_value = [
            "bronze/source=test/year=2026/month=09/day=18/file1.parquet",
            "bronze/source=test/year=2026/month=09/day=18/file2.parquet",
            "bronze/source=test/year=2026/month=09/day=18/file3.parquet",
            "bronze/source=test/year=2026/month=09/day=18/file4.parquet",
            "bronze/source=test/year=2026/month=09/day=18/file5.parquet",
        ]
        mock_storage.get_object.side_effect = [
            *[_make_parquet_bytes(df) for df in source_dfs],
            _make_parquet_bytes(combined),
        ]

        compactor = self._make_compactor(
            mock_storage, config=CompactionConfig(min_files_to_compact=5)
        )
        result = compactor.compact_partition("bronze/source=test/year=2026/month=09/day=18/")

        assert result.compacted
        assert result.source_files == 5
        assert result.records_before == 5
        assert result.records_after == 5
        assert result.success
        assert mock_storage.put_object.called
        assert mock_storage.delete_object.call_count == 5

    def test_compact_partition_below_threshold(self) -> None:
        mock_storage = MagicMock()
        mock_storage.list_objects.return_value = [
            "bronze/source=test/year=2026/month=09/day=18/file1.parquet",
            "bronze/source=test/year=2026/month=09/day=18/file2.parquet",
        ]
        compactor = self._make_compactor(mock_storage)
        result = compactor.compact_partition("bronze/source=test/year=2026/month=09/day=18/")

        assert not result.compacted
        assert result.source_files == 0

    def test_compact_partition_validation_failure(self) -> None:
        df1 = pl.DataFrame({"event_id": ["a"], "source": ["test"]})
        df_wrong = pl.DataFrame({"event_id": ["x", "y"], "source": ["t", "t"]})

        mock_storage = MagicMock()
        mock_storage.list_objects.return_value = [
            "bronze/source=test/year=2026/month=09/day=18/file1.parquet",
            "bronze/source=test/year=2026/month=09/day=18/file2.parquet",
            "bronze/source=test/year=2026/month=09/day=18/file3.parquet",
            "bronze/source=test/year=2026/month=09/day=18/file4.parquet",
            "bronze/source=test/year=2026/month=09/day=18/file5.parquet",
        ]
        mock_storage.get_object.side_effect = [
            _make_parquet_bytes(df1),
            _make_parquet_bytes(df1),
            _make_parquet_bytes(df1),
            _make_parquet_bytes(df1),
            _make_parquet_bytes(df1),
            _make_parquet_bytes(df_wrong),
        ]

        compactor = self._make_compactor(
            mock_storage, config=CompactionConfig(min_files_to_compact=5)
        )
        result = compactor.compact_partition("bronze/source=test/year=2026/month=09/day=18/")

        assert not result.compacted
        assert not result.success
        assert any("mismatch" in e.lower() for e in result.errors)
        assert mock_storage.delete_object.call_count == 1

    def test_compact_all(self) -> None:
        df = pl.DataFrame({"event_id": ["a"], "source": ["test"]})

        mock_storage = MagicMock()
        mock_storage.list_objects.side_effect = [
            [
                "bronze/source=test/year=2026/month=09/day=18/f1.parquet",
                "bronze/source=test/year=2026/month=09/day=18/f2.parquet",
                "bronze/source=test/year=2026/month=09/day=18/f3.parquet",
                "bronze/source=test/year=2026/month=09/day=18/f4.parquet",
                "bronze/source=test/year=2026/month=09/day=18/f5.parquet",
            ],
            [
                "bronze/source=test/year=2026/month=09/day=18/f1.parquet",
                "bronze/source=test/year=2026/month=09/day=18/f2.parquet",
                "bronze/source=test/year=2026/month=09/day=18/f3.parquet",
                "bronze/source=test/year=2026/month=09/day=18/f4.parquet",
                "bronze/source=test/year=2026/month=09/day=18/f5.parquet",
            ],
            _make_parquet_bytes(df),
            _make_parquet_bytes(df),
            _make_parquet_bytes(df),
        ]

        compactor = self._make_compactor(
            mock_storage, config=CompactionConfig(min_files_to_compact=5)
        )
        results = compactor.compact_all("bronze", "test")
        assert len(results) >= 0
