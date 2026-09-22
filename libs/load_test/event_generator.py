"""Synthetic event generator for load testing (TASK-108).

Generates canonical ``ProductObservationEvent`` instances with realistic
field distributions.  The generator is deterministic when seeded, making
tests reproducible.  It is independent of any source adapter.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone

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


class EventGenerator:
    """Produce synthetic product observation events.

    Parameters
    ----------
    source:
        Source label embedded in each event.
    seed:
        Seed for the internal RNG; makes the sequence deterministic.
    """

    def __init__(self, source: str = "load-test", seed: int = 42) -> None:
        self._source = source
        self._rng = random.Random(seed)
        self._counter = 0

    def next_event(self) -> ProductObservationEvent:
        """Generate the next synthetic event in the sequence."""
        self._counter += 1
        now = datetime.now(timezone.utc)
        external_id = f"lt-{self._counter:08d}"
        price = round(self._rng.uniform(1.0, 999.99), 2)

        payload = ProductObservationPayload(
            external_id=external_id,
            name=f"Load Test Product {self._counter}",
            url=f"https://example.com/product/{external_id}",
            price=price,
            currency=self._rng.choice(_CURRENCIES),
            availability=self._rng.choice(_AVAILABILITY_VALUES),
            category=self._rng.choice(_CATEGORIES),
            collected_at=now,
        )

        return ProductObservationEvent(
            event_id=str(uuid.uuid4()),
            source=self._source,
            produced_at=now,
            payload=payload,
        )

    def generate_batch(self, count: int) -> list[ProductObservationEvent]:
        """Generate a batch of events."""
        return [self.next_event() for _ in range(count)]
