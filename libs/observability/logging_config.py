"""Structured logging configuration for platform services (TASK-089).

Provides machine-readable JSON logging with standardized fields:
- service: service name (e.g., "processor", "raw-writer")
- environment: deployment environment (e.g., "dev", "prod")
- timestamp: ISO 8601 UTC timestamp
- level: log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- message: log message
- Plus any extra fields passed via logger.info("msg", extra={...})

Usage:
    from libs.observability.logging_config import setup_logging

    setup_logging(service_name="processor", environment="dev")
    logger = logging.getLogger(__name__)
    logger.info("processing_started", extra={"topic": "products.raw.v1"})
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


class StructuredFormatter(logging.Formatter):
    """JSON formatter that renders log records as machine-readable objects.

    Includes standard fields (service, environment, timestamp, level, message)
    plus any extra fields passed via the `extra` parameter. Correlation ID is
    included if set via set_correlation_id().
    """

    def __init__(self, service: str, environment: str) -> None:
        super().__init__()
        self.service = service
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service,
            "environment": self.environment,
        }

        correlation_id = correlation_id_var.get()
        if correlation_id is not None:
            log_entry["correlation_id"] = correlation_id

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key in (
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "message",
                "service",
                "environment",
            ):
                continue
            if key.startswith("_"):
                continue
            try:
                json.dumps(value)
                log_entry[key] = value
            except (TypeError, ValueError):
                log_entry[key] = str(value)

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(
    service_name: str,
    environment: str | None = None,
    level: int = logging.INFO,
) -> None:
    """Configure structured JSON logging for a service.

    Args:
        service_name: Service identifier (e.g., "processor", "raw-writer")
        environment: Deployment environment (defaults to APP_ENVIRONMENT env var or "dev")
        level: Logging level (default: INFO)
    """
    import os

    if environment is None:
        environment = os.environ.get("APP_ENVIRONMENT", "dev")

    formatter = StructuredFormatter(service=service_name, environment=environment)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    logging.captureWarnings(True)


def set_correlation_id(correlation_id: str | None) -> None:
    """Set correlation ID for the current context.

    The correlation ID will be included in all log records within this context.
    Use contextvars to propagate through async/sync boundaries. Pass None to clear.
    """
    correlation_id_var.set(correlation_id)


def get_correlation_id() -> str | None:
    """Get the current correlation ID, or None if not set."""
    return correlation_id_var.get()
