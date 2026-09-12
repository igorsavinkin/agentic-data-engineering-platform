"""Shared partition-path utilities for Bronze and Silver layers.

This package provides deterministic, layer-aware partition-key generation
that enforces consistent temporal partitioning across the data lake while
safely sanitizing path components to prevent injection or encoding issues.
"""

from libs.partitioning.partition_key import (
    LakeLayer,
    build_partition_key,
    sanitize_path_segment,
)

__all__ = [
    "LakeLayer",
    "build_partition_key",
    "sanitize_path_segment",
]
