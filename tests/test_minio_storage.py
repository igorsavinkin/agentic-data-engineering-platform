"""Unit tests for the MinIO / S3-compatible storage layer (TASK-020).

These tests mock ``boto3`` so they run without Docker or network access.
Integration tests against a real MinIO container live in
``tests/test_minio_storage_integration.py``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import SecretStr, ValidationError

from libs.common.config import ConfigurationError, load_settings
from libs.common.minio_storage import (
    BucketCreationError,
    HealthStatus,
    MinIOSettings,
    MinIOStorage,
    StorageError,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_BASE_ENV = {
    "APP_ENVIRONMENT": "development",
    "APP_MINIO_ENDPOINT": "http://localhost:9000",
    "APP_MINIO_ACCESS_KEY": "test-access",
    "APP_MINIO_SECRET_KEY": "test-secret",
}


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Run every test in a clean temp directory with no leftover APP_ vars."""
    monkeypatch.chdir(tmp_path)
    for key in list(os.environ):
        if key.upper().startswith("APP_"):
            monkeypatch.delenv(key, raising=False)
    yield


def _apply_env(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    env = {**_BASE_ENV, **overrides}
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def _client_error(code: str, message: str = "mock error") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": message}}, "operation")


# ---------------------------------------------------------------------------
# MinIOSettings — configuration
# ---------------------------------------------------------------------------


class TestMinIOSettings:
    def test_defaults_loaded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _apply_env(monkeypatch)
        settings = load_settings(MinIOSettings)
        assert isinstance(settings, MinIOSettings)
        assert settings.minio_endpoint == "http://localhost:9000"
        assert settings.minio_region == "us-east-1"
        assert settings.minio_bucket_bronze == "bronze"
        assert settings.minio_bucket_silver == "silver"
        assert settings.minio_secure is False
        assert settings.minio_connect_timeout_s == 5
        assert settings.minio_read_timeout_s == 10

    def test_secrets_are_secret_str(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _apply_env(monkeypatch)
        settings = load_settings(MinIOSettings)
        assert isinstance(settings.minio_access_key, SecretStr)
        assert isinstance(settings.minio_secret_key, SecretStr)
        assert settings.minio_access_key.get_secret_value() == "test-access"
        assert settings.minio_secret_key.get_secret_value() == "test-secret"

    def test_secret_repr_is_redacted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _apply_env(monkeypatch)
        settings = load_settings(MinIOSettings)
        assert "test-secret" not in repr(settings)
        assert "**********" in repr(settings)

    def test_custom_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _apply_env(
            monkeypatch,
            APP_MINIO_ENDPOINT="http://minio.internal:9000",
            APP_MINIO_REGION="eu-west-1",
            APP_MINIO_BUCKET_BRONZE="raw-zone",
            APP_MINIO_BUCKET_SILVER="clean-zone",
            APP_MINIO_SECURE="true",
            APP_MINIO_CONNECT_TIMEOUT_S="10",
            APP_MINIO_READ_TIMEOUT_S="30",
        )
        settings = load_settings(MinIOSettings)
        assert settings.minio_endpoint == "http://minio.internal:9000"
        assert settings.minio_region == "eu-west-1"
        assert settings.minio_bucket_bronze == "raw-zone"
        assert settings.minio_bucket_silver == "clean-zone"
        assert settings.minio_secure is True
        assert settings.minio_connect_timeout_s == 10
        assert settings.minio_read_timeout_s == 30

    def test_bucket_names_property(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _apply_env(monkeypatch)
        settings = load_settings(MinIOSettings)
        assert settings.bucket_names == ["bronze", "silver"]

    def test_invalid_endpoint_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _apply_env(monkeypatch, APP_MINIO_ENDPOINT="not-a-url")
        with pytest.raises(ConfigurationError, match="Invalid configuration"):
            load_settings(MinIOSettings)

    def test_invalid_bucket_name_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _apply_env(monkeypatch, APP_MINIO_BUCKET_BRONZE="INVALID_UPPER")
        with pytest.raises(ConfigurationError, match="Invalid configuration"):
            load_settings(MinIOSettings)

    def test_short_bucket_name_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _apply_env(monkeypatch, APP_MINIO_BUCKET_BRONZE="ab")
        with pytest.raises(ConfigurationError, match="Invalid configuration"):
            load_settings(MinIOSettings)

    def test_timeout_bounds_enforced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _apply_env(monkeypatch, APP_MINIO_CONNECT_TIMEOUT_S="0")
        with pytest.raises(ConfigurationError):
            load_settings(MinIOSettings)

    def test_settings_are_frozen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _apply_env(monkeypatch)
        settings = load_settings(MinIOSettings)
        with pytest.raises(ValidationError):
            settings.minio_endpoint = "http://other:9000"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# MinIOStorage — bucket initialisation
# ---------------------------------------------------------------------------


def _make_settings(monkeypatch: pytest.MonkeyPatch) -> MinIOSettings:
    _apply_env(monkeypatch)
    return load_settings(MinIOSettings)


class TestEnsureBucket:
    @patch("libs.common.minio_storage.boto3")
    def test_creates_bucket_when_missing(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.head_bucket.side_effect = _client_error("404")
        client.create_bucket.return_value = {}

        storage = MinIOStorage(settings)
        storage.ensure_bucket("bronze")

        client.create_bucket.assert_called_once_with(Bucket="bronze")

    @patch("libs.common.minio_storage.boto3")
    def test_skips_creation_when_bucket_exists(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.head_bucket.return_value = {}

        storage = MinIOStorage(settings)
        storage.ensure_bucket("bronze")

        client.create_bucket.assert_not_called()

    @patch("libs.common.minio_storage.boto3")
    def test_idempotent_when_already_owned(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.head_bucket.side_effect = _client_error("404")
        client.create_bucket.side_effect = _client_error("BucketAlreadyOwnedByYou")

        storage = MinIOStorage(settings)
        storage.ensure_bucket("bronze")

    @patch("libs.common.minio_storage.boto3")
    def test_idempotent_when_already_exists(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.head_bucket.side_effect = _client_error("404")
        client.create_bucket.side_effect = _client_error("BucketAlreadyExists")

        storage = MinIOStorage(settings)
        storage.ensure_bucket("bronze")

    @patch("libs.common.minio_storage.boto3")
    def test_raises_on_unexpected_probe_error(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.head_bucket.side_effect = _client_error("500")

        storage = MinIOStorage(settings)
        with pytest.raises(StorageError, match="Cannot probe"):
            storage.ensure_bucket("bronze")

    @patch("libs.common.minio_storage.boto3")
    def test_raises_bucket_creation_error_on_failure(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.head_bucket.side_effect = _client_error("404")
        client.create_bucket.side_effect = _client_error("AccessDenied")

        storage = MinIOStorage(settings)
        with pytest.raises(BucketCreationError, match="Cannot create bucket"):
            storage.ensure_bucket("bronze")

    @patch("libs.common.minio_storage.boto3")
    def test_raises_on_network_error_during_creation(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.head_bucket.side_effect = _client_error("404")
        client.create_bucket.side_effect = BotoCoreError()

        storage = MinIOStorage(settings)
        with pytest.raises(BucketCreationError, match="network error"):
            storage.ensure_bucket("bronze")


class TestEnsureAllBuckets:
    @patch("libs.common.minio_storage.boto3")
    def test_creates_all_configured_buckets(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.head_bucket.side_effect = _client_error("404")
        client.create_bucket.return_value = {}

        storage = MinIOStorage(settings)
        storage.ensure_all_buckets()

        calls = [c.kwargs["Bucket"] for c in client.create_bucket.call_args_list]
        assert calls == ["bronze", "silver"]

    @patch("libs.common.minio_storage.boto3")
    def test_idempotent_multiple_calls(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.head_bucket.return_value = {}

        storage = MinIOStorage(settings)
        storage.ensure_all_buckets()
        storage.ensure_all_buckets()

        client.create_bucket.assert_not_called()


# ---------------------------------------------------------------------------
# MinIOStorage — put / get / exists
# ---------------------------------------------------------------------------


class TestPutObject:
    @patch("libs.common.minio_storage.boto3")
    def test_put_bytes(self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.put_object.return_value = {}

        storage = MinIOStorage(settings)
        storage.put_object("bronze", "test/key.json", b'{"hello":"world"}')

        client.put_object.assert_called_once_with(
            Bucket="bronze", Key="test/key.json", Body=b'{"hello":"world"}'
        )

    @patch("libs.common.minio_storage.boto3")
    def test_put_stream(self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.put_object.return_value = {}

        stream = BytesIO(b"binary-data")
        storage = MinIOStorage(settings)
        storage.put_object("silver", "data/file.parquet", stream)

        client.put_object.assert_called_once()

    @patch("libs.common.minio_storage.boto3")
    def test_put_raises_storage_error_on_client_error(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.put_object.side_effect = _client_error("InternalError")

        storage = MinIOStorage(settings)
        with pytest.raises(StorageError, match="put_object failed"):
            storage.put_object("bronze", "key", b"data")

    @patch("libs.common.minio_storage.boto3")
    def test_put_raises_storage_error_on_network_error(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.put_object.side_effect = BotoCoreError()

        storage = MinIOStorage(settings)
        with pytest.raises(StorageError, match="put_object failed"):
            storage.put_object("bronze", "key", b"data")


class TestGetObject:
    @patch("libs.common.minio_storage.boto3")
    def test_get_returns_bytes(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        body_mock = MagicMock()
        body_mock.read.return_value = b'{"result":true}'
        client.get_object.return_value = {"Body": body_mock}

        storage = MinIOStorage(settings)
        result = storage.get_object("bronze", "test/key.json")

        assert result == b'{"result":true}'
        client.get_object.assert_called_once_with(Bucket="bronze", Key="test/key.json")

    @patch("libs.common.minio_storage.boto3")
    def test_get_raises_key_error_for_missing_object(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.get_object.side_effect = _client_error("NoSuchKey")

        storage = MinIOStorage(settings)
        with pytest.raises(KeyError, match="Object not found"):
            storage.get_object("bronze", "missing/key")

    @patch("libs.common.minio_storage.boto3")
    def test_get_raises_storage_error_on_other_client_error(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.get_object.side_effect = _client_error("InternalError")

        storage = MinIOStorage(settings)
        with pytest.raises(StorageError, match="get_object failed"):
            storage.get_object("bronze", "key")

    @patch("libs.common.minio_storage.boto3")
    def test_get_raises_storage_error_on_network_error(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.get_object.side_effect = BotoCoreError()

        storage = MinIOStorage(settings)
        with pytest.raises(StorageError, match="get_object failed"):
            storage.get_object("bronze", "key")


class TestObjectExists:
    @patch("libs.common.minio_storage.boto3")
    def test_returns_true_when_exists(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.head_object.return_value = {}

        storage = MinIOStorage(settings)
        assert storage.object_exists("bronze", "key") is True

    @patch("libs.common.minio_storage.boto3")
    def test_returns_false_when_missing(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.head_object.side_effect = _client_error("404")

        storage = MinIOStorage(settings)
        assert storage.object_exists("bronze", "key") is False

    @patch("libs.common.minio_storage.boto3")
    def test_returns_false_for_no_such_bucket(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.head_object.side_effect = _client_error("NoSuchBucket")

        storage = MinIOStorage(settings)
        assert storage.object_exists("bronze", "key") is False

    @patch("libs.common.minio_storage.boto3")
    def test_raises_on_unexpected_error(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.head_object.side_effect = _client_error("500")

        storage = MinIOStorage(settings)
        with pytest.raises(StorageError, match="object_exists failed"):
            storage.object_exists("bronze", "key")


# ---------------------------------------------------------------------------
# MinIOStorage — health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    @patch("libs.common.minio_storage.boto3")
    def test_healthy_when_reachable(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.list_buckets.return_value = {"Buckets": []}

        storage = MinIOStorage(settings)
        status = storage.check_health()

        assert status == HealthStatus(healthy=True, detail="ok")

    @patch("libs.common.minio_storage.boto3")
    def test_unhealthy_on_client_error(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.list_buckets.side_effect = _client_error("AccessDenied")

        storage = MinIOStorage(settings)
        status = storage.check_health()

        assert status.healthy is False
        assert status.detail == "ClientError"

    @patch("libs.common.minio_storage.boto3")
    def test_unhealthy_on_network_error(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client
        client.list_buckets.side_effect = BotoCoreError()

        storage = MinIOStorage(settings)
        status = storage.check_health()

        assert status.healthy is False
        assert status.detail == "BotoCoreError"


# ---------------------------------------------------------------------------
# MinIOStorage — lifecycle and edge cases
# ---------------------------------------------------------------------------


class TestLifecycle:
    @patch("libs.common.minio_storage.boto3")
    def test_context_manager_closes_client(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client

        with MinIOStorage(settings) as storage:
            storage.check_health()

        client.close.assert_called_once()

    @patch("libs.common.minio_storage.boto3")
    def test_operations_fail_after_close(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client

        storage = MinIOStorage(settings)
        storage.close()

        with pytest.raises(StorageError, match="closed"):
            storage.put_object("bronze", "key", b"data")
        with pytest.raises(StorageError, match="closed"):
            storage.get_object("bronze", "key")
        with pytest.raises(StorageError, match="closed"):
            storage.object_exists("bronze", "key")
        with pytest.raises(StorageError, match="closed"):
            storage.check_health()
        with pytest.raises(StorageError, match="closed"):
            storage.ensure_bucket("bronze")

    @patch("libs.common.minio_storage.boto3")
    def test_close_is_idempotent(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client

        storage = MinIOStorage(settings)
        storage.close()
        storage.close()

        client.close.assert_called_once()

    @patch("libs.common.minio_storage.boto3")
    def test_client_uses_path_style_addressing(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        mock_boto3.client.return_value = MagicMock()

        MinIOStorage(settings)

        call_kwargs = mock_boto3.client.call_args
        boto_config = call_kwargs.kwargs["config"]
        assert boto_config.s3["addressing_style"] == "path"

    @patch("libs.common.minio_storage.boto3")
    def test_client_uses_configured_endpoint(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _apply_env(monkeypatch, APP_MINIO_ENDPOINT="http://minio.custom:9000")
        settings = load_settings(MinIOSettings)
        mock_boto3.client.return_value = MagicMock()

        MinIOStorage(settings)

        call_kwargs = mock_boto3.client.call_args
        assert call_kwargs.kwargs["endpoint_url"] == "http://minio.custom:9000"


# ---------------------------------------------------------------------------
# Smoke test — put/get round-trip with mock
# ---------------------------------------------------------------------------


class TestSmokeRoundTrip:
    @patch("libs.common.minio_storage.boto3")
    def test_put_then_get_returns_same_bytes(
        self, mock_boto3: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(monkeypatch)
        client = MagicMock()
        mock_boto3.client.return_value = client

        payload = b'{"event_id":"abc-123","source":"fake-store"}'
        client.put_object.return_value = {}
        body_mock = MagicMock()
        body_mock.read.return_value = payload
        client.get_object.return_value = {"Body": body_mock}

        storage = MinIOStorage(settings)
        storage.put_object("bronze", "source=fake/year=2026/event.json", payload)
        result = storage.get_object("bronze", "source=fake/year=2026/event.json")

        assert result == payload
