"""Unit tests for API latency probe (TASK-114)."""

from __future__ import annotations

import io
import urllib.error
from unittest.mock import MagicMock, patch

from libs.load_test.api_latency_collector import ApiLatencyCollector
from libs.load_test.api_latency_probe import create_api_probe_fn


class TestCreateApiProbeFn:
    def test_successful_probe_records_sample(self) -> None:
        collector = ApiLatencyCollector()
        probe = create_api_probe_fn(
            collector=collector,
            base_url="http://localhost:8000",
            endpoints=["/api/v1/health"],
        )

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"status": "ok"}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            probe()

        assert collector.sample_count == 1
        samples = collector.get_samples()
        assert samples[0].endpoint == "/api/v1/health"
        assert samples[0].status_code == 200
        assert samples[0].latency_ms >= 0

    def test_multiple_endpoints(self) -> None:
        collector = ApiLatencyCollector()
        probe = create_api_probe_fn(
            collector=collector,
            base_url="http://localhost:8000",
            endpoints=["/api/v1/health", "/api/v1/products"],
        )

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b""
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            probe()

        assert collector.sample_count == 2
        endpoints = {s.endpoint for s in collector.get_samples()}
        assert endpoints == {"/api/v1/health", "/api/v1/products"}

    def test_http_error_records_status_code(self) -> None:
        collector = ApiLatencyCollector()
        probe = create_api_probe_fn(
            collector=collector,
            base_url="http://localhost:8000",
            endpoints=["/api/v1/products"],
        )

        http_error = urllib.error.HTTPError(
            url="http://localhost:8000/api/v1/products",
            code=503,
            msg="Service Unavailable",
            hdrs=MagicMock(),
            fp=io.BytesIO(b""),
        )

        with patch("urllib.request.urlopen", side_effect=http_error):
            probe()

        assert collector.sample_count == 1
        samples = collector.get_samples()
        assert samples[0].status_code == 503

    def test_connection_error_skips_endpoint(self) -> None:
        collector = ApiLatencyCollector()
        probe = create_api_probe_fn(
            collector=collector,
            base_url="http://localhost:8000",
            endpoints=["/api/v1/health"],
        )

        with patch("urllib.request.urlopen", side_effect=ConnectionRefusedError("refused")):
            probe()

        assert collector.sample_count == 0

    def test_base_url_trailing_slash_stripped(self) -> None:
        collector = ApiLatencyCollector()
        probe = create_api_probe_fn(
            collector=collector,
            base_url="http://localhost:8000/",
            endpoints=["/api/v1/health"],
        )

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b""
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            probe()

        call_args = mock_open.call_args
        request = call_args[0][0]
        assert request.full_url == "http://localhost:8000/api/v1/health"
