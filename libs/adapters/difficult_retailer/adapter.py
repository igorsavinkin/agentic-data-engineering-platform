"""Difficult retailer source adapter implementing SourceAdapterProtocol.

Demonstrates adapter behavior for a high-traffic retailer that exhibits
challenging collection patterns: bot detection (403/CAPTCHA), rate limiting
(429), service unavailability (503/maintenance), structural page changes,
and partial parseability.

All non-success response classifications are surfaced as SourceFetchError
so downstream consumers can implement source-aware retry and degradation
strategies (TASK-052, TASK-053).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

from libs.adapters import FetchResult, SourceAdapterProtocol, SourceFetchError
from libs.adapters.difficult_retailer.client import DifficultRetailerClient
from libs.adapters.difficult_retailer.parser import ParseResult, parse_listing_page
from libs.event_contracts.product_observation import ProductObservationEvent
from libs.observability.source_metrics import SourceMetric, SourceMetrics

logger = logging.getLogger(__name__)


class DifficultRetailerAdapter(SourceAdapterProtocol):
    """Source adapter for a difficult retailer with anti-bot measures.

    Targets a fictional premium retailer that demonstrates challenging
    collection behaviors. The adapter classifies responses, handles
    structural variations, and surfaces degradation signals through
    SourceFetchError for downstream retry/degradation strategies.

    The adapter does NOT implement stealth or evasion behavior. It respects
    the source's access constraints and reports blocking/rate-limiting as
    explicit outcomes rather than attempting to circumvent them.
    """

    def __init__(
        self,
        *,
        catalog_path: str | None = None,
        timeout: float | None = None,
        base_url: str | None = None,
        user_agent: str | None = None,
        client: DifficultRetailerClient | None = None,
        metrics: SourceMetrics | None = None,
    ) -> None:
        self._catalog_path = catalog_path
        self._metrics = metrics or SourceMetrics(source_name=self.source_name)
        if client is not None:
            self._client = client
        else:
            self._client = DifficultRetailerClient(
                base_url=base_url,
                timeout=timeout,
                user_agent=user_agent,
                catalog_path=catalog_path,
                metrics=self._metrics,
            )

    @property
    def source_name(self) -> str:
        return "premium_retailer"

    async def fetch(self) -> FetchResult[Any]:
        """Fetch and parse a difficult retailer listing page.

        Single-page fetch (no pagination) — difficult sources typically
        require careful request pacing, so pagination is left to the
        caller/orchestrator.

        Raises:
            SourceFetchError: When the source is blocked, rate-limited,
                unavailable, or returns an unusable response.
        """
        self._metrics.increment(SourceMetric.FETCH_ATTEMPTS)

        with self._metrics.time_fetch():
            try:
                return await self._fetch_single()
            except SourceFetchError:
                self._metrics.record_fetch_failure()
                raise
            except Exception:
                self._metrics.record_fetch_failure()
                raise

    async def _fetch_single(self) -> FetchResult[Any]:
        """Execute a single-page fetch-parse cycle."""
        collected_at = datetime.now(timezone.utc)

        html = await self._client.fetch_listing_page(self._catalog_path)

        if not html or not html.strip():
            raise SourceFetchError(
                "Premium retailer returned empty HTML body",
                source="premium_retailer",
            )

        page_url = self._build_page_url()
        result: ParseResult = parse_listing_page(html, page_url=page_url)

        if result.structural_change:
            raise SourceFetchError(
                "Premium retailer page structure has changed: "
                "expected product containers not found",
                source="premium_retailer",
            )

        all_events: list[ProductObservationEvent] = []
        all_malformed: list[dict[str, Any]] = list(result.malformed)

        for product in result.products:
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

        total_collected = len(result.products) + len(result.malformed)

        self._metrics.record_pages_fetched(1)
        if all_malformed:
            self._metrics.record_malformed(len(all_malformed))

        fetch_result: FetchResult[ProductObservationEvent] = FetchResult(
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

        if all_malformed:
            logger.warning(
                "degraded_collection",
                extra={
                    "operation": "fetch",
                    "source": self.source_name,
                    "events_emitted": len(all_events),
                    "malformed_records": len(all_malformed),
                },
            )

        return fetch_result

    def _build_page_url(self) -> str:
        """Build the full page URL for relative URL resolution."""
        resolved_path = self._catalog_path or self._client.catalog_path
        if resolved_path and resolved_path.startswith(("http://", "https://")):
            return resolved_path
        return urljoin(self._client.base_url + "/", (resolved_path or "").lstrip("/"))

    def _to_canonical_event(self, product: Any, collected_at: datetime) -> ProductObservationEvent:
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
