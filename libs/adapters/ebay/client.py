"""HTTP client for the eBay Browse API with auth, retries, and rate-limit handling."""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from libs.adapters import SourceFetchError
from libs.adapters.ebay.models import EbayListingSummary, EbaySearchResponse

EBAY_BROWSE_API_BASE = "https://api.ebay.com/buy/browse/v1"
DEFAULT_TIMEOUT = 30.0  # seconds
MAX_RETRIES = 3


class EbayClient:
    """Typed HTTP client for eBay Browse API product search endpoints.

    Handles OAuth2 Client Credentials authentication, automatic retries with
    exponential backoff, and explicit rate-limit response handling.

    Attributes:
        base_url: eBay Browse API base URL.
        timeout: HTTP request timeout in seconds.
    """

    def __init__(
        self,
        *,
        app_id: Optional[str] = None,
        cert_id: Optional[str] = None,
        dev_id: Optional[str] = None,
        base_url: str = EBAY_BROWSE_API_BASE,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        """Initialize the eBay API client.

        Args:
            app_id: eBay application ID (OAuth2 client ID).
            cert_id: eBay certificate ID.
            dev_id: eBay developer ID.
            base_url: Override the eBay Browse API base URL (for testing).
            timeout: HTTP request timeout in seconds.
            max_retries: Maximum number of retry attempts for transient failures.
            http_client: Pre-configured httpx.AsyncClient (for testing/injection).
        """
        self._app_id = app_id or os.getenv("EBAY_APP_ID")
        self._cert_id = cert_id or os.getenv("EBAY_CERT_ID")
        self._dev_id = dev_id or os.getenv("EBAY_DEV_ID")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = http_client
        self._access_token: Optional[str] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the underlying HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
            )
        return self._client

    async def _authenticate(self) -> str:
        """Obtain OAuth2 access token using Client Credentials flow.

        Returns:
            Bearer access token string.

        Raises:
            SourceFetchError: On authentication failure.
        """
        if not all([self._app_id, self._cert_id, self._dev_id]):
            raise SourceFetchError(
                "eBay API credentials not configured (EBAY_APP_ID, EBAY_CERT_ID, EBAY_DEV_ID)",
                source="ebay",
            )

        client = await self._get_client()

        # eBay uses Basic auth with app_id:cert_id for token endpoint
        auth_string = f"{self._app_id}:{self._cert_id}"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {auth_string}",
        }
        data = {
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        }

        try:
            response = await client.post(
                "https://api.ebay.com/identity/v1/oauth2/token",
                headers=headers,
                data=data,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SourceFetchError(
                f"eBay authentication failed: HTTP {exc.response.status_code}",
                source="ebay",
            ) from exc
        except httpx.RequestError as exc:
            raise SourceFetchError(
                f"eBay authentication request failed: {exc}",
                source="ebay",
            ) from exc

        token_data = response.json()
        self._access_token = token_data.get("access_token")
        if not self._access_token:
            raise SourceFetchError(
                "eBay authentication response missing access_token",
                source="ebay",
            )
        return self._access_token

    async def _get_auth_headers(self) -> dict[str, str]:
        """Get authorization headers, refreshing token if needed."""
        if self._access_token is None:
            await self._authenticate()
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        }

    async def search_items(
        self,
        *,
        query: Optional[str] = None,
        category_ids: Optional[list[str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> tuple[EbaySearchResponse, list[dict[str, Any]]]:
        """Search for items using eBay Browse API item_summary endpoint.

        Args:
            query: Search query string.
            category_ids: Category IDs to filter results.
            limit: Maximum number of results to return (max 200).
            offset: Result offset for pagination.

        Returns:
            Tuple of (parsed search response, malformed records).

        Raises:
            SourceFetchError: On HTTP errors, timeouts, or auth failures.
        """
        client = await self._get_client()
        params: dict[str, Any] = {}

        if query:
            params["q"] = query
        if category_ids:
            params["category_ids"] = ",".join(category_ids)
        if limit is not None:
            params["limit"] = min(limit, 200)  # eBay API max is 200
        if offset is not None:
            params["offset"] = offset

        headers = await self._get_auth_headers()

        # Retry policy: retry on transient HTTP errors (5xx, 429) and network issues
        retryer = AsyncRetrying(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.RemoteProtocolError)),
            reraise=True,
        )

        async def _do_request() -> httpx.Response:
            try:
                response = await client.get(
                    f"{self._base_url}/item_summary/search",
                    headers=headers,
                    params=params,
                )
            except httpx.TimeoutException:
                raise
            except httpx.RemoteProtocolError:
                raise

            # Handle rate limiting explicitly
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "5")
                raise SourceFetchError(
                    f"eBay API rate limited (Retry-After: {retry_after}s)",
                    source="ebay",
                )

            # Handle auth errors - refresh token and retry once
            if response.status_code == 401:
                self._access_token = None  # Force re-authentication
                new_headers = await self._get_auth_headers()
                response = await client.get(
                    f"{self._base_url}/item_summary/search",
                    headers=new_headers,
                    params=params,
                )

            response.raise_for_status()
            return response

        try:
            response = await retryer(_do_request)
        except SourceFetchError:
            raise
        except httpx.HTTPStatusError as exc:
            raise SourceFetchError(
                f"eBay API returned HTTP {exc.response.status_code}",
                source="ebay",
            ) from exc
        except httpx.RequestError as exc:
            raise SourceFetchError(
                f"eBay API request failed: {exc}",
                source="ebay",
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise SourceFetchError(
                "eBay API returned invalid JSON",
                source="ebay",
            ) from exc

        # Parse into typed model, capturing any malformed records
        malformed: list[dict[str, Any]] = []

        # First validate top-level structure
        if not isinstance(data, dict):
            malformed.append(
                {
                    "raw_record": data,
                    "reason": "Top-level response is not a dict",
                }
            )
            return EbaySearchResponse(total=0, item_summaries=[]), malformed

        # Check for required top-level fields
        if "total" not in data and "itemSummaries" not in data and "item_summaries" not in data:
            malformed.append(
                {
                    "raw_record": data,
                    "reason": "Top-level response missing required fields (total, itemSummaries)",
                }
            )
            return EbaySearchResponse(total=0, item_summaries=[]), malformed

        # Extract total and raw item summaries
        total = data.get("total", 0)
        raw_summaries = data.get("itemSummaries", data.get("item_summaries", []))

        # Validate individual item summaries
        valid_summaries: list[EbayListingSummary] = []
        for idx, raw_item in enumerate(raw_summaries):
            try:
                summary = EbayListingSummary.model_validate(raw_item)
                valid_summaries.append(summary)
            except Exception as exc:
                malformed.append(
                    {
                        "raw_record": raw_item,
                        "reason": f"Item summary validation failed at index {idx}: {exc}",
                    }
                )

        search_response = EbaySearchResponse(total=total, item_summaries=valid_summaries)

        return search_response, malformed

    async def close(self) -> None:
        """Close the underlying HTTP client if we own it."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
