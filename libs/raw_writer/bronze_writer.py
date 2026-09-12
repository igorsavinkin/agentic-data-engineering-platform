"""Bronze Parquet writer — persist raw events to MinIO/S3 (TASK-021).

This module owns the boundary between canonical ``ProductObservationEvent``
objects and Bronze-layer Parquet files in object storage.  It provides:

* deterministic partition-key generation via shared utility (source + temporal);
* event-to-row conversion preserving all envelope and payload fields;
* batch accumulation with configurable flush thresholds;
* idempotent writes using deterministic object keys so replay does not
  create duplicate files;
* explicit retry semantics on transient storage failures.

Offset / delivery semantics
---------------------------
The caller (typically a Kafka consumer loop) must commit the input offset
ONLY after ``flush_batch`` succeeds.  If the write fails, the offset is
NOT committed and the same record will be redelivered on restart/rebalance.
Because object keys are deterministic (derived from ``event_id``), replay
is safe even if a prior attempt partially succeeded.

Partitioning strategy
---------------------
Bronze data uses the canonical partition layout defined in
``libs.partitioning.partition_key``:

    bronze/source=<source>/year=<YYYY>/month=<MM>/day=<DD>/<event_id>.parquet

This avoids high-cardinality product identifiers as primary partitions while
still enabling efficient time-range queries per source.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Any

import polars as pl

from libs.common.minio_storage import MinIOStorage, StorageError
from libs.event_contracts import ProductObservationEvent
from libs.partitioning import LakeLayer, build_partition_key
from libs.schema import BRONZE_SCHEMA, validate_row_against_schema

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event → Polars row
# ---------------------------------------------------------------------------


def event_to_row(event: ProductObservationEvent) -> dict[str, Any]:
    """Convert a validated event into a flat dictionary suitable for Polars.

    All envelope fields and payload fields are preserved.  Nullable fields
    (e.g. ``price``) remain nullable in the resulting schema.

    Price is stored as a string to preserve exact Decimal precision without
    floating-point loss.  Downstream consumers can convert back to Decimal
    when needed.
    """
    return {
        # Envelope
        "event_id": event.event_id,
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "source": event.source,
        "produced_at": event.produced_at.isoformat(),
        # Payload
        "external_id": event.payload.external_id,
        "name": event.payload.name,
        "url": event.payload.url,
        "price": str(event.payload.price) if event.payload.price is not None else None,
        "currency": event.payload.currency,
        "availability": event.payload.availability.value,
        "category": event.payload.category,
        "collected_at": event.payload.collected_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Batch accumulator
# ---------------------------------------------------------------------------


@dataclass
class BronzeBatch:
    """Accumulate events until a flush threshold is reached."""

    events: list[ProductObservationEvent]
    max_size: int = 100  # flush after this many events

    def add(self, event: ProductObservationEvent) -> bool:
        """Add an event; return True when the batch should be flushed."""
        self.events.append(event)
        return len(self.events) >= self.max_size

    def clear(self) -> None:
        self.events.clear()


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


class BronzeWriter:
    """Write canonical events to Bronze Parquet in MinIO/S3.

    Parameters
    ----------
    storage:
        An initialised ``MinIOStorage`` instance (TASK-020).
    bucket:
        The Bronze bucket name (defaults to settings value).
    batch_size:
        Number of events to accumulate before flushing.  Set to 1 for
        immediate per-event persistence (simpler but more PUT calls).
    """

    def __init__(
        self,
        storage: MinIOStorage,
        bucket: str = "bronze",
        batch_size: int = 100,
    ) -> None:
        self._storage = storage
        self._bucket = bucket
        self._batch = BronzeBatch(events=[], max_size=batch_size)
        logger.info(
            "bronze_writer_initialized",
            extra={"bucket": bucket, "batch_size": batch_size},
        )

    def add_event(self, event: ProductObservationEvent) -> bool:
        """Add an event to the current batch.

        Returns True when the batch has reached its flush threshold.

        .. deprecated:: Use ``write_event`` for at-least-once delivery.
           Batch mode risks losing committed-but-unwritten records on crash.
        """
        return self._batch.add(event)

    def write_event(self, event: ProductObservationEvent) -> None:
        """Persist a single event to Bronze Parquet immediately.

        This is the preferred method for at-least-once delivery: each event
        is written and confirmed before the caller commits the Kafka offset.
        Raises ``StorageError`` on failure so the offset is NOT committed.
        """
        self._write_single(event)

    def flush_batch(self) -> None:
        """Persist the accumulated batch as individual Parquet files.

        Each event gets its own file keyed by ``event_id`` so that replay
        overwrites rather than duplicates.  The method raises ``StorageError``
        on failure so the caller must NOT commit the Kafka offset.
        """
        if not self._batch.events:
            return

        logger.info(
            "bronze_flush_start",
            extra={"count": len(self._batch.events)},
        )

        errors: list[tuple[str, Exception]] = []
        for event in self._batch.events:
            try:
                self._write_single(event)
            except StorageError as exc:
                errors.append((event.event_id, exc))
                logger.error(
                    "bronze_write_failed",
                    extra={"event_id": event.event_id, "error": str(exc)},
                )

        self._batch.clear()

        if errors:
            raise StorageError(
                f"bronze_flush failed for {len(errors)} event(s): "
                f"{', '.join(eid for eid, _ in errors[:5])}"
            )

        logger.info("bronze_flush_complete")

    def _write_single(self, event: ProductObservationEvent) -> None:
        """Serialize one event to Parquet bytes and upload to object storage.

        Validates the row against the explicit Bronze schema before writing.
        Raises ``ValueError`` if the row does not conform to the schema.
        """
        row = event_to_row(event)

        # Validate row against explicit schema
        violations = validate_row_against_schema(row, BRONZE_SCHEMA)
        if violations:
            raise ValueError(
                f"Bronze schema validation failed for event {event.event_id}: "
                f"{', '.join(violations)}"
            )

        # Create DataFrame from row dict
        df = pl.DataFrame([row])

        buf = io.BytesIO()
        df.write_parquet(buf)
        parquet_bytes = buf.getvalue()

        key = build_partition_key(event, LakeLayer.BRONZE)
        self._storage.put_object(self._bucket, key, parquet_bytes)
        logger.debug(
            "bronze_event_written",
            extra={"event_id": event.event_id, "key": key},
        )

    def health_check(self) -> bool:
        """Probe whether the underlying storage is reachable."""
        status = self._storage.check_health()
        return status.healthy
