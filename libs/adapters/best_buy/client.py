"""HTTP client for the Best Buy Products API v1."""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

from libs.adapters import SourceFetchError
from libs.adapters.best_buy.models import BestBuyProduct

BESTBUY_BASE_URL = "https://api.bestbuy.com/v1"
DEFAULT_TIMEOUT = 30.0  # seconds


class BestBuyClient:
    """Typed HTTP client for Best Buy Products API v1."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = BESTBUY_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._api_key = api_key or os.environ.get("BESTBUY_API_KEY")
        if not self._api_key:
            raise SourceFetchError(
                "Best Buy API key is required. Set BESTBUY_API_KEY environment variable or pass api_key parameter.",
                source="best_buy",
            )
        self._client = http_client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout),
            )
        return self._client

    async def fetch_products(
        self,
        *,
        show: Optional[str] = None,
        page_size: int = 10,
        page: int = 1,
        sort: Optional[str] = None,
    ) -> tuple[list[BestBuyProduct], list[dict[str, Any]]]:
        """Fetch products from Best Buy Products API /products endpoint.

        Args:
            show: Comma-separated list of fields to include in response.
                  Defaults to all standard fields.
            page_size: Number of products per page (max 100).
            page: Page number (1-indexed).
            sort: Sort order, e.g. "sku.asc" or "salePrice.desc".

        Returns:
            Tuple of (valid products, malformed records). Malformed records include
            the original raw dict plus a 'reason' field describing the validation failure.

        Raises:
            SourceFetchError: On auth failures, rate limits, timeouts, or malformed responses.
        """
        client = await self._get_client()
        params: dict[str, Any] = {
            "apiKey": self._api_key,
            "pageSize": min(page_size, 100),
            "page": page,
            "format": "json",
        }
        if show:
            params["show"] = show
        if sort:
            params["sort"] = sort

        try:
            response = await client.get("/products", params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 403:
                raise SourceFetchError(
                    "Best Buy API authentication failed (403). Check your API key.",
                    source="best_buy",
                ) from exc
            elif status == 429:
                raise SourceFetchError(
                    "Best Buy API rate limit exceeded (429). Retry after cooldown.",
                    source="best_buy",
                ) from exc
            else:
                raise SourceFetchError(
                    f"Best Buy API returned HTTP {status}",
                    source="best_buy",
                ) from exc
        except httpx.TimeoutException as exc:
            raise SourceFetchError(
                "Best Buy API request timed out",
                source="best_buy",
            ) from exc
        except httpx.RequestError as exc:
            raise SourceFetchError(
                f"Best Buy API request failed: {exc}",
                source="best_buy",
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise SourceFetchError(
                "Best Buy API returned invalid JSON",
                source="best_buy",
            ) from exc

        # Best Buy wraps results in {"products": [...], "from": 1, "to": 10, "total": 123, ...}
        if not isinstance(data, dict) or "products" not in data:
            raise SourceFetchError(
                "Best Buy API returned unexpected response structure (missing 'products' key)",
                source="best_buy",
            )

        products_data = data["products"]
        if not isinstance(products_data, list):
            raise SourceFetchError(
                "Best Buy API 'products' field is not a list",
                source="best_buy",
            )

        products: list[BestBuyProduct] = []
        malformed: list[dict[str, Any]] = []
        for idx, item in enumerate(products_data):
            try:
                product = BestBuyProduct.model_validate(item)
                products.append(product)
            except Exception as exc:
                # Capture malformed record with diagnostic reason for DLQ routing
                malformed.append(
                    {
                        "raw_record": item,
                        "reason": f"Validation failed at index {idx}: {exc}",
                    }
                )

        return products, malformed

    async def close(self) -> None:
        """Close the underlying HTTP client if we own it."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
