"""Source adapter protocol and shared ingestion contract.

Every external source adapter must implement ``SourceAdapterProtocol`` so that
it can emit canonical ``ProductObservationEvent`` instances into the platform
pipeline without leaking source-specific response models downstream.

The protocol is deliberately narrow: adapters own fetching, parsing, mapping,
and error handling; downstream components consume only the canonical event
contract defined in ``libs.event_contracts.product_observation``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from libs.event_contracts.product_observation import (
    ProductObservationEvent,
    utc_now,
)

# ---------------------------------------------------------------------------
# Error types — explicit failure semantics for source adapters
# ---------------------------------------------------------------------------


class SourceFetchError(Exception):
    """Raised when a source adapter cannot complete a fetch cycle.

    This covers transient HTTP failures, timeouts, authentication errors,
    rate-limit responses, and any other condition where the adapter could not
    obtain a usable response from the upstream source.  Callers may retry
    transient failures but should treat persistent failures as a signal that
    the source is degraded or unavailable.
    """

    def __init__(self, message: str, *, source: str | None = None) -> None:
        super().__init__(message)
        self.source = source


class MalformedRecordError(Exception):
    """Raised when an individual source record cannot be mapped to the
    canonical event contract.

    The caller should skip the offending record and continue processing
    remaining records rather than aborting the entire batch.  The error
    carries the raw record so that diagnostics can be emitted without
    exposing the full upstream response structure downstream.
    """

    def __init__(
        self,
        message: str,
        *,
        raw_record: Any | None = None,
        source: str | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_record = raw_record
        self.source = source


# ---------------------------------------------------------------------------
# FetchResult — typed boundary between adapter and pipeline
# ---------------------------------------------------------------------------

T = TypeVar("T")


@dataclass(frozen=True)
class FetchResult(Generic[T]):
    """Result of a single adapter fetch cycle.

    Parameters
    ----------
    events:
        Canonical product-observation events ready for publication to Kafka.
        May be empty when the source returns no records.
    malformed:
        Records that could not be mapped to the canonical contract.  Each entry
        contains the original source record plus a diagnostic message.  Callers
        should route these to the invalid/DLQ path rather than silently
        discarding them.
    source:
        Identifier of the source adapter that produced this result.  Must match
        the ``source`` field on every event in ``events``.
    fetched_at:
        Timestamp when the fetch cycle completed.  Used for freshness tracking
        and observability.
    total_records:
        Total number of records received from the source before filtering.
        Useful for distinguishing "no records" from "all records were malformed".
    """

    events: tuple[ProductObservationEvent, ...]
    malformed: tuple[dict[str, Any], ...]
    source: str
    fetched_at: datetime
    total_records: int = 0

    @property
    def has_events(self) -> bool:
        """Whether this result contains any publishable events."""
        return len(self.events) > 0

    @property
    def has_malformed(self) -> bool:
        """Whether any records failed canonical mapping."""
        return len(self.malformed) > 0


@dataclass
class _MalformedEntry:
    """Internal mutable builder for malformed-record diagnostics."""

    raw: Any
    reason: str


# ---------------------------------------------------------------------------
# SourceAdapterProtocol — the mandatory interface
# ---------------------------------------------------------------------------


class SourceAdapterProtocol(ABC):
    """Mandatory interface for all source adapters.

    Implementations must satisfy these invariants:

    1. Every event in a ``FetchResult`` has ``event.source == self.source_name``.
    2. Every event's ``payload.external_id`` preserves the source-level
       identifier without transformation.
    3. Source-specific response structures never appear in ``events``; they are
       either mapped to the canonical payload or recorded in ``malformed``.
    4. A fetch cycle that encounters *only* malformed records returns an empty
       ``events`` tuple with non-empty ``malformed``.
    5. A fetch cycle that encounters zero source records returns empty
       ``events`` and empty ``malformed`` with ``total_records == 0``.
    6. Transient network/auth failures raise ``SourceFetchError`` rather than
       returning partial results.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique identifier for this source adapter.

        Must be stable across restarts and must match the ``source`` field on
        every emitted event.  Examples: ``"fake_store"``, ``"best_buy"``.
        """
        ...

    @abstractmethod
    async def fetch(self) -> FetchResult[Any]:
        """Execute one fetch cycle against the upstream source.

        Returns
        -------
        FetchResult
            Canonical events ready for Kafka publication, plus any malformed
            records that could not be mapped.

        Raises
        ------
        SourceFetchError
            When the adapter cannot obtain a usable response from the source
            (timeout, HTTP error, auth failure, rate limit).
        """
        ...

    # -- helpers available to concrete implementations ------------------------

    @staticmethod
    def _make_event_id(source: str, external_id: str, collected_at: datetime) -> str:
        """Build a deterministic event id for testing and replay."""
        return f"{source}:{external_id}:{collected_at.isoformat()}"

    @staticmethod
    def _now_utc() -> datetime:
        """Current UTC timestamp for event timestamps."""
        return utc_now()

    @staticmethod
    def _build_event(
        *,
        source: str,
        external_id: str,
        name: str,
        url: str,
        price: float | None,
        currency: str,
        availability: str,
        category: str,
        collected_at: datetime,
    ) -> ProductObservationEvent:
        """Construct a validated canonical event.

        Concrete adapters call this helper after mapping source fields to the
        canonical shape.  All validation (non-negative price, timezone-aware
        timestamps, schema version) is enforced by the Pydantic model.
        """
        from decimal import Decimal

        from libs.event_contracts.product_observation import (
            Availability,
            ProductObservationPayload,
        )

        payload = ProductObservationPayload(
            external_id=external_id,
            name=name,
            url=url,
            price=Decimal(str(price)) if price is not None else None,
            currency=currency.upper(),
            availability=Availability(availability),
            category=category,
            collected_at=collected_at,
        )

        return ProductObservationEvent(
            event_id=f"{source}:{external_id}:{collected_at.isoformat()}",
            source=source,
            produced_at=datetime.now(timezone.utc),
            payload=payload,
        )
