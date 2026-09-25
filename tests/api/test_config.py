"""Tests for API service typed configuration."""

from __future__ import annotations

import pytest

from services.api.config import APISettings, DatabaseSettings


class TestDatabaseSettings:
    def test_default_url(self) -> None:
        settings = DatabaseSettings()
        assert settings.url == "postgresql+psycopg2://postgres@localhost:5432/warehouse"

    def test_custom_url(self) -> None:
        settings = DatabaseSettings(url="sqlite://")
        assert settings.url == "sqlite://"

    def test_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WAREHOUSE_DB_HOST", "custom-host")
        monkeypatch.setenv("WAREHOUSE_DB_PORT", "5433")
        monkeypatch.setenv("WAREHOUSE_DB_NAME", "custom_db")
        monkeypatch.setenv("WAREHOUSE_DB_USER", "custom_user")
        monkeypatch.setenv("WAREHOUSE_DB_PASSWORD", "custom_pass")

        settings = DatabaseSettings.from_env()
        assert (
            settings.url
            == "postgresql+psycopg2://custom_user:custom_pass@custom-host:5433/custom_db"
        )

    def test_from_env_without_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WAREHOUSE_DB_HOST", "db")
        monkeypatch.setenv("WAREHOUSE_DB_PORT", "5432")
        monkeypatch.setenv("WAREHOUSE_DB_NAME", "warehouse")
        monkeypatch.setenv("WAREHOUSE_DB_USER", "usr")
        monkeypatch.delenv("WAREHOUSE_DB_PASSWORD", raising=False)

        settings = DatabaseSettings.from_env()
        assert settings.url == "postgresql+psycopg2://usr@db:5432/warehouse"

    def test_frozen(self) -> None:
        settings = DatabaseSettings()
        with pytest.raises(AttributeError):
            settings.url = "other"  # type: ignore[misc]


class TestAPISettings:
    def test_defaults(self) -> None:
        settings = APISettings()
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000
        assert settings.debug is False

    def test_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_API_HOST", "127.0.0.1")
        monkeypatch.setenv("APP_API_PORT", "9000")
        monkeypatch.setenv("APP_DEBUG", "true")

        settings = APISettings.from_env()
        assert settings.host == "127.0.0.1"
        assert settings.port == 9000
        assert settings.debug is True

    def test_debug_false_for_unknown_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_DEBUG", "nope")
        settings = APISettings.from_env()
        assert settings.debug is False

    def test_frozen(self) -> None:
        settings = APISettings()
        with pytest.raises(AttributeError):
            settings.port = 1234  # type: ignore[misc]
