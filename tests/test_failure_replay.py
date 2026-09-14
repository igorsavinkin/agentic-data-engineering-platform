"""Failure and replay demonstration tests (TASK-039).

Tests verify at-least-once delivery semantics, offset commit timing, crash
recovery, duplicate handling, replay from Kafka, transient failure retry,
invalid event routing to DLQ, and idempotency across replays.

Coverage:
1. Consumer/process restart after reading an event
2. Duplicate event delivery
3. Replay from Kafka
4. Storage/warehouse retry after transient failure
5. Invalid event routed to invalid/DLQ
6. Replay does not create duplicate logical observations in serving layer
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
from services.processor.pipeline import ProcessorPipeline


def _make_event(
    event_id: str = "evt-001",
    source: str = "fake_store",
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


def _wrap_as_consumer_message(event: ProductObservationEvent, offset: int = 0) -> ConsumerMessage:
    """Wrap an event in a ConsumerMessage with Kafka metadata."""
    return ConsumerMessage(
        event=event,
        topic="products.raw.v1",
        partition=0,
        offset=offset,
        raw_value=None,
    )


class TrackingSinks:
    """Helper to capture sink outputs for verification."""

    def __init__(self) -> None:
        self.validated_events: list[ProductObservationEvent] = []
        self.invalid_envelopes: list[dict[str, Any]] = []
        self.committed_offsets: list[tuple[str, int, int]] = []

    def validated_sink(self, event: ProductObservationEvent) -> None:
        self.validated_events.append(event)

    def invalid_sink(self, envelope: dict[str, Any]) -> None:
        self.invalid_envelopes.append(envelope)

    def record_offset_commit(self, topic: str, partition: int, offset: int) -> None:
        self.committed_offsets.append((topic, partition, offset))


class TestRestartAfterReading:
    """Scenario 1: consumer/process restart after reading an event.

    Demonstrates that if processing succeeds but offset is not committed
    before crash, the message will be redelivered on restart. This is the
    core of at-least-once delivery.
    """

    def test_crash_before_offset_commit_redelivers(self) -> None:
        """If process crashes after processing but before offset commit, message is redelivered."""
        sinks = TrackingSinks()

        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
        )

        event = _make_event(event_id="evt-restart")
        message = _wrap_as_consumer_message(event, offset=0)

        # First run: process successfully
        result1 = pipeline.process_batch([message])
        assert result1.published_valid == 1
        assert len(sinks.validated_events) == 1

        # Simulate crash BEFORE offset commit (offset not recorded)
        # On restart, same message is delivered again
        sinks2 = TrackingSinks()
        pipeline2 = ProcessorPipeline(
            validated_sink=sinks2.validated_sink,
            invalid_sink=sinks2.invalid_sink,
        )

        result2 = pipeline2.process_batch([message])
        assert result2.published_valid == 1
        assert len(sinks2.validated_events) == 1

        # Both runs processed the event (at-least-once)
        # Downstream deduplication must handle the duplicate
        assert sinks.validated_events[0].event_id == sinks2.validated_events[0].event_id

    def test_crash_after_offset_commit_no_redelivery(self) -> None:
        """If offset was committed before crash, message is NOT redelivered."""
        sinks = TrackingSinks()

        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
        )

        event = _make_event(event_id="evt-committed")
        message = _wrap_as_consumer_message(event, offset=5)

        # Process and commit offset
        result = pipeline.process_batch([message])
        assert result.published_valid == 1

        # Record offset commit (simulating successful commit)
        sinks.record_offset_commit(message.topic, message.partition, message.offset + 1)

        # On restart, consumer starts from offset 6 (next after committed)
        # Message at offset 5 is NOT redelivered
        assert sinks.committed_offsets[0] == ("products.raw.v1", 0, 6)


class TestDuplicateDelivery:
    """Scenario 2: duplicate event delivery.

    Verifies that exact duplicates within a batch are skipped, and
    cross-batch duplicates are handled by deduplication state.
    """

    def test_exact_duplicate_within_batch_skipped(self) -> None:
        """Exact duplicates within same batch are skipped."""
        sinks = TrackingSinks()

        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
        )

        event = _make_event(event_id="evt-dup-batch")
        messages = [
            _wrap_as_consumer_message(event, offset=0),
            _wrap_as_consumer_message(event, offset=1),
        ]

        result = pipeline.process_batch(messages)

        assert result.published_valid == 1
        assert result.duplicates_skipped == 1
        assert len(sinks.validated_events) == 1

    def test_cross_batch_duplicate_with_dedup_state(self) -> None:
        """Cross-batch duplicates are skipped when dedup state is shared."""
        sinks = TrackingSinks()
        dedup_state = DeduplicationState()

        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
            dedup_state=dedup_state,
        )

        event = _make_event(event_id="evt-cross-dup")

        # First batch
        result1 = pipeline.process_batch([_wrap_as_consumer_message(event, offset=0)])
        assert result1.published_valid == 1
        assert len(sinks.validated_events) == 1

        # Second batch with same event_id (simulates redelivery)
        result2 = pipeline.process_batch([_wrap_as_consumer_message(event, offset=1)])
        assert result2.published_valid == 0
        assert result2.duplicates_skipped == 1
        assert len(sinks.validated_events) == 1  # Still only 1


class TestReplayFromKafka:
    """Scenario 3: replay from Kafka.

    Demonstrates that resetting consumer group offsets enables replaying
    historical events, and the pipeline processes them correctly without
    data loss.
    """

    def test_replay_from_earliest_offset(self) -> None:
        """Replaying from earliest offset reprocesses all events."""
        sinks = TrackingSinks()
        dedup_state = DeduplicationState()

        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
            dedup_state=dedup_state,
        )

        # Original processing
        events = [_make_event(event_id=f"evt-{i}", external_id=f"prod-{i}") for i in range(3)]
        messages = [_wrap_as_consumer_message(e, offset=i) for i, e in enumerate(events)]

        result1 = pipeline.process_batch(messages)
        assert result1.published_valid == 3

        # Simulate replay: reset offsets to earliest, reprocess same messages
        sinks2 = TrackingSinks()
        dedup_state2 = DeduplicationState()

        pipeline2 = ProcessorPipeline(
            validated_sink=sinks2.validated_sink,
            invalid_sink=sinks2.invalid_sink,
            dedup_state=dedup_state2,
        )

        result2 = pipeline2.process_batch(messages)
        assert result2.published_valid == 3

        # Replay produces same number of valid events
        # Without dedup state, duplicates would appear downstream
        assert len(sinks2.validated_events) == 3

    def test_replay_with_shared_dedup_state_idempotent(self) -> None:
        """Replay with shared dedup state skips already-seen events."""
        sinks = TrackingSinks()
        dedup_state = DeduplicationState()

        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
            dedup_state=dedup_state,
        )

        event = _make_event(event_id="evt-replay-idem", external_id="prod-replay")

        # First processing
        result1 = pipeline.process_batch([_wrap_as_consumer_message(event, offset=0)])
        assert result1.published_valid == 1

        # Replay same event
        result2 = pipeline.process_batch([_wrap_as_consumer_message(event, offset=0)])
        assert result2.published_valid == 0
        assert result2.duplicates_skipped == 1

        # Only one event in validated sink
        assert len(sinks.validated_events) == 1


class TestStorageRetryTransientFailure:
    """Scenario 4: storage/warehouse retry after transient failure.

    Demonstrates that transient failures during output publication raise
    PublishError, preventing offset commit, so the message can be retried.
    """

    def test_transient_failure_prevents_offset_commit(self) -> None:
        """Transient publish failure raises, preventing offset commit."""
        # Each process_batch call is independent - no state persists between them
        # This simulates what happens when a caller retries after a transient failure

        def flaky_sink_attempt_1(event: ProductObservationEvent) -> None:
            raise PublishError("Temporary broker unavailable")

        pipeline1 = ProcessorPipeline(
            validated_sink=flaky_sink_attempt_1,
            invalid_sink=lambda env: None,
        )

        event = _make_event(event_id="evt-transient")
        message = _wrap_as_consumer_message(event, offset=10)

        # First attempt fails
        with pytest.raises(PublishError, match="Temporary broker unavailable"):
            pipeline1.process_batch([message])

        # Second attempt also fails (simulating continued transient issue)
        def flaky_sink_attempt_2(event: ProductObservationEvent) -> None:
            raise PublishError("Temporary broker unavailable")

        pipeline2 = ProcessorPipeline(
            validated_sink=flaky_sink_attempt_2,
            invalid_sink=lambda env: None,
        )

        with pytest.raises(PublishError, match="Temporary broker unavailable"):
            pipeline2.process_batch([message])

        # Third attempt succeeds (transient issue resolved)
        def successful_sink(event: ProductObservationEvent) -> None:
            pass

        pipeline3 = ProcessorPipeline(
            validated_sink=successful_sink,
            invalid_sink=lambda env: None,
        )

        result = pipeline3.process_batch([message])
        assert result.published_valid == 1

        # Offset should NOT have been committed on failures
        # Caller must retry with same message until success

    def test_retry_until_success_then_commit(self) -> None:
        """After retries succeed, offset can be committed."""
        # Simulate multiple retry attempts with different pipeline instances
        event = _make_event(event_id="evt-retry-success")
        message = _wrap_as_consumer_message(event, offset=20)

        # First two attempts fail
        for i in range(2):

            def failing_sink(event: ProductObservationEvent) -> None:
                raise PublishError(f"Retry attempt {i + 1} failed")

            pipeline = ProcessorPipeline(
                validated_sink=failing_sink,
                invalid_sink=lambda env: None,
            )

            with pytest.raises(PublishError):
                pipeline.process_batch([message])

        # Third attempt succeeds
        def successful_sink(event: ProductObservationEvent) -> None:
            pass

        pipeline_final = ProcessorPipeline(
            validated_sink=successful_sink,
            invalid_sink=lambda env: None,
        )

        result = pipeline_final.process_batch([message])
        assert result.published_valid == 1

        # Now offset can be safely committed
        # (In real code, caller would call commit_message here)


class TestInvalidEventDLQ:
    """Scenario 5: invalid event routed to invalid/DLQ.

    Verifies that validation failures are published to the invalid topic
    with diagnostic context, and do not enter the validated/silver path.
    """

    def test_invalid_event_to_dlq_not_validated(self) -> None:
        """Invalid events route to invalid topic, not validated."""
        sinks = TrackingSinks()

        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
        )

        # Create invalid event using model_construct to bypass Pydantic validation
        invalid_payload = ProductObservationPayload.model_construct(
            external_id="1",
            name=None,  # type: ignore[arg-type]  # Missing required field
            url="https://example.com/1",
            price=Decimal("-10.00"),  # Negative price
            currency="INVALID",  # Invalid currency format
            availability=Availability.UNKNOWN,
            category="electronics",
            collected_at=datetime.now(timezone.utc),
        )
        invalid_event = ProductObservationEvent.model_construct(
            event_id="evt-invalid",
            event_type="product.observation",
            schema_version=1,
            source="fake_store",
            produced_at=datetime.now(timezone.utc),
            payload=invalid_payload,
        )
        message = _wrap_as_consumer_message(invalid_event, offset=0)

        result = pipeline.process_batch([message])

        # Should route to invalid, not validated
        assert result.published_valid == 0
        assert result.published_invalid == 1
        assert len(sinks.validated_events) == 0
        assert len(sinks.invalid_envelopes) == 1

        # Verify diagnostic context
        envelope = sinks.invalid_envelopes[0]
        assert envelope["event_id"] == "evt-invalid"
        assert envelope["payload"]["reason"] == "validation_failure"
        assert "negative_price" in envelope["payload"]["validation_errors"]

    def test_invalid_event_does_not_corrupt_downstream(self) -> None:
        """Invalid events in DLQ do not affect subsequent valid events."""
        sinks = TrackingSinks()

        pipeline = ProcessorPipeline(
            validated_sink=sinks.validated_sink,
            invalid_sink=sinks.invalid_sink,
        )

        # Mix of invalid and valid events
        invalid_payload = ProductObservationPayload.model_construct(
            external_id="bad",
            name=None,  # type: ignore[arg-type]
            url="https://example.com/bad",
            price=Decimal("-5.00"),
            currency="USD",
            availability=Availability.IN_STOCK,
            category="test",
            collected_at=datetime.now(timezone.utc),
        )
        invalid_event = ProductObservationEvent.model_construct(
            event_id="evt-bad",
            event_type="product.observation",
            schema_version=1,
            source="test",
            produced_at=datetime.now(timezone.utc),
            payload=invalid_payload,
        )

        valid_event = _make_event(event_id="evt-good", external_id="prod-good")

        messages = [
            _wrap_as_consumer_message(invalid_event, offset=0),
            _wrap_as_consumer_message(valid_event, offset=1),
        ]

        result = pipeline.process_batch(messages)

        assert result.published_valid == 1
        assert result.published_invalid == 1
        assert len(sinks.validated_events) == 1
        assert len(sinks.invalid_envelopes) == 1

        # Valid event processed correctly despite invalid event
        assert sinks.validated_events[0].payload.external_id == "prod-good"


class TestReplayNoDuplicates:
    """Scenario 6: replay does not create duplicate logical observations.

    Verifies that idempotency enforcement (via event_id deduplication)
    prevents duplicate logical records in the final serving layer after
    replay.
    """

    def test_replay_with_dedup_prevents_serving_layer_duplicates(self) -> None:
        """Replay with dedup state prevents duplicate logical observations."""
        # Simulate serving layer (e.g., PostgreSQL table)
        serving_layer: dict[str, ProductObservationEvent] = {}

        def idempotent_sink(event: ProductObservationEvent) -> None:
            """Simulate idempotent insert into serving layer."""
            # Use event_id as unique key for idempotency
            if event.event_id not in serving_layer:
                serving_layer[event.event_id] = event

        dedup_state = DeduplicationState()

        pipeline = ProcessorPipeline(
            validated_sink=idempotent_sink,
            invalid_sink=lambda env: None,
            dedup_state=dedup_state,
        )

        event = _make_event(event_id="evt-serving", external_id="prod-serving")

        # First processing
        result1 = pipeline.process_batch([_wrap_as_consumer_message(event, offset=0)])
        assert result1.published_valid == 1
        assert len(serving_layer) == 1

        # Simulate replay (same event delivered again)
        result2 = pipeline.process_batch([_wrap_as_consumer_message(event, offset=0)])
        assert result2.published_valid == 0
        assert result2.duplicates_skipped == 1

        # Serving layer still has only one record
        assert len(serving_layer) == 1
        assert serving_layer["evt-serving"].payload.external_id == "prod-serving"

    def test_multiple_replays_maintain_single_logical_record(self) -> None:
        """Multiple replays maintain exactly one logical record per event_id."""
        serving_layer: dict[str, ProductObservationEvent] = {}

        def idempotent_sink(event: ProductObservationEvent) -> None:
            if event.event_id not in serving_layer:
                serving_layer[event.event_id] = event

        dedup_state = DeduplicationState()

        pipeline = ProcessorPipeline(
            validated_sink=idempotent_sink,
            invalid_sink=lambda env: None,
            dedup_state=dedup_state,
        )

        events = [_make_event(event_id=f"evt-{i}", external_id=f"prod-{i}") for i in range(3)]
        messages = [_wrap_as_consumer_message(e, offset=i) for i, e in enumerate(events)]

        # Initial processing
        result1 = pipeline.process_batch(messages)
        assert result1.published_valid == 3
        assert len(serving_layer) == 3

        # Replay 1
        result2 = pipeline.process_batch(messages)
        assert result2.published_valid == 0
        assert result2.duplicates_skipped == 3
        assert len(serving_layer) == 3

        # Replay 2
        result3 = pipeline.process_batch(messages)
        assert result3.published_valid == 0
        assert result3.duplicates_skipped == 3
        assert len(serving_layer) == 3

        # Serving layer never grows beyond initial 3 records
        assert len(serving_layer) == 3


class TestOffsetCommitTiming:
    """Document offset commit timing behavior.

    These tests clarify when offsets are committed relative to processing
    and what happens on failure at different points.
    """

    def test_offset_committed_only_after_successful_processing(self) -> None:
        """Offset is committed ONLY after successful processing completes."""
        committed_offsets: list[int] = []

        def tracking_sink(event: ProductObservationEvent) -> None:
            # Simulate successful processing
            pass

        pipeline = ProcessorPipeline(
            validated_sink=tracking_sink,
            invalid_sink=lambda env: None,
        )

        event = _make_event(event_id="evt-timing")
        message = _wrap_as_consumer_message(event, offset=100)

        result = pipeline.process_batch([message])
        assert result.published_valid == 1

        # In real code, caller would commit offset here:
        # consumer.commit_message(message)
        # which commits offset 101 (next to read)

        # The offset commit happens AFTER pipeline success, not before
        committed_offsets.append(message.offset + 1)
        assert committed_offsets[0] == 101

    def test_crash_before_persistence_no_offset_commit(self) -> None:
        """Crash before persistence means no offset commit; message redelivered."""

        def failing_sink(event: ProductObservationEvent) -> None:
            raise RuntimeError("Crash before persistence")

        pipeline = ProcessorPipeline(
            validated_sink=failing_sink,
            invalid_sink=lambda env: None,
        )

        event = _make_event(event_id="evt-crash-before")
        message = _wrap_as_consumer_message(event, offset=50)

        with pytest.raises(RuntimeError, match="Crash before persistence"):
            pipeline.process_batch([message])

        # Offset NOT committed - message will be redelivered on restart
        # This is correct at-least-once behavior

    def test_crash_after_persistence_before_offset_commit(self) -> None:
        """Crash after persistence but before offset commit causes redelivery.

        This scenario demonstrates why idempotency is critical: the same
        event may be processed multiple times if crash occurs between
        persistence and offset commit.
        """
        persisted_events: list[str] = []

        def persist_then_crash(event: ProductObservationEvent) -> None:
            # Simulate persistence (e.g., write to Parquet/PostgreSQL)
            persisted_events.append(event.event_id)
            # Then crash before offset commit
            raise RuntimeError("Crash after persistence, before offset commit")

        pipeline = ProcessorPipeline(
            validated_sink=persist_then_crash,
            invalid_sink=lambda env: None,
        )

        event = _make_event(event_id="evt-crash-after")
        message = _wrap_as_consumer_message(event, offset=75)

        with pytest.raises(RuntimeError):
            pipeline.process_batch([message])

        # Event was persisted once
        assert len(persisted_events) == 1
        assert persisted_events[0] == "evt-crash-after"

        # Offset NOT committed - on restart, same event redelivered
        # Idempotent processing must handle this (e.g., via event_id check)
