"""Tests for the source adapter protocol and shared ingestion contract.

Covers:
- adapter contract / protocol behavior
- canonical mapping boundary (source identity preservation)
- empty result behavior
- malformed record behavior
- deterministic mock adapter
- FetchResult semantics
- error types
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from libs.adapters import (
    FetchResult,
    MalformedRecordError,
    MockSourceAdapter,
    SourceAdapterProtocol,
    SourceFetchError,
)
from libs.event_contracts.product_observation import (
    ProductObservationEvent,
    make_event_id,
    utc_now,
)

# ---------------------------------------------------------------------------
# Fixtures — reusable canonical events
# ---------------------------------------------------------------------------


def _make_test_event(
    *,
    source: str = "test_source",
    external_id: str = "prod-1",
    name: str = "Test Product",
    url: str = "https://example.com/1",
    price: float | None = 29.99,
    currency: str = "USD",
    availability: str = "in_stock",
    category: str = "electronics",
    collected_at: datetime | None = None,
) -> ProductObservationEvent:
    """Build a valid canonical event for tests."""
    ts = collected_at or utc_now()
    return ProductObservationEvent(
        event_id=make_event_id(source, external_id, ts),
        source=source,
        produced_at=datetime.now(timezone.utc),
        payload={
            "external_id": external_id,
            "name": name,
            "url": url,
            "price": Decimal(str(price)) if price is not None else None,
            "currency": currency,
            "availability": availability,
            "category": category,
            "collected_at": ts,
        },
    )


@pytest.fixture
def sample_event() -> ProductObservationEvent:
    return _make_test_event()


@pytest.fixture
def sample_events() -> list[ProductObservationEvent]:
    return [
        _make_test_event(external_id="p-1", name="Widget A"),
        _make_test_event(external_id="p-2", name="Widget B"),
        _make_test_event(external_id="p-3", name="Widget C"),
    ]


# ---------------------------------------------------------------------------
# 1. Adapter contract / protocol behavior
# ---------------------------------------------------------------------------


class TestAdapterContract:
    """Verify that the protocol enforces the mandatory interface."""

    def test_protocol_is_abstract(self) -> None:
        """SourceAdapterProtocol cannot be instantiated directly."""
        with pytest.raises(TypeError):
            SourceAdapterProtocol()  # type: ignore[abstract]

    def test_mock_implements_protocol(self) -> None:
        """MockSourceAdapter satisfies the protocol interface."""
        adapter = MockSourceAdapter(source_name="mock")
        assert isinstance(adapter, SourceAdapterProtocol)
        assert adapter.source_name == "mock"

    def test_fetch_returns_fetch_result(self) -> None:
        """fetch() must return a FetchResult instance."""
        adapter = MockSourceAdapter()
        result = asyncio.run(adapter.fetch())
        assert isinstance(result, FetchResult)

    def test_source_name_matches_event_source(
        self, sample_events: list[ProductObservationEvent]
    ) -> None:
        """Every event's source field must equal adapter.source_name."""
        # Override the event's source to match the adapter
        evt = _make_test_event(source="fake_store", external_id="p-1")
        adapter_with_match = MockSourceAdapter(source_name="fake_store", events=[evt])
        result = asyncio.run(adapter_with_match.fetch())
        assert all(e.source == "fake_store" for e in result.events)

    def test_fetch_is_async(self) -> None:
        """fetch() must be an async method."""
        adapter = MockSourceAdapter()
        coro = adapter.fetch()
        assert hasattr(coro, "__await__")
        asyncio.run(coro)


# ---------------------------------------------------------------------------
# 2. Canonical mapping boundary — source identity preservation
# ---------------------------------------------------------------------------


class TestCanonicalMappingBoundary:
    """Source identity and external_id must be preserved through the boundary."""

    def test_source_identity_preserved(self) -> None:
        """Events carry the adapter's source_name unchanged."""
        evt = _make_test_event(source="best_buy", external_id="sku-123")
        adapter_with_evt = MockSourceAdapter(source_name="best_buy", events=[evt])
        result = asyncio.run(adapter_with_evt.fetch())
        assert result.source == "best_buy"
        assert result.events[0].source == "best_buy"

    def test_external_id_preserved(self) -> None:
        """payload.external_id is the source-level identifier, untransformed."""
        evt = _make_test_event(external_id="BESTBUY-SKU-99999")
        adapter_with_evt = MockSourceAdapter(events=[evt])
        result = asyncio.run(adapter_with_evt.fetch())
        assert result.events[0].payload.external_id == "BESTBUY-SKU-99999"

    def test_no_source_specific_fields_leak(self) -> None:
        """Events contain only canonical fields; no extra source data."""
        evt = _make_test_event()
        adapter_with_evt = MockSourceAdapter(events=[evt])
        result = asyncio.run(adapter_with_evt.fetch())
        event_dict = result.events[0].model_dump()
        # The canonical envelope has exactly these top-level keys
        assert set(event_dict.keys()) == {
            "event_id",
            "event_type",
            "schema_version",
            "source",
            "produced_at",
            "payload",
        }

    def test_multiple_sources_remain_separate(self) -> None:
        """Two adapters produce events with distinct source values."""
        fake = MockSourceAdapter(
            source_name="fake_store",
            events=[_make_test_event(source="fake_store", external_id="fs-1")],
        )
        bestbuy = MockSourceAdapter(
            source_name="best_buy",
            events=[_make_test_event(source="best_buy", external_id="bb-1")],
        )
        r_fake = asyncio.run(fake.fetch())
        r_bb = asyncio.run(bestbuy.fetch())
        assert r_fake.events[0].source == "fake_store"
        assert r_bb.events[0].source == "best_buy"
        assert r_fake.events[0].source != r_bb.events[0].source


# ---------------------------------------------------------------------------
# 3. Empty result behavior
# ---------------------------------------------------------------------------


class TestEmptyResultBehavior:
    """Adapters must handle zero-record responses correctly."""

    def test_empty_fetch_returns_empty_events(self) -> None:
        """No events when the source returns nothing."""
        adapter = MockSourceAdapter()
        result = asyncio.run(adapter.fetch())
        assert result.events == ()
        assert result.malformed == ()
        assert result.total_records == 0
        assert not result.has_events
        assert not result.has_malformed

    def test_empty_fetch_total_records_zero(self) -> None:
        """total_records is 0 when there are truly no records."""
        adapter = MockSourceAdapter()
        result = asyncio.run(adapter.fetch())
        assert result.total_records == 0

    def test_explicit_total_records_override(self) -> None:
        """Caller can override total_records for edge cases."""
        adapter = MockSourceAdapter(total_records=5)
        result = asyncio.run(adapter.fetch())
        assert result.total_records == 5


# ---------------------------------------------------------------------------
# 4. Malformed record behavior
# ---------------------------------------------------------------------------


class TestMalformedRecordBehavior:
    """Adapters must separate valid events from unmappable records."""

    def test_malformed_records_returned_separately(self) -> None:
        """Malformed records appear in .malformed, not .events."""
        bad_record = {"reason": "missing external_id", "raw": {"id": None}}
        adapter = MockSourceAdapter(malformed=[bad_record])
        result = asyncio.run(adapter.fetch())
        assert result.events == ()
        assert len(result.malformed) == 1
        assert result.malformed[0]["reason"] == "missing external_id"
        assert result.has_malformed

    def test_mixed_valid_and_malformed(self, sample_events: list[ProductObservationEvent]) -> None:
        """Valid events and malformed records coexist in one result."""
        bad = {"reason": "invalid price", "raw": {"price": -1}}
        adapter = MockSourceAdapter(
            events=sample_events[:2],
            malformed=[bad],
            total_records=3,
        )
        result = asyncio.run(adapter.fetch())
        assert len(result.events) == 2
        assert len(result.malformed) == 1
        assert result.total_records == 3

    def test_all_malformed_yields_empty_events(self) -> None:
        """When every record is malformed, events is empty."""
        bads = [
            {"reason": "no name"},
            {"reason": "bad currency"},
        ]
        adapter = MockSourceAdapter(malformed=bads, total_records=2)
        result = asyncio.run(adapter.fetch())
        assert result.events == ()
        assert len(result.malformed) == 2
        assert result.total_records == 2


# ---------------------------------------------------------------------------
# 5. Deterministic mock adapter
# ---------------------------------------------------------------------------


class TestDeterministicMockAdapter:
    """MockSourceAdapter must be fully predictable and repeatable."""

    def test_deterministic_results(self) -> None:
        """Same configuration produces identical results across calls."""
        evt = _make_test_event(external_id="det-1")
        adapter = MockSourceAdapter(source_name="det", events=[evt])
        r1 = asyncio.run(adapter.fetch())
        r2 = asyncio.run(adapter.fetch())
        # Events are the same objects (frozen tuple)
        assert r1.events == r2.events
        assert r1.source == r2.source == "det"

    def test_fetch_call_count_tracks_invocations(self) -> None:
        """fetch_call_count increments on each fetch()."""
        adapter = MockSourceAdapter()
        assert adapter.fetch_call_count == 0
        asyncio.run(adapter.fetch())
        assert adapter.fetch_call_count == 1
        asyncio.run(adapter.fetch())
        assert adapter.fetch_call_count == 2

    def test_raise_on_fetch_raises_exception(self) -> None:
        """Configured exception is raised instead of returning a result."""
        err = SourceFetchError("simulated timeout", source="mock")
        adapter = MockSourceAdapter(raise_on_fetch=err)
        with pytest.raises(SourceFetchError, match="simulated timeout"):
            asyncio.run(adapter.fetch())

    def test_custom_source_name(self) -> None:
        """source_name is configurable and reflected in results."""
        adapter = MockSourceAdapter(source_name="custom_src")
        result = asyncio.run(adapter.fetch())
        assert result.source == "custom_src"
        assert adapter.source_name == "custom_src"


# ---------------------------------------------------------------------------
# 6. FetchResult semantics
# ---------------------------------------------------------------------------


class TestFetchResultSemantics:
    """FetchResult properties and frozen immutability."""

    def test_frozen_dataclass(self, sample_event: ProductObservationEvent) -> None:
        """FetchResult is immutable after construction."""
        result = FetchResult(
            events=(sample_event,),
            malformed=(),
            source="test",
            fetched_at=utc_now(),
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            result.events = ()  # type: ignore[misc]

    def test_has_events_property(self, sample_events: list[ProductObservationEvent]) -> None:
        """has_events reflects whether events tuple is non-empty."""
        empty = FetchResult(events=(), malformed=(), source="x", fetched_at=utc_now())
        full = FetchResult(
            events=tuple(sample_events), malformed=(), source="x", fetched_at=utc_now()
        )
        assert not empty.has_events
        assert full.has_events

    def test_has_malformed_property(self) -> None:
        """has_malformed reflects whether malformed tuple is non-empty."""
        clean = FetchResult(events=(), malformed=(), source="x", fetched_at=utc_now())
        dirty = FetchResult(
            events=(),
            malformed=({"reason": "bad"},),
            source="x",
            fetched_at=utc_now(),
        )
        assert not clean.has_malformed
        assert dirty.has_malformed

    def test_fetched_at_is_timezone_aware(self) -> None:
        """fetched_at must carry timezone information."""
        result = FetchResult(events=(), malformed=(), source="x", fetched_at=utc_now())
        assert result.fetched_at.tzinfo is not None


# ---------------------------------------------------------------------------
# 7. Error types
# ---------------------------------------------------------------------------


class TestErrorTypes:
    """SourceFetchError and MalformedRecordError semantics."""

    def test_source_fetch_error_message(self) -> None:
        err = SourceFetchError("connection refused", source="fake_store")
        assert str(err) == "connection refused"
        assert err.source == "fake_store"

    def test_source_fetch_error_without_source(self) -> None:
        err = SourceFetchError("timeout")
        assert err.source is None

    def test_malformed_record_error_carries_raw(self) -> None:
        raw = {"id": None, "name": ""}
        err = MalformedRecordError(
            "external_id is required",
            raw_record=raw,
            source="best_buy",
        )
        assert str(err) == "external_id is required"
        assert err.raw_record == raw
        assert err.source == "best_buy"

    def test_malformed_record_error_without_raw(self) -> None:
        err = MalformedRecordError("parse failure")
        assert err.raw_record is None
        assert err.source is None

    def test_errors_are_exception_subclasses(self) -> None:
        assert issubclass(SourceFetchError, Exception)
        assert issubclass(MalformedRecordError, Exception)


# ---------------------------------------------------------------------------
# 8. Protocol helper methods
# ---------------------------------------------------------------------------


class TestProtocolHelpers:
    """Static helpers on SourceAdapterProtocol."""

    def test_make_event_id_deterministic(self) -> None:
        eid = SourceAdapterProtocol._make_event_id(
            source="test",
            external_id="e-1",
            collected_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
        )
        assert eid == "test:e-1:2026-09-14T00:00:00+00:00"

    def test_build_event_produces_valid_event(self) -> None:
        evt = SourceAdapterProtocol._build_event(
            source="test_src",
            external_id="t-1",
            name="Helper Product",
            url="https://example.com/t-1",
            price=19.99,
            currency="EUR",
            availability="in_stock",
            category="gadgets",
            collected_at=datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc),
        )
        assert isinstance(evt, ProductObservationEvent)
        assert evt.source == "test_src"
        assert evt.payload.external_id == "t-1"
        assert evt.payload.price == Decimal("19.99")
        assert evt.payload.currency == "EUR"

    def test_build_event_none_price(self) -> None:
        evt = SourceAdapterProtocol._build_event(
            source="test",
            external_id="np",
            name="No Price",
            url="https://example.com/np",
            price=None,
            currency="USD",
            availability="unknown",
            category="misc",
            collected_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
        )
        assert evt.payload.price is None
