"""Lake Writer library — Silver Parquet persistence (TASK-022).

This package provides the core Silver-layer writing logic that is consumed
by the ``services/lake-writer`` entry point.  Keeping it in ``libs/`` makes
it importable for testing while maintaining the service boundary.
"""

from libs.lake_writer.silver_writer import (
    SilverBatch,
    SilverWriter,
    build_silver_partition_key,
    validated_event_to_row,
)

__all__ = [
    "SilverBatch",
    "SilverWriter",
    "build_silver_partition_key",
    "validated_event_to_row",
]
