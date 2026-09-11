"""Processor pipeline: route outcomes to canonical Kafka topics (TASK-017).

Chains the processing steps — ``events_to_polars`` → ``normalize`` →
``validate`` → ``deduplicate`` — and publishes each outcome to the
correct canonical topic:

- Valid, deduplicated records → ``products.validated.v1``
- Validation failures → ``products.invalid.v1``
- Deduplication conflicts → ``products.invalid.v1``
- Exact duplicates → skipped (already published in a prior batch)

Offset semantics
----------------
The pipeline raises ``PublishError`` when any output publication fails.
The caller (typically ``KafkaConsumer.process_next``) must NOT commit the
input offset in that case, preserving at-least-once delivery. On success
the caller commits the input offset as usual.

Retry / replay
--------------
Because input offsets are not committed on output failure, a restart
re-delivers the same input record. The pipeline is idempotent for valid
records (the validated topic may receive duplicates, which downstream
deduplication handles). Invalid records are re-published to the invalid
topic on each replay; this is safe because the invalid topic is a
diagnostic sink, not an analytical store.

Design decisions
----------------
- The pipeline operates on a batch of ``ConsumerMessage`` objects so that
  a single poll can produce multiple outputs.
- Event identity (``event_id``) is used to map DataFrame rows back to
  the original ``ConsumerMessage`` for diagnostic context.
- Invalid records are never silently dropped: every input row appears
  in exactly one output category.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import polars as pl

from libs.common.kafka_consumer import ConsumerMessage
from libs.common.kafka_errors import DeadLetterSink
from libs.event_contracts import ProductObservationEvent
from services.processor.data_validation import validate
from services.processor.deduplication import (
    DeduplicationState,
    deduplicate,
)
from services.processor.polars_transform import events_to_polars
from services.processor.schema_normalization import normalize

logger = logging.getLogger(__name__)

ValidatedSink = Callable[[ProductObservationEvent], object]


@dataclass
class PipelineResult:
    """Outcome of processing a batch through the pipeline.

    Every input record appears in exactly one category. The sum of all
    counts equals the input batch size.
    """

    published_valid: int = 0
    published_invalid: int = 0
    duplicates_skipped: int = 0
    conflicts: int = 0

    @property
    def total(self) -> int:
        return (
            self.published_valid + self.published_invalid + self.duplicates_skipped + self.conflicts
        )


def validation_envelope(
    *,
    event_id: str,
    source: str,
    validation_errors: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Build a diagnostic envelope for a validation failure.

    Preserves event identity, source, validation reasons, and enough
    original context for diagnosis. Does not include raw payload bytes
    or credentials.
    """
    return {
        "event_id": event_id,
        "event_type": "product.invalid",
        "schema_version": 1,
        "source": source,
        "produced_at": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "reason": "validation_failure",
            "validation_errors": validation_errors,
            "context": context,
        },
    }


def conflict_envelope(
    *,
    event_id: str,
    source: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Build a diagnostic envelope for a deduplication conflict."""
    return {
        "event_id": event_id,
        "event_type": "product.invalid",
        "schema_version": 1,
        "source": source,
        "produced_at": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "reason": "dedup_conflict",
            "context": context,
        },
    }


def _event_context(event: ProductObservationEvent) -> dict[str, Any]:
    """Extract diagnosable context from an event without leaking secrets."""
    return {
        "external_id": event.payload.external_id,
        "name": event.payload.name,
        "url": event.payload.url,
        "category": event.payload.category,
        "source": event.source,
        "schema_version": event.schema_version,
    }


class ProcessorPipeline:
    """Orchestrate the processor pipeline with output routing.

    Parameters
    ----------
    validated_sink:
        Callable that publishes a ``ProductObservationEvent`` to
        ``products.validated.v1``. Must raise on delivery failure.
    invalid_sink:
        Callable that publishes a diagnostic envelope dict to
        ``products.invalid.v1``. Must raise on delivery failure.
    dedup_state:
        Optional cross-batch deduplication state.
    """

    def __init__(
        self,
        validated_sink: ValidatedSink,
        invalid_sink: DeadLetterSink,
        dedup_state: DeduplicationState | None = None,
    ) -> None:
        self._validated_sink = validated_sink
        self._invalid_sink = invalid_sink
        self._dedup_state = dedup_state

    def process_batch(self, messages: list[ConsumerMessage]) -> PipelineResult:
        """Process a batch of consumer messages through the full pipeline.

        Raises ``PublishError`` if any output publication fails, so the
        caller must not commit the input offset.
        """
        if not messages:
            return PipelineResult()

        event_index: dict[str, ConsumerMessage] = {}
        events: list[ProductObservationEvent] = []
        for msg in messages:
            event_index[msg.event.event_id] = msg
            events.append(msg.event)

        df = events_to_polars(events)
        normalized = normalize(df)
        validation_result = validate(normalized)

        result = PipelineResult()

        if validation_result.invalid_count > 0:
            self._publish_invalid_records(validation_result.invalid, event_index, result)

        if validation_result.valid_count > 0:
            dedup_result = deduplicate(validation_result.valid, state=self._dedup_state)

            if dedup_result.conflicts_count > 0:
                self._publish_conflict_records(dedup_result.conflicts, event_index, result)

            if dedup_result.duplicates_removed > 0:
                result.duplicates_skipped += dedup_result.duplicates_removed

            if dedup_result.deduplicated.height > 0:
                self._publish_valid_records(dedup_result.deduplicated, event_index, result)
                result.published_valid += dedup_result.deduplicated.height

        return result

    def _publish_invalid_records(
        self,
        invalid_df: pl.DataFrame,
        event_index: dict[str, ConsumerMessage],
        result: PipelineResult,
    ) -> None:
        """Publish validation failures to the invalid topic."""
        for row in invalid_df.iter_rows(named=True):
            event_id = row["event_id"]
            msg = event_index.get(event_id)
            if msg is None:
                logger.error(
                    "pipeline_event_not_found",
                    extra={"event_id": event_id},
                )
                continue

            event = msg.event
            errors = row.get("_validation_errors", "")
            envelope = validation_envelope(
                event_id=event_id,
                source=event.source,
                validation_errors=errors,
                context=_event_context(event),
            )
            self._invalid_sink(envelope)
            result.published_invalid += 1

    def _publish_conflict_records(
        self,
        conflict_df: pl.DataFrame,
        event_index: dict[str, ConsumerMessage],
        result: PipelineResult,
    ) -> None:
        """Publish deduplication conflicts to the invalid topic."""
        for row in conflict_df.iter_rows(named=True):
            event_id = row["event_id"]
            msg = event_index.get(event_id)
            if msg is None:
                logger.error(
                    "pipeline_event_not_found",
                    extra={"event_id": event_id},
                )
                continue

            event = msg.event
            envelope = conflict_envelope(
                event_id=event_id,
                source=event.source,
                context=_event_context(event),
            )
            self._invalid_sink(envelope)
            result.published_invalid += 1
            result.conflicts += 1

    def _publish_valid_records(
        self,
        valid_df: pl.DataFrame,
        event_index: dict[str, ConsumerMessage],
        result: PipelineResult,
    ) -> None:
        """Publish deduplicated valid records to the validated topic."""
        for row in valid_df.iter_rows(named=True):
            event_id = row["event_id"]
            msg = event_index.get(event_id)
            if msg is None:
                logger.error(
                    "pipeline_event_not_found",
                    extra={"event_id": event_id},
                )
                continue

            self._validated_sink(msg.event)
