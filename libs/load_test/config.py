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
    lag_consumer_groups: list[str] = Field(
        default_factory=list,
        description=(
            "Consumer group IDs to monitor for lag during the load test. "
            "Empty list disables lag monitoring."
        ),
    )
    lag_topics: list[str] = Field(
        default_factory=lambda: ["products.raw.v1"],
        description="Topics to include in consumer-lag queries.",
    )
    lag_poll_interval_sec: float = Field(
        default=5.0,
        gt=0,
        description="Interval between consumer-lag queries in seconds.",
    )
    lag_partition_count: int = Field(
        default=3,
        ge=1,
        description="Number of partitions per monitored topic.",
    )
    pg_db_url: str = Field(
        default="",
        description=(
            "PostgreSQL connection URL for end-to-end latency probing. "
            "Empty string disables latency probing."
        ),
    )
    pg_latency_poll_interval_sec: float = Field(
        default=10.0,
        gt=0,
        description="Interval between PostgreSQL arrival checks in seconds.",
    )
    pg_latency_source: str = Field(
        default="load-test",
        description="Source label used to filter load-test events in PostgreSQL.",
    )
    api_base_url: str = Field(
        default="",
        description=(
            "Base URL of the API service for latency probing during load tests. "
            "Empty string disables API latency probing."
        ),
    )
    api_endpoints: list[str] = Field(
        default_factory=lambda: [
            "/api/v1/health",
            "/api/v1/products",
            "/api/v1/analytics/price-changes",
            "/api/v1/quality/summary",
        ],
        description="Endpoint paths to probe during load tests.",
    )
    api_latency_poll_interval_sec: float = Field(
        default=5.0,
        gt=0,
        description="Interval between API latency probe cycles in seconds.",
    )
    api_latency_timeout_sec: float = Field(
        default=10.0,
        gt=0,
        description="HTTP request timeout for API latency probes in seconds.",
    )
