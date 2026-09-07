"""Typed application configuration for AI Data Platform services.

Settings are read exclusively from ``APP_``-prefixed environment variables,
optionally seeded from a local ``.env`` file, so the same code runs locally,
under Docker, and under Kubernetes unchanged. The ``.env`` file may also
carry variables owned by other tools (for example Docker Compose); those are
ignored. See ``docs/configuration.md``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
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
    * unknown ``APP_`` variables fail startup instead of being silently
      ignored, so typos surface immediately (``load_settings`` checks both
      the environment and the ``.env`` file);
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
        # Unknown keys must not fail validation here: the same .env file also
        # carries variables owned by other tools. load_settings() rejects
        # unknown APP_ variables explicitly instead.
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


def _dotenv_keys(settings_cls: type[BaseAppSettings]) -> list[str]:
    """Return the keys present in the ``.env`` file(s) configured for the class."""
    env_file = settings_cls.model_config.get("env_file")
    if isinstance(env_file, str):
        files: list[str | Path] = [env_file]
    else:
        raw = env_file or []
        files = [Path(p) if not isinstance(p, Path) else p for p in raw]  # type: ignore[union-attr]
    keys: list[str] = []
    for path in files:
        keys.extend(dotenv_values(path))
    return keys


def _unknown_app_variables(settings_cls: type[BaseAppSettings]) -> list[str]:
    """Find ``APP_``-prefixed variables no field consumes.

    pydantic-settings deliberately ignores unknown variables: the
    environment is a shared namespace, and ``.env`` also carries variables
    owned by other tools (Docker Compose, IDEs). Only ``APP_``-prefixed
    names are this platform's responsibility, so only those are checked —
    in both the environment and ``.env`` — to surface typos immediately.
    """
    known = {f"app_{field}" for field in settings_cls.model_fields}
    candidates = {*os.environ, *_dotenv_keys(settings_cls)}
    return sorted(
        variable.upper()
        for variable in candidates
        if variable.lower().startswith("app_") and variable.lower() not in known
    )


def load_settings() -> AppSettings:
    """Load platform settings from the environment, failing fast.

    Raises:
        ConfigurationError: a required variable is missing, a value is
            invalid, or an unknown ``APP_`` variable is set (in the
            environment or in ``.env``). Services must treat this as a
            startup failure.
    """
    unknown = _unknown_app_variables(AppSettings)
    if unknown:
        details = "\n".join(
            f"  {variable}: unknown APP_ variable (typo, or not supported by this service)"
            for variable in unknown
        )
        raise ConfigurationError(
            f"Invalid configuration:\n{details}\n"
            "See docs/configuration.md for the expected variables."
        )
    try:
        return AppSettings()
    except ValidationError as exc:
        raise ConfigurationError(format_validation_error(exc)) from exc
