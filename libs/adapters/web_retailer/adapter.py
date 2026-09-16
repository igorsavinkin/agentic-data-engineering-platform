"""Web retailer source adapter implementing SourceAdapterProtocol."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

from libs.adapters import FetchResult, SourceAdapterProtocol, SourceFetchError
from libs.adapters.web_retailer.client import WebRetailerClient
from libs.adapters.web_retailer.parser import (
    ParsedProduct,
    extract_next_page_url,
    parse_listing_page,
)
from libs.event_contracts.product_observation import ProductObservationEvent
from libs.observability.source_metrics import SourceMetric, SourceMetrics

logger = logging.getLogger(__name__)

DEFAULT_MAX_PAGES = 5


class WebRetailerAdapter(SourceAdapterProtocol):
    """Source adapter for a web retailer product listing pages.

    Targets books.toscrape.com — a realistic bookstore with standard
    e-commerce product pages served as plain HTML.

    Paginates through listing pages up to ``max_pages`` and aggregates
    all events into a single FetchResult. Partial failures (page N+1
    fails after page N succeeded) return collected pages rather than
    losing everything.
    """

    def __init__(
        self,
        *,
        catalog_path: str | None = None,
        timeout: float | None = None,
        base_url: str | None = None,
        user_agent: str | None = None,
        max_pages: int | None = None,
        client: WebRetailerClient | None = None,
        metrics: SourceMetrics | None = None,
    ) -> None:
        self._catalog_path = catalog_path
        self._max_pages = max_pages if max_pages is not None else DEFAULT_MAX_PAGES
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
        """Fetch and parse web retailer listing pages with pagination.

        Paginates through pages up to max_pages, aggregating events and
        malformed records. If a page fails after previous pages succeeded,
        returns partial results with a logged error.

        Raises:
            SourceFetchError: On first-page failure or non-recoverable errors.
        """
        self._metrics.increment(SourceMetric.FETCH_ATTEMPTS)

        with self._metrics.time_fetch():
            try:
                return await self._fetch_paginated()
            except SourceFetchError:
                self._metrics.record_fetch_failure()
                raise
            except Exception:
                self._metrics.record_fetch_failure()
                raise

    async def _fetch_paginated(self) -> FetchResult[Any]:
        """Execute the pagination loop, aggregating results across pages."""
        collected_at = datetime.now(timezone.utc)
        all_events: list[ProductObservationEvent] = []
        all_malformed: list[dict[str, Any]] = []
        total_collected = 0

        current_path: str | None = self._catalog_path

        for page_num in range(1, self._max_pages + 1):
            try:
                html = await self._client.fetch_listing_page(current_path)
            except SourceFetchError:
                if page_num > 1:
                    logger.error(
                        "Pagination failed at page %d after %d successful pages; "
                        "returning partial results",
                        page_num,
                        page_num - 1,
                    )
                    break
                raise

            if not html or not html.strip():
                if page_num == 1:
                    raise SourceFetchError(
                        "Web retailer returned empty HTML body",
                        source="web_retailer",
                    )
                logger.warning("Empty HTML on page %d, stopping pagination", page_num)
                break

            page_url = self._build_page_url_for_path(current_path)
            parsed, parser_malformed = parse_listing_page(html, page_url=page_url)

            for product in parsed:
                try:
                    event = self._to_canonical_event(product, collected_at)
                    all_events.append(event)
                except Exception:
                    all_malformed.append(
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

            page_total = len(parsed) + len(parser_malformed)
            total_collected += page_total
            all_malformed.extend(parser_malformed)

            if page_num >= self._max_pages:
                break

            next_url = extract_next_page_url(html, page_url)
            if next_url is None:
                break
            current_path = next_url

        result: FetchResult[ProductObservationEvent] = FetchResult(
            events=tuple(all_events),
            malformed=tuple(all_malformed),
            source=self.source_name,
            fetched_at=collected_at,
            total_records=total_collected,
        )

        self._metrics.record_fetch_success(
            records_collected=total_collected,
            records_emitted=len(all_events),
        )

        return result

    def _build_page_url_for_path(self, path: str | None) -> str:
        """Build the full page URL for a given path (for relative URL resolution)."""
        resolved_path = path or self._catalog_path or self._client.catalog_path
        if resolved_path and resolved_path.startswith(("http://", "https://")):
            return resolved_path
        return urljoin(self._client.base_url + "/", (resolved_path or "").lstrip("/"))

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
