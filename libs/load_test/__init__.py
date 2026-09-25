"""Reusable load-test harness for the AI Data Platform (TASK-108).

Produces canonical product-observation events at configurable rates and
measures producer-side latency, consumer lag, end-to-end processing latency,
and resource utilization.  The harness is source-adapter independent and
produces structured JSON results.

See ``docs/load-test-harness.md`` for usage instructions.
"""

from __future__ import annotations

from libs.load_test.api_latency_collector import ApiLatencyCollector, ApiLatencySample
from libs.load_test.config import LoadTestSettings
from libs.load_test.event_generator import EventGenerator
from libs.load_test.lag_collector import (
    LagCollector,
    LagQueryFn,
    LagSample,
    LagSummary,
    PartitionLagStats,
)
from libs.load_test.latency_collector import (
    EndToEndSample,
    LatencyCollector,
    PgQueryFn,
    ProduceRecord,
)
from libs.load_test.metrics_collector import MetricsCollector
from libs.load_test.report import build_report, write_report
from libs.load_test.runner import LoadTestRunner, ProduceFn

__all__ = [
    "ApiLatencyCollector",
    "ApiLatencySample",
    "EndToEndSample",
    "EventGenerator",
    "LagCollector",
    "LagQueryFn",
    "LagSample",
    "LagSummary",
    "LatencyCollector",
    "LoadTestRunner",
    "LoadTestSettings",
    "MetricsCollector",
    "PartitionLagStats",
    "PgQueryFn",
    "ProduceFn",
    "ProduceRecord",
    "build_report",
    "write_report",
]
