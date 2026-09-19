"""Lightweight HTTP server exposing Prometheus metrics for background services.

Background services (ingestion, processor, raw-writer, lake-writer,
warehouse-loader) do not run a full HTTP framework. This module provides
a minimal threaded HTTP server that serves ``/metrics`` using a dedicated
Prometheus ``CollectorRegistry``.

Usage::

    from libs.observability.metrics_http_server import MetricsHTTPServer

    server = MetricsHTTPServer(registry=registry, port=9100)
    server.start()
    # ... service runs ...
    server.stop()

The server binds to ``0.0.0.0`` by default. Set ``host`` to restrict.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from prometheus_client import CollectorRegistry
from prometheus_client.exposition import generate_latest


class _MetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler that serves Prometheus text format on ``/metrics``."""

    registry: CollectorRegistry

    def do_GET(self) -> None:
        if self.path == "/metrics":
            output = generate_latest(self.registry)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(output)))
            self.end_headers()
            self.wfile.write(output)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


class MetricsHTTPServer:
    """Threaded HTTP server exposing ``/metrics`` for Prometheus scraping.

    Parameters
    ----------
    registry:
        Prometheus CollectorRegistry to serve.
    port:
        TCP port to listen on. Default 9100.
    host:
        Bind address. Default ``0.0.0.0``.
    """

    def __init__(
        self,
        registry: CollectorRegistry,
        port: int = 9100,
        host: str = "0.0.0.0",
    ) -> None:
        self._port = port
        self._host = host
        self._registry = registry
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        handler_class = type(
            "_BoundMetricsHandler",
            (_MetricsHandler,),
            {"registry": self._registry},
        )
        self._server = HTTPServer((self._host, self._port), handler_class)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="metrics-http",
        )
        self._thread.start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    @property
    def port(self) -> int:
        return self._port
