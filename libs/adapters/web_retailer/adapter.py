"""Web retailer source adapter implementing SourceAdapterProtocol."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from libs.adapters import FetchResult, SourceAdapterProtocol, SourceFetchError
from libs.adapters.web_retailer.client import WebRetailerClient
from libs.observability.source_metrics import SourceMetric, SourceMetrics


class WebRetailerAdapter(SourceAdapterProtocol):
    """Source adapter for a web retailer product listing pages.

    Targets books.toscrape.com — a realistic bookstore with standard
    e-commerce product pages served as plain HTML.

    TASK-046: Fetches HTML from the retailer but does not parse it into
    product records. HTML parsing will be implemented in TASK-047.

    The adapter returns an empty FetchResult to confirm the HTTP client,
    error handling, and protocol wiring work correctly.
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
        """Fetch a web retailer product listing page.

        TASK-046: Returns an empty FetchResult after successfully fetching HTML.
        HTML parsing into canonical events will be implemented in TASK-047.

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

                result: FetchResult[Any] = FetchResult(
                    events=(),
                    malformed=(),
                    source=self.source_name,
                    fetched_at=collected_at,
                    total_records=0,
                )

                self._metrics.record_fetch_success(
                    records_collected=0,
                    records_emitted=0,
                )

                return result

            except SourceFetchError:
                self._metrics.record_fetch_failure()
                raise
            except Exception:
                self._metrics.record_fetch_failure()
                raise

    async def close(self) -> None:
        """Close underlying HTTP resources."""
        await self._client.close()
