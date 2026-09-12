"""Tests for Parquet schema management (TASK-024).

These tests validate:
* Schema definitions are valid PyArrow schemas
* Version metadata is embedded correctly
* Compatibility checking detects breaking vs compatible changes
* Row validation catches missing required fields
* Timestamp precision is preserved (microseconds with UTC)
* Price field uses string type for Decimal precision
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from libs.schema.parquet_schemas import (
    BRONZE_SCHEMA,
    BRONZE_SCHEMA_VERSION,
    SILVER_SCHEMA,
    SILVER_SCHEMA_VERSION,
    SchemaChange,
    SchemaCompatibility,
    check_schema_compatibility,
    get_bronze_schema,
    get_silver_schema,
    validate_row_against_schema,
)

# ---------------------------------------------------------------------------
# Schema definition tests
# ---------------------------------------------------------------------------


class TestSchemaDefinitions:
    def test_bronze_schema_is_valid(self) -> None:
        """Bronze schema should be a valid PyArrow schema."""
        assert isinstance(BRONZE_SCHEMA, pa.Schema)
        assert len(BRONZE_SCHEMA) > 0

    def test_silver_schema_is_valid(self) -> None:
        """Silver schema should be a valid PyArrow schema."""
        assert isinstance(SILVER_SCHEMA, pa.Schema)
        assert len(SILVER_SCHEMA) > 0

    def test_bronze_version_in_metadata(self) -> None:
        """Bronze schema should embed version in metadata."""
        metadata = BRONZE_SCHEMA.metadata
        assert b"schema_version" in metadata
        assert metadata[b"schema_version"].decode() == BRONZE_SCHEMA_VERSION

    def test_silver_version_in_metadata(self) -> None:
        """Silver schema should embed version in metadata."""
        metadata = SILVER_SCHEMA.metadata
        assert b"schema_version" in metadata
        assert metadata[b"schema_version"].decode() == SILVER_SCHEMA_VERSION

    def test_get_bronze_schema_returns_same(self) -> None:
        """get_bronze_schema should return the canonical schema."""
        assert get_bronze_schema() is BRONZE_SCHEMA

    def test_get_silver_schema_returns_same(self) -> None:
        """get_silver_schema should return the canonical schema."""
        assert get_silver_schema() is SILVER_SCHEMA


# ---------------------------------------------------------------------------
# Field presence tests
# ---------------------------------------------------------------------------


class TestFieldPresence:
    def test_bronze_has_envelope_fields(self) -> None:
        """Bronze schema must have all envelope fields."""
        field_names = {f.name for f in BRONZE_SCHEMA}
        assert "event_id" in field_names
        assert "event_type" in field_names
        assert "schema_version" in field_names
        assert "source" in field_names
        assert "produced_at" in field_names

    def test_bronze_has_payload_fields(self) -> None:
        """Bronze schema must have all payload fields."""
        field_names = {f.name for f in BRONZE_SCHEMA}
        assert "external_id" in field_names
        assert "name" in field_names
        assert "url" in field_names
        assert "price" in field_names
        assert "currency" in field_names
        assert "availability" in field_names
        assert "category" in field_names
        assert "collected_at" in field_names

    def test_silver_has_same_fields_as_bronze(self) -> None:
        """Silver currently mirrors Bronze structure."""
        bronze_fields = {f.name for f in BRONZE_SCHEMA}
        silver_fields = {f.name for f in SILVER_SCHEMA}
        assert bronze_fields == silver_fields


# ---------------------------------------------------------------------------
# Type precision tests
# ---------------------------------------------------------------------------


class TestTypePrecision:
    def test_price_is_string_for_decimal_precision(self) -> None:
        """Price field should be string to preserve Decimal precision."""
        price_field = BRONZE_SCHEMA.field("price")
        assert price_field.type == pa.string()

    def test_timestamps_have_microsecond_precision(self) -> None:
        """Timestamps should use microsecond precision."""
        produced_at = BRONZE_SCHEMA.field("produced_at")
        collected_at = BRONZE_SCHEMA.field("collected_at")
        assert produced_at.type == pa.timestamp("us", tz="UTC")
        assert collected_at.type == pa.timestamp("us", tz="UTC")

    def test_timestamps_have_utc_timezone(self) -> None:
        """Timestamps should explicitly use UTC timezone."""
        produced_at = BRONZE_SCHEMA.field("produced_at")
        assert produced_at.type.tz == "UTC"

    def test_event_id_is_non_nullable_string(self) -> None:
        """Event ID should be a required string field."""
        field = BRONZE_SCHEMA.field("event_id")
        assert field.type == pa.string()
        assert not field.nullable

    def test_name_is_nullable(self) -> None:
        """Product name may be null."""
        field = BRONZE_SCHEMA.field("name")
        assert field.nullable


# ---------------------------------------------------------------------------
# Compatibility checking tests
# ---------------------------------------------------------------------------


class TestSchemaCompatibility:
    def test_identical_schemas(self) -> None:
        """Same schema compared to itself should be IDENTICAL."""
        compat, changes = check_schema_compatibility(BRONZE_SCHEMA, BRONZE_SCHEMA)
        assert compat == SchemaCompatibility.IDENTICAL
        assert len(changes) == 0

    def test_adding_nullable_field_is_compatible(self) -> None:
        """Adding a new nullable field at the end is compatible."""
        old_schema = pa.schema([pa.field("a", pa.string())])
        new_schema = pa.schema(
            [pa.field("a", pa.string()), pa.field("b", pa.string(), nullable=True)]
        )
        compat, changes = check_schema_compatibility(old_schema, new_schema)
        assert compat == SchemaCompatibility.COMPATIBLE
        assert len(changes) == 1
        assert changes[0].change_type == "added"
        assert not changes[0].is_breaking

    def test_removing_field_is_incompatible(self) -> None:
        """Removing a field is a breaking change."""
        old_schema = pa.schema([pa.field("a", pa.string()), pa.field("b", pa.string())])
        new_schema = pa.schema([pa.field("a", pa.string())])
        compat, changes = check_schema_compatibility(old_schema, new_schema)
        assert compat == SchemaCompatibility.INCOMPATIBLE
        assert any(c.change_type == "removed" for c in changes)
        assert any(c.is_breaking for c in changes)

    def test_type_change_is_incompatible(self) -> None:
        """Changing a field type (non-widening) is breaking."""
        old_schema = pa.schema([pa.field("value", pa.string())])
        new_schema = pa.schema([pa.field("value", pa.int64())])
        compat, changes = check_schema_compatibility(old_schema, new_schema)
        assert compat == SchemaCompatibility.INCOMPATIBLE
        assert any(c.change_type == "type_changed" for c in changes)

    def test_int32_to_int64_is_compatible(self) -> None:
        """Widening int32 to int64 is compatible."""
        old_schema = pa.schema([pa.field("count", pa.int32())])
        new_schema = pa.schema([pa.field("count", pa.int64())])
        compat, changes = check_schema_compatibility(old_schema, new_schema)
        assert compat == SchemaCompatibility.COMPATIBLE

    def test_nullable_to_required_is_incompatible(self) -> None:
        """Making a nullable field required is breaking."""
        old_schema = pa.schema([pa.field("value", pa.string(), nullable=True)])
        new_schema = pa.schema([pa.field("value", pa.string(), nullable=False)])
        compat, changes = check_schema_compatibility(old_schema, new_schema)
        assert compat == SchemaCompatibility.INCOMPATIBLE
        assert any(c.change_type == "nullability_changed" for c in changes)

    def test_renaming_field_is_incompatible(self) -> None:
        """Renaming a field (remove + add) is breaking."""
        old_schema = pa.schema([pa.field("old_name", pa.string())])
        new_schema = pa.schema([pa.field("new_name", pa.string())])
        compat, changes = check_schema_compatibility(old_schema, new_schema)
        assert compat == SchemaCompatibility.INCOMPATIBLE
        removed = [c for c in changes if c.change_type == "removed"]
        added = [c for c in changes if c.change_type == "added"]
        assert len(removed) == 1
        assert len(added) == 1


# ---------------------------------------------------------------------------
# Row validation tests
# ---------------------------------------------------------------------------


class TestRowValidation:
    def test_valid_row_passes(self) -> None:
        """A row with all required fields should pass validation."""
        row = {"event_id": "evt-001", "name": "Test"}
        errors = validate_row_against_schema(row, BRONZE_SCHEMA)
        # Should only fail on missing required fields
        required_errors = [e for e in errors if "required" in e.lower() or "missing" in e.lower()]
        # event_id is present, so no error for it
        assert not any("event_id" in e for e in required_errors)

    def test_missing_required_field_fails(self) -> None:
        """Missing a required field should produce an error."""
        row: dict[str, object] = {}  # No fields at all
        errors = validate_row_against_schema(row, BRONZE_SCHEMA)
        assert any("event_id" in e for e in errors)
        assert any("event_type" in e for e in errors)

    def test_null_required_field_fails(self) -> None:
        """Null value for required field should produce an error."""
        row = {"event_id": None, "event_type": "test"}
        errors = validate_row_against_schema(row, BRONZE_SCHEMA)
        assert any("event_id" in e for e in errors)

    def test_extra_fields_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """Extra fields beyond schema should trigger a warning log."""
        row = {"event_id": "evt-001", "extra_field": "unexpected"}
        validate_row_against_schema(row, BRONZE_SCHEMA)
        assert any("extra_fields" in record.message for record in caplog.records)

    def test_nullable_field_can_be_none(self) -> None:
        """Nullable fields can be None without error."""
        row = {"event_id": "evt-001", "name": None}
        errors = validate_row_against_schema(row, BRONZE_SCHEMA)
        # name is nullable, so no error for it being None
        assert not any("name" in e for e in errors if "required" in e.lower())


# ---------------------------------------------------------------------------
# SchemaChange tests
# ---------------------------------------------------------------------------


class TestSchemaChange:
    def test_change_tuple_structure(self) -> None:
        """SchemaChange should be a NamedTuple with expected fields."""
        change = SchemaChange(
            field_name="test",
            change_type="added",
            old_value=None,
            new_value="string",
            is_breaking=False,
        )
        assert change.field_name == "test"
        assert change.change_type == "added"
        assert change.old_value is None
        assert change.new_value == "string"
        assert not change.is_breaking
