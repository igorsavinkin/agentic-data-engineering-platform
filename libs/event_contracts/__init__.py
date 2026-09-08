"""Shared event contract models.

The canonical product-observation event envelope and payload definitions
used by Kafka producers and consumers. See ``ai/SPECIFICATION.md`` §7
(Event Contract).
"""

from __future__ import annotations

from libs.event_contracts.product_observation import (
    CURRENT_SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    Availability,
    ProductObservationEvent,
    ProductObservationPayload,
    deserialize_event,
    make_event_id,
    serialize_event,
    utc_now,
)

__all__ = [
    "Availability",
    "CURRENT_SCHEMA_VERSION",
    "ProductObservationEvent",
    "ProductObservationPayload",
    "SUPPORTED_SCHEMA_VERSIONS",
    "deserialize_event",
    "make_event_id",
    "serialize_event",
    "utc_now",
]
