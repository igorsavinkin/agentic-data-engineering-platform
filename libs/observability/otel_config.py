"""OpenTelemetry configuration and instrumentation for platform services (TASK-090).

Provides shared OpenTelemetry setup with:
- Consistent resource identity (service.name, service.version, deployment.environment)
- Configurable exporters (OTLP gRPC, Console, or NoOp)
- Bounded safe attributes (prevent high-cardinality labels and secret leakage)
- Graceful degradation when OTel is disabled or exporter is unreachable

Usage:
    from libs.observability.otel_config import setup_opentelemetry, OTelSettings

    settings = OTelSettings(
        service_name="processor",
        service_version="0.1.0",
        environment="dev",
        otel_enabled=True,
        otel_exporter_endpoint="http://localhost:4317",
    )
    setup_opentelemetry(settings)

    # Get a tracer for creating spans (TASK-091 will add actual instrumentation)
    from libs.observability.otel_config import get_tracer
    tracer = get_tracer(__name__)
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "session",
        "credit_card",
        "ssn",
    }
)

_MAX_ATTRIBUTE_LENGTH = 256
_MAX_ATTRIBUTES_COUNT = 128


class OTelSettings(BaseSettings):
    """OpenTelemetry configuration.

    Reads from environment variables with APP_ prefix for app-specific settings,
    and OTEL_ prefix for standard OpenTelemetry settings.
    """

    service_name: str = Field(
        ..., description="Service identifier (e.g., 'processor', 'raw-writer')"
    )
    service_version: str = Field(
        default="0.1.0", description="Service version for resource identity"
    )
    environment: str = Field(
        default="dev", description="Deployment environment (dev, staging, prod)"
    )

    otel_enabled: bool = Field(default=False, description="Enable OpenTelemetry tracing")
    otel_exporter_endpoint: str | None = Field(
        default=None,
        description="OTLP exporter endpoint (e.g., 'http://localhost:4317' for gRPC)",
    )
    otel_exporter_type: str = Field(
        default="otlp",
        description="Exporter type: 'otlp' (gRPC), 'console', or 'none'",
    )

    model_config = {"env_prefix": "APP_", "case_sensitive": False, "extra": "ignore"}


def truncate_attribute(value: str, max_length: int = _MAX_ATTRIBUTE_LENGTH) -> str:
    """Truncate a string attribute to bounded length.

    Prevents high-cardinality or unbounded attributes from overwhelming the
    tracing backend. Returns the original string if within limits.
    """
    if len(value) <= max_length:
        return value
    return value[:max_length] + "...[truncated]"


def safe_attributes(data: dict[str, Any]) -> dict[str, Any]:
    """Filter and sanitize attributes for span inclusion.

    - Removes sensitive keys (password, secret, token, api_key, etc.)
    - Truncates long string values
    - Limits total attribute count
    - Converts non-serializable values to strings

    Returns a new dict with sanitized attributes.
    """
    if not data:
        return {}

    sanitized: dict[str, Any] = {}
    count = 0

    for key, value in data.items():
        if count >= _MAX_ATTRIBUTES_COUNT:
            logger.debug("attributes_limit_reached", extra={"limit": _MAX_ATTRIBUTES_COUNT})
            break

        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in _SENSITIVE_KEYS):
            logger.debug("sensitive_attribute_filtered", extra={"key": key})
            continue

        if isinstance(value, str):
            sanitized[key] = truncate_attribute(value)
        elif isinstance(value, (int, float, bool)) or value is None:
            sanitized[key] = value
        else:
            sanitized[key] = truncate_attribute(str(value))

        count += 1

    return sanitized


def get_tracer(name: str) -> Any:
    """Get an OpenTelemetry tracer by name.

    Returns a no-op tracer if OpenTelemetry is not initialized. This allows
    code to call get_tracer() unconditionally without checking if OTel is enabled.
    """
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except ImportError:
        logger.debug("opentelemetry_not_installed")
        return _NoOpTracer()


class _NoOpTracer:
    """Fallback tracer when OpenTelemetry is not installed or disabled."""

    def start_as_current_span(self, *args: Any, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()

    def start_span(self, *args: Any, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()


class _NoOpSpan:
    """Fallback span when OpenTelemetry is not installed or disabled."""

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_attributes(self, attributes: dict[str, Any]) -> None:
        pass

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        pass

    def record_exception(self, exception: Exception) -> None:
        pass

    def set_status(self, status: Any) -> None:
        pass


def setup_opentelemetry(settings: OTelSettings) -> None:
    """Initialize OpenTelemetry TracerProvider with configured exporter.

    Args:
        settings: OTel configuration (service identity, exporter endpoint, etc.)

    If otel_enabled is False, this function returns immediately without
    initializing anything. Code can still call get_tracer() which will return
    a no-op tracer.
    """
    if not settings.otel_enabled:
        logger.info("opentelemetry_disabled", extra={"service": settings.service_name})
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    except ImportError:
        logger.warning(
            "opentelemetry_sdk_not_installed",
            extra={"hint": "Install opentelemetry-api and opentelemetry-sdk"},
        )
        return

    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "service.version": settings.service_version,
            "deployment.environment": settings.environment,
        }
    )

    provider = TracerProvider(resource=resource)

    exporter_type = settings.otel_exporter_type.lower()

    if exporter_type == "console":
        processor = BatchSpanProcessor(ConsoleSpanExporter())
        provider.add_span_processor(processor)
        logger.info(
            "opentelemetry_console_exporter_enabled",
            extra={"service": settings.service_name},
        )
    elif exporter_type == "otlp":
        if not settings.otel_exporter_endpoint:
            logger.warning(
                "opentelemetry_otlp_endpoint_missing",
                extra={"hint": "Set APP_OTEL_EXPORTER_ENDPOINT for OTLP export"},
            )
            trace.set_tracer_provider(provider)
            return

        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            otlp_exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_endpoint)
            processor = BatchSpanProcessor(otlp_exporter)
            provider.add_span_processor(processor)
            logger.info(
                "opentelemetry_otlp_exporter_enabled",
                extra={
                    "service": settings.service_name,
                    "endpoint": settings.otel_exporter_endpoint,
                },
            )
        except ImportError:
            logger.warning(
                "opentelemetry_otlp_exporter_not_installed",
                extra={"hint": "Install opentelemetry-exporter-otlp-proto-grpc"},
            )
            trace.set_tracer_provider(provider)
            return
    elif exporter_type == "none":
        logger.info(
            "opentelemetry_exporter_none",
            extra={"service": settings.service_name, "hint": "No exporter configured"},
        )
    else:
        logger.warning(
            "opentelemetry_unknown_exporter_type",
            extra={"exporter_type": exporter_type, "hint": "Use 'otlp', 'console', or 'none'"},
        )

    trace.set_tracer_provider(provider)
    logger.info(
        "opentelemetry_initialized",
        extra={
            "service": settings.service_name,
            "version": settings.service_version,
            "environment": settings.environment,
        },
    )
