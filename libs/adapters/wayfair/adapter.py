"""Wayfair source adapter implementing SourceAdapterProtocol."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from libs.adapters import FetchResult, SourceAdapterProtocol, SourceFetchError
from libs.adapters.wayfair.client import WayfairClient
from libs.observability.source_metrics import SourceMetric, SourceMetrics


class WayfairAdapter(SourceAdapterProtocol):
    """Source adapter for Wayfair product listing pages.

    TASK-046: Fetches HTML from Wayfair but does not parse it into product
    records. HTML parsing will be implemented in TASK-047.

    The adapter returns an empty FetchResult to confirm the HTTP client,
    error handling, and protocol wiring work correctly.
    """

    def __init__(
        self,
        *,
        search_path: str = "/search/products?keyword=electronics",
        timeout: float = 30.0,
        user_agent: Optional[str] = None,
        client: Optional[WayfairClient] = None,
        metrics: Optional[SourceMetrics] = None,
    ) -> None:
        self._search_path = search_path
        if client is not None:
            self._client = client
        else:
            kwargs: dict[str, Any] = {"timeout": timeout, "search_path": search_path}
            if user_agent is not None:
                kwargs["user_agent"] = user_agent
            self._client = WayfairClient(**kwargs)
        self._metrics = metrics or SourceMetrics(source_name=self.source_name)

    @property
    def source_name(self) -> str:
        return "wayfair"

    async def fetch(self) -> FetchResult[Any]:
        """Fetch a Wayfair product listing page.

        TASK-046: Returns an empty FetchResult after successfully fetching HTML.
        HTML parsing into canonical events will be implemented in TASK-047.

        Raises:
            SourceFetchError: On HTTP errors, timeouts, or connection failures.
        """
        self._metrics.increment(SourceMetric.FETCH_ATTEMPTS)

        with self._metrics.time_fetch():
            try:
                html = await self._client.fetch_listing_page(self._search_path)

                # TASK-046: HTML parsing not yet implemented.
                # Confirm we received non-empty HTML as a sanity check.
                if not html or not html.strip():
                    raise SourceFetchError(
                        "Wayfair returned empty HTML body",
                        source="wayfair",
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
