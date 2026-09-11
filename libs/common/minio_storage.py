"""S3-compatible object-storage client for the data lake (TASK-020).

MinIO provides the local S3-compatible layer; AWS S3 is used in production.
The same ``boto3`` client works for both — only the endpoint URL changes.

This module owns:

* typed endpoint / credential / bucket configuration (``MinIOSettings``);
* a thin, reusable storage client (``MinIOStorage``) with put / get / exists;
* idempotent bucket initialisation (``ensure_bucket``);
* a health / readiness probe (``check_health``).

Parquet serialisation is deliberately out of scope here; later tasks
(TASK-021 …) consume this boundary to write Bronze and Silver data.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from threading import Lock
from types import TracebackType
from typing import IO

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import Field, SecretStr, field_validator

from libs.common.config import AppSettings

logger = logging.getLogger(__name__)

# MinIO / S3 bucket names must follow DNS naming rules: 3-63 characters,
# lowercase letters, digits, dots, hyphens.  This regex is intentionally
# strict so a typo fails at startup rather than at the first write.
_BUCKET_NAME_RE = r"[a-z0-9][a-z0-9.\-]{1,61}[a-z0-9]"


class MinIOSettings(AppSettings):
    """Load with ``load_settings(MinIOSettings)``; see docs/minio-storage.md."""

    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: SecretStr = SecretStr("minioadmin")
    minio_secret_key: SecretStr = SecretStr("minioadmin-local")
    minio_region: str = "us-east-1"
    minio_bucket_bronze: str = "bronze"
    minio_bucket_silver: str = "silver"
    minio_connect_timeout_s: int = Field(default=5, ge=1, le=60)
    minio_read_timeout_s: int = Field(default=10, ge=1, le=120)
    minio_secure: bool = False

    @field_validator("minio_endpoint")
    @classmethod
    def valid_endpoint(cls, value: str) -> str:
        if not re.fullmatch(r"https?://[A-Za-z0-9_.:-]+", value):
            raise ValueError("expected http:// or https:// followed by host[:port]")
        return value

    @field_validator("minio_bucket_bronze", "minio_bucket_silver")
    @classmethod
    def valid_bucket_name(cls, value: str) -> str:
        if not re.fullmatch(_BUCKET_NAME_RE, value):
            raise ValueError(
                "bucket name must be 3-63 chars: lowercase letters, digits, dots, hyphens"
            )
        return value

    @property
    def bucket_names(self) -> list[str]:
        return [self.minio_bucket_bronze, self.minio_bucket_silver]


class StorageError(Exception):
    """Object-storage operation failed.  The caller may retry."""


class BucketCreationError(Exception):
    """Bucket initialisation failed after all retries."""


@dataclass(frozen=True)
class HealthStatus:
    healthy: bool
    detail: str


class MinIOStorage:
    """Thin wrapper around a ``boto3`` S3 client.

    The class is intentionally small: it exposes only the operations the
    data-lake layer needs (bucket init, put, get, exists, health).  Later
    tasks build Parquet writing on top of this boundary.

    Thread safety: a single internal lock serialises mutating operations
    (bucket creation, put) so concurrent callers on the same instance
    observe a consistent state.  Read-only operations (get, exists,
    health) are safe to call concurrently with each other.
    """

    def __init__(self, settings: MinIOSettings) -> None:
        self._settings = settings
        self._lock = Lock()
        self._closed = False
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.minio_endpoint,
            aws_access_key_id=settings.minio_access_key.get_secret_value(),
            aws_secret_access_key=settings.minio_secret_key.get_secret_value(),
            region_name=settings.minio_region,
            config=BotoConfig(
                connect_timeout=settings.minio_connect_timeout_s,
                read_timeout=settings.minio_read_timeout_s,
                retries={"max_attempts": 3, "mode": "standard"},
                s3={"addressing_style": "path"},
            ),
        )
        logger.info(
            "minio_client_initialized",
            extra={"endpoint": settings.minio_endpoint, "region": settings.minio_region},
        )

    def ensure_bucket(self, bucket: str) -> None:
        """Create the bucket if it does not already exist (idempotent).

        Idempotency matters because the platform is at-least-once: services
        restart, replay, and the initialisation path may run many times.
        A 409 BucketAlreadyOwnedByYou is treated as success.
        """
        with self._lock:
            self._assert_open()
            try:
                self._client.head_bucket(Bucket=bucket)
                logger.debug("bucket_exists", extra={"bucket": bucket})
                return
            except ClientError as exc:
                status = exc.response["Error"]["Code"]
                if status not in ("404", "NoSuchBucket", "403"):
                    raise StorageError(f"Cannot probe bucket {bucket!r}: {status}") from exc
            try:
                self._client.create_bucket(Bucket=bucket)
                logger.info("bucket_created", extra={"bucket": bucket})
            except ClientError as exc:
                code = exc.response["Error"]["Code"]
                if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                    logger.debug("bucket_already_exists", extra={"bucket": bucket})
                    return
                raise BucketCreationError(f"Cannot create bucket {bucket!r}: {code}") from exc
            except BotoCoreError as exc:
                raise BucketCreationError(
                    f"Cannot create bucket {bucket!r}: network error"
                ) from exc

    def ensure_all_buckets(self) -> None:
        """Idempotently create every bucket declared in settings."""
        for bucket in self._settings.bucket_names:
            self.ensure_bucket(bucket)

    def put_object(self, bucket: str, key: str, body: bytes | IO[bytes]) -> None:
        with self._lock:
            self._assert_open()
            try:
                self._client.put_object(Bucket=bucket, Key=key, Body=body)
            except (ClientError, BotoCoreError) as exc:
                raise StorageError(f"put_object failed: bucket={bucket!r} key={key!r}") from exc
        logger.info("object_written", extra={"bucket": bucket, "key": key})

    def get_object(self, bucket: str, key: str) -> bytes:
        self._assert_open()
        try:
            response = self._client.get_object(Bucket=bucket, Key=key)
            body: bytes = response["Body"].read()
            return body
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in ("NoSuchKey", "404"):
                raise KeyError(f"Object not found: s3://{bucket}/{key}") from exc
            raise StorageError(f"get_object failed: bucket={bucket!r} key={key!r}") from exc
        except BotoCoreError as exc:
            raise StorageError(f"get_object failed: bucket={bucket!r} key={key!r}") from exc

    def object_exists(self, bucket: str, key: str) -> bool:
        self._assert_open()
        try:
            self._client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in ("404", "NoSuchKey", "NoSuchBucket"):
                return False
            raise StorageError(f"object_exists failed: bucket={bucket!r} key={key!r}") from exc
        except BotoCoreError as exc:
            raise StorageError(f"object_exists failed: bucket={bucket!r} key={key!r}") from exc

    def check_health(self) -> HealthStatus:
        """Probe whether the object store is reachable and authenticated.

        Used by readiness / liveness probes.  A failing health check must
        not crash the service; the caller decides the recovery strategy.
        """
        self._assert_open()
        try:
            self._client.list_buckets()
            return HealthStatus(healthy=True, detail="ok")
        except (ClientError, BotoCoreError) as exc:
            return HealthStatus(healthy=False, detail=str(exc.__class__.__name__))

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._client.close()
            self._closed = True
            logger.info("minio_client_closed")

    def _assert_open(self) -> None:
        if self._closed:
            raise StorageError("MinIOStorage is closed")

    def __enter__(self) -> MinIOStorage:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
