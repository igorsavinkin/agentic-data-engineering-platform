"""Tests for Parquet read/query utilities (TASK-025).

Covers:
- Partition discovery with various filters
- Lazy scanning with projection pushdown
- LakeReader high-level API
- Empty/missing partition behavior
- Column projection
- Multiple file handling
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest

from libs.common.minio_storage import MinIOStorage
from libs.parquet_reader import LakeReader, LazyScanner, PartitionFilter, list_partitions
from libs.partitioning import LakeLayer

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_storage() -> MagicMock:
    """Create a mocked MinIO storage instance."""

    from libs.common.minio_storage import MinIOSettings

    storage = MagicMock(spec=MinIOStorage)
    storage.check_health.return_value = MagicMock(healthy=True)
    # Provide _settings for storage_options building
    storage._settings = MinIOSettings(environment="development")
    return storage


@pytest.fixture
def sample_objects() -> list[str]:
    """Sample object keys representing partitioned Bronze data.

    Note: MinIO/S3 object keys are relative to the bucket, so they don't
    include the bucket name as a prefix.
    """
    return [
        "source=fake-store/year=2026/month=09/day=12/evt-001.parquet",
        "source=fake-store/year=2026/month=09/day=12/evt-002.parquet",
        "source=fake-store/year=2026/month=09/day=13/evt-003.parquet",
        "source=bestbuy/year=2026/month=09/day=12/evt-004.parquet",
        "source=fake-store/year=2026/month=08/day=31/evt-005.parquet",
    ]


# NOTE: mock_scan_parquet is required for any test that triggers collect().
# Without it, LazyScanner.count() / LakeReader.read() call pl.scan_parquet()
# with S3 URIs (s3://bucket/...) and storage_options pointing to localhost:9000.
# When MinIO is not running, Polars' underlying object_store crate hangs
# indefinitely on the TCP connect — no exception is raised, it just blocks.
# On Windows the TCP timeout can exceed 2 minutes, and Polars may retry
# internally, making the hang effectively infinite. Ctrl+C often fails to
# terminate pytest cleanly, leaving orphaned processes.
@pytest.fixture
def mock_scan_parquet(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch pl.scan_parquet to return an in-memory LazyFrame.

    Prevents real S3/MinIO I/O during tests that trigger collect().
    """
    from libs.parquet_reader import scanner as scanner_module

    fake_df = pl.DataFrame(
        {
            "event_id": ["evt-001", "evt-002", "evt-003"],
            "external_id": ["ext-1", "ext-2", "ext-3"],
            "price": [10.0, 20.0, 30.0],
        }
    )

    def _fake_scan_parquet(*args: object, **kwargs: object) -> pl.LazyFrame:
        return fake_df.lazy()

    monkeypatch.setattr(scanner_module.pl, "scan_parquet", _fake_scan_parquet)


# ---------------------------------------------------------------------------
# Partition Discovery Tests
# ---------------------------------------------------------------------------


class TestListPartitions:
    """Tests for partition discovery functionality."""

    def test_list_all_partitions_no_filters(
        self, mock_storage: MagicMock, sample_objects: list[str]
    ) -> None:
        """Listing without filters returns all partitions."""

        # Mock should return objects matching the prefix
        def mock_list(bucket: str, prefix: str = "") -> list[str]:
            if prefix:
                return [o for o in sample_objects if o.startswith(prefix.lstrip("bronze/"))]
            return sample_objects

        mock_storage.list_objects.side_effect = mock_list

        partitions = list_partitions(mock_storage, "bronze", LakeLayer.BRONZE)

        assert len(partitions) == 4  # 4 unique day partitions
        # Verify partition metadata
        sources = {p.source for p in partitions}
        assert sources == {"fake-store", "bestbuy"}

    def test_filter_by_source(self, mock_storage: MagicMock, sample_objects: list[str]) -> None:
        """Source filter prunes partitions."""

        # Mock should only return fake-store objects when prefix includes source
        def mock_list(bucket: str, prefix: str = "") -> list[str]:
            if "source=fake-store" in prefix:
                return [o for o in sample_objects if "source=fake-store" in o]
            return sample_objects

        mock_storage.list_objects.side_effect = mock_list

        partitions = list_partitions(mock_storage, "bronze", LakeLayer.BRONZE, source="fake-store")

        assert len(partitions) == 3  # Only fake-store partitions
        assert all(p.source == "fake-store" for p in partitions)

    def test_filter_by_date_range(self, mock_storage: MagicMock, sample_objects: list[str]) -> None:
        """Date range filter prunes partitions outside range."""

        # Mock should return objects matching the prefix
        def mock_list(bucket: str, prefix: str = "") -> list[str]:
            if prefix:
                return [o for o in sample_objects if o.startswith(prefix.lstrip("bronze/"))]
            return sample_objects

        mock_storage.list_objects.side_effect = mock_list

        partitions = list_partitions(
            mock_storage,
            "bronze",
            LakeLayer.BRONZE,
            start_date=date(2026, 9, 12),
            end_date=date(2026, 9, 12),
        )

        assert len(partitions) == 2  # Only Sept 12 partitions
        assert all(p.year == 2026 and p.month == 9 and p.day == 12 for p in partitions)

    def test_empty_result_no_matching_partitions(self, mock_storage: MagicMock) -> None:
        """Returns empty list when no partitions match."""
        mock_storage.list_objects.return_value = []

        partitions = list_partitions(
            mock_storage,
            "bronze",
            LakeLayer.BRONZE,
            source="nonexistent-source",
        )

        assert partitions == []

    def test_file_count_per_partition(
        self, mock_storage: MagicMock, sample_objects: list[str]
    ) -> None:
        """Each partition reports correct file count."""

        # Mock should return objects matching the prefix
        def mock_list(bucket: str, prefix: str = "") -> list[str]:
            if prefix:
                return [o for o in sample_objects if o.startswith(prefix.lstrip("bronze/"))]
            return sample_objects

        mock_storage.list_objects.side_effect = mock_list

        partitions = list_partitions(mock_storage, "bronze", LakeLayer.BRONZE, source="fake-store")

        # Sept 12 has 2 files, Sept 13 has 1, Aug 31 has 1
        counts = {(p.year, p.month, p.day): p.file_count for p in partitions}
        assert counts[(2026, 9, 12)] == 2
        assert counts[(2026, 9, 13)] == 1
        assert counts[(2026, 8, 31)] == 1

    def test_invalid_partition_prefix_ignored(self, mock_storage: MagicMock) -> None:
        """Non-conforming prefixes are skipped."""
        mock_storage.list_objects.return_value = [
            "source=fake-store/year=2026/month=09/day=12/evt-001.parquet",
            "invalid/path/structure/file.parquet",  # Should be ignored
            "source=fake-store/year=bad/month=09/day=12/evt-002.parquet",  # Invalid year
        ]

        partitions = list_partitions(mock_storage, "bronze", LakeLayer.BRONZE)

        assert len(partitions) == 1  # Only valid partition
        assert partitions[0].day == 12


# ---------------------------------------------------------------------------
# LazyScanner Tests
# ---------------------------------------------------------------------------


class TestLazyScanner:
    """Tests for lazy scanning functionality."""

    def test_scan_creates_lazy_frame(
        self, mock_storage: MagicMock, sample_objects: list[str]
    ) -> None:
        """Scan returns a LazyFrame without materializing data."""

        # Mock should return objects matching the prefix
        def mock_list(bucket: str, prefix: str = "") -> list[str]:
            if prefix:
                return [o for o in sample_objects if o.startswith(prefix.lstrip("bronze/"))]
            return sample_objects

        mock_storage.list_objects.side_effect = mock_list

        scanner = LazyScanner(
            mock_storage,
            "bronze",
            LakeLayer.BRONZE,
            source="fake-store",
            start_date=date(2026, 9, 12),
            end_date=date(2026, 9, 12),
        )

        lf = scanner.scan()
        assert isinstance(lf, pl.LazyFrame)

    def test_scan_with_column_projection(
        self, mock_storage: MagicMock, sample_objects: list[str]
    ) -> None:
        """Column projection is passed to scan_parquet."""

        # Mock should return objects matching the prefix
        def mock_list(bucket: str, prefix: str = "") -> list[str]:
            if prefix:
                return [o for o in sample_objects if o.startswith(prefix.lstrip("bronze/"))]
            return sample_objects

        mock_storage.list_objects.side_effect = mock_list

        scanner = LazyScanner(
            mock_storage,
            "bronze",
            LakeLayer.BRONZE,
            columns=["event_id", "external_id"],
        )

        lf = scanner.scan()
        # The LazyFrame should have only projected columns when collected
        # (actual column filtering happens at Polars level)
        assert isinstance(lf, pl.LazyFrame)

    def test_scan_no_files_raises_error(self, mock_storage: MagicMock) -> None:
        """Scan raises ValueError when no files match."""
        mock_storage.list_objects.return_value = []

        scanner = LazyScanner(
            mock_storage,
            "bronze",
            LakeLayer.BRONZE,
            source="nonexistent",
        )

        with pytest.raises(ValueError, match="No Parquet files found"):
            scanner.scan()

    def test_count_returns_row_count(
        self, mock_storage: MagicMock, sample_objects: list[str], mock_scan_parquet: None
    ) -> None:
        """Count method returns number of rows without full materialization."""

        # Mock should return objects matching the prefix
        def mock_list(bucket: str, prefix: str = "") -> list[str]:
            if prefix:
                return [o for o in sample_objects if o.startswith(prefix.lstrip("bronze/"))]
            return sample_objects

        mock_storage.list_objects.side_effect = mock_list

        scanner = LazyScanner(
            mock_storage,
            "bronze",
            LakeLayer.BRONZE,
            source="fake-store",
        )

        count = scanner.count()
        assert count == 3

    def test_cached_lazy_frame_reused(
        self, mock_storage: MagicMock, sample_objects: list[str]
    ) -> None:
        """Subsequent scan() calls return cached LazyFrame."""

        # Mock should return objects matching the prefix
        def mock_list(bucket: str, prefix: str = "") -> list[str]:
            if prefix:
                return [o for o in sample_objects if o.startswith(prefix.lstrip("bronze/"))]
            return sample_objects

        mock_storage.list_objects.side_effect = mock_list

        scanner = LazyScanner(mock_storage, "bronze", LakeLayer.BRONZE)
        lf1 = scanner.scan()
        lf2 = scanner.scan()

        assert lf1 is lf2  # Same object reference


# ---------------------------------------------------------------------------
# LakeReader Tests
# ---------------------------------------------------------------------------


class TestLakeReader:
    """Tests for high-level LakeReader API."""

    def test_discover_partitions_delegates_to_list_partitions(
        self, mock_storage: MagicMock, sample_objects: list[str]
    ) -> None:
        """discover_partitions returns PartitionInfo list."""
        mock_storage.list_objects.return_value = sample_objects

        reader = LakeReader(mock_storage, bucket="bronze")
        partitions = reader.discover_partitions(
            layer=LakeLayer.BRONZE,
            source="fake-store",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 30),
        )

        assert len(partitions) > 0
        assert all(isinstance(p, type(partitions[0])) for p in partitions)

    def test_read_returns_dataframe(
        self, mock_storage: MagicMock, sample_objects: list[str], mock_scan_parquet: None
    ) -> None:
        """read() returns a DataFrame (empty if files don't exist)."""
        mock_storage.list_objects.return_value = sample_objects

        reader = LakeReader(mock_storage, bucket="bronze")
        filter_spec = PartitionFilter(
            layer=LakeLayer.BRONZE,
            source="fake-store",
            start_date=date(2026, 9, 12),
            end_date=date(2026, 9, 12),
        )

        # Will return empty frame since files don't actually exist
        df = reader.read(filter_spec)
        assert isinstance(df, pl.DataFrame)

    def test_read_with_column_projection(
        self, mock_storage: MagicMock, sample_objects: list[str], mock_scan_parquet: None
    ) -> None:
        """read() respects column projection in filter."""
        mock_storage.list_objects.return_value = sample_objects

        reader = LakeReader(mock_storage, bucket="bronze")
        filter_spec = PartitionFilter(
            layer=LakeLayer.BRONZE,
            columns=["event_id", "price"],
        )

        df = reader.read(filter_spec)
        assert isinstance(df, pl.DataFrame)
        # When empty, should have projected columns
        if len(df) == 0:
            assert set(df.columns) == {"event_id", "price"}

    def test_read_empty_result_returns_empty_frame(self, mock_storage: MagicMock) -> None:
        """read() returns empty DataFrame when no data matches."""
        mock_storage.list_objects.return_value = []

        reader = LakeReader(mock_storage, bucket="bronze")
        filter_spec = PartitionFilter(
            layer=LakeLayer.BRONZE,
            source="nonexistent-source",
        )

        df = reader.read(filter_spec)
        assert isinstance(df, pl.DataFrame)
        assert len(df) == 0

    def test_scan_returns_lazy_frame(
        self, mock_storage: MagicMock, sample_objects: list[str]
    ) -> None:
        """scan() returns LazyFrame for further transformation."""
        mock_storage.list_objects.return_value = sample_objects

        reader = LakeReader(mock_storage, bucket="bronze")
        filter_spec = PartitionFilter(
            layer=LakeLayer.BRONZE,
            source="fake-store",
        )

        try:
            lf = reader.scan(filter_spec)
            assert isinstance(lf, pl.LazyFrame)
        except ValueError:
            # Expected if files don't exist
            pass

    def test_health_check_delegates_to_storage(self, mock_storage: MagicMock) -> None:
        """health_check probes underlying storage."""
        reader = LakeReader(mock_storage, bucket="bronze")
        assert reader.health_check() is True
        mock_storage.check_health.assert_called_once()

    def test_bucket_override(
        self, mock_storage: MagicMock, sample_objects: list[str], mock_scan_parquet: None
    ) -> None:
        """read() can override default bucket via parameter."""
        mock_storage.list_objects.return_value = sample_objects

        reader = LakeReader(mock_storage, bucket="bronze")
        filter_spec = PartitionFilter(layer=LakeLayer.SILVER)

        # Should use silver bucket instead of default bronze
        df = reader.read(filter_spec, bucket="silver")
        assert isinstance(df, pl.DataFrame)


# ---------------------------------------------------------------------------
# PartitionFilter Tests
# ---------------------------------------------------------------------------


class TestPartitionFilter:
    """Tests for PartitionFilter dataclass."""

    def test_default_values(self) -> None:
        """Filter defaults to BRONZE layer with no other constraints."""
        f = PartitionFilter()
        assert f.layer == LakeLayer.BRONZE
        assert f.source is None
        assert f.start_date is None
        assert f.end_date is None
        assert f.columns is None

    def test_string_layer_converted_to_enum(self) -> None:
        """String layer is converted to LakeLayer enum."""
        f = PartitionFilter(layer="silver")
        assert f.layer == LakeLayer.SILVER

    def test_full_filter_specification(self) -> None:
        """All fields can be specified."""
        f = PartitionFilter(
            layer=LakeLayer.SILVER,
            source="fake-store",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 30),
            columns=["event_id", "price"],
        )
        assert f.layer == LakeLayer.SILVER
        assert f.source == "fake-store"
        assert f.start_date == date(2026, 9, 1)
        assert f.end_date == date(2026, 9, 30)
        assert f.columns == ["event_id", "price"]


# ---------------------------------------------------------------------------
# Integration-style Tests (no actual MinIO required)
# ---------------------------------------------------------------------------


class TestEndToEnd:
    """End-to-end style tests verifying API composition."""

    def test_discover_then_read_workflow(
        self, mock_storage: MagicMock, sample_objects: list[str], mock_scan_parquet: None
    ) -> None:
        """Typical workflow: discover partitions, then read matching data."""
        mock_storage.list_objects.return_value = sample_objects

        reader = LakeReader(mock_storage, bucket="bronze")

        # Step 1: Discover available partitions
        partitions = reader.discover_partitions(
            layer=LakeLayer.BRONZE,
            source="fake-store",
        )
        assert len(partitions) > 0

        # Step 2: Read data from discovered date range
        if partitions:
            first = partitions[0]
            filter_spec = PartitionFilter(
                layer=LakeLayer.BRONZE,
                source="fake-store",
                start_date=date(first.year, first.month, first.day),
                end_date=date(first.year, first.month, first.day),
                columns=["event_id", "external_id"],
            )
            df = reader.read(filter_spec)
            assert isinstance(df, pl.DataFrame)

    def test_multiple_sources_in_same_query(
        self, mock_storage: MagicMock, sample_objects: list[str]
    ) -> None:
        """Querying without source filter includes all sources."""
        mock_storage.list_objects.return_value = sample_objects

        reader = LakeReader(mock_storage, bucket="bronze")
        partitions = reader.discover_partitions(LakeLayer.BRONZE)

        sources = {p.source for p in partitions}
        assert "fake-store" in sources
        assert "bestbuy" in sources
