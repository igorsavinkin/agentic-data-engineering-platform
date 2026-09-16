"""Web retailer source adapter implementing SourceAdapterProtocol."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

from libs.adapters import FetchResult, SourceAdapterProtocol, SourceFetchError
from libs.adapters.web_retailer.client import WebRetailerClient
from libs.adapters.web_retailer.parser import ParsedProduct, parse_listing_page
from libs.event_contracts.product_observation import ProductObservationEvent
from libs.observability.source_metrics import SourceMetric, SourceMetrics

logger = logging.getLogger(__name__)


class WebRetailerAdapter(SourceAdapterProtocol):
    """Source adapter for a web retailer product listing pages.

    Targets books.toscrape.com — a realistic bookstore with standard
    e-commerce product pages served as plain HTML.
    """

    def __init__(
        self,
        *,
        catalog_path: str | None = None,
        timeout: float | None = None,
        base_url: str | None = None,
        user_agent: str | None = None,
        client: WebRetailerClient | None = None,
        metrics: SourceMetrics | None = None,
    ) -> None:
        self._catalog_path = catalog_path
        if client is not None:
            self._client = client
        else:
            self._client = WebRetailerClient(
                base_url=base_url,
                timeout=timeout,
                user_agent=user_agent,
                catalog_path=catalog_path,
            )
        self._metrics = metrics or SourceMetrics(source_name=self.source_name)

    @property
    def source_name(self) -> str:
        return "web_retailer"

    async def fetch(self) -> FetchResult[Any]:
        """Fetch and parse a web retailer product listing page.

        Fetches HTML from the retailer, parses product records, and maps
        them to canonical ProductObservationEvent instances.

        Raises:
            SourceFetchError: On HTTP errors, timeouts, or connection failures.
        """
        self._metrics.increment(SourceMetric.FETCH_ATTEMPTS)

        with self._metrics.time_fetch():
            try:
                html = await self._client.fetch_listing_page(self._catalog_path)

                if not html or not html.strip():
                    raise SourceFetchError(
                        "Web retailer returned empty HTML body",
                        source="web_retailer",
                    )

                collected_at = datetime.now(timezone.utc)
                page_url = self._build_page_url()

                parsed, parser_malformed = parse_listing_page(html, page_url=page_url)

                events: list[ProductObservationEvent] = []
                malformed: list[dict[str, Any]] = list(parser_malformed)

                for product in parsed:
                    try:
                        event = self._to_canonical_event(product, collected_at)
                        events.append(event)
                    except Exception:
                        malformed.append(
                            {
                                "raw_record": {
                                    "product_id": product.product_id,
                                    "name": product.name,
                                    "price": str(product.price) if product.price else None,
                                    "url": product.url,
                                },
                                "reason": "Failed canonical event construction",
                            }
                        )

                total_collected = len(parsed) + len(parser_malformed)

                result: FetchResult[ProductObservationEvent] = FetchResult(
                    events=tuple(events),
                    malformed=tuple(malformed),
                    source=self.source_name,
                    fetched_at=collected_at,
                    total_records=total_collected,
                )

                self._metrics.record_fetch_success(
                    records_collected=total_collected,
                    records_emitted=len(events),
                )

                return result

            except SourceFetchError:
                self._metrics.record_fetch_failure()
                raise
            except Exception:
                self._metrics.record_fetch_failure()
                raise

    def _build_page_url(self) -> str:
        """Build the full page URL for relative URL resolution."""
        path = self._catalog_path or self._client.catalog_path
        return urljoin(self._client.base_url + "/", path.lstrip("/"))

    def _to_canonical_event(
        self, product: ParsedProduct, collected_at: datetime
    ) -> ProductObservationEvent:
        """Map a ParsedProduct to a canonical ProductObservationEvent."""
        return SourceAdapterProtocol._build_event(
            source=self.source_name,
            external_id=product.product_id,
            name=product.name,
            url=product.url,
            price=product.price,
            currency=product.currency,
            availability=product.availability,
            category=product.category,
            collected_at=collected_at,
        )

    async def close(self) -> None:
        """Close underlying HTTP resources."""
        await self._client.close()
