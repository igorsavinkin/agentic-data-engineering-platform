"""Fake Store API source adapter implementing SourceAdapterProtocol."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from libs.adapters import FetchResult, SourceAdapterProtocol
from libs.adapters.fake_store.client import FakeStoreClient
from libs.event_contracts.product_observation import (
    ProductObservationEvent,
)

# Availability mapping: Fake Store doesn't provide availability, so we default to in_stock.
DEFAULT_AVAILABILITY = "in_stock"


class FakeStoreAdapter(SourceAdapterProtocol):
    """Source adapter for Fake Store API.

    Implements the SourceAdapterProtocol to fetch products from the Fake Store
    REST API and emit canonical ProductObservationEvent instances.

    Attributes:
        source_name: Always "fake_store" for this adapter.
    """

    def __init__(
        self,
        *,
        limit: Optional[int] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        client: Optional[FakeStoreClient] = None,
    ) -> None:
        """Initialize the Fake Store adapter.

        Args:
            limit: Maximum number of products to fetch per call. None = all.
            base_url: Override the Fake Store API base URL (for testing).
            timeout: HTTP request timeout in seconds.
            client: Pre-configured FakeStoreClient (for testing/injection).
        """
        self._limit = limit
        if client is not None:
            self._client = client
        else:
            self._client = FakeStoreClient(
                base_url=base_url or "https://fakestoreapi.com",
                timeout=timeout,
            )

    @property
    def source_name(self) -> str:
        """Return the canonical source identifier."""
        return "fake_store"

    async def fetch(self) -> FetchResult[Any]:
        """Fetch products from Fake Store API and map to canonical events.

        Returns:
            FetchResult containing canonical events, any malformed records,
            source identity, and metadata.

        Raises:
            SourceFetchError: On HTTP errors, timeouts, or response parsing failures.
        """
        collected_at = datetime.now(timezone.utc)

        try:
            products = await self._client.fetch_products(limit=self._limit)
        except Exception:
            # Re-raise SourceFetchError as-is; wrap unexpected exceptions
            raise

        events: list[ProductObservationEvent] = []
        malformed: list[dict[str, Any]] = []

        for product in products:
            try:
                event = SourceAdapterProtocol._build_event(
                    source=self.source_name,
                    external_id=str(product.id),
                    name=product.title,
                    url=f"https://fakestoreapi.com/products/{product.id}",
                    price=product.price if product.price is not None else None,
                    currency="USD",
                    availability=DEFAULT_AVAILABILITY,
                    category=product.category,
                    collected_at=collected_at,
                )
                events.append(event)
            except Exception:
                # Record the raw data as malformed
                malformed.append(product.model_dump())

        return FetchResult(
            events=tuple(events),
            malformed=tuple(malformed),
            source=self.source_name,
            fetched_at=datetime.now(timezone.utc),
            total_records=len(products),
        )

    async def close(self) -> None:
        """Close underlying HTTP resources."""
        await self._client.close()
