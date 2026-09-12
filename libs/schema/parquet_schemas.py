"""Explicit PyArrow schema definitions for Bronze and Silver Parquet files.

This module defines canonical schemas with version tracking and compatibility
checking to prevent breaking changes from silently corrupting the data lake.

Schema evolution policy
-----------------------
Compatible changes (can be applied without migration):
- Adding new nullable columns at the end of the schema
- Widening numeric types (int32 -> int64, float32 -> float64)
- Increasing string length limits (if enforced)

Incompatible changes (require version bump + migration plan):
- Removing or renaming existing columns
- Changing column types in non-widening ways (string -> int, etc.)
- Making nullable columns required
- Reordering columns (affects positional readers)
- Changing timestamp precision or timezone handling

Version format: MAJOR.MINOR where MAJOR increments on incompatible changes
and MINOR increments on compatible additions.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import NamedTuple

import pyarrow as pa  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema versions
# ---------------------------------------------------------------------------

BRONZE_SCHEMA_VERSION = "1.0"
SILVER_SCHEMA_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Bronze schema
# ---------------------------------------------------------------------------

# Bronze preserves raw observation data with minimal transformation.
# All fields from ProductObservationEvent envelope + payload are included.
_BRONZE_FIELDS = [
    # Envelope fields
    pa.field("event_id", pa.string(), nullable=False),
    pa.field("event_type", pa.string(), nullable=False),
    pa.field("schema_version", pa.string(), nullable=False),
    pa.field("source", pa.string(), nullable=False),
    pa.field("produced_at", pa.timestamp("us", tz="UTC"), nullable=False),
    # Payload fields
    pa.field("external_id", pa.string(), nullable=False),
    pa.field("name", pa.string(), nullable=True),
    pa.field("url", pa.string(), nullable=True),
    pa.field("price", pa.string(), nullable=True),  # String to preserve Decimal precision
    pa.field("currency", pa.string(), nullable=True),
    pa.field("availability", pa.string(), nullable=False),
    pa.field("category", pa.string(), nullable=True),
    pa.field("collected_at", pa.timestamp("us", tz="UTC"), nullable=False),
]

BRONZE_SCHEMA = pa.schema(
    _BRONZE_FIELDS, metadata={b"schema_version": BRONZE_SCHEMA_VERSION.encode()}
)


def get_bronze_schema() -> pa.Schema:
    """Return the current Bronze Parquet schema."""
    return BRONZE_SCHEMA


# ---------------------------------------------------------------------------
# Silver schema
# ---------------------------------------------------------------------------

# Silver contains validated and normalized data. Currently mirrors Bronze
# structure but may diverge in future (e.g., additional normalized fields).
_SILVER_FIELDS = [
    # Envelope fields
    pa.field("event_id", pa.string(), nullable=False),
    pa.field("event_type", pa.string(), nullable=False),
    pa.field("schema_version", pa.string(), nullable=False),
    pa.field("source", pa.string(), nullable=False),
    pa.field("produced_at", pa.timestamp("us", tz="UTC"), nullable=False),
    # Payload fields
    pa.field("external_id", pa.string(), nullable=False),
    pa.field("name", pa.string(), nullable=True),
    pa.field("url", pa.string(), nullable=True),
    pa.field("price", pa.string(), nullable=True),  # String to preserve Decimal precision
    pa.field("currency", pa.string(), nullable=True),
    pa.field("availability", pa.string(), nullable=False),
    pa.field("category", pa.string(), nullable=True),
    pa.field("collected_at", pa.timestamp("us", tz="UTC"), nullable=False),
]

SILVER_SCHEMA = pa.schema(
    _SILVER_FIELDS, metadata={b"schema_version": SILVER_SCHEMA_VERSION.encode()}
)


def get_silver_schema() -> pa.Schema:
    """Return the current Silver Parquet schema."""
    return SILVER_SCHEMA


# ---------------------------------------------------------------------------
# Compatibility checking
# ---------------------------------------------------------------------------


class SchemaCompatibility(Enum):
    """Result of schema compatibility check between two versions."""

    COMPATIBLE = "compatible"  # New schema can read old data safely
    INCOMPATIBLE = "incompatible"  # Breaking change — requires migration
    IDENTICAL = "identical"  # No changes


class SchemaChange(NamedTuple):
    """Description of a single schema change."""

    field_name: str
    change_type: str  # "added", "removed", "type_changed", "nullability_changed"
    old_value: str | None
    new_value: str | None
    is_breaking: bool


class BronzeSchemaError(Exception):
    """Raised when a Bronze schema validation or compatibility check fails."""

    pass


def _compare_fields(
    old_schema: pa.Schema,
    new_schema: pa.Schema,
) -> list[SchemaChange]:
    """Compare two schemas and return a list of detected changes."""
    changes: list[SchemaChange] = []

    old_fields = {field.name: field for field in old_schema}
    new_fields = {field.name: field for field in new_schema}

    # Check for removed fields
    for name in old_fields:
        if name not in new_fields:
            changes.append(
                SchemaChange(
                    field_name=name,
                    change_type="removed",
                    old_value=str(old_fields[name].type),
                    new_value=None,
                    is_breaking=True,
                )
            )

    # Check for added fields
    for name in new_fields:
        if name not in old_fields:
            new_field = new_fields[name]
            # Adding a non-nullable field is breaking — existing data has no value for it
            is_breaking = not new_field.nullable
            changes.append(
                SchemaChange(
                    field_name=name,
                    change_type="added",
                    old_value=None,
                    new_value=str(new_field.type),
                    is_breaking=is_breaking,
                )
            )

    # Check for type/nullability changes
    for name in old_fields:
        if name in new_fields:
            old_field = old_fields[name]
            new_field = new_fields[name]

            # Type change
            if old_field.type != new_field.type:
                # Check if it's a widening conversion (compatible)
                is_widening = _is_widening_conversion(old_field.type, new_field.type)
                changes.append(
                    SchemaChange(
                        field_name=name,
                        change_type="type_changed",
                        old_value=str(old_field.type),
                        new_value=str(new_field.type),
                        is_breaking=not is_widening,
                    )
                )

            # Nullability change (nullable -> non-nullable is breaking)
            if old_field.nullable and not new_field.nullable:
                changes.append(
                    SchemaChange(
                        field_name=name,
                        change_type="nullability_changed",
                        old_value="nullable",
                        new_value="required",
                        is_breaking=True,
                    )
                )

    return changes


def _is_widening_conversion(old_type: pa.DataType, new_type: pa.DataType) -> bool:
    """Check if a type conversion is widening (safe/compatible)."""
    widening_pairs = {
        (pa.int32(), pa.int64()),
        (pa.float32(), pa.float64()),
    }
    return (old_type, new_type) in widening_pairs


def check_schema_compatibility(
    old_schema: pa.Schema,
    new_schema: pa.Schema,
) -> tuple[SchemaCompatibility, list[SchemaChange]]:
    """Check if a new schema is compatible with an old schema.

    Parameters
    ----------
    old_schema:
        The previously used schema.
    new_schema:
        The proposed new schema.

    Returns
    -------
    tuple[SchemaCompatibility, list[SchemaChange]]
        Compatibility result and list of detected changes.

    Examples
    --------
    >>> compat, changes = check_schema_compatibility(BRONZE_SCHEMA, BRONZE_SCHEMA)
    >>> compat
    <SchemaCompatibility.IDENTICAL: 'identical'>
    >>> len(changes)
    0
    """
    changes = _compare_fields(old_schema, new_schema)

    if not changes:
        return SchemaCompatibility.IDENTICAL, []

    has_breaking = any(c.is_breaking for c in changes)
    if has_breaking:
        return SchemaCompatibility.INCOMPATIBLE, changes

    return SchemaCompatibility.COMPATIBLE, changes


def _check_type_compatible(value: object, pa_type: pa.DataType) -> bool:
    """Check if a Python value is compatible with a PyArrow type for Parquet serialization.

    Polars/PyArrow can serialize these Python types to Parquet:
    - str -> pa.string()
    - int -> pa.int32(), pa.int64(), etc.
    - float -> pa.float32(), pa.float64()
    - bool -> pa.bool_()
    - datetime -> pa.timestamp()
    - None -> any nullable type
    - str (ISO format) -> pa.timestamp() via Polars parsing
    """
    if value is None:
        return True  # Nullability checked separately

    # String values are compatible with string fields
    if pa.types.is_string(pa_type) or pa.types.is_large_string(pa_type):
        return isinstance(value, str)

    # Integer values
    if pa.types.is_integer(pa_type):
        return isinstance(value, int) and not isinstance(value, bool)

    # Float values
    if pa.types.is_floating(pa_type):
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    # Boolean values
    if pa.types.is_boolean(pa_type):
        return isinstance(value, bool)

    # Timestamp values — accept both datetime objects and ISO format strings
    # (Polars will parse ISO strings when writing Parquet)
    if pa.types.is_timestamp(pa_type):
        from datetime import datetime

        return isinstance(value, (datetime, str))

    # Duration values
    if pa.types.is_duration(pa_type):
        from datetime import timedelta

        return isinstance(value, (timedelta, int))

    # For other types, be permissive — let Polars handle conversion
    return True


def validate_row_against_schema(row: dict[str, object], schema: pa.Schema) -> list[str]:
    """Validate a data row against a schema, returning list of errors.

    Checks:
    - Required fields are present and non-null
    - Field values have compatible Python types for the declared PyArrow types

    Parameters
    ----------
    row:
        Dictionary of field names to values.
    schema:
        PyArrow schema to validate against.

    Returns
    -------
    list[str]
        List of validation error messages. Empty list means valid.
    """
    errors: list[str] = []

    schema_fields = {f.name: f for f in schema}

    for field_name, value in row.items():
        if field_name not in schema_fields:
            continue  # Extra fields logged below

        field = schema_fields[field_name]

        # Check required fields
        if not field.nullable and value is None:
            errors.append(f"Required field is null: {field_name}")

        # Check type compatibility (only for non-null values)
        if value is not None and not _check_type_compatible(value, field.type):
            errors.append(
                f"Type mismatch for '{field_name}': "
                f"expected {field.type}, got {type(value).__name__}"
            )

    # Check for missing required fields
    for field in schema:
        if not field.nullable and field.name not in row:
            errors.append(f"Missing required field: {field.name}")

    # Check for unexpected extra fields (informational, not an error)
    extra_fields = set(row.keys()) - schema_fields.keys()
    if extra_fields:
        logger.warning(
            "extra_fields_in_row",
            extra={"fields": list(extra_fields)},
        )

    return errors
