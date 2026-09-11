# TASK-020 Review — MinIO Integration

| Field | Value |
| --- | --- |
| Task | TASK-020 |
| Review date | 2026-09-11 |
| Change set | `33da909...b63643d` (`main...feature/TASK-020`) |
| Scope | MinIO / S3-compatible object-storage client for the data lake |
| Verdict | **APPROVED WITH NON-BLOCKING FINDINGS** |

---

## 1. Requirements Coverage

| Requirement | Status | Evidence |
| --- | --- | --- |
| Configure MinIO in the local stack | Met | MinIO already present in `docker-compose.yml`; application-side config via `MinIOSettings` (`libs/common/minio_storage.py:41-72`) with `APP_MINIO_*` env vars |
| Typed endpoint/credential/bucket configuration | Met | `MinIOSettings(AppSettings)` with `SecretStr` credentials, `Field` constraints, `field_validator` for endpoint URL and bucket names |
| Reusable S3-compatible client | Met | `MinIOStorage` class (`libs/common/minio_storage.py:89-230`) with `put_object`, `get_object`, `object_exists`, context manager support |
| Idempotent bucket initialization | Met | `ensure_bucket` probes with `head_bucket` first, creates only on 404/NoSuchBucket/403, treats `BucketAlreadyOwnedByYou`/`BucketAlreadyExists` as success (`minio_storage.py:124-153`) |
| Health/readiness coverage | Met | `check_health()` returns `HealthStatus` dataclass, never raises (`minio_storage.py:196-207`) |
| Object put/get smoke test | Met | `TestSmokeRoundTrip` unit test; integration test `test_put_get_round_trip` |
| Do not implement Parquet writing | Met | No Parquet code in the diff; module docstring explicitly states Parquet is out of scope |
| At-least-once / idempotent semantics | Met | Bucket creation is idempotent; no exactly-once claims |
| No secrets in source control | Met | Credentials use `SecretStr`; `.env.example` has only placeholder comments; integration test uses fixed local-only credentials |
| Tests: success, failure, edge cases | Met | 40 unit tests + 6 integration tests covering all categories |
| Run pytest, Ruff, mypy | Met | All pass for TASK-020 files (pre-existing failures in unrelated processor/polars tests confirmed on main) |

---

## 2. Git Diff Review

**Scope correctness:** All 9 changed files belong to TASK-020.

| File | Change | In scope |
| --- | --- | --- |
| `.env.example` | Added `APP_MINIO_*` commented variables | Yes |
| `docs/configuration.md` | Added MinIO reference line | Yes |
| `docs/minio-storage.md` | New documentation (90 lines) | Yes |
| `libs/common/__init__.py` | Added MinIO exports | Yes |
| `libs/common/minio_storage.py` | New implementation (230 lines) | Yes |
| `pyproject.toml` | Added mypy override for boto3/botocore | Yes |
| `requirements.txt` | Added `boto3>=1.35,<2` | Yes |
| `tests/test_minio_storage.py` | New unit tests (612 lines) | Yes |
| `tests/test_minio_storage_integration.py` | New integration tests (172 lines) | Yes |

**Unrelated changes:** None detected.

**Architectural changes:** No existing boundaries altered. New module added to `libs/common/` following the established pattern (`kafka_producer.py`).

**Accidental changes:** None — no debug code, temporary files, dead code, or secrets.

**Dependency changes:** `boto3>=1.35,<2` added — appropriate for S3-compatible access to both MinIO (local) and AWS S3 (production). mypy override for untyped `boto3.*`/`botocore.*` is standard practice.

---

## 3. Implementation Review

### Configuration (`MinIOSettings`)

Correctly subclasses `AppSettings`, inheriting `APP_` prefix mapping, `.env` loading, environment precedence, frozen settings, and unknown-variable rejection. Credentials use `SecretStr` — `repr`/`str` redact values. Validators enforce endpoint URL format and DNS-compliant bucket names. Timeout fields use `Field(ge=..., le=...)` for range constraints. The `bucket_names` property provides a clean list for iteration.

### Storage client (`MinIOStorage`)

The class is intentionally small and focused — bucket init, put, get, exists, health, close. Key design decisions:

- **boto3 over minio SDK:** Correct choice — same client works for MinIO and AWS S3; only the endpoint URL changes.
- **Path-style addressing:** Required for MinIO compatibility. Verified in test `test_client_uses_path_style_addressing`.
- **Retries:** `BotoConfig(retries={"max_attempts": 3, "mode": "standard"})` — reasonable default.
- **Thread safety:** `Lock` serializes mutating operations (bucket creation, put). Read-only operations (get, exists, health) are safe to call concurrently.
- **Lifecycle:** Context manager support; `close()` is idempotent; operations raise `StorageError` after close.

### Error handling

Clean exception hierarchy:
- `StorageError` — operation failed, caller may retry
- `BucketCreationError` — bucket init failed
- `KeyError` — object not found (standard Python semantics)

All exceptions chain with `from exc` for traceability. Error messages include bucket/key context but not credentials.

### Health check

`check_health()` uses `list_buckets()` as a lightweight probe. Returns `HealthStatus` dataclass — never raises. The caller decides recovery strategy. Correct design for readiness/liveness probes.

### Security

- Credentials stored as `SecretStr` — verified by `test_secret_repr_is_redacted`
- No hardcoded credentials in source
- `.env.example` contains only comments
- Integration test uses fixed local-only credentials (`it-admin`/`it-admin-secret`)
- Error messages do not echo secrets

---

## 4. Test and Verification Review

### Unit tests (`tests/test_minio_storage.py`)

40 tests covering:

| Category | Tests | Assessment |
| --- | --- | --- |
| Settings validation | 10 | Defaults, custom values, secrets, frozen, validators, bucket names |
| Bucket creation | 9 | Missing, exists, idempotent (owned/exists), unexpected probe error, creation failure, network error |
| Put object | 4 | Bytes, stream, client error, network error |
| Get object | 4 | Success, missing (KeyError), other client error, network error |
| Object exists | 4 | True, false (404), false (NoSuchBucket), unexpected error |
| Health check | 3 | Healthy, unhealthy (client error), unhealthy (network error) |
| Lifecycle | 5 | Context manager, post-close errors, idempotent close, path-style addressing, configured endpoint |
| Smoke round-trip | 1 | Put then get returns same bytes |

Tests mock `boto3` — no Docker or network required. Environment isolation via `autouse` fixture that clears `APP_` vars and uses a temp directory. Well-structured with helper functions (`_make_settings`, `_client_error`, `_apply_env`).

### Integration tests (`tests/test_minio_storage_integration.py`)

6 tests against a real MinIO container:

| Test | What it verifies |
| --- | --- |
| `test_health_check_passes` | Real connectivity and authentication |
| `test_ensure_bucket_is_idempotent` | Multiple calls don't fail |
| `test_put_get_round_trip` | End-to-end put, exists, get |
| `test_get_missing_object_raises_key_error` | KeyError for missing objects |
| `test_object_exists_returns_false_for_missing` | False for non-existent objects |
| `test_overwrite_replaces_content` | Overwrite semantics |

Uses the established pattern from `test_docker_compose.py`: alternate host ports (19000/19001), fixed test credentials, module-scoped stack fixture, Docker availability check with skip.

### Verification

- **Implementation evidence reviewed:** ruff format, ruff check, mypy, pytest (40/40 unit tests pass) confirmed by implementation agent. Pre-existing failures in unrelated processor/polars tests confirmed on main branch.
- **Unverified:** Integration tests not independently executed (require Docker daemon). Test structure and patterns reviewed and found correct.

### Test adequacy

Tests are comprehensive for the scope. They cover success, failure, edge cases, and idempotency/replay behavior as required. The mock-based unit tests are fast and deterministic. Integration tests provide real end-to-end coverage.

---

## 5. Findings

### Finding 1 — `minio_secure` field is not wired to the client

- **Severity:** Minor
- **File:** `libs/common/minio_storage.py:52, 106-117`
- **Problem:** `minio_secure: bool = False` is declared as a settings field but never passed to `boto3.client()`. The `use_ssl` parameter is not set. Security is instead determined by the endpoint URL scheme (`http://` vs `https://`), which the endpoint validator already enforces.
- **Impact:** Low. The field is currently decorative — setting `APP_MINIO_SECURE=true` with an `http://` endpoint has no effect. The endpoint URL validator prevents mismatched schemes in practice.
- **Recommendation:** Either (a) remove `minio_secure` and rely on the endpoint URL scheme, or (b) pass `use_ssl=settings.minio_secure` to `boto3.client()` and add a cross-validator that rejects `http://` endpoints when `minio_secure=True`. Not a blocker for this task.

### Finding 2 — Integration test fixture typing is awkward

- **Severity:** Minor
- **File:** `tests/test_minio_storage_integration.py:100-121`
- **Problem:** The `storage` fixture returns `Iterator` (untyped) and each test uses `storage: object` with a `type: ignore[assignment]` comment and a local import + cast. This works but is verbose.
- **Impact:** Low. Tests are correct and type-check passes. The pattern is just more verbose than necessary.
- **Recommendation:** Type the fixture return as `MinIOStorage` directly and import the type at module level. Not a blocker.

---

## 6. Non-Defect Observations

1. **boto3 version pin:** `boto3>=1.35,<2` is appropriate. boto3 is stable and the major version pin prevents breaking changes.

2. **Logging design:** Structured logging with `extra={}` dicts for endpoint, region, bucket, key. Log levels are appropriate: `info` for lifecycle events, `debug` for existence checks. No credentials logged.

3. **Documentation quality:** `docs/minio-storage.md` follows the established pattern from `kafka-producer.md`. Configuration table, usage example, bucket initialization docs, failure behavior, verification commands. Well-written and complete.

4. **`_closed` flag thread safety:** The `_closed` boolean is read outside the lock in `_assert_open()`. This is safe in CPython due to the GIL making boolean assignment atomic, and the lock in `close()` provides a memory barrier. Acceptable for this platform.

5. **`ensure_all_buckets` locking:** Each `ensure_bucket` call acquires/releases the lock independently. This means bucket creation is not atomic across buckets, but this is fine — each bucket is independently idempotent, and partial failure leaves a consistent state.

6. **Future extensibility:** The `MinIOStorage` class is small by design. Later tasks (TASK-021+) will add Parquet writing on top of this boundary. The current API (put/get/exists) provides the foundation those tasks need.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The implementation correctly satisfies all TASK-020 requirements: typed configuration, reusable S3-compatible client, idempotent bucket initialization, health checks, and comprehensive tests. The scope is well-maintained — no Parquet writing, no out-of-scope changes. The code follows established project patterns, handles errors appropriately, and maintains security invariants. The two minor findings (`minio_secure` wiring and integration test typing) do not block acceptance.
