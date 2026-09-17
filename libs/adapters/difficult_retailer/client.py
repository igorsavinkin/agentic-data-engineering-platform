"""HTTP client for a difficult retailer source.

Classifies responses into ResponseKind categories and raises classified
SourceFetchError for non-success responses. Retries transient failures
(5xx, timeouts, connection errors) with bounded exponential backoff.
"""

from __future__ import annotations

import asyncio
import logging
import os
from urllib.parse import urlparse

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from libs.adapters import SourceFetchError
from libs.adapters.difficult_retailer.classifier import ResponseKind, classify_response
from libs.observability.source_metrics import SourceMetrics

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://premium-retailer.example.com"
DEFAULT_TIMEOUT = 30.0
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_CATALOG_PATH = "/products"
DEFAULT_MAX_RETRIES = 3


class _TransientHttpError(Exception):
    """Retryable HTTP error (5xx, timeout, connection error)."""

    def __init__(
        self, message: str, *, status_code: int = 0, retry_after: float | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


def _resolve_config(
    env_var: str,
    constructor_value: str | float | int | None,
    default: str | float | int,
) -> str | float | int:
    """Resolve configuration: constructor arg > env var > default."""
    if constructor_value is not None:
        return constructor_value
    env_value = os.environ.get(env_var)
    if env_value is not None:
        return env_value
    return default


def _validate_base_url(url: str) -> None:
    if not url or not url.strip():
        raise SourceFetchError("base_url must be a non-empty string", source="premium_retailer")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SourceFetchError(
            f"base_url must use http or https scheme, got '{parsed.scheme or '(none)'}'",
            source="premium_retailer",
        )
    if not parsed.netloc:
        raise SourceFetchError("base_url must include a hostname", source="premium_retailer")


def _validate_timeout(timeout: float) -> None:
    if timeout <= 0:
        raise SourceFetchError(
            f"timeout must be positive, got {timeout}", source="premium_retailer"
        )
    if timeout != timeout:
        raise SourceFetchError("timeout must be a finite number", source="premium_retailer")


def _validate_max_retries(max_retries: int) -> None:
    if max_retries < 1:
        raise SourceFetchError(
            f"max_retries must be >= 1, got {max_retries}", source="premium_retailer"
        )


class DifficultRetailerClient:
    """HTTP client that classifies difficult-source responses.

    Returns raw HTML body for SUCCESS responses. For non-success responses,
    raises SourceFetchError with the ResponseKind attached so callers can
    implement source-aware retry and degradation strategies.

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
        max_retries: int | None = None,
        http_client: httpx.AsyncClient | None = None,
        metrics: SourceMetrics | None = None,
    ) -> None:
        resolved_base_url = str(
            _resolve_config("DIFFICULT_RETAILER_BASE_URL", base_url, DEFAULT_BASE_URL)
        )
        resolved_timeout = float(
            _resolve_config("DIFFICULT_RETAILER_TIMEOUT", timeout, DEFAULT_TIMEOUT)
        )
        resolved_user_agent = str(
            _resolve_config("DIFFICULT_RETAILER_USER_AGENT", user_agent, DEFAULT_USER_AGENT)
        )
        resolved_path = str(
            _resolve_config("DIFFICULT_RETAILER_CATALOG_PATH", catalog_path, DEFAULT_CATALOG_PATH)
        )
        resolved_retries = int(
            _resolve_config("DIFFICULT_RETAILER_MAX_RETRIES", max_retries, DEFAULT_MAX_RETRIES)
        )

        _validate_base_url(resolved_base_url)
        _validate_timeout(resolved_timeout)
        _validate_max_retries(resolved_retries)

        self._base_url = resolved_base_url.rstrip("/")
        self._timeout = resolved_timeout
        self._user_agent = resolved_user_agent
        self._catalog_path = resolved_path
        self._max_retries = resolved_retries
        self._client = http_client
        self._metrics = metrics

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def catalog_path(self) -> str:
        return self._catalog_path

    @property
    def max_retries(self) -> int:
        return self._max_retries

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
        """Fetch a listing page, classify the response, and return HTML.

        Returns HTML body only for SUCCESS responses. For all other response
        kinds, raises SourceFetchError with ``response_kind`` set.

        Retries transient failures (5xx except 503, timeouts, connection errors)
        with bounded exponential backoff. 429 responses respect Retry-After.
        """
        client = await self._get_client()
        fetch_path = path or self._catalog_path

        retryer = AsyncRetrying(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            retry=retry_if_exception_type(
                (httpx.TimeoutException, httpx.ConnectError, _TransientHttpError)
            ),
            reraise=True,
            before_sleep=self._on_retry,
        )

        try:
            async for attempt in retryer:
                with attempt:
                    return await self._do_request(client, fetch_path)
        except _ClassifiedError as exc:
            raise SourceFetchError(
                f"Premium retailer ({exc.kind.value}): response classified as {exc.kind.value}",
                source="premium_retailer",
            ) from exc
        except _TransientHttpError as exc:
            raise SourceFetchError(
                f"Premium retailer (transient): request failed after {self._max_retries} attempts: {exc}",
                source="premium_retailer",
            ) from exc
        except httpx.TimeoutException as exc:
            raise SourceFetchError(
                "Premium retailer request timed out",
                source="premium_retailer",
            ) from exc
        except httpx.ConnectError as exc:
            raise SourceFetchError(
                f"Premium retailer connection failed: {exc}",
                source="premium_retailer",
            ) from exc
        except httpx.RequestError as exc:
            raise SourceFetchError(
                f"Premium retailer request failed: {exc}",
                source="premium_retailer",
            ) from exc

        raise SourceFetchError(
            "Premium retailer request failed unexpectedly",
            source="premium_retailer",
        )

    async def _do_request(self, client: httpx.AsyncClient, path: str) -> str:
        """Execute a single HTTP GET with response classification."""
        response = await client.get(path)

        kind = classify_response(response.status_code, response.text)

        if kind == ResponseKind.SUCCESS:
            return response.text

        if kind == ResponseKind.RATE_LIMITED:
            retry_after_text = response.headers.get("Retry-After")
            retry_after: float | None = None
            if retry_after_text is not None:
                try:
                    retry_after = float(retry_after_text)
                except ValueError:
                    retry_after = None
            if retry_after is not None:
                logger.info("Rate limited (429), waiting %.1fs per Retry-After", retry_after)
                await asyncio.sleep(retry_after)
            raise _TransientHttpError(
                f"Rate limited (HTTP 429, Retry-After: {retry_after_text})",
                status_code=429,
                retry_after=retry_after,
            )

        if kind == ResponseKind.UNAVAILABLE and response.status_code == 503:
            raise _TransientHttpError(
                "Service unavailable (HTTP 503)",
                status_code=503,
            )

        raise _ClassifiedError(kind)

    async def close(self) -> None:
        """Close the underlying HTTP client if we own it."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _on_retry(self, retry_state: object) -> None:
        """Tenacity before_sleep callback — record retry metric."""
        if self._metrics is not None:
            self._metrics.record_retry()


class _ClassifiedError(Exception):
    """Non-retryable classified response from the difficult source."""

    def __init__(self, kind: ResponseKind) -> None:
        super().__init__(f"Classified response: {kind.value}")
        self.kind = kind
