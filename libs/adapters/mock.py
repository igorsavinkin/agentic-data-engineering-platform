"""Deterministic mock source adapter for testing.

This module provides ``MockSourceAdapter`` which implements
``SourceAdapterProtocol`` with fully configurable, deterministic behavior.
It is intended for unit tests and integration tests that must not depend on
live upstream sources.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from libs.adapters.protocol import FetchResult, SourceAdapterProtocol


class MockSourceAdapter(SourceAdapterProtocol):
    """A mock adapter whose fetch behavior is entirely configured by the caller.

    Parameters
    ----------
    source_name:
        The value returned by ``self.source_name`` and placed in every event's
        ``source`` field.  Defaults to ``"mock_source"``.
    events:
        Pre-built canonical events to return on every call to ``fetch()``.
        When empty, ``fetch()`` returns an empty result.
    malformed:
        Raw records that could not be mapped.  Each entry is a dict containing
        at least a ``"reason"`` key; these are returned verbatim in the
        ``FetchResult.malformed`` tuple.
    raise_on_fetch:
        If set, ``fetch()`` raises this exception instead of returning a result.
        Useful for testing transient-failure handling.
    total_records:
        Override the ``total_records`` field on the returned ``FetchResult``.
        When ``None``, it defaults to ``len(events) + len(malformed)``.
    """

    def __init__(
        self,
        *,
        source_name: str = "mock_source",
        events: Sequence[Any] | None = None,
        malformed: Sequence[dict[str, Any]] | None = None,
        raise_on_fetch: Exception | None = None,
        total_records: int | None = None,
    ) -> None:
        self._source_name = source_name
        self._events = tuple(events or [])
        self._malformed = tuple(malformed or [])
        self._raise_on_fetch = raise_on_fetch
        self._total_records = total_records
        self.fetch_call_count: int = 0

    @property
    def source_name(self) -> str:
        return self._source_name

    async def fetch(self) -> FetchResult[Any]:
        if self._raise_on_fetch is not None:
            raise self._raise_on_fetch

        self.fetch_call_count += 1
        total = (
            self._total_records
            if self._total_records is not None
            else len(self._events) + len(self._malformed)
        )

        return FetchResult(
            events=self._events,
            malformed=self._malformed,
            source=self._source_name,
            fetched_at=datetime.now(timezone.utc),
            total_records=total,
        )
