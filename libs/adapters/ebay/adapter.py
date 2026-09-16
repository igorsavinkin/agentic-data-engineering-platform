"""eBay Browse API source adapter implementing SourceAdapterProtocol."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from libs.adapters import FetchResult, SourceAdapterProtocol
from libs.adapters.ebay.client import EbayClient
from libs.adapters.ebay.models import EbayListingSummary
from libs.event_contracts.product_observation import (
    ProductObservationEvent,
)
from libs.marketplace.identity import build_listing_id, build_seller_id
from libs.observability.source_metrics import SourceMetric, SourceMetrics

# Default availability when eBay doesn't provide explicit stock info
DEFAULT_AVAILABILITY = "unknown"


class EbayAdapter(SourceAdapterProtocol):
    """Source adapter for eBay Browse API.

    Implements the SourceAdapterProtocol to fetch product listings from the
    eBay Browse API and emit canonical ProductObservationEvent instances.

    The adapter uses the item_summary/search endpoint which provides lightweight
    listing data suitable for price/availability observations without requiring
    full item detail lookups.

    Attributes:
        source_name: Always "ebay" for this adapter.
    """

    def __init__(
        self,
        *,
        query: Optional[str] = None,
        category_ids: Optional[list[str]] = None,
        limit: Optional[int] = None,
        client: Optional[EbayClient] = None,
        metrics: Optional[SourceMetrics] = None,
        app_id: Optional[str] = None,
        cert_id: Optional[str] = None,
        dev_id: Optional[str] = None,
    ) -> None:
        """Initialize the eBay adapter.

        Args:
            query: Search query string for filtering listings.
            category_ids: Category IDs to filter results.
            limit: Maximum number of listings to fetch per call.
            client: Pre-configured EbayClient (for testing/injection).
            metrics: Optional SourceMetrics instance for observability.
            app_id: eBay application ID (OAuth2 client ID).
            cert_id: eBay certificate ID.
            dev_id: eBay developer ID.
        """
        self._query = query
        self._category_ids = category_ids
        self._limit = limit
        if client is not None:
            self._client = client
        else:
            self._client = EbayClient(
                app_id=app_id,
                cert_id=cert_id,
                dev_id=dev_id,
            )
        self._metrics = metrics or SourceMetrics(source_name=self.source_name)

    @property
    def source_name(self) -> str:
        """Return the canonical source identifier."""
        return "ebay"

    async def fetch(self) -> FetchResult[Any]:
        """Fetch listings from eBay Browse API and map to canonical events.

        Returns:
            FetchResult containing canonical events, any malformed records,
            source identity, and metadata.

        Raises:
            SourceFetchError: On HTTP errors, timeouts, auth failures, or
                rate-limit responses.
        """
        self._metrics.increment(SourceMetric.FETCH_ATTEMPTS)

        with self._metrics.time_fetch():
            try:
                collected_at = datetime.now(timezone.utc)

                # Fetch from eBay API
                search_response, client_malformed = await self._client.search_items(
                    query=self._query,
                    category_ids=self._category_ids,
                    limit=self._limit,
                )

                events: list[ProductObservationEvent] = []
                adapter_malformed: list[dict[str, Any]] = []

                for summary in search_response.item_summaries:
                    try:
                        event = self._map_listing_to_event(summary, collected_at)
                        events.append(event)
                    except Exception:
                        # Canonical validation failure - record with reason
                        adapter_malformed.append(
                            {
                                "raw_record": summary.model_dump(),
                                "reason": "Failed canonical event construction",
                            }
                        )

                # Combine client-level and adapter-level malformed records
                all_malformed = client_malformed + adapter_malformed
                total_collected = len(search_response.item_summaries) + len(client_malformed)

                result: FetchResult[ProductObservationEvent] = FetchResult(
                    events=tuple(events),
                    malformed=tuple(all_malformed),
                    source=self.source_name,
                    fetched_at=datetime.now(timezone.utc),
                    total_records=total_collected,
                )

                # Record success metrics
                self._metrics.record_fetch_success(
                    records_collected=total_collected,
                    records_emitted=len(events),
                )

                return result

            except Exception:
                # Record failure metrics before re-raising
                self._metrics.record_fetch_failure()
                raise

    def _map_listing_to_event(
        self,
        summary: EbayListingSummary,
        collected_at: datetime,
    ) -> ProductObservationEvent:
        """Map an eBay listing summary to a canonical product observation event.

        Args:
            summary: Typed eBay listing summary.
            collected_at: Timestamp when the observation was collected.

        Returns:
            Validated ProductObservationEvent.
        """
        # Determine availability from eBay availability object
        availability = DEFAULT_AVAILABILITY
        if summary.availability is not None:
            if summary.availability.is_in_stock:
                availability = "in_stock"
            else:
                availability = "out_of_stock"

        # Build URL - prefer item_web_url, fallback to constructed URL
        url = summary.item_web_url or f"https://www.ebay.com/itm/{summary.item_id}"

        listing_id = build_listing_id(self.source_name, summary.item_id)
        seller_id = (
            build_seller_id(self.source_name, summary.seller.username) if summary.seller else None
        )

        return self._build_event(
            source=self.source_name,
            external_id=summary.item_id,
            name=summary.title,
            url=url,
            price=summary.price.value if summary.price else None,
            currency=summary.price.currency if summary.price else "USD",
            availability=availability,
            category=self._extract_category(summary),
            collected_at=collected_at,
            listing_id=listing_id,
            seller_id=seller_id,
        )

    @staticmethod
    def _extract_category(summary: EbayListingSummary) -> str:
        """Extract primary category from listing summary.

        Args:
            summary: Typed eBay listing summary.

        Returns:
            Category string, defaults to "uncategorized" if unavailable.
        """
        if summary.category_ids and len(summary.category_ids) > 0:
            # Use the most specific category (last in hierarchy)
            return f"ebay_category_{summary.category_ids[-1]}"
        return "uncategorized"

    async def close(self) -> None:
        """Close underlying HTTP resources."""
        await self._client.close()
