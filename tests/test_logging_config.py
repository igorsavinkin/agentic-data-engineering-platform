"""Tests for structured logging configuration (TASK-089)."""

from __future__ import annotations

import json
import logging

from libs.observability.logging_config import (
    StructuredFormatter,
    get_correlation_id,
    set_correlation_id,
    setup_logging,
)


class TestStructuredFormatter:
    def test_format_includes_standard_fields(self) -> None:
        formatter = StructuredFormatter(service="test-service", environment="test")
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["service"] == "test-service"
        assert parsed["environment"] == "test"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.logger"
        assert parsed["message"] == "test message"
        assert "timestamp" in parsed

    def test_format_includes_extra_fields(self) -> None:
        formatter = StructuredFormatter(service="test-service", environment="test")
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        record.topic = "products.raw.v1"
        record.partition = 0
        record.count = 42

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["topic"] == "products.raw.v1"
        assert parsed["partition"] == 0
        assert parsed["count"] == 42

    def test_format_handles_non_json_serializable_extra(self) -> None:
        formatter = StructuredFormatter(service="test-service", environment="test")
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        record.custom_object = object()

        output = formatter.format(record)
        parsed = json.loads(output)

        assert "custom_object" in parsed
        assert isinstance(parsed["custom_object"], str)

    def test_format_includes_exception_info(self) -> None:
        formatter = StructuredFormatter(service="test-service", environment="test")
        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="error occurred",
            args=(),
            exc_info=exc_info,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]
        assert "test error" in parsed["exception"]

    def test_format_includes_correlation_id_when_set(self) -> None:
        formatter = StructuredFormatter(service="test-service", environment="test")
        set_correlation_id("test-correlation-123")

        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["correlation_id"] == "test-correlation-123"

        set_correlation_id(None)

    def test_format_excludes_correlation_id_when_not_set(self) -> None:
        formatter = StructuredFormatter(service="test-service", environment="test")
        set_correlation_id(None)

        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert "correlation_id" not in parsed


class TestSetupLogging:
    def test_setup_logging_configures_root_logger(self) -> None:
        setup_logging(service_name="test-service", environment="test")

        root_logger = logging.getLogger()
        assert len(root_logger.handlers) > 0
        assert isinstance(root_logger.handlers[0].formatter, StructuredFormatter)

    def test_setup_logging_uses_default_environment(self) -> None:
        setup_logging(service_name="test-service")

        root_logger = logging.getLogger()
        formatter = root_logger.handlers[0].formatter
        assert isinstance(formatter, StructuredFormatter)
        assert formatter.environment in ["dev", "test", "prod"]


class TestCorrelationId:
    def test_set_and_get_correlation_id(self) -> None:
        set_correlation_id("test-id-123")
        assert get_correlation_id() == "test-id-123"

        set_correlation_id(None)
        assert get_correlation_id() is None

    def test_correlation_id_default_is_none(self) -> None:
        set_correlation_id(None)
        assert get_correlation_id() is None
