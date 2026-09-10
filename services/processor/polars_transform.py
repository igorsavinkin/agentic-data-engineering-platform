"""Polars-based analytical record transformations.

This module provides pure, deterministic functions that convert canonical
``ProductObservationEvent`` objects into Polars DataFrame representations
suitable for downstream analytical processing. The transformation logic is
transport-independent and does not perform normalization, validation,
deduplication, DLQ routing, or metrics collection — those concerns belong
to subsequent tasks (TASK-014 through TASK-018).

The processor core operates on in-memory event lists and produces Polars
DataFrames without mutating the input events. Kafka I/O, PostgreSQL writes,
and Parquet persistence are outside this module's scope.
"""

from __future__ import annotations

from typing import Sequence

import polars as pl

from libs.event_contracts import ProductObservationEvent


def _event_to_row(event: ProductObservationEvent) -> dict[str, object]:
    """Convert a single validated event to a flat dictionary row.

    Parameters
    ----------
    event:
        A validated ``ProductObservationEvent`` instance.

    Returns
    -------
    dict
        A flat dictionary with all envelope and payload fields preserved.
        Timestamps are kept as timezone-aware ``datetime`` objects. Price
        is converted to ``float`` for Polars compatibility when non-null;
        null prices remain ``None``.
    """
    payload = event.payload
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "source": event.source,
        "produced_at": event.produced_at,
        "external_id": payload.external_id,
        "name": payload.name,
        "url": payload.url,
        "price": float(payload.price) if payload.price is not None else None,
        "currency": payload.currency,
        "availability": payload.availability.value,
        "category": payload.category,
        "collected_at": payload.collected_at,
    }


def events_to_polars(events: Sequence[ProductObservationEvent]) -> pl.DataFrame:
    """Transform a sequence of canonical events into a Polars DataFrame.

    This is the primary entry point for TASK-013. It converts each event
    into a row while preserving all identifiers, timestamps, and optional
    fields exactly as they appear in the validated contract.

    Parameters
    ----------
    events:
        A sequence of validated ``ProductObservationEvent`` instances. May be
        empty.

    Returns
    -------
    pl.DataFrame
        A DataFrame with deterministic column ordering matching the canonical
        event contract. When ``events`` is empty, returns a DataFrame with the
        correct schema but zero rows.

    Notes
    -----
    - The function does **not** mutate the input events.
    - Column order is fixed and documented below for reproducibility.
    - No validation, normalization, or deduplication is performed here;
      those are out of scope for TASK-013.
    """
    columns = [
        "event_id",
        "event_type",
        "schema_version",
        "source",
        "produced_at",
        "external_id",
        "name",
        "url",
        "price",
        "currency",
        "availability",
        "category",
        "collected_at",
    ]

    if not events:
        return pl.DataFrame(schema={col: None for col in columns})

    rows = [_event_to_row(event) for event in events]
    df = pl.from_dicts(rows, schema={col: None for col in columns})

    return df.select(columns)
