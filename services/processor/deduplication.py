"""Replay-safe deduplication for valid product-observation records.

This module provides deterministic deduplication of validated DataFrames
(output of ``data_validation.validate().valid``) so that at-least-once Kafka
delivery does not create duplicate logical processor output.

Design decisions:
    - Uses ``event_id`` as the observation-event identity (per TASK-006).
    - Exact duplicates (same event_id, identical payload) are collapsed:
      the first occurrence is kept.
    - Conflicting payloads (same event_id, different payload) are surfaced
      explicitly in the ``conflicts`` DataFrame rather than silently dropped.
    - Legitimate repeated observations of the same product at different
      collection times have *different* event_ids (since event_id is derived
      from source + external_id + collected_at), so they are never collapsed.
    - Semantics remain at-least-once + idempotent — this module does NOT
      claim exactly-once processing.

State lifetime:
    The ``DeduplicationState`` is an in-memory structure scoped to a single
    processor instance. It tracks ``event_id → payload_hash`` across batches
    within the same process. Durable cross-instance deduplication (e.g.,
    PostgreSQL uniqueness constraints) is out of scope for TASK-016 and must
    be enforced by later tasks at the warehouse/serving layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

from services.processor.schema_normalization import NORMALIZED_SCHEMA

_PAYLOAD_HASH_COL = "_payload_hash"
_DUPLICATE_FLAG_COL = "_is_duplicate"
_CONFLICT_FLAG_COL = "_is_conflict"

_ALL_COLUMNS = list(NORMALIZED_SCHEMA.keys())
_HASH_COLUMNS = [c for c in _ALL_COLUMNS if c != "event_id"]


@dataclass(frozen=True)
class DeduplicationResult:
    """Outcome of deduplicating a validated product-observation DataFrame.

    Every input row appears in exactly one of ``deduplicated``, ``duplicates``
    (exact replays removed), or ``conflicts`` (same event_id, different payload).
    """

    deduplicated: pl.DataFrame
    duplicates: pl.DataFrame
    conflicts: pl.DataFrame
    duplicates_removed: int = field(init=False)
    conflicts_count: int = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "duplicates_removed", self.duplicates.height)
        object.__setattr__(self, "conflicts_count", self.conflicts.height)

    @property
    def total_input_count(self) -> int:
        return self.deduplicated.height + self.duplicates_removed + self.conflicts_count


class DeduplicationState:
    """In-memory cross-batch deduplication state.

    Tracks ``event_id → payload_hash`` mappings across processor calls within
    a single process. This is a best-effort replay guard: it catches replays
    that span multiple batches within the same processor instance but does
    NOT provide cross-instance or durable deduplication.

    State boundary:
        This state lives only as long as the processor process. If the
        processor restarts, the state is lost and earlier events may be
        re-emitted. Durable deduplication (e.g., PostgreSQL uniqueness on
        event_id) is required for full replay safety across restarts and
        is out of scope for TASK-016.
    """

    def __init__(self) -> None:
        self._seen: dict[str, str] = {}

    def check_and_update(self, event_ids: list[str], payload_hashes: list[str]) -> list[bool]:
        """Check each event_id against seen state and update.

        Returns a list of booleans: ``True`` means the event is a cross-batch
        duplicate (already seen with the same hash), ``False`` means it is new
        or a conflict (seen with a different hash).
        """
        results: list[bool] = []
        for eid, phash in zip(event_ids, payload_hashes):
            if eid in self._seen:
                if self._seen[eid] == phash:
                    results.append(True)
                else:
                    results.append(False)
            else:
                self._seen[eid] = phash
                results.append(False)
        return results

    @property
    def size(self) -> int:
        return len(self._seen)


def deduplicate(
    df: pl.DataFrame,
    state: DeduplicationState | None = None,
) -> DeduplicationResult:
    """Deduplicate a validated product-observation DataFrame.

    Parameters
    ----------
    df:
        A Polars DataFrame with columns matching ``NORMALIZED_SCHEMA``
        (i.e., the ``valid`` output of ``data_validation.validate()``).
    state:
        Optional cross-batch deduplication state. When provided, events
        from previous batches are also detected as duplicates.

    Returns
    -------
    DeduplicationResult
        Deterministic split into deduplicated (unique), duplicates (exact
        replays removed), and conflicts (same event_id, different payload).
    """
    empty = _empty_schema()
    if df.height == 0:
        return DeduplicationResult(
            deduplicated=empty,
            duplicates=empty,
            conflicts=empty,
        )

    annotated = _add_payload_hash(df)

    if state is not None:
        annotated = _mark_cross_batch_duplicates(annotated, state)
    else:
        annotated = annotated.with_columns(
            pl.lit(False).alias(_DUPLICATE_FLAG_COL),
        )

    annotated = _mark_within_batch_status(annotated)

    dedup_df = annotated.filter(~pl.col(_DUPLICATE_FLAG_COL) & ~pl.col(_CONFLICT_FLAG_COL)).drop(
        _PAYLOAD_HASH_COL, _DUPLICATE_FLAG_COL, _CONFLICT_FLAG_COL
    )

    dup_df = annotated.filter(pl.col(_DUPLICATE_FLAG_COL)).drop(
        _PAYLOAD_HASH_COL, _DUPLICATE_FLAG_COL, _CONFLICT_FLAG_COL
    )

    conflict_df = annotated.filter(pl.col(_CONFLICT_FLAG_COL)).drop(
        _PAYLOAD_HASH_COL, _DUPLICATE_FLAG_COL, _CONFLICT_FLAG_COL
    )

    return DeduplicationResult(
        deduplicated=dedup_df,
        duplicates=dup_df,
        conflicts=conflict_df,
    )


def _add_payload_hash(df: pl.DataFrame) -> pl.DataFrame:
    """Add a payload hash column for duplicate detection."""
    if not _HASH_COLUMNS:
        return df.with_columns(pl.lit("").alias(_PAYLOAD_HASH_COL))

    hash_expr = pl.concat_str(
        [pl.col(c).cast(pl.Utf8, strict=False) for c in _HASH_COLUMNS],
        separator="|",
    ).hash()

    return df.with_columns(hash_expr.alias(_PAYLOAD_HASH_COL))


def _mark_cross_batch_duplicates(df: pl.DataFrame, state: DeduplicationState) -> pl.DataFrame:
    """Mark rows that are cross-batch duplicates based on state."""
    event_ids = df["event_id"].to_list()
    payload_hashes = df[_PAYLOAD_HASH_COL].cast(pl.Utf8).to_list()

    is_cross_dup = state.check_and_update(event_ids, payload_hashes)

    return df.with_columns(
        pl.Series(_DUPLICATE_FLAG_COL, is_cross_dup, dtype=pl.Boolean),
    )


def _mark_within_batch_status(df: pl.DataFrame) -> pl.DataFrame:
    """Mark within-batch duplicates and conflicts.

    For each event_id group:
    - If all payload hashes are the same → exact duplicates. Keep first,
      mark rest as duplicates.
    - If payload hashes differ → conflict. Mark all rows in the group
      as conflicts.
    """
    window_unique_hashes = pl.col(_PAYLOAD_HASH_COL).n_unique().over("event_id")
    window_row_rank = pl.col(_PAYLOAD_HASH_COL).rank("ordinal").over("event_id")

    is_conflict = window_unique_hashes > 1
    is_within_dup = (~is_conflict) & (window_row_rank > 1)

    existing_dup = pl.col(_DUPLICATE_FLAG_COL)

    return df.with_columns(
        (existing_dup | is_within_dup).alias(_DUPLICATE_FLAG_COL),
        is_conflict.alias(_CONFLICT_FLAG_COL),
    )


def _empty_schema() -> pl.DataFrame:
    return pl.DataFrame(schema=NORMALIZED_SCHEMA)
