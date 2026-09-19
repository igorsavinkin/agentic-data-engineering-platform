"""Typed application configuration for AI Data Platform services.

Settings are read exclusively from ``APP_``-prefixed environment variables,
optionally seeded from a local ``.env`` file, so the same code runs locally,
under Docker, and under Kubernetes unchanged. The ``.env`` file may also
carry variables owned by other tools (for example Docker Compose); those are
ignored. See ``docs/configuration.md``.
"""

from __future__ import annotations

from typing import Literal, TypeVar, overload

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class ConfigurationError(Exception):
    """Raised when configuration is missing or invalid.

    Messages are safe to log: they name the offending environment variable
    but never echo its value.
    """


class BaseAppSettings(BaseSettings):
    """Base class for typed settings.

    Subclasses declare their fields; this base enforces the platform
    conventions:

    * variables are prefixed ``APP_`` (``log_level`` -> ``APP_LOG_LEVEL``);
    * variable names are matched case-insensitively;
    * unknown ``APP_`` variables are silently ignored, allowing services to
      load multiple settings classes from the same environment;
    * non-``APP_`` keys in ``.env`` belong to other tools (for example
      Docker Compose's ``POSTGRES_USER``) and are ignored;
    * loaded settings are immutable;
    * real environment variables win over ``.env`` file values, so containers
      and Kubernetes can inject configuration directly.
    """

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )


class AppSettings(BaseAppSettings):
    """Platform-wide settings shared by every service."""

    name: str = "ai-data-platform"
    environment: Environment
    log_level: LogLevel = "INFO"


def format_validation_error(error: ValidationError) -> str:
    """Render a validation error as a log-safe, actionable message.

    Pydantic error details can include the offending input value; this
    formatter deliberately drops it so configuration errors can be logged
    without leaking secrets.
    """
    lines = ["Invalid configuration:"]
    for err in error.errors():
        location = ".".join(str(part) for part in err["loc"]) or "<root>"
        variable = f"APP_{location.upper()}"
        lines.append(f"  {variable}: {err['msg']}")
    lines.append("See docs/configuration.md for the expected variables.")
    return "\n".join(lines)


TSettings = TypeVar("TSettings", bound=BaseAppSettings)


@overload
def load_settings() -> AppSettings: ...


@overload
def load_settings(settings_cls: type[TSettings]) -> TSettings: ...


def load_settings(
    settings_cls: type[BaseAppSettings] | None = None,
) -> BaseAppSettings:
    """Load settings from APP_-prefixed environment variables.

    Unknown APP_ variables are silently ignored (pydantic's ``extra="ignore"``),
    allowing services to load multiple settings classes without cross-class
    rejection. For example, raw-writer loads both ``KafkaConsumerSettings`` and
    ``MinIOSettings`` from the same environment.
    """
    cls = settings_cls or AppSettings

    try:
        return cls()
    except ValidationError as exc:
        raise ConfigurationError(format_validation_error(exc)) from exc
