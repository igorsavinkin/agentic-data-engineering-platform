"""Unit tests for API latency collection and analysis (TASK-114)."""

from __future__ import annotations

from libs.load_test.api_latency_collector import (
    ApiLatencyCollector,
    ApiLatencySample,
    _compute_percentiles,
)


class TestApiLatencySample:
    def test_creation(self) -> None:
        s = ApiLatencySample(endpoint="/api/v1/health", latency_ms=12.5, status_code=200)
        assert s.endpoint == "/api/v1/health"
        assert s.latency_ms == 12.5
        assert s.status_code == 200

    def test_frozen(self) -> None:
        s = ApiLatencySample(endpoint="/x", latency_ms=1.0, status_code=200)
        try:
            s.latency_ms = 2.0  # type: ignore[misc]
        except AttributeError:
            pass
        else:
            raise AssertionError("ApiLatencySample should be frozen")


class TestApiLatencyCollector:
    def test_empty_report(self) -> None:
        c = ApiLatencyCollector()
        assert c.to_report_dict() is None
        assert c.sample_count == 0

    def test_record_sample(self) -> None:
        c = ApiLatencyCollector()
        c.record_sample("/api/v1/health", 10.0, 200)
        c.record_sample("/api/v1/products", 50.0, 200)
        assert c.sample_count == 2

    def test_get_samples(self) -> None:
        c = ApiLatencyCollector()
        c.record_sample("/api/v1/health", 10.0, 200)
        c.record_sample("/api/v1/health", 20.0, 200)
        samples = c.get_samples()
        assert len(samples) == 2
        assert all(s.endpoint == "/api/v1/health" for s in samples)

    def test_report_single_endpoint(self) -> None:
        c = ApiLatencyCollector()
        for i in range(10):
            c.record_sample("/api/v1/health", float(10 + i), 200)

        report = c.to_report_dict()
        assert report is not None
        assert report["total_samples"] == 10
        assert report["endpoint_count"] == 1
        assert "/api/v1/health" in report["endpoints"]

        ep = report["endpoints"]["/api/v1/health"]
        assert ep["sample_count"] == 10
        assert "p50" in ep["latency_ms"]
        assert "p95" in ep["latency_ms"]
        assert "p99" in ep["latency_ms"]
        assert ep["status_codes"] == {"200": 10}

    def test_report_multiple_endpoints(self) -> None:
        c = ApiLatencyCollector()
        c.record_sample("/api/v1/health", 5.0, 200)
        c.record_sample("/api/v1/health", 10.0, 200)
        c.record_sample("/api/v1/products", 100.0, 200)
        c.record_sample("/api/v1/products", 200.0, 500)

        report = c.to_report_dict()
        assert report is not None
        assert report["total_samples"] == 4
        assert report["endpoint_count"] == 2

        health = report["endpoints"]["/api/v1/health"]
        assert health["sample_count"] == 2
        assert health["status_codes"] == {"200": 2}

        products = report["endpoints"]["/api/v1/products"]
        assert products["sample_count"] == 2
        assert products["status_codes"] == {"200": 1, "500": 1}

    def test_overall_latency_in_report(self) -> None:
        c = ApiLatencyCollector()
        c.record_sample("/a", 10.0, 200)
        c.record_sample("/b", 30.0, 200)

        report = c.to_report_dict()
        assert report is not None
        overall = report["overall_latency_ms"]
        assert overall["min"] == 10.0
        assert overall["max"] == 30.0
        assert overall["mean"] == 20.0

    def test_report_with_error_status_codes(self) -> None:
        c = ApiLatencyCollector()
        c.record_sample("/api/v1/products", 50.0, 200)
        c.record_sample("/api/v1/products", 100.0, 503)
        c.record_sample("/api/v1/products", 200.0, 200)

        report = c.to_report_dict()
        assert report is not None
        ep = report["endpoints"]["/api/v1/products"]
        assert ep["status_codes"] == {"200": 2, "503": 1}


class TestComputePercentiles:
    def test_empty(self) -> None:
        result = _compute_percentiles([])
        assert result["min"] == 0.0
        assert result["mean"] == 0.0

    def test_single_value(self) -> None:
        result = _compute_percentiles([42.0])
        assert result["min"] == 42.0
        assert result["max"] == 42.0
        assert result["mean"] == 42.0
        assert result["p50"] == 42.0

    def test_multiple_values(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        result = _compute_percentiles(values)
        assert result["min"] == 1.0
        assert result["max"] == 10.0
        assert result["mean"] == 5.5
        assert result["p50"] == 5.5

    def test_latency_distribution(self) -> None:
        values = sorted([5.0, 10.0, 15.0, 50.0, 100.0, 500.0])
        result = _compute_percentiles(values)
        assert result["min"] == 5.0
        assert result["max"] == 500.0
        assert result["p95"] > result["p50"]
