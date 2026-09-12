"""Tests for shared partition-key utilities (TASK-023).

These tests validate:
* deterministic key generation for both Bronze and Silver layers;
* temporal partitioning using collected_at (not produced_at);
* path sanitization of unsafe characters;
* rejection of directory traversal attempts;
* consistent behavior across different sources and dates.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from libs.event_contracts import Availability, ProductObservationEvent, ProductObservationPayload
from libs.partitioning import LakeLayer, build_partition_key, sanitize_path_segment

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_event(
    event_id: str = "evt-001",
    source: str = "test-source",
    collected_at: datetime | None = None,
) -> ProductObservationEvent:
    """Helper to construct a minimal valid event."""
    if collected_at is None:
        collected_at = datetime(2026, 9, 3, 10, 30, 0, tzinfo=timezone.utc)
    return ProductObservationEvent(
        event_id=event_id,
        event_type="product.observation",
        schema_version="1.0",
        source=source,
        produced_at=datetime(2026, 9, 3, 10, 35, 0, tzinfo=timezone.utc),
        payload=ProductObservationPayload(
            external_id="ext-123",
            name="Test Product",
            url="https://example.com/product/123",
            price=Decimal("42.50"),
            currency="USD",
            availability=Availability.IN_STOCK,
            category="electronics",
            collected_at=collected_at,
        ),
    )


# ---------------------------------------------------------------------------
# Sanitization tests
# ---------------------------------------------------------------------------


class TestSanitizePathSegment:
    def test_preserves_safe_characters(self) -> None:
        """Alphanumerics, hyphens, underscores, and dots should pass through."""
        assert sanitize_path_segment("my-safe_source.name123") == "my-safe_source.name123"

    def test_replaces_spaces(self) -> None:
        """Spaces should be replaced with underscores."""
        assert sanitize_path_segment("source with spaces") == "source_with_spaces"

    def test_removes_directory_traversal(self) -> None:
        """Directory traversal sequences should be neutralized."""
        assert sanitize_path_segment("../evil") == "._evil"
        assert sanitize_path_segment("path/../trick") == "path_._trick"

    def test_removes_slashes(self) -> None:
        """Forward and back slashes should be removed."""
        assert sanitize_path_segment("path/to/file") == "path_to_file"
        assert sanitize_path_segment("back\\slash") == "back_slash"

    def test_removes_null_bytes(self) -> None:
        """Null bytes should be stripped."""
        assert sanitize_path_segment("safe\x00value") == "safevalue"

    def test_custom_replacement(self) -> None:
        """Custom replacement character should be used."""
        assert sanitize_path_segment("a b c", replacement="-") == "a-b-c"

    def test_empty_string(self) -> None:
        """Empty string should remain empty."""
        assert sanitize_path_segment("") == ""

    def test_only_unsafe_characters(self) -> None:
        """String with only unsafe chars becomes all replacements."""
        result = sanitize_path_segment("!@#$%")
        assert result == "_____"


# ---------------------------------------------------------------------------
# Partition key tests
# ---------------------------------------------------------------------------


class TestBuildPartitionKey:
    def test_bronze_key_structure(self) -> None:
        """Bronze keys should start with bronze/ prefix."""
        event = make_event(
            source="bestbuy", collected_at=datetime(2026, 9, 15, tzinfo=timezone.utc)
        )
        key = build_partition_key(event, LakeLayer.BRONZE)
        assert key.startswith("bronze/")
        assert "source=bestbuy" in key
        assert "year=2026" in key
        assert "month=09" in key
        assert "day=15" in key
        assert "evt-001.parquet" in key

    def test_silver_key_structure(self) -> None:
        """Silver keys should start with silver/ prefix."""
        event = make_event(
            source="amazon", collected_at=datetime(2026, 12, 25, tzinfo=timezone.utc)
        )
        key = build_partition_key(event, LakeLayer.SILVER)
        assert key.startswith("silver/")
        assert "source=amazon" in key
        assert "year=2026" in key
        assert "month=12" in key
        assert "day=25" in key
        assert "evt-001.parquet" in key

    def test_uses_collected_at_not_produced_at(self) -> None:
        """Partition should use payload.collected_at, not envelope.produced_at."""
        event = make_event(
            collected_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
        )
        # produced_at is 2026-09-03 but collected_at is 2025-06-15
        key = build_partition_key(event, LakeLayer.BRONZE)
        assert "year=2025" in key
        assert "month=06" in key
        assert "day=15" in key
        assert "year=2026" not in key

    def test_deterministic_for_same_event(self) -> None:
        """Same event should always produce the same key."""
        event = make_event()
        key1 = build_partition_key(event, LakeLayer.BRONZE)
        key2 = build_partition_key(event, LakeLayer.BRONZE)
        assert key1 == key2

    def test_different_sources_different_keys(self) -> None:
        """Different sources should produce different partition prefixes."""
        evt_a = make_event(source="source-a")
        evt_b = make_event(source="source-b")
        key_a = build_partition_key(evt_a, LakeLayer.BRONZE)
        key_b = build_partition_key(evt_b, LakeLayer.BRONZE)
        assert key_a != key_b
        assert "source=source-a" in key_a
        assert "source=source-b" in key_b

    def test_different_dates_different_partitions(self) -> None:
        """Events on different dates should go to different day partitions."""
        jan = make_event(collected_at=datetime(2026, 1, 5, tzinfo=timezone.utc))
        dec = make_event(collected_at=datetime(2026, 12, 25, tzinfo=timezone.utc))
        key_jan = build_partition_key(jan, LakeLayer.SILVER)
        key_dec = build_partition_key(dec, LakeLayer.SILVER)
        assert "month=01/day=05" in key_jan
        assert "month=12/day=25" in key_dec

    def test_sanitizes_unsafe_source(self) -> None:
        """Source names with unsafe chars should be sanitized."""
        event = make_event(source="my/../../evil/source")
        key = build_partition_key(event, LakeLayer.BRONZE)
        # Should not contain directory traversal
        assert "../" not in key
        assert "..\\" not in key
        # Each .. becomes a single dot, slashes become underscores
        assert "source=my_._._evil_source" in key

    def test_sanitizes_unsafe_event_id(self) -> None:
        """Event IDs with unsafe chars should be sanitized."""
        event = make_event(event_id="evt/../../../hack")
        key = build_partition_key(event, LakeLayer.SILVER)
        # Should not allow traversal via filename
        assert "../" not in key
        assert "..\\" not in key

    def test_zero_padding_for_single_digit_values(self) -> None:
        """Month and day should be zero-padded."""
        event = make_event(collected_at=datetime(2026, 1, 5, tzinfo=timezone.utc))
        key = build_partition_key(event, LakeLayer.BRONZE)
        assert "month=01" in key
        assert "day=05" in key
        # Not single digit
        assert "month=1/" not in key
        assert "day=5/" not in key

    def test_layer_enum_values(self) -> None:
        """LakeLayer enum should have correct string values."""
        assert LakeLayer.BRONZE.value == "bronze"
        assert LakeLayer.SILVER.value == "silver"

    def test_different_layers_different_prefixes(self) -> None:
        """Same event should produce different layer prefixes."""
        event = make_event()
        bronze_key = build_partition_key(event, LakeLayer.BRONZE)
        silver_key = build_partition_key(event, LakeLayer.SILVER)
        assert bronze_key.startswith("bronze/")
        assert silver_key.startswith("silver/")
        assert bronze_key != silver_key
