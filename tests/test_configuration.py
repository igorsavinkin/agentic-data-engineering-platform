"""Tests for typed application configuration (TASK-003)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import SettingsConfigDict

from libs.common.config import (
    AppSettings,
    BaseAppSettings,
    ConfigurationError,
    Environment,
    format_validation_error,
    load_settings,
)


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Keep tests hermetic: no ambient APP_ variables, no developer .env file."""
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.upper().startswith("APP_"):
            monkeypatch.delenv(name, raising=False)
    yield


def test_valid_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "production")
    monkeypatch.setenv("APP_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("APP_NAME", "custom-service")

    settings = load_settings()

    assert settings.environment == "production"
    assert settings.log_level == "DEBUG"
    assert settings.name == "custom-service"


def test_defaults_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "development")

    settings = load_settings()

    assert settings.name == "ai-data-platform"
    assert settings.log_level == "INFO"


def test_missing_required_configuration() -> None:
    with pytest.raises(ConfigurationError) as exc_info:
        load_settings()

    message = str(exc_info.value)
    assert "APP_ENVIRONMENT" in message
    assert "Field required" in message


def test_invalid_environment_value_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "staging")

    with pytest.raises(ConfigurationError) as exc_info:
        load_settings()

    message = str(exc_info.value)
    assert "APP_ENVIRONMENT" in message
    assert "development" in message
    assert "staging" not in message


def test_environment_values_are_case_sensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "Development")

    with pytest.raises(ConfigurationError) as exc_info:
        load_settings()

    message = str(exc_info.value)
    assert "development" in message
    assert "Development" not in message


def test_invalid_log_level_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    monkeypatch.setenv("APP_LOG_LEVEL", "VERBOSE")

    with pytest.raises(ConfigurationError) as exc_info:
        load_settings()

    assert "APP_LOG_LEVEL" in str(exc_info.value)


def test_unknown_app_variable_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    monkeypatch.setenv("APP_SOMETHING", "distinctive-typo-value")

    with pytest.raises(ConfigurationError) as exc_info:
        load_settings()

    message = str(exc_info.value)
    assert "APP_SOMETHING" in message
    assert "distinctive-typo-value" not in message


def test_unknown_dotenv_key_is_rejected(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "APP_ENVIRONMENT=development\nAPP_SOMETHING=dotenv-typo-value\n", encoding="utf-8"
    )

    with pytest.raises(ConfigurationError) as exc_info:
        load_settings()

    message = str(exc_info.value)
    assert "APP_SOMETHING" in message
    assert "APP_APP_SOMETHING" not in message
    assert "dotenv-typo-value" not in message


def test_foreign_dotenv_keys_are_ignored(tmp_path: Path) -> None:
    # .env also carries Docker Compose variables (TASK-004); only
    # APP_-prefixed keys belong to application settings.
    (tmp_path / ".env").write_text(
        "APP_ENVIRONMENT=development\n"
        "POSTGRES_USER=platform\n"
        "POSTGRES_PASSWORD=platform-local\n"
        "MINIO_ROOT_USER=minioadmin\n",
        encoding="utf-8",
    )

    settings = load_settings()

    assert settings.environment == "development"


def test_environment_variables_override_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".env").write_text("APP_ENVIRONMENT=production\n", encoding="utf-8")
    monkeypatch.setenv("APP_ENVIRONMENT", "development")

    settings = load_settings()

    assert settings.environment == "development"


def test_dotenv_file_is_loaded(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("APP_ENVIRONMENT=production\n", encoding="utf-8")

    settings = load_settings()

    assert settings.environment == "production"


def test_settings_are_immutable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    settings = load_settings()

    with pytest.raises(ValidationError):
        settings.log_level = "DEBUG"  # type: ignore[misc]


def test_secret_values_are_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    class ServiceSettings(BaseAppSettings):
        api_key: SecretStr

    monkeypatch.setenv("APP_API_KEY", "super-secret-value")
    settings = ServiceSettings()

    rendered = repr(settings) + str(settings) + repr(settings.model_dump())
    assert "super-secret-value" not in rendered
    assert settings.api_key.get_secret_value() == "super-secret-value"


def test_secret_values_never_appear_in_error_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ServiceSettings(BaseAppSettings):
        api_token: SecretStr = Field(min_length=20)

    monkeypatch.setenv("APP_API_TOKEN", "short-secret")

    with pytest.raises(ValidationError) as exc_info:
        ServiceSettings()

    message = format_validation_error(exc_info.value)
    assert "APP_API_TOKEN" in message
    assert "short-secret" not in message


def test_app_settings_requires_environment_field() -> None:
    # AppSettings itself declares `environment` as the single required field.
    assert "environment" in AppSettings.model_fields
    assert AppSettings.model_fields["environment"].is_required()


def test_load_settings_with_subclass(monkeypatch: pytest.MonkeyPatch) -> None:
    """MAJOR-1: load_settings() works generically with BaseAppSettings subclasses."""

    class KafkaSettings(BaseAppSettings):
        environment: Environment
        bootstrap_servers: str

    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    monkeypatch.setenv("APP_BOOTSTRAP_SERVERS", "localhost:9092")

    settings = load_settings(KafkaSettings)

    assert isinstance(settings, KafkaSettings)
    assert settings.bootstrap_servers == "localhost:9092"
    assert settings.environment == "development"


def test_load_settings_rejects_unknown_vars_in_subclass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MAJOR-1: Unknown APP_ variables are rejected even for subclasses."""

    class ServiceSettings(BaseAppSettings):
        service_port: int = 8080

    monkeypatch.setenv("APP_ENVIRONMENT", "production")
    monkeypatch.setenv("APP_SERVICE_PORT", "8080")
    monkeypatch.setenv("APP_TYPO_VAR", "should-fail")

    with pytest.raises(ConfigurationError) as exc_info:
        load_settings(ServiceSettings)

    message = str(exc_info.value)
    assert "APP_TYPO_VAR" in message


def test_dotenv_keys_handles_single_path(tmp_path: Path) -> None:
    """MINOR-1: _dotenv_keys() correctly handles a single Path/PathLike."""
    from libs.common.config import _dotenv_keys

    env_file = tmp_path / ".env"
    env_file.write_text("APP_FOO=bar\n", encoding="utf-8")

    class TestSettings(BaseAppSettings):
        model_config = SettingsConfigDict(env_file=env_file)

    keys = _dotenv_keys(TestSettings)
    assert "APP_FOO" in keys


def test_dotenv_keys_handles_pathlib_path(tmp_path: Path) -> None:
    """MINOR-1: _dotenv_keys() handles pathlib.Path without TypeError."""
    from libs.common.config import _dotenv_keys

    env_file = tmp_path / ".env"
    env_file.write_text("APP_TEST=value\n", encoding="utf-8")

    class TestSettings(BaseAppSettings):
        model_config = SettingsConfigDict(env_file=Path(env_file))

    # Should not raise TypeError
    keys = _dotenv_keys(TestSettings)
    assert "APP_TEST" in keys


def test_duplicate_unknown_variables_eliminated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """MINOR-2: Same variable with different cases produces only one error line."""
    # Set variable in environment with uppercase
    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    monkeypatch.setenv("APP_DUP_VAR", "from-env")

    # Set same variable in .env with lowercase (different case)
    (tmp_path / ".env").write_text("app_dup_var=from-dotenv\n", encoding="utf-8")

    with pytest.raises(ConfigurationError) as exc_info:
        load_settings()

    message = str(exc_info.value)
    # Should appear only once, not twice
    assert message.count("APP_DUP_VAR") == 1
