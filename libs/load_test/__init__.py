"""Reusable load-test harness for the AI Data Platform (TASK-108).

Produces canonical product-observation events at configurable rates and
measures producer-side latency, consumer lag, and resource utilization.  The
harness is source-adapter independent and produces structured JSON results.

See ``docs/load-test-harness.md`` for usage instructions.
"""

from __future__ import annotations

from libs.load_test.config import LoadTestSettings
from libs.load_test.event_generator import EventGenerator
from libs.load_test.lag_collector import (
    LagCollector,
    LagQueryFn,
    LagSample,
    LagSummary,
    PartitionLagStats,
)
from libs.load_test.metrics_collector import MetricsCollector
from libs.load_test.report import build_report, write_report
from libs.load_test.runner import LoadTestRunner, ProduceFn

__all__ = [
    "EventGenerator",
    "LagCollector",
    "LagQueryFn",
    "LagSample",
    "LagSummary",
    "LoadTestRunner",
    "LoadTestSettings",
    "MetricsCollector",
    "PartitionLagStats",
    "ProduceFn",
    "build_report",
    "write_report",
]
