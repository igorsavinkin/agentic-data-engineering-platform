"""Tests for OpenTelemetry configuration module (TASK-090)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from libs.observability.otel_config import (
    OTelSettings,
    _NoOpSpan,
    _NoOpTracer,
    extract_trace_context,
    get_current_trace_id,
    get_tracer,
    inject_trace_context,
    safe_attributes,
    setup_opentelemetry,
    truncate_attribute,
)


class TestTruncateAttribute:
    def test_short_string_unchanged(self) -> None:
        assert truncate_attribute("hello") == "hello"

    def test_exact_max_length_unchanged(self) -> None:
        value = "x" * 256
        assert truncate_attribute(value) == value

    def test_long_string_truncated(self) -> None:
        value = "x" * 300
        result = truncate_attribute(value)
        assert len(result) == 256 + len("...[truncated]")
        assert result.endswith("...[truncated]")

    def test_custom_max_length(self) -> None:
        value = "hello world"
        result = truncate_attribute(value, max_length=5)
        assert result == "hello...[truncated]"


class TestSafeAttributes:
    def test_empty_dict(self) -> None:
        assert safe_attributes({}) == {}

    def test_none_values_preserved(self) -> None:
        result = safe_attributes({"key": None})
        assert result == {"key": None}

    def test_primitive_types_preserved(self) -> None:
        data = {"int": 42, "float": 3.14, "bool": True, "str": "hello"}
        result = safe_attributes(data)
        assert result == data

    def test_sensitive_keys_filtered(self) -> None:
        data = {
            "user_id": "123",
            "password": "secret123",
            "api_key": "abc-def",
            "authorization": "Bearer token",
        }
        result = safe_attributes(data)
        assert "user_id" in result
        assert "password" not in result
        assert "api_key" not in result
        assert "authorization" not in result

    def test_case_insensitive_sensitive_filtering(self) -> None:
        data = {"Password": "secret", "API_KEY": "key", "normal": "value"}
        result = safe_attributes(data)
        assert "Password" not in result
        assert "API_KEY" not in result
        assert "normal" in result

    def test_long_strings_truncated(self) -> None:
        data = {"message": "x" * 300}
        result = safe_attributes(data)
        assert len(result["message"]) < 300
        assert result["message"].endswith("...[truncated]")

    def test_non_serializable_converted_to_string(self) -> None:
        data = {"obj": object()}
        result = safe_attributes(data)
        assert isinstance(result["obj"], str)

    def test_max_attributes_limit(self) -> None:
        data = {f"key_{i}": i for i in range(200)}
        result = safe_attributes(data)
        assert len(result) == 128


class TestOTelSettings:
    def test_default_values(self) -> None:
        settings = OTelSettings(service_name="test-service")
        assert settings.service_name == "test-service"
        assert settings.service_version == "0.1.0"
        assert settings.environment == "dev"
        assert settings.otel_enabled is False
        assert settings.otel_exporter_endpoint is None
        assert settings.otel_exporter_type == "otlp"

    def test_env_var_override(self) -> None:
        with patch.dict(
            os.environ,
            {
                "APP_SERVICE_NAME": "env-service",
                "APP_OTEL_ENABLED": "true",
                "APP_OTEL_EXPORTER_ENDPOINT": "http://localhost:4317",
            },
        ):
            settings = OTelSettings()
            assert settings.service_name == "env-service"
            assert settings.otel_enabled is True
            assert settings.otel_exporter_endpoint == "http://localhost:4317"


class TestNoOpTracer:
    def test_noop_tracer_returns_noop_span(self) -> None:
        tracer = _NoOpTracer()
        span = tracer.start_span("test")
        assert isinstance(span, _NoOpSpan)

    def test_noop_span_context_manager(self) -> None:
        span = _NoOpSpan()
        with span as s:
            assert s is span

    def test_noop_span_methods_do_not_raise(self) -> None:
        span = _NoOpSpan()
        span.set_attribute("key", "value")
        span.set_attributes({"key": "value"})
        span.add_event("event", {"key": "value"})
        span.record_exception(Exception("test"))
        span.set_status("ok")


class TestGetTracer:
    def test_get_tracer_returns_noop_when_otel_not_initialized(self) -> None:
        with patch.dict("sys.modules", {"opentelemetry": None}):
            tracer = get_tracer("test")
            assert isinstance(tracer, _NoOpTracer)

    def test_get_tracer_with_otel_installed(self) -> None:
        mock_trace = MagicMock()
        mock_tracer = MagicMock()
        mock_trace.get_tracer.return_value = mock_tracer

        with patch.dict("sys.modules", {"opentelemetry": MagicMock(trace=mock_trace)}):
            get_tracer("test")
            mock_trace.get_tracer.assert_called_once_with("test")


class TestSetupOpenTelemetry:
    def test_disabled_does_nothing(self) -> None:
        settings = OTelSettings(service_name="test", otel_enabled=False)
        with patch("libs.observability.otel_config.logger") as mock_logger:
            setup_opentelemetry(settings)
            mock_logger.info.assert_called_once()

    def test_missing_sdk_logs_warning(self) -> None:
        settings = OTelSettings(service_name="test", otel_enabled=True)
        with (
            patch.dict("sys.modules", {"opentelemetry": MagicMock(), "opentelemetry.sdk": None}),
            patch("libs.observability.otel_config.logger") as mock_logger,
        ):
            setup_opentelemetry(settings)
            mock_logger.warning.assert_called()

    def test_console_exporter_configured(self) -> None:
        settings = OTelSettings(
            service_name="test",
            otel_enabled=True,
            otel_exporter_type="console",
        )

        mock_trace = MagicMock()
        mock_resource = MagicMock()
        mock_provider = MagicMock()
        mock_processor = MagicMock()
        mock_exporter = MagicMock()

        with (
            patch.dict(
                "sys.modules",
                {
                    "opentelemetry": MagicMock(trace=mock_trace),
                    "opentelemetry.sdk": MagicMock(),
                    "opentelemetry.sdk.resources": MagicMock(Resource=mock_resource),
                    "opentelemetry.sdk.trace": MagicMock(TracerProvider=mock_provider),
                    "opentelemetry.sdk.trace.export": MagicMock(
                        BatchSpanProcessor=mock_processor,
                        ConsoleSpanExporter=mock_exporter,
                    ),
                },
            ),
        ):
            setup_opentelemetry(settings)
            mock_provider.assert_called_once()
            mock_processor.assert_called_once()
            mock_provider.return_value.add_span_processor.assert_called_once()

    def test_otlp_without_endpoint_logs_warning(self) -> None:
        settings = OTelSettings(
            service_name="test",
            otel_enabled=True,
            otel_exporter_type="otlp",
            otel_exporter_endpoint=None,
        )

        mock_trace = MagicMock()
        mock_resource = MagicMock()
        mock_provider = MagicMock()

        with (
            patch.dict(
                "sys.modules",
                {
                    "opentelemetry": MagicMock(trace=mock_trace),
                    "opentelemetry.sdk": MagicMock(),
                    "opentelemetry.sdk.resources": MagicMock(Resource=mock_resource),
                    "opentelemetry.sdk.trace": MagicMock(TracerProvider=mock_provider),
                    "opentelemetry.sdk.trace.export": MagicMock(),
                },
            ),
            patch("libs.observability.otel_config.logger") as mock_logger,
        ):
            setup_opentelemetry(settings)
            mock_logger.warning.assert_called()

    def test_unknown_exporter_type_logs_warning(self) -> None:
        settings = OTelSettings(
            service_name="test",
            otel_enabled=True,
            otel_exporter_type="unknown",
        )

        mock_trace = MagicMock()
        mock_resource = MagicMock()
        mock_provider = MagicMock()

        with (
            patch.dict(
                "sys.modules",
                {
                    "opentelemetry": MagicMock(trace=mock_trace),
                    "opentelemetry.sdk": MagicMock(),
                    "opentelemetry.sdk.resources": MagicMock(Resource=mock_resource),
                    "opentelemetry.sdk.trace": MagicMock(TracerProvider=mock_provider),
                    "opentelemetry.sdk.trace.export": MagicMock(),
                },
            ),
            patch("libs.observability.otel_config.logger") as mock_logger,
        ):
            setup_opentelemetry(settings)
            mock_logger.warning.assert_called()


class TestInjectTraceContext:
    def test_inject_without_otel_does_not_raise(self) -> None:
        carrier: dict[str, bytes] = {}
        with patch.dict("sys.modules", {"opentelemetry": None}):
            inject_trace_context(carrier)

    def test_inject_with_otel_populates_carrier(self) -> None:
        carrier: dict[str, bytes] = {}
        mock_propagate = MagicMock()

        def fake_inject(headers: dict[str, str], setter: object = None) -> None:
            headers["traceparent"] = "00-abc123-def456-01"

        mock_propagate.inject.side_effect = fake_inject

        with patch.dict(
            "sys.modules",
            {
                "opentelemetry": MagicMock(
                    propagate=mock_propagate,
                    context=MagicMock(),
                ),
            },
        ):
            inject_trace_context(carrier)

        assert "traceparent" in carrier
        assert isinstance(carrier["traceparent"], bytes)
        assert carrier["traceparent"] == b"00-abc123-def456-01"


class TestExtractTraceContext:
    def test_extract_without_otel_returns_none(self) -> None:
        carrier = {"traceparent": b"00-abc123-def456-01"}
        with patch.dict("sys.modules", {"opentelemetry": None}):
            result = extract_trace_context(carrier)
        assert result is None

    def test_extract_with_otel_calls_propagator(self) -> None:
        carrier = {"traceparent": b"00-abc123-def456-01"}
        mock_propagate = MagicMock()
        mock_ctx = MagicMock()
        mock_propagate.extract.return_value = mock_ctx

        with patch.dict(
            "sys.modules",
            {"opentelemetry": MagicMock(propagate=mock_propagate)},
        ):
            result = extract_trace_context(carrier)

        assert result is mock_ctx
        mock_propagate.extract.assert_called_once()
        call_args = mock_propagate.extract.call_args
        headers_arg = call_args[0][0]
        assert headers_arg["traceparent"] == "00-abc123-def456-01"

    def test_extract_handles_string_values(self) -> None:
        carrier = {"traceparent": "00-abc123-def456-01"}
        mock_propagate = MagicMock()
        mock_propagate.extract.return_value = MagicMock()

        with patch.dict(
            "sys.modules",
            {"opentelemetry": MagicMock(propagate=mock_propagate)},
        ):
            extract_trace_context(carrier)

        call_args = mock_propagate.extract.call_args
        headers_arg = call_args[0][0]
        assert headers_arg["traceparent"] == "00-abc123-def456-01"


class TestGetCurrentTraceId:
    def test_returns_none_without_otel(self) -> None:
        with patch.dict("sys.modules", {"opentelemetry": None}):
            assert get_current_trace_id() is None

    def test_returns_none_without_active_span(self) -> None:
        mock_span = MagicMock()
        mock_span.get_span_context.return_value.trace_id = 0

        with patch.dict(
            "sys.modules",
            {"opentelemetry": MagicMock(trace=MagicMock())},
        ):
            from opentelemetry import trace

            trace.get_current_span = MagicMock(return_value=mock_span)
            result = get_current_trace_id()
        assert result is None

    def test_returns_hex_trace_id(self) -> None:
        mock_span = MagicMock()
        mock_span.get_span_context.return_value.trace_id = 0x1234567890ABCDEF1234567890ABCDEF

        mock_trace = MagicMock()
        mock_trace.get_current_span.return_value = mock_span

        with patch.dict(
            "sys.modules",
            {"opentelemetry": MagicMock(trace=mock_trace)},
        ):
            result = get_current_trace_id()
        assert result == "1234567890abcdef1234567890abcdef"
