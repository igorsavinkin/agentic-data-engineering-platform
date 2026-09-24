"""Synthetic event generator for load testing (TASK-108).

Generates canonical ``ProductObservationEvent`` instances with realistic
field distributions.  The generator is deterministic when seeded, making
tests reproducible.  It is independent of any source adapter.

Performance: event IDs use a fast counter scheme (``{run_id}-{worker_id}-{n}``)
instead of ``uuid.uuid4()`` to avoid per-event ``os.urandom`` overhead at
high throughput.  Model construction uses ``model_construct()`` to bypass
Pydantic validation — safe because the generator produces valid data by
construction.  The ``collected_at`` timestamp is cached and refreshed at
100 ms intervals to avoid a system call per event.
"""

from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from decimal import Decimal

from libs.event_contracts import (
    Availability,
    ProductObservationEvent,
    ProductObservationPayload,
)

_CATEGORIES = [
    "electronics",
    "clothing",
    "home",
    "sports",
    "books",
    "toys",
    "automotive",
    "garden",
]

_AVAILABILITY_VALUES = list(Availability)
_CURRENCIES = ["EUR", "USD", "GBP"]
_UTC = timezone.utc
_TIMESTAMP_REFRESH_SEC = 0.1


class EventGenerator:
    """Produce synthetic product observation events.

    Parameters
    ----------
    source:
        Source label embedded in each event.
    seed:
        Seed for the internal RNG; makes the sequence deterministic.
    worker_id:
        Worker index; used to build globally unique event IDs without
        requiring ``uuid.uuid4()``.
    run_id:
        Short run identifier embedded in each event ID for traceability.
    """

    def __init__(
        self,
        source: str = "load-test",
        seed: int = 42,
        worker_id: int = 0,
        run_id: str = "0",
    ) -> None:
        self._source = source
        self._rng = random.Random(seed)
        self._counter = 0
        self._worker_id = worker_id
        self._id_prefix = f"{run_id}-{worker_id}-"
        self._cached_now = datetime.now(_UTC)
        self._last_timestamp_refresh = time.monotonic()

    def next_event(self) -> ProductObservationEvent:
        """Generate the next synthetic event in the sequence."""
        self._counter += 1
        now = self._get_timestamp()
        external_id = f"lt-{self._counter:08d}"
        price = Decimal(str(round(self._rng.uniform(1.0, 999.99), 2)))

        payload = ProductObservationPayload.model_construct(
            external_id=external_id,
            name=f"Load Test Product {self._counter}",
            url=f"https://example.com/product/{external_id}",
            price=price,
            currency=self._rng.choice(_CURRENCIES),
            availability=self._rng.choice(_AVAILABILITY_VALUES),
            category=self._rng.choice(_CATEGORIES),
            listing_id=None,
            seller_id=None,
            collected_at=now,
        )

        return ProductObservationEvent.model_construct(
            event_id=f"{self._id_prefix}{self._counter}",
            event_type="product.observation",
            schema_version=1,
            source=self._source,
            produced_at=now,
            payload=payload,
        )

    def generate_batch(self, count: int) -> list[ProductObservationEvent]:
        """Generate a batch of events."""
        return [self.next_event() for _ in range(count)]

    def _get_timestamp(self) -> datetime:
        """Return a cached UTC timestamp, refreshed every 100 ms."""
        if time.monotonic() - self._last_timestamp_refresh >= _TIMESTAMP_REFRESH_SEC:
            self._cached_now = datetime.now(_UTC)
            self._last_timestamp_refresh = time.monotonic()
        return self._cached_now
