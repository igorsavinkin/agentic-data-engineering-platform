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

        # Client returns (valid_products, malformed_records) - both count toward total
        products, client_malformed = await self._client.fetch_products(limit=self._limit)

        events: list[ProductObservationEvent] = []
        adapter_malformed: list[dict[str, Any]] = []

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
                # Canonical validation failure - record with reason
                adapter_malformed.append(
                    {
                        "raw_record": product.model_dump(),
                        "reason": "Failed canonical event construction",
                    }
                )

        # Combine client-level and adapter-level malformed records
        all_malformed = client_malformed + adapter_malformed

        return FetchResult(
            events=tuple(events),
            malformed=tuple(all_malformed),
            source=self.source_name,
            fetched_at=datetime.now(timezone.utc),
            total_records=len(products) + len(client_malformed),
        )

    async def close(self) -> None:
        """Close underlying HTTP resources."""
        await self._client.close()
