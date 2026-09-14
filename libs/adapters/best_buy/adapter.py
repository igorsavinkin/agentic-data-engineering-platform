"""Best Buy API source adapter implementing SourceAdapterProtocol."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from libs.adapters import FetchResult, SourceAdapterProtocol
from libs.adapters.best_buy.client import BestBuyClient
from libs.adapters.best_buy.models import BestBuyProduct
from libs.event_contracts.product_observation import ProductObservationEvent


# Availability mapping: derive from inStoreAvailability/onlineAvailability
def _map_availability(product: BestBuyProduct) -> str:
    """Map Best Buy availability flags to canonical availability string."""
    in_store = product.inStoreAvailability
    online = product.onlineAvailability

    if in_store is True or online is True:
        return "in_stock"
    elif in_store is False and online is False:
        return "out_of_stock"
    else:
        # Unknown when both are None/unset
        return "unknown"


def _extract_category(product: BestBuyProduct) -> str:
    """Extract the most specific category name from categoryPath."""
    if product.categoryPath and isinstance(product.categoryPath, list):
        # Use the last (most specific) category in the path
        for cat in reversed(product.categoryPath):
            if isinstance(cat, dict) and "name" in cat:
                return str(cat["name"])
    return "uncategorized"


class BestBuyAdapter(SourceAdapterProtocol):
    """Source adapter for Best Buy Products API v1.

    Implements the SourceAdapterProtocol to fetch products from the Best Buy
    REST API and emit canonical ProductObservationEvent instances.

    Attributes:
        source_name: Always "best_buy" for this adapter.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        page_size: int = 10,
        sort: Optional[str] = None,
        timeout: float = 30.0,
        client: Optional[BestBuyClient] = None,
    ) -> None:
        """Initialize the Best Buy adapter.

        Args:
            api_key: Best Buy API key. Falls back to BESTBUY_API_KEY env var.
            page_size: Number of products to fetch per call (max 100).
            sort: Sort order for results, e.g. "sku.asc".
            timeout: HTTP request timeout in seconds.
            client: Pre-configured BestBuyClient (for testing/injection).
        """
        self._page_size = page_size
        self._sort = sort
        if client is not None:
            self._client = client
        else:
            self._client = BestBuyClient(
                api_key=api_key,
                timeout=timeout,
            )

    @property
    def source_name(self) -> str:
        """Return the canonical source identifier."""
        return "best_buy"

    async def fetch(self) -> FetchResult[Any]:
        """Fetch products from Best Buy API and map to canonical events.

        Returns:
            FetchResult containing canonical events, any malformed records,
            source identity, and metadata.

        Raises:
            SourceFetchError: On auth failures, rate limits, timeouts, or response parsing failures.
        """
        collected_at = datetime.now(timezone.utc)

        try:
            products = await self._client.fetch_products(
                page_size=self._page_size,
                sort=self._sort,
            )
        except Exception:
            # Re-raise SourceFetchError as-is; wrap unexpected exceptions
            raise

        events: list[ProductObservationEvent] = []
        malformed: list[dict[str, Any]] = []

        for product in products:
            try:
                event = SourceAdapterProtocol._build_event(
                    source=self.source_name,
                    external_id=str(product.sku),
                    name=product.name,
                    url=product.url or f"https://www.bestbuy.com/site/-/{product.sku}.p",
                    price=product.salePrice
                    if product.salePrice is not None
                    else product.regularPrice,
                    currency="USD",
                    availability=_map_availability(product),
                    category=_extract_category(product),
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
