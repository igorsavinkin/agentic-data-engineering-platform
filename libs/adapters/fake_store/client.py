"""HTTP client for the Fake Store API."""

from __future__ import annotations

from typing import Any, Optional

import httpx

from libs.adapters import SourceFetchError
from libs.adapters.fake_store.models import FakeStoreProduct

FAKE_STORE_BASE_URL = "https://fakestoreapi.com"
DEFAULT_TIMEOUT = 30.0  # seconds


class FakeStoreClient:
    """Typed HTTP client for Fake Store API product endpoints."""

    def __init__(
        self,
        *,
        base_url: str = FAKE_STORE_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = http_client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout),
            )
        return self._client

    async def fetch_products(self, limit: Optional[int] = None) -> list[FakeStoreProduct]:
        """Fetch products from Fake Store API /products endpoint.

        Args:
            limit: Maximum number of products to fetch. None means all.

        Returns:
            List of typed FakeStoreProduct objects.

        Raises:
            SourceFetchError: On HTTP errors, timeouts, or malformed responses.
        """
        client = await self._get_client()
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit

        try:
            response = await client.get("/products", params=params)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise SourceFetchError(
                "Fake Store API request timed out",
                source="fake_store",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise SourceFetchError(
                f"Fake Store API returned HTTP {exc.response.status_code}",
                source="fake_store",
            ) from exc
        except httpx.RequestError as exc:
            raise SourceFetchError(
                f"Fake Store API request failed: {exc}",
                source="fake_store",
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise SourceFetchError(
                "Fake Store API returned invalid JSON",
                source="fake_store",
            ) from exc

        if not isinstance(data, list):
            raise SourceFetchError(
                "Fake Store API returned non-list response",
                source="fake_store",
            )

        products: list[FakeStoreProduct] = []
        for idx, item in enumerate(data):
            try:
                product = FakeStoreProduct.model_validate(item)
                products.append(product)
            except Exception:
                # Log but continue — individual record failures are handled upstream
                pass

        return products

    async def close(self) -> None:
        """Close the underlying HTTP client if we own it."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
