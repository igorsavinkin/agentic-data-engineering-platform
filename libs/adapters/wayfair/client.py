"""HTTP client for fetching Wayfair product listing pages."""

from __future__ import annotations

from typing import Optional

import httpx

from libs.adapters import SourceFetchError

WAYFAIR_BASE_URL = "https://www.wayfair.com"
DEFAULT_TIMEOUT = 30.0
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class WayfairClient:
    """Typed HTTP client for fetching Wayfair HTML product listing pages.

    Returns raw HTML body. HTML parsing into product records is out of scope
    for TASK-046 and will be implemented in TASK-047.
    """

    def __init__(
        self,
        *,
        base_url: str = WAYFAIR_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
        search_path: str = "/search/products?keyword=electronics",
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._user_agent = user_agent
        self._search_path = search_path
        self._client = http_client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout),
                headers={
                    "User-Agent": self._user_agent,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                },
            )
        return self._client

    async def fetch_listing_page(self, path: Optional[str] = None) -> str:
        """Fetch a product listing page and return the raw HTML body.

        Args:
            path: URL path to fetch. Defaults to the configured search_path.

        Returns:
            Raw HTML body as a string.

        Raises:
            SourceFetchError: On HTTP errors, timeouts, or connection failures.
        """
        client = await self._get_client()
        fetch_path = path or self._search_path

        try:
            response = await client.get(fetch_path)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 403:
                raise SourceFetchError(
                    "Wayfair returned HTTP 403 (Forbidden). "
                    "The request may have been blocked by bot detection.",
                    source="wayfair",
                ) from exc
            elif status == 429:
                raise SourceFetchError(
                    "Wayfair rate limit exceeded (HTTP 429).",
                    source="wayfair",
                ) from exc
            else:
                raise SourceFetchError(
                    f"Wayfair returned HTTP {status}",
                    source="wayfair",
                ) from exc
        except httpx.TimeoutException as exc:
            raise SourceFetchError(
                "Wayfair request timed out",
                source="wayfair",
            ) from exc
        except httpx.ConnectError as exc:
            raise SourceFetchError(
                f"Wayfair connection failed: {exc}",
                source="wayfair",
            ) from exc
        except httpx.RequestError as exc:
            raise SourceFetchError(
                f"Wayfair request failed: {exc}",
                source="wayfair",
            ) from exc

        return response.text

    async def close(self) -> None:
        """Close the underlying HTTP client if we own it."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
