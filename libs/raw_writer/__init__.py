"""Raw Writer library — Bronze Parquet persistence (TASK-021).

This package provides the core Bronze-layer writing logic that is consumed
by the ``services/raw-writer`` entry point.  Keeping it in ``libs/`` makes
it importable for testing while maintaining the service boundary.
"""

from libs.raw_writer.bronze_writer import (
    BronzeBatch,
    BronzeWriter,
    build_partition_key,
    event_to_row,
)

__all__ = [
    "BronzeBatch",
    "BronzeWriter",
    "build_partition_key",
    "event_to_row",
]
