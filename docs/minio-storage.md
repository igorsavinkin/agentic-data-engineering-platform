# MinIO object-storage client (TASK-020)

`libs.common.minio_storage.MinIOStorage` provides a thin, reusable S3-compatible
object-storage boundary for the data lake.  Local development uses MinIO;
production uses AWS S3.  The same `boto3` client works for both — only the
endpoint URL changes.

Parquet serialisation is deliberately out of scope; later tasks (TASK-021 ...)
consume this boundary to write Bronze and Silver data.

## Configuration and use

Load `MinIOSettings` with the existing `load_settings` helper.  It inherits
`AppSettings`, including required `APP_ENVIRONMENT`, `.env` loading, environment
precedence, immutable settings, and rejection of unknown `APP_` variables.

| Variable | Default | Accepted values |
| --- | --- | --- |
| `APP_MINIO_ENDPOINT` | `http://localhost:9000` | `http://` or `https://` followed by `host[:port]` |
| `APP_MINIO_ACCESS_KEY` | `minioadmin` | non-empty string (stored as `SecretStr`) |
| `APP_MINIO_SECRET_KEY` | `minioadmin-local` | non-empty string (stored as `SecretStr`) |
| `APP_MINIO_REGION` | `us-east-1` | non-empty string |
| `APP_MINIO_BUCKET_BRONZE` | `bronze` | DNS-compliant bucket name (3-63 chars, lowercase, digits, dots, hyphens) |
| `APP_MINIO_BUCKET_SILVER` | `silver` | DNS-compliant bucket name |
| `APP_MINIO_CONNECT_TIMEOUT_S` | `5` | integer, 1-60 seconds |
| `APP_MINIO_READ_TIMEOUT_S` | `10` | integer, 1-120 seconds |
| `APP_MINIO_SECURE` | `false` | `true` or `false` |

Host processes use `http://localhost:9000`; containers on the Compose network
use `http://minio:9000`.  If changing `MINIO_HOST_PORT`, set the application
endpoint port to match.  These application variables are separate from the
Docker Compose stack's own `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`.

```python
from libs.common import MinIOSettings, MinIOStorage, load_settings

settings = load_settings(MinIOSettings)
with MinIOStorage(settings) as storage:
    storage.ensure_all_buckets()
    storage.put_object("bronze", "raw/test.bin", b"data")
    data = storage.get_object("bronze", "raw/test.bin")
    assert storage.object_exists("bronze", "raw/test.bin")
    health = storage.check_health()
    assert health.healthy
```

## Bucket initialisation

`ensure_bucket` is idempotent: it first probes with `head_bucket`, then creates
only if the probe returns 404/NoSuchBucket/403.  A 409
`BucketAlreadyOwnedByYou` is treated as success.  This matters because the
platform is at-least-once — services restart, replay, and the initialisation
path may run many times.

`ensure_all_buckets` creates every bucket declared in settings (bronze, silver).

## Delivery and failure behavior

- `StorageError`: object-storage operation failed.  The caller may retry.
- `BucketCreationError`: bucket initialisation failed after all retries.
- `KeyError`: `get_object` raises this when the object does not exist
  (`NoSuchKey` / 404).
- `check_health` returns a `HealthStatus` dataclass; it never raises.  A
  failing health check must not crash the service.
- `close()` releases the underlying `boto3` client.  Operations raise
  `StorageError` after close.  The context manager closes automatically.
- `close()` is idempotent.

Thread safety: a single internal lock serialises mutating operations (bucket
creation, put).  Read-only operations (get, exists, health) are safe to call
concurrently with each other.

Path-style addressing (`addressing_style: "path"`) is used for MinIO
compatibility.  boto3 retries up to 3 attempts with standard mode.

## Verification

```powershell
python -m pytest tests/test_minio_storage.py
python -m pytest tests/test_minio_storage_integration.py -m integration -v
./scripts/task_check.ps1
```

Unit tests cover settings validation, secrets redaction, bucket creation
(idempotent, error cases), put/get/exists (success, failure, edge cases),
health checks, lifecycle (context manager, post-close errors), and a smoke
round-trip.  The integration test starts an isolated Compose project with a
temporary host port and fixed credentials, exercises real put/get/exists/health
through the `MinIOStorage` client, and verifies overwrite semantics.  It skips
if Docker is unavailable.
