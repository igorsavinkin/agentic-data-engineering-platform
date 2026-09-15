"""Tests for the eBay Browse API client.

Covers:
- successful search with valid response
- authentication flow
- rate-limit handling (429)
- HTTP errors (5xx, 4xx)
- timeout handling
- invalid JSON response
- pagination parameters
- malformed response validation
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from libs.adapters import SourceFetchError
from libs.adapters.ebay.client import EbayClient
from libs.adapters.ebay.models import EbaySearchResponse

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_search_response() -> dict[str, Any]:
    """Valid eBay search API response."""
    return {
        "total": 2,
        "itemSummaries": [
            {
                "itemId": "123456789012",
                "title": "Test Product",
                "price": {"value": 99.99, "currency": "USD"},
                "condition": "New",
                "itemWebUrl": "https://www.ebay.com/itm/123456789012",
                "seller": {"username": "test_seller"},
                "availability": {"shipToLocationAvailability": [{"quantity": 1}]},
                "categoryIds": ["9355"],
            },
            {
                "itemId": "987654321098",
                "title": "Another Product",
                "price": {"value": 49.99, "currency": "EUR"},
                "condition": "Used",
                "itemWebUrl": "https://www.ebay.com/itm/987654321098",
                "seller": None,
                "availability": None,
                "categoryIds": None,
            },
        ],
    }


@pytest.fixture
def mock_auth_response() -> dict[str, Any]:
    """Valid eBay OAuth2 token response."""
    return {
        "access_token": "v^1.1#test_access_token_12345",
        "token_type": "User Access Token",
        "expires_in": 7200,
        "refresh_token": "v^1.1#test_refresh_token_67890",
    }


# ---------------------------------------------------------------------------
# 1. Successful search
# ---------------------------------------------------------------------------


class TestSuccessfulSearch:
    """Test successful search operations."""

    @pytest.mark.asyncio
    async def test_search_items_success(self, mock_search_response: dict[str, Any]) -> None:
        """Successful search returns parsed response."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_search_response
        mock_response.headers = {}

        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.aclose = AsyncMock()

        client = EbayClient(
            app_id="test_app",
            cert_id="test_cert",
            dev_id="test_dev",
            http_client=mock_http,
        )
        # Pre-set access token to skip auth
        client._access_token = "test_token"

        result, malformed = await client.search_items(query="laptop")

        assert isinstance(result, EbaySearchResponse)
        assert result.total == 2
        assert len(result.item_summaries) == 2
        assert len(malformed) == 0
        assert result.item_summaries[0].item_id == "123456789012"
        assert result.item_summaries[1].item_id == "987654321098"

    @pytest.mark.asyncio
    async def test_search_with_category_ids(self, mock_search_response: dict[str, Any]) -> None:
        """Search passes category_ids parameter correctly."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_search_response
        mock_response.headers = {}

        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.aclose = AsyncMock()

        client = EbayClient(
            app_id="test_app",
            cert_id="test_cert",
            dev_id="test_dev",
            http_client=mock_http,
        )
        client._access_token = "test_token"

        await client.search_items(category_ids=["9355", "58058"])

        mock_http.get.assert_called_once()
        call_args = mock_http.get.call_args
        params = call_args.kwargs.get("params", {})
        assert "category_ids" in params
        assert params["category_ids"] == "9355,58058"

    @pytest.mark.asyncio
    async def test_search_with_limit_and_offset(self, mock_search_response: dict[str, Any]) -> None:
        """Search passes limit and offset parameters correctly."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_search_response
        mock_response.headers = {}

        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.aclose = AsyncMock()

        client = EbayClient(
            app_id="test_app",
            cert_id="test_cert",
            dev_id="test_dev",
            http_client=mock_http,
        )
        client._access_token = "test_token"

        await client.search_items(limit=50, offset=100)

        mock_http.get.assert_called_once()
        call_args = mock_http.get.call_args
        params = call_args.kwargs.get("params", {})
        assert params.get("limit") == 50
        assert params.get("offset") == 100

    @pytest.mark.asyncio
    async def test_limit_capped_at_200(self, mock_search_response: dict[str, Any]) -> None:
        """Limit is capped at eBay's maximum of 200."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_search_response
        mock_response.headers = {}

        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.aclose = AsyncMock()

        client = EbayClient(
            app_id="test_app",
            cert_id="test_cert",
            dev_id="test_dev",
            http_client=mock_http,
        )
        client._access_token = "test_token"

        await client.search_items(limit=500)

        mock_http.get.assert_called_once()
        call_args = mock_http.get.call_args
        params = call_args.kwargs.get("params", {})
        assert params.get("limit") == 200  # Capped at max


# ---------------------------------------------------------------------------
# 2. Authentication
# ---------------------------------------------------------------------------


class TestAuthentication:
    """Test OAuth2 authentication flow."""

    @pytest.mark.asyncio
    async def test_authenticate_success(self, mock_auth_response: dict[str, Any]) -> None:
        """Successful authentication stores access token."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_auth_response
        mock_response.raise_for_status = MagicMock()

        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.aclose = AsyncMock()

        client = EbayClient(
            app_id="test_app",
            cert_id="test_cert",
            dev_id="test_dev",
            http_client=mock_http,
        )

        token = await client._authenticate()

        assert token == "v^1.1#test_access_token_12345"
        assert client._access_token == "v^1.1#test_access_token_12345"
        mock_http.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_authenticate_missing_credentials(self) -> None:
        """Missing credentials raises SourceFetchError."""
        client = EbayClient(app_id=None, cert_id=None, dev_id=None)

        with pytest.raises(SourceFetchError) as exc_info:
            await client._authenticate()

        assert "credentials" in exc_info.value.args[0].lower()
        assert exc_info.value.source == "ebay"

    @pytest.mark.asyncio
    async def test_authenticate_http_failure(self) -> None:
        """HTTP error during auth raises SourceFetchError."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 401

        http_error = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        )
        mock_response.raise_for_status.side_effect = http_error

        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.aclose = AsyncMock()

        client = EbayClient(
            app_id="test_app",
            cert_id="test_cert",
            dev_id="test_dev",
            http_client=mock_http,
        )

        with pytest.raises(SourceFetchError) as exc_info:
            await client._authenticate()

        assert "authentication" in exc_info.value.args[0].lower()
        assert exc_info.value.source == "ebay"

    @pytest.mark.asyncio
    async def test_authenticate_missing_token(self) -> None:
        """Response without access_token raises SourceFetchError."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"token_type": "User Access Token"}
        mock_response.raise_for_status = MagicMock()

        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.aclose = AsyncMock()

        client = EbayClient(
            app_id="test_app",
            cert_id="test_cert",
            dev_id="test_dev",
            http_client=mock_http,
        )

        with pytest.raises(SourceFetchError) as exc_info:
            await client._authenticate()

        assert "access_token" in exc_info.value.args[0].lower()
        assert exc_info.value.source == "ebay"


# ---------------------------------------------------------------------------
# 3. Rate-limit handling
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """Test explicit rate-limit response handling."""

    @pytest.mark.asyncio
    async def test_429_rate_limit(self) -> None:
        """HTTP 429 raises SourceFetchError with retry-after info."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "30"}

        http_error = httpx.HTTPStatusError(
            "Too Many Requests", request=MagicMock(), response=mock_response
        )
        mock_response.raise_for_status.side_effect = http_error

        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.aclose = AsyncMock()

        client = EbayClient(
            app_id="test_app",
            cert_id="test_cert",
            dev_id="test_dev",
            http_client=mock_http,
        )
        client._access_token = "test_token"

        with pytest.raises(SourceFetchError) as exc_info:
            await client.search_items(query="test")

        assert "rate limited" in exc_info.value.args[0].lower()
        assert "30" in exc_info.value.args[0]
        assert exc_info.value.source == "ebay"


# ---------------------------------------------------------------------------
# 4. HTTP errors
# ---------------------------------------------------------------------------


class TestHTTPErrors:
    """Test HTTP error handling."""

    @pytest.mark.asyncio
    async def test_5xx_error(self) -> None:
        """5xx errors raise SourceFetchError."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 503

        http_error = httpx.HTTPStatusError(
            "Service Unavailable", request=MagicMock(), response=mock_response
        )
        mock_response.raise_for_status.side_effect = http_error

        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.aclose = AsyncMock()

        client = EbayClient(
            app_id="test_app",
            cert_id="test_cert",
            dev_id="test_dev",
            http_client=mock_http,
        )
        client._access_token = "test_token"

        with pytest.raises(SourceFetchError) as exc_info:
            await client.search_items(query="test")

        assert "503" in exc_info.value.args[0]
        assert exc_info.value.source == "ebay"

    @pytest.mark.asyncio
    async def test_4xx_error(self) -> None:
        """4xx errors raise SourceFetchError."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 404

        http_error = httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_response)
        mock_response.raise_for_status.side_effect = http_error

        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.aclose = AsyncMock()

        client = EbayClient(
            app_id="test_app",
            cert_id="test_cert",
            dev_id="test_dev",
            http_client=mock_http,
        )
        client._access_token = "test_token"

        with pytest.raises(SourceFetchError) as exc_info:
            await client.search_items(query="test")

        assert "404" in exc_info.value.args[0]
        assert exc_info.value.source == "ebay"


# ---------------------------------------------------------------------------
# 5. Timeout handling
# ---------------------------------------------------------------------------


class TestTimeouts:
    """Test timeout handling."""

    @pytest.mark.asyncio
    async def test_timeout_raises_source_fetch_error(self) -> None:
        """HTTP timeout raises SourceFetchError."""
        mock_http = MagicMock()
        timeout_error = httpx.TimeoutException("Request timed out")
        mock_http.get = AsyncMock(side_effect=timeout_error)
        mock_http.aclose = AsyncMock()

        client = EbayClient(
            app_id="test_app",
            cert_id="test_cert",
            dev_id="test_dev",
            http_client=mock_http,
        )
        client._access_token = "test_token"

        with pytest.raises(SourceFetchError) as exc_info:
            await client.search_items(query="test")

        assert "timed out" in exc_info.value.args[0].lower()
        assert exc_info.value.source == "ebay"


# ---------------------------------------------------------------------------
# 6. Invalid JSON
# ---------------------------------------------------------------------------


class TestInvalidJSON:
    """Test invalid JSON response handling."""

    @pytest.mark.asyncio
    async def test_invalid_json_raises_source_fetch_error(self) -> None:
        """Invalid JSON response raises SourceFetchError."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.raise_for_status = MagicMock()

        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.aclose = AsyncMock()

        client = EbayClient(
            app_id="test_app",
            cert_id="test_cert",
            dev_id="test_dev",
            http_client=mock_http,
        )
        client._access_token = "test_token"

        with pytest.raises(SourceFetchError) as exc_info:
            await client.search_items(query="test")

        assert "invalid json" in exc_info.value.args[0].lower()
        assert exc_info.value.source == "ebay"


# ---------------------------------------------------------------------------
# 7. Malformed response validation
# ---------------------------------------------------------------------------


class TestMalformedResponse:
    """Test malformed response handling."""

    @pytest.mark.asyncio
    async def test_top_level_validation_failure(self) -> None:
        """Top-level response validation failure returns empty response with malformed record."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "invalid": "structure"
        }  # Missing 'total' and 'itemSummaries'
        mock_response.raise_for_status = MagicMock()

        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.aclose = AsyncMock()

        client = EbayClient(
            app_id="test_app",
            cert_id="test_cert",
            dev_id="test_dev",
            http_client=mock_http,
        )
        client._access_token = "test_token"

        result, malformed = await client.search_items(query="test")

        assert isinstance(result, EbaySearchResponse)
        assert result.total == 0
        assert len(result.item_summaries) == 0
        assert len(malformed) == 1
        assert "raw_record" in malformed[0]
        assert "reason" in malformed[0]

    @pytest.mark.asyncio
    async def test_partial_item_validation_failure(self) -> None:
        """Individual item validation failures are captured in malformed."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total": 2,
            "itemSummaries": [
                {
                    "itemId": "123",
                    "title": "Valid Item",
                    "price": {"value": 10.0, "currency": "USD"},
                    "condition": "New",
                    "itemWebUrl": "https://ebay.com/itm/123",
                    "seller": None,
                    "image": None,
                    "availability": None,
                    "categoryIds": None,
                },
                {
                    "itemId": "456",
                    # Missing title - should fail validation
                },
            ],
        }
        mock_response.raise_for_status = MagicMock()

        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.aclose = AsyncMock()

        client = EbayClient(
            app_id="test_app",
            cert_id="test_cert",
            dev_id="test_dev",
            http_client=mock_http,
        )
        client._access_token = "test_token"

        result, malformed = await client.search_items(query="test")

        assert len(result.item_summaries) == 1
        assert result.item_summaries[0].item_id == "123"
        assert len(malformed) == 1
        assert "456" in str(malformed[0].get("raw_record", {}))


# ---------------------------------------------------------------------------
# 8. Client lifecycle
# ---------------------------------------------------------------------------


class TestClientLifecycle:
    """Test client resource management."""

    @pytest.mark.asyncio
    async def test_close_releases_resources(self) -> None:
        """close() releases underlying HTTP client resources."""
        mock_http = MagicMock()
        mock_http.aclose = AsyncMock()

        client = EbayClient(http_client=mock_http)
        await client.close()

        mock_http.aclose.assert_called_once()
        assert client._client is None

    @pytest.mark.asyncio
    async def test_close_without_client(self) -> None:
        """close() is safe when no client was created."""
        client = EbayClient()
        # Should not raise
        await client.close()
