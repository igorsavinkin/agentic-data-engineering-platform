"""Parquet schema management for Bronze and Silver layers (TASK-024).

This package provides explicit, version-aware PyArrow schema definitions for
both Bronze and Silver Parquet files, along with compatibility checking to
detect breaking schema changes before they silently corrupt the data lake.
"""

from libs.schema.parquet_schemas import (
    BRONZE_SCHEMA,
    BRONZE_SCHEMA_VERSION,
    SILVER_SCHEMA,
    SILVER_SCHEMA_VERSION,
    BronzeSchemaError,
    SchemaCompatibility,
    check_schema_compatibility,
    get_bronze_schema,
    get_silver_schema,
    validate_row_against_schema,
)

__all__ = [
    "BRONZE_SCHEMA",
    "BRONZE_SCHEMA_VERSION",
    "SILVER_SCHEMA",
    "SILVER_SCHEMA_VERSION",
    "BronzeSchemaError",
    "SchemaCompatibility",
    "check_schema_compatibility",
    "get_bronze_schema",
    "get_silver_schema",
    "validate_row_against_schema",
]
