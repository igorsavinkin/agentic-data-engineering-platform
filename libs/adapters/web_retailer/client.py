"""HTTP client for fetching web retailer product listing pages."""

from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx

from libs.adapters import SourceFetchError

DEFAULT_BASE_URL = "http://books.toscrape.com"
DEFAULT_TIMEOUT = 30.0
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_CATALOG_PATH = "/catalogue/category/books_1/index.html"


def _resolve_config(
    env_var: str, constructor_value: str | float | None, default: str | float
) -> str | float:
    """Resolve configuration: constructor arg > env var > default."""
    if constructor_value is not None:
        return constructor_value
    env_value = os.environ.get(env_var)
    if env_value is not None:
        return env_value
    return default


def _validate_base_url(url: str) -> None:
    """Validate that base_url is a non-empty, parseable URL."""
    if not url or not url.strip():
        raise SourceFetchError("base_url must be a non-empty string", source="web_retailer")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SourceFetchError(
            f"base_url must use http or https scheme, got '{parsed.scheme or '(none)'}'",
            source="web_retailer",
        )
    if not parsed.netloc:
        raise SourceFetchError("base_url must include a hostname", source="web_retailer")


def _validate_timeout(timeout: float) -> None:
    """Validate that timeout is a positive finite number."""
    if timeout <= 0:
        raise SourceFetchError(
            f"timeout must be positive, got {timeout}",
            source="web_retailer",
        )
    if timeout != timeout:  # NaN check
        raise SourceFetchError("timeout must be a finite number", source="web_retailer")


class WebRetailerClient:
    """Typed HTTP client for fetching web retailer HTML product listing pages.

    Returns raw HTML body. HTML parsing into product records is out of scope
    for TASK-046 and will be implemented in TASK-047.

    Configuration is resolved in priority order: constructor argument,
    environment variable, default value.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        user_agent: str | None = None,
        catalog_path: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        resolved_base_url = str(
            _resolve_config("WEB_RETAILER_BASE_URL", base_url, DEFAULT_BASE_URL)
        )
        resolved_timeout = float(_resolve_config("WEB_RETAILER_TIMEOUT", timeout, DEFAULT_TIMEOUT))
        resolved_user_agent = str(
            _resolve_config("WEB_RETAILER_USER_AGENT", user_agent, DEFAULT_USER_AGENT)
        )
        resolved_path = str(
            _resolve_config("WEB_RETAILER_CATALOG_PATH", catalog_path, DEFAULT_CATALOG_PATH)
        )

        _validate_base_url(resolved_base_url)
        _validate_timeout(resolved_timeout)

        self._base_url = resolved_base_url.rstrip("/")
        self._timeout = resolved_timeout
        self._user_agent = resolved_user_agent
        self._catalog_path = resolved_path
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

    async def fetch_listing_page(self, path: str | None = None) -> str:
        """Fetch a product listing page and return the raw HTML body.

        Args:
            path: URL path to fetch. Defaults to the configured catalog_path.

        Returns:
            Raw HTML body as a string.

        Raises:
            SourceFetchError: On HTTP errors, timeouts, or connection failures.
        """
        client = await self._get_client()
        fetch_path = path or self._catalog_path

        try:
            response = await client.get(fetch_path)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 403:
                raise SourceFetchError(
                    "Web retailer returned HTTP 403 (Forbidden).",
                    source="web_retailer",
                ) from exc
            elif status == 429:
                raise SourceFetchError(
                    "Web retailer rate limit exceeded (HTTP 429).",
                    source="web_retailer",
                ) from exc
            else:
                raise SourceFetchError(
                    f"Web retailer returned HTTP {status}",
                    source="web_retailer",
                ) from exc
        except httpx.TimeoutException as exc:
            raise SourceFetchError(
                "Web retailer request timed out",
                source="web_retailer",
            ) from exc
        except httpx.ConnectError as exc:
            raise SourceFetchError(
                f"Web retailer connection failed: {exc}",
                source="web_retailer",
            ) from exc
        except httpx.RequestError as exc:
            raise SourceFetchError(
                f"Web retailer request failed: {exc}",
                source="web_retailer",
            ) from exc

        return response.text

    async def close(self) -> None:
        """Close the underlying HTTP client if we own it."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
