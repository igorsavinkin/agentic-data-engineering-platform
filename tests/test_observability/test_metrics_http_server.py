"""Tests for the metrics HTTP server (TASK-084)."""

from __future__ import annotations

import http.client
import time

from libs.observability.kafka_metrics import KafkaMetric, KafkaMetrics
from libs.observability.metrics_http_server import MetricsHTTPServer
from libs.observability.prometheus_exporter import create_prometheus_registry


class TestMetricsHTTPServer:
    def test_serves_metrics_endpoint(self) -> None:
        registry, collector = create_prometheus_registry(service_name="test")
        kafka = KafkaMetrics()
        for _ in range(5):
            kafka.increment(KafkaMetric.PRODUCED)
        collector.register_kafka(kafka)

        server = MetricsHTTPServer(registry=registry, port=0)
        server._port = 19101
        server.start()
        try:
            time.sleep(0.2)
            conn = http.client.HTTPConnection("127.0.0.1", 19101, timeout=5)
            conn.request("GET", "/metrics")
            response = conn.getresponse()
            body = response.read().decode("utf-8")

            assert response.status == 200
            content_type = response.getheader("Content-Type", "")
            assert "text/plain" in content_type
            assert "ingestion_events_total" in body
            conn.close()
        finally:
            server.stop()

    def test_returns_404_for_unknown_path(self) -> None:
        registry, _ = create_prometheus_registry(service_name="test")
        server = MetricsHTTPServer(registry=registry, port=19102)
        server.start()
        try:
            time.sleep(0.2)
            conn = http.client.HTTPConnection("127.0.0.1", 19102, timeout=5)
            conn.request("GET", "/unknown")
            response = conn.getresponse()
            assert response.status == 404
            conn.close()
        finally:
            server.stop()

    def test_stop_is_idempotent(self) -> None:
        registry, _ = create_prometheus_registry(service_name="test")
        server = MetricsHTTPServer(registry=registry, port=19103)
        server.start()
        time.sleep(0.1)
        server.stop()
        server.stop()
