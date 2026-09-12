"""Canonical partition-key builder for Bronze and Silver Parquet files.

This module centralizes the logic for generating deterministic S3/MinIO keys
from a ``ProductObservationEvent`` so that both Bronze and Silver writers use
the same temporal partitioning strategy with consistent path sanitization.

Partition layout
----------------
Both layers follow the same structure:

    <layer>/source=<source>/year=<YYYY>/month=<MM>/day=<DD>/<event_id>.parquet

where ``<layer>`` is either ``bronze`` or ``silver``.  The leaf filename is
always the ``event_id`` to guarantee idempotent writes across replays.

Temporal dimension
------------------
The partition uses ``payload.collected_at`` (observation time) rather than
``produced_at`` (envelope ingestion time).  This ensures events are grouped
by when the data was actually observed in the source system, which is critical
for accurate time-range queries and cross-source joins.

Path sanitization
-----------------
All dynamic segments (source, event_id) are sanitized to remove characters
that could break filesystem paths or enable directory traversal attacks.
Only alphanumeric characters, hyphens, underscores, and dots are retained.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from libs.event_contracts import ProductObservationEvent


class LakeLayer(str, Enum):
    """Data lake layer identifiers used in partition prefixes."""

    BRONZE = "bronze"
    SILVER = "silver"


# Characters allowed in path segments: alphanumerics, hyphen, underscore, dot
_SAFE_SEGMENT_RE = re.compile(r"[^a-zA-Z0-9\-_.]")


def sanitize_path_segment(segment: str, replacement: str = "_") -> str:
    """Sanitize a string for safe use in an S3/MinIO path segment.

    Removes or replaces characters that could cause filesystem issues or
    enable directory traversal (e.g. ``..``, ``/``, ``\\``, null bytes).

    Parameters
    ----------
    segment:
        Raw string value (e.g. source name, event ID).
    replacement:
        Character to substitute for unsafe characters. Defaults to ``_``.

    Returns
    -------
    str
        Sanitized segment safe for use in object storage keys.

    Examples
    --------
    >>> sanitize_path_segment("my-source")
    'my-source'
    >>> sanitize_path_segment("path/../evil")
    'path___evil'
    >>> sanitize_path_segment("source with spaces")
    'source_with_spaces'
    """
    # Strip null bytes first
    segment = segment.replace("\x00", "")
    # Replace unsafe characters
    segment = _SAFE_SEGMENT_RE.sub(replacement, segment)
    # Neutralize directory traversal: replace ".." with single dot
    while ".." in segment:
        segment = segment.replace("..", ".")
    return segment


def build_partition_key(
    event: ProductObservationEvent,
    layer: LakeLayer,
) -> str:
    """Generate a deterministic partition key for a validated event.

    The key follows the canonical layout:

        <layer>/source=<source>/year=<YYYY>/month=<MM>/day=<DD>/<event_id>.parquet

    where temporal dimensions are derived from ``payload.collected_at``
    (observation time), not ``produced_at`` (ingestion time).

    Parameters
    ----------
    event:
        A validated ``ProductObservationEvent``.
    layer:
        Target lake layer (``bronze`` or ``silver``).

    Returns
    -------
    str
        Full S3/MinIO object key suitable for ``put_object``.

    Notes
    -----
    - The ``event_id`` is used as the leaf filename to ensure idempotent
      writes: replaying the same event overwrites the existing file rather
      than creating duplicates.
    - Both ``source`` and ``event_id`` are sanitized to prevent path
      injection or encoding issues.
    """
    collected: datetime = event.payload.collected_at
    source = sanitize_path_segment(event.source)
    event_id = sanitize_path_segment(event.event_id)

    return (
        f"{layer.value}/"
        f"source={source}/"
        f"year={collected.strftime('%Y')}/"
        f"month={collected.strftime('%m')}/"
        f"day={collected.strftime('%d')}/"
        f"{event_id}.parquet"
    )
