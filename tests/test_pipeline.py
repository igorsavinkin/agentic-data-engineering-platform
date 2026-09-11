"""Unit tests for the processor pipeline (TASK-017).

Tests verify that the pipeline correctly routes outcomes to canonical
Kafka topics while preserving diagnostics and offset semantics.

Coverage:
- valid → validated topic only
- invalid → invalid topic only
- multiple validation reasons preserved
- output publish failure raises (offset not committed)
- malformed input diagnostics
- retry/replay behavior (idempotency)
- deduplication conflicts → invalid topic
- exact duplicates → skipped
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from libs.common.kafka_consumer import ConsumerMessage
from libs.common.kafka_producer import PublishError
from libs.event_contracts import (
    Availability,
    ProductObservationEvent,
    ProductObservationPayload,
)
from services.processor.deduplication import DeduplicationState
from services.processor.pipeline import (
    ProcessorPipeline,
    conflict_envelope,
    validation_envelope,
)


def _make_event(
    event_id: str = "evt-001",
    source: str = "test-source",
    external_id: str = "prod-123",
    name: str = "Test Product",
    url: str = "https://example.com/product/123",
    price: Decimal | None = Decimal("99.99"),
    currency: str = "EUR",
    availability: Availability = Availability.IN_STOCK,
    category: str = "electronics",
    schema_version: int = 1,
) -> ProductObservationEvent:
    """Create a test event with sensible defaults."""
    ts = datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc)
    return ProductObservationEvent(
        event_id=event_id,
        event_type="product.observation",
        schema_version=schema_version,
        source=source,
        produced_at=ts,
        payload=ProductObservationPayload(
            external_id=external_id,
            name=name,
            url=url,
            price=price,
            currency=currency,
            availability=availability,
            category=category,
            collected_at=ts,
        ),
    )


def _make_message(
    event: ProductObservationEvent,
    topic: str = "products.raw.v1",
    partition: int = 0,
    offset: int = 0,
) -> ConsumerMessage:
    """Wrap an event in a ConsumerMessage with Kafka metadata."""
    return ConsumerMessage(
        event=event,
        topic=topic,
        partition=partition,
        offset=offset,
        raw_value=None,
    )


class _FakeAvail:
    """Stand-in for Availability enum that exposes a ``.value`` attribute.

    ``_event_to_row`` reads ``payload.availability.value``; when we bypass
    Pydantic validation we may supply a non-enum string, so this wrapper
    lets the transform step succeed while the validator still rejects it.
    """

    def __init__(self, value: str) -> None:
        self.value = value


def _make_invalid_event(
    event_id: str = "evt-bad",
    source: str = "test-source",
    external_id: str = "prod-123",
    name: str = "Test Product",
    url: str = "https://example.com/product/123",
    price: Decimal | None = Decimal("-10.00"),
    currency: str = "EUR",
    availability: Availability | _FakeAvail = Availability.IN_STOCK,
    category: str = "electronics",
    schema_version: int = 1,
) -> ProductObservationEvent:
    """Create an event *bypassing* Pydantic validation.

    Use this for tests that need data the DataFrame-level ``validate()``
    will reject (negative price, bad currency, …).  The Pydantic model
    rejects such values at construction time, so we use ``model_construct``
    to skip validators while keeping attribute access working.
    """
    ts = datetime(2026, 9, 3, 8, 0, 0, tzinfo=timezone.utc)
    payload = ProductObservationPayload.model_construct(
        external_id=external_id,
        name=name,
        url=url,
        price=price,
        currency=currency,
        availability=availability,  # type: ignore[arg-type]
        category=category,
        collected_at=ts,
    )
    return ProductObservationEvent.model_construct(
        event_id=event_id,
        event_type="product.observation",
        schema_version=schema_version,
        source=source,
        produced_at=ts,
        payload=payload,
    )


class TestValidRecordsRouting:
    """Valid records must publish to validated topic only."""

    def test_single_valid_record(self) -> None:
        """A single valid record publishes to validated topic."""
        validated_events: list[ProductObservationEvent] = []
        invalid_envelopes: list[dict[str, Any]] = []

        def validated_sink(event: ProductObservationEvent) -> None:
            validated_events.append(event)

        def invalid_sink(envelope: dict[str, object]) -> None:
            invalid_envelopes.append(envelope)

        pipeline = ProcessorPipeline(
            validated_sink=validated_sink,
            invalid_sink=invalid_sink,
        )

        event = _make_event()
        message = _make_message(event)

        result = pipeline.process_batch([message])

        assert result.published_valid == 1
        assert result.published_invalid == 0
        assert result.duplicates_skipped == 0
        assert result.conflicts == 0
        assert len(validated_events) == 1
        assert validated_events[0].event_id == event.event_id
        assert len(invalid_envelopes) == 0

    def test_multiple_valid_records(self) -> None:
        """Multiple valid records all publish to validated topic."""
        validated_events: list[ProductObservationEvent] = []
        invalid_envelopes: list[dict[str, Any]] = []

        pipeline = ProcessorPipeline(
            validated_sink=lambda e: validated_events.append(e),
            invalid_sink=lambda env: invalid_envelopes.append(env),
        )

        events = [_make_event(event_id=f"evt-{i}", external_id=f"prod-{i}") for i in range(5)]
        messages = [_make_message(e, offset=i) for i, e in enumerate(events)]

        result = pipeline.process_batch(messages)

        assert result.published_valid == 5
        assert result.published_invalid == 0
        assert len(validated_events) == 5
        assert len(invalid_envelopes) == 0


class TestInvalidRecordsRouting:
    """Invalid records must publish to invalid topic only."""

    def test_single_invalid_record(self) -> None:
        """A single invalid record publishes to invalid topic."""
        validated_events: list[ProductObservationEvent] = []
        invalid_envelopes: list[dict[str, Any]] = []

        pipeline = ProcessorPipeline(
            validated_sink=lambda e: validated_events.append(e),
            invalid_sink=lambda env: invalid_envelopes.append(env),
        )

        event = _make_invalid_event(price=Decimal("-10.00"))
        message = _make_message(event)

        result = pipeline.process_batch([message])

        assert result.published_valid == 0
        assert result.published_invalid == 1
        assert len(validated_events) == 0
        assert len(invalid_envelopes) == 1

        envelope = invalid_envelopes[0]
        assert envelope["event_id"] == event.event_id
        assert envelope["event_type"] == "product.invalid"
        assert envelope["source"] == event.source
        payload = envelope["payload"]
        assert payload["reason"] == "validation_failure"
        assert "negative_price" in payload["validation_errors"]

    def test_multiple_invalid_records(self) -> None:
        """Multiple invalid records all publish to invalid topic."""
        validated_events: list[ProductObservationEvent] = []
        invalid_envelopes: list[dict[str, Any]] = []

        pipeline = ProcessorPipeline(
            validated_sink=lambda e: validated_events.append(e),
            invalid_sink=lambda env: invalid_envelopes.append(env),
        )

        events = [
            _make_invalid_event(event_id=f"evt-{i}", price=Decimal("-10.00")) for i in range(3)
        ]
        messages = [_make_message(e, offset=i) for i, e in enumerate(events)]

        result = pipeline.process_batch(messages)

        assert result.published_valid == 0
        assert result.published_invalid == 3
        assert len(validated_events) == 0
        assert len(invalid_envelopes) == 3


class TestMultipleValidationReasons:
    """Multiple validation reasons must be preserved in diagnostics."""

    def test_multiple_errors_preserved(self) -> None:
        """A record with multiple validation errors preserves all reasons."""
        invalid_envelopes: list[dict[str, Any]] = []

        pipeline = ProcessorPipeline(
            validated_sink=lambda e: None,
            invalid_sink=lambda env: invalid_envelopes.append(env),
        )

        event = _make_invalid_event(
            price=Decimal("-10.00"),
            currency="usd",
            availability=_FakeAvail("invalid_value"),
        )
        message = _make_message(event)

        result = pipeline.process_batch([message])

        assert result.published_invalid == 1
        envelope = invalid_envelopes[0]
        payload = envelope["payload"]
        errors = payload["validation_errors"]

        assert "negative_price" in errors
        assert "invalid_currency_format" in errors or "invalid_availability" in errors


class TestOutputPublishFailure:
    """Output publish failure must raise and prevent offset commit."""

    def test_validated_publish_failure_raises(self) -> None:
        """Failure to publish validated record raises PublishError."""

        def failing_sink(event: ProductObservationEvent) -> None:
            raise PublishError("Broker unavailable")

        pipeline = ProcessorPipeline(
            validated_sink=failing_sink,
            invalid_sink=lambda env: None,
        )

        event = _make_event()
        message = _make_message(event)

        with pytest.raises(PublishError, match="Broker unavailable"):
            pipeline.process_batch([message])

    def test_invalid_publish_failure_raises(self) -> None:
        """Failure to publish invalid record raises PublishError."""

        def failing_sink(envelope: dict[str, object]) -> None:
            raise PublishError("DLQ broker unavailable")

        pipeline = ProcessorPipeline(
            validated_sink=lambda e: None,
            invalid_sink=failing_sink,
        )

        event = _make_invalid_event(price=Decimal("-10.00"))
        message = _make_message(event)

        with pytest.raises(PublishError, match="DLQ broker unavailable"):
            pipeline.process_batch([message])


class TestMalformedInputDiagnostics:
    """Malformed input should retain diagnosable context."""

    def test_validation_failure_has_context(self) -> None:
        """Validation failure envelope includes diagnostic context."""
        invalid_envelopes: list[dict[str, Any]] = []

        pipeline = ProcessorPipeline(
            validated_sink=lambda e: None,
            invalid_sink=lambda env: invalid_envelopes.append(env),
        )

        event = _make_invalid_event(
            event_id="evt-malformed",
            external_id="prod-bad",
            name="Bad Product",
            price=Decimal("-5.00"),
        )
        message = _make_message(event)

        pipeline.process_batch([message])

        envelope = invalid_envelopes[0]
        assert envelope["event_id"] == "evt-malformed"
        payload = envelope["payload"]
        context = payload["context"]
        assert context["external_id"] == "prod-bad"
        assert context["name"] == "Bad Product"
        assert context["source"] == event.source


class TestRetryReplayBehavior:
    """Retry/replay must be idempotent and not lose records."""

    def test_exact_duplicate_skipped(self) -> None:
        """Exact duplicates within a batch are skipped."""
        validated_events: list[ProductObservationEvent] = []

        pipeline = ProcessorPipeline(
            validated_sink=lambda e: validated_events.append(e),
            invalid_sink=lambda env: None,
        )

        event = _make_event(event_id="evt-dup")
        messages = [
            _make_message(event, offset=0),
            _make_message(event, offset=1),
        ]

        result = pipeline.process_batch(messages)

        assert result.published_valid == 1
        assert result.duplicates_skipped == 1
        assert len(validated_events) == 1

    def test_cross_batch_duplicate_skipped(self) -> None:
        """Cross-batch duplicates are skipped with dedup state."""
        validated_events: list[ProductObservationEvent] = []
        dedup_state = DeduplicationState()

        pipeline = ProcessorPipeline(
            validated_sink=lambda e: validated_events.append(e),
            invalid_sink=lambda env: None,
            dedup_state=dedup_state,
        )

        event = _make_event(event_id="evt-cross")

        result1 = pipeline.process_batch([_make_message(event, offset=0)])
        assert result1.published_valid == 1

        result2 = pipeline.process_batch([_make_message(event, offset=1)])
        assert result2.published_valid == 0
        assert result2.duplicates_skipped == 1
        assert len(validated_events) == 1

    def test_dedup_conflict_to_invalid(self) -> None:
        """Deduplication conflicts route to invalid topic."""
        validated_events: list[ProductObservationEvent] = []
        invalid_envelopes: list[dict[str, Any]] = []

        pipeline = ProcessorPipeline(
            validated_sink=lambda e: validated_events.append(e),
            invalid_sink=lambda env: invalid_envelopes.append(env),
        )

        event1 = _make_event(event_id="evt-conflict", external_id="prod-1")
        event2 = _make_event(event_id="evt-conflict", external_id="prod-2")

        messages = [
            _make_message(event1, offset=0),
            _make_message(event2, offset=1),
        ]

        result = pipeline.process_batch(messages)

        assert result.published_valid == 0
        assert result.conflicts == 2
        assert result.published_invalid == 2
        assert len(invalid_envelopes) == 2

        for envelope in invalid_envelopes:
            assert envelope["event_id"] == "evt-conflict"
            payload = envelope["payload"]
            assert payload["reason"] == "dedup_conflict"


class TestMixedOutcomes:
    """Batches with mixed valid/invalid/duplicate/conflict records."""

    def test_mixed_batch(self) -> None:
        """A batch with mixed outcomes routes each correctly."""
        validated_events: list[ProductObservationEvent] = []
        invalid_envelopes: list[dict[str, Any]] = []

        pipeline = ProcessorPipeline(
            validated_sink=lambda e: validated_events.append(e),
            invalid_sink=lambda env: invalid_envelopes.append(env),
        )

        valid_event = _make_event(event_id="evt-valid")
        invalid_event = _make_invalid_event(event_id="evt-invalid", price=Decimal("-5.00"))
        dup_event = _make_event(event_id="evt-dup")

        messages = [
            _make_message(valid_event, offset=0),
            _make_message(invalid_event, offset=1),
            _make_message(dup_event, offset=2),
            _make_message(dup_event, offset=3),
        ]

        result = pipeline.process_batch(messages)

        assert result.published_valid == 2
        assert result.published_invalid == 1
        assert result.duplicates_skipped == 1
        assert result.total == 4


class TestEnvelopeBuilders:
    """Test diagnostic envelope builder functions."""

    def test_validation_envelope_structure(self) -> None:
        """Validation envelope has correct structure."""
        envelope = validation_envelope(
            event_id="evt-001",
            source="test-source",
            validation_errors="negative_price; invalid_currency",
            context={"external_id": "prod-123"},
        )

        assert envelope["event_id"] == "evt-001"
        assert envelope["event_type"] == "product.invalid"
        assert envelope["source"] == "test-source"
        assert "produced_at" in envelope
        payload = envelope["payload"]
        assert payload["reason"] == "validation_failure"
        assert payload["validation_errors"] == "negative_price; invalid_currency"
        assert payload["context"]["external_id"] == "prod-123"

    def test_conflict_envelope_structure(self) -> None:
        """Conflict envelope has correct structure."""
        envelope = conflict_envelope(
            event_id="evt-002",
            source="test-source",
            context={"external_id": "prod-456"},
        )

        assert envelope["event_id"] == "evt-002"
        assert envelope["event_type"] == "product.invalid"
        payload = envelope["payload"]
        assert payload["reason"] == "dedup_conflict"
        assert payload["context"]["external_id"] == "prod-456"


class TestEmptyBatch:
    """Empty batches should return zero counts."""

    def test_empty_batch(self) -> None:
        """An empty batch returns zero counts."""
        pipeline = ProcessorPipeline(
            validated_sink=lambda e: None,
            invalid_sink=lambda env: None,
        )

        result = pipeline.process_batch([])

        assert result.published_valid == 0
        assert result.published_invalid == 0
        assert result.duplicates_skipped == 0
        assert result.conflicts == 0
        assert result.total == 0
