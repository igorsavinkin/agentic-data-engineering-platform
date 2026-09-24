"""Typed configuration for load-test runs (TASK-108).

Settings are read from ``APP_``-prefixed environment variables, following the
same convention as the rest of the platform (``docs/configuration.md``).
"""

from __future__ import annotations

from pydantic import Field

from libs.common.config import BaseAppSettings


class LoadTestSettings(BaseAppSettings):
    """Configuration for a single load-test run.

    The harness is source-adapter independent: it generates synthetic
    canonical events directly rather than calling any adapter.
    """

    target_events_per_sec: float = Field(
        default=100.0,
        gt=0,
        description="Target production rate in events per second.",
    )
    duration_sec: float = Field(
        default=30.0,
        gt=0,
        description="How long the load test runs in seconds.",
    )
    total_events: int = Field(
        default=0,
        ge=0,
        description=(
            "If positive, produce at least this many events instead of running "
            "for duration_sec.  When both are set, the first limit wins. "
            "Multi-worker runs may overshoot slightly due to race conditions."
        ),
    )
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_raw_topic: str = "products.raw.v1"
    kafka_client_id: str = "load-test-harness"
    worker_count: int = Field(
        default=1,
        ge=1,
        le=64,
        description="Number of parallel producer threads.",
    )
    output_path: str = Field(
        default="load_test_results.json",
        description="Path for the structured JSON result report.",
    )
    source_name: str = Field(
        default="load-test",
        description="Source label embedded in generated events.",
    )
    seed: int = Field(
        default=42,
        description="Random seed for deterministic event generation.",
    )
    disable_auto_scaling: bool = Field(
        default=False,
        description="If true, use exactly worker_count workers (skip auto-scaler).",
    )
