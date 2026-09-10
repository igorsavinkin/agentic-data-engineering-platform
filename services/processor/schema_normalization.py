"""Deterministic schema normalization for product-observation records.

This module defines the canonical normalized analytical schema and provides
a ``normalize()`` function that transforms a raw Polars DataFrame (as produced
by ``events_to_polars()``) into a deterministically-typed DataFrame suitable
for downstream validation (TASK-015), deduplication (TASK-016), and Silver-layer
persistence.

Schema invariants guaranteed after ``normalize()``:
    - Column names and order match ``NORMALIZED_SCHEMA`` exactly.
    - All columns have the Polars dtype declared in ``NORMALIZED_SCHEMA``.
    - ``produced_at`` and ``collected_at`` are ``Datetime("us", "UTC")``.
    - ``schema_version`` is ``Int64``.
    - ``price`` is ``Float64``; null prices remain null (never zero-filled).
    - ``availability`` is ``Utf8``; only the four canonical values are valid,
      but invalid values are preserved as-is for TASK-015 to flag.
    - Semantic IDs (``event_id``, ``external_id``) and ``url`` are NOT
      whitespace-stripped or otherwise modified.
    - ``name``, ``category``, ``currency``, ``source``, ``event_type`` have
      leading/trailing whitespace stripped.
    - Row count is preserved — no silent row dropping.

What ``normalize()`` does NOT guarantee (those are TASK-015 responsibilities):
    - Rejecting rows with invalid availability values.
    - Rejecting rows with null or negative prices.
    - Detecting duplicate events.
    - Routing invalid records to a DLQ.
    - Enforcing business-rule constraints (e.g., currency format).
"""

from __future__ import annotations

from typing import Any

import polars as pl

UTC_DATETIME = pl.Datetime(time_unit="us", time_zone="UTC")

NORMALIZED_SCHEMA: dict[str, Any] = {
    "event_id": pl.Utf8,
    "event_type": pl.Utf8,
    "schema_version": pl.Int64,
    "source": pl.Utf8,
    "produced_at": UTC_DATETIME,
    "external_id": pl.Utf8,
    "name": pl.Utf8,
    "url": pl.Utf8,
    "price": pl.Float64,
    "currency": pl.Utf8,
    "availability": pl.Utf8,
    "category": pl.Utf8,
    "collected_at": UTC_DATETIME,
}

_COLUMNS = list(NORMALIZED_SCHEMA.keys())

_STRIP_WHITESPACE_COLS = ["name", "category", "currency", "source", "event_type"]

_TIMESTAMP_COLS = ["produced_at", "collected_at"]


def normalize(df: pl.DataFrame) -> pl.DataFrame:
    """Normalize a raw product-observation DataFrame into the canonical schema.

    Applies deterministic type coercions, whitespace stripping, and timestamp
    normalization. The output has exactly the same number of rows as the input.
    Invalid or unparseable values are preserved in a detectable form (null for
    numeric coercion failures, original string for enum violations) so that
    TASK-015 validation can flag them.

    Parameters
    ----------
    df:
        A Polars DataFrame with columns matching the canonical event contract
        fields (e.g., as produced by ``events_to_polars()``).

    Returns
    -------
    pl.DataFrame
        A new DataFrame with columns typed according to ``NORMALIZED_SCHEMA``.
        Row count equals ``df.height``.

    Notes
    -----
    - Semantic IDs (``event_id``, ``external_id``) and ``url`` are cast to
      ``Utf8`` but NOT whitespace-stripped.
    - Unparseable price values become ``null`` via ``strict=False`` casting;
      they are not silently zeroed.
    - Availability values outside the canonical set are preserved as-is.
    """
    if df.height == 0:
        return pl.DataFrame(schema=NORMALIZED_SCHEMA)

    result = df

    result = result.with_columns(
        [pl.col(c).cast(pl.Utf8, strict=False) for c in _COLUMNS if NORMALIZED_SCHEMA[c] == pl.Utf8]
    )

    result = result.with_columns([pl.col(c).str.strip_chars() for c in _STRIP_WHITESPACE_COLS])

    result = _normalize_timestamps(result)

    result = result.with_columns(pl.col("schema_version").cast(pl.Int64, strict=False))

    result = result.with_columns(pl.col("price").cast(pl.Float64, strict=False))

    result = result.with_columns(pl.col("availability").str.strip_chars().str.to_lowercase())

    return result.select(_COLUMNS)


def _normalize_timestamps(df: pl.DataFrame) -> pl.DataFrame:
    """Normalize timestamp columns to ``Datetime("us", "UTC")``.

    Handles three input cases:
    - Timezone-aware timestamps: converted to UTC.
    - Timezone-naive timestamps: assumed to be UTC (time zone replaced).
    - Non-timestamp values: cast with ``strict=False``, failures become null.
    """
    exprs = []
    for col_name in _TIMESTAMP_COLS:
        col = pl.col(col_name)
        dtype = df.schema.get(col_name)

        if dtype is not None and isinstance(dtype, pl.Datetime) and dtype.time_zone is not None:
            exprs.append(col.dt.convert_time_zone("UTC").cast(UTC_DATETIME))
        elif dtype is not None and isinstance(dtype, pl.Datetime) and dtype.time_zone is None:
            exprs.append(col.dt.replace_time_zone("UTC").cast(UTC_DATETIME))
        else:
            exprs.append(col.cast(UTC_DATETIME, strict=False))

    return df.with_columns(exprs)
