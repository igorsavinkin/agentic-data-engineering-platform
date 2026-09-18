# TASK-063 Review — FastAPI Foundation

**Reviewer:** Qwen Code (independent review, no code modified)
**Date:** 2026-09-19
**Branch:** feature/TASK-063
**Reviewed HEAD:** ad63701e32ce9ef745252ad0d114141cb9f8dbd1
**Git range:** c8ad070b9fe522e41a4ef84baa431669d123b999..ad63701e32ce9ef745252ad0d114141cb9f8dbd1
**Commits reviewed:** 4436667 (feat), ad63701 (fix)
**Scope:** `services/api/` FastAPI foundation, `tests/api/`, `requirements.txt`
**Verdict:** APPROVED WITH NON-BLOCKING FINDINGS

---

## 1. Requirements Coverage

Primary source: `ai/tasks/TASK-063-fastapi-foundation.md`. Supporting: `ai/SPECIFICATION.md` §16 (FastAPI), §6.6; `ai/PROJECT.md` §4 (FastAPI), §6, §9, §10; `ai/ROADMAP.md` Milestone 7.

| Requirement | Status | Evidence |
|---|---|---|
| Create `services/api/` package | ✅ Met | `services/api/` with `__init__.py`, `__main__.py`, `app.py`, `config.py`, `database.py`, `dependencies.py`, `errors.py`, `schemas.py`, `routes/` |
| Application factory | ✅ Met | `create_app()` in `services/api/app.py` builds the app, wires config, DB dependency, exception handlers, and router |
| Lifespan | ❌ **Missing** | `create_app()` defines no `lifespan` context manager; the SQLAlchemy engine/connection pool is never disposed on shutdown. Commit message claims "with lifespan" but none exists. See Finding M1 |
| Typed config | ✅ Met | Frozen dataclasses `DatabaseSettings` and `APISettings` with `from_env()` |
| DB dependency / session lifecycle | ✅ Met | `get_db` dependency overridden in `create_app`; session closed in `finally`; `expire_on_commit=False` |
| Health / readiness | ✅ Met | `GET /api/v1/health` (liveness) and `GET /api/v1/ready` (readiness, 503 on DB failure) |
| Versioned API prefix | ✅ Met | Router mounted at `/api/v1` |
| Pydantic response conventions | ✅ Met | `schemas.py` provides `HealthStatus`, `ReadinessStatus`, `ErrorResponse`, `PaginatedResponse` |
| Structured errors | ⚠️ Partial | `APIError` + generic `Exception` handlers return `{"error": {...}}`; FastAPI built-in `HTTPException`/`RequestValidationError` are not wrapped. See Finding M2 |
| OpenAPI | ✅ Met | `openapi_url="/api/openapi.json"`, `docs_url="/api/docs"`; tested |
| Keep DB/query logic out of routes | ✅ Met | Only minimal `SELECT 1` connectivity probe in readiness (appropriate); no business query logic |
| Bound queries and pagination | ⚠️ N/A / partial | `PaginatedResponse` envelope exists with bounds (`page >= 1`, `1 <= page_size <= 100`); no query routes yet |
| Never expose secrets / internal stack traces | ✅ Met | `test_unhandled_error_hides_internals` confirms `INTERNAL_ERROR` body omits exception text |
| No unrelated changes | ✅ Met | See Git Diff Review |

Definition of Done: deterministic tests present and passing (26 unit tests), API schemas typed, ruff/format pass, no unrelated changes, no secrets. Type checking is only partially satisfied (see Finding M2's sibling, Finding M3). Documentation is only partially updated (OpenAPI is auto-generated; README/`.env.example` not updated — Finding m2).

---

## 2. Git Diff Review

Net change: **23 files, +707 insertions** (no deletions), across two commits:

- `4436667` — main implementation (+720)
- `ad63701` — fixes from a prior review pass (−32/+19)

Scope correctness: All changes belong to TASK-063 (new `services/api/` package, its tests, and runtime dependency additions).

Dependency/configuration changes:
- `requirements.txt` gains `fastapi>=0.115,<1`, `uvicorn>=0.32,<1`, `sqlalchemy>=2.0`. SQLAlchemy was previously an undeclared transitive dependency of other modules (`libs/quality`, `warehouse/loader`, etc.); adding it here is a legitimate fix (M1 from prior review). Note: `sqlalchemy>=2.0` has no upper bound while `fastapi`/`uvicorn` do — minor inconsistency, non-blocking.

Unrelated changes: none. `services/api/README.md` pre-existed (tracked since initial commit) and was not touched.

Architectural changes: none. The implementation respects the FastAPI-as-serving-layer boundary (`ai/PROJECT.md` §4) and does not introduce Kafka, MinIO, or pipeline coupling.

Accidental changes: none — no debug code, dead code, temporary files, generated artifacts, or secrets committed.

The `ad63701` fix commit is well-scoped and correct: the C1 fix (plain generator instead of `@contextmanager` for the dependency override) is necessary — FastAPI cannot consume a `_GeneratorContextManager`; the M2 fix makes the readiness failure test assert 503 rather than 500.

---

## 3. Test and Verification Review

Tests examined (`tests/api/`): `test_config.py` (9), `test_database.py` (2), `test_errors.py` (3), `test_schemas.py` (5), `test_health.py` (4), `test_app.py` (3) = **26 tests**.

Adequacy:
- Config: covers defaults, `from_env` (with/without password), frozen immutability, debug parsing.
- Database: engine creation + session factory on SQLite.
- Errors: structured `APIError` response, generic-error internal-hiding, and detail-omission when empty.
- Health/readiness: 200 liveness, readiness connected (200) and DB-failure (503) paths.
- App: OpenAPI availability, docs UI, and route registration.
- Good coverage of the foundation's acceptance behavior. The readiness "DB down" path is exercised via a mock session rather than a real unreachable engine, which is reasonable and hermetic.

Independently executed (by reviewer):

| Command | Result |
|---|---|
| `python -m pytest tests/api -q` | **26 passed** |
| `python -m ruff check services/api tests/api` | **All checks passed** |
| `python -m ruff format --check services/api tests/api` | **23 files already formatted** |
| `python -m mypy` (configured default) | Success — 161 files (but excludes `services/`, see Finding M3) |
| `python -m mypy services/api` | **Error** — module-name conflict (namespace package) |
| `python -m mypy --explicit-package-bases services/api` | Success — 12 files, no issues |

Verification status: **Independently verified** for unit tests and lint/format. Type checking is the exception — the new code is type-clean when checked directly, but the configured `mypy` invocation does not check it (Finding M3).

No integration tests are required for this task (no Kafka/persistence boundary touched), so `-m integration` deselection is not a gap here.

---

## 4. Findings

### M1 — Missing `lifespan` / engine disposal (Moderate)
- **File:** `services/api/app.py`
- **Problem:** The task objective explicitly names "lifespan" as a deliverable, and the commit message claims "Application factory … with lifespan". `create_app()` defines no `lifespan` context manager, so the SQLAlchemy `Engine` (and its connection pool) is never disposed on graceful shutdown.
- **Impact:** Requirements-coverage gap; resource-hygiene issue for a long-running service. Functionally the health/readiness endpoints work, but the named deliverable is absent and the commit message overstates what was implemented.
- **Recommendation:** Add a FastAPI `lifespan` that disposes the engine on shutdown (and optionally performs startup checks). Update the commit history/claim accordingly.

### M2 — Structured error convention does not cover FastAPI built-in errors (Moderate)
- **File:** `services/api/errors.py`
- **Problem:** `register_exception_handlers` only registers `APIError` and a generic `Exception` handler. FastAPI/Starlette's built-in `HTTPException` (404 route-not-found, 405, etc.) and `RequestValidationError` (422) are handled by the framework's default handlers and return `{"detail": ...}`, not the documented `{"error": {...}}` shape. The module docstring states "All error responses follow a consistent JSON shape", which is not true.
- **Impact:** Inconsistent client error contract. Not triggered by TASK-063's endpoints (no request parameters yet), but will surface immediately with TASK-064+ product/pagination endpoints.
- **Recommendation:** Add handlers for `HTTPException` and `RequestValidationError` that emit the same envelope (or document the deliberate split).

### M3 — Type checking does not cover `services/api` (Moderate)
- **File:** `pyproject.toml` (`[tool.mypy] files = ["scripts", "tests", "libs"]`); `services/` (namespace package)
- **Problem:** The configured `mypy` invocation excludes `services/`, so the standard "type checks pass" step silently skips the new FastAPI code. Worse, `services/` has no `__init__.py` (namespace package), so `mypy services/api` fails with "Source file found twice under different module names: api.dependencies and services.api.dependencies". The code itself is type-clean — `mypy --explicit-package-bases services/api` reports no issues.
- **Impact:** The "typed" quality gate is not actually enforced for this deliverable, and the package layout breaks mypy's default module resolution for any future attempt to check it.
- **Recommendation:** Add `services` (and the other `services/*` packages) to mypy `files`, and either add `services/__init__.py` or set `explicit_package_bases = true` so the new service is actually type-checked.

### m1 — Structured logging convention not followed (Minor)
- **File:** `services/api/routes/v1/health.py`, `services/api/errors.py`
- **Problem:** Project convention (`ai/AGENTS.md` §6/§9; `services/ingestion`) uses message-as-event-name with structured `extra={...}` fields. The API service logs plain strings (`logger.warning("Readiness check failed: database unreachable")`, `logger.exception("Unhandled exception: %s", exc)`) without structured `extra`, and the readiness warning drops the underlying exception (no `exc_info`/error field).
- **Impact:** Reduced diagnosability of readiness failures; inconsistent observability with the rest of the platform.
- **Recommendation:** Log structured fields (`extra={"operation": "readiness", "error": str(exc)}`) and include `exc_info`/`extra` in the readiness failure path.

### m2 — Documentation/`.env.example` not updated (Minor)
- **File:** `services/api/README.md`, `.env.example`
- **Problem:** The pre-existing stub `services/api/README.md` was not updated to document the new endpoints, run command, or config variables. `.env.example` does not mention `APP_API_HOST`/`APP_API_PORT`/`APP_DEBUG` (or the API's use of `WAREHOUSE_DB_*`). The task's Definition of Done asks for documentation updated "where appropriate".
- **Impact:** Operators cannot discover the new service's configuration surface from the standard places.
- **Recommendation:** Document the service in `services/api/README.md` and add the `APP_API_*` variables to `.env.example`.

---

## 5. Non-Defect Observations

- **Config convention fidelity** — `DatabaseSettings.from_env()` correctly reuses the `WAREHOUSE_DB_*` convention (matching `libs/quality/persistence.py`, `libs/metrics/persistence.py`, `warehouse/migrations/env.py`) and improves on it by omitting the password from the URL when empty.
- **Correct dependency-override fix** — the C1 change (plain generator, not `@contextmanager`) is the right pattern for FastAPI `dependency_overrides`; the guard `get_db` raising `RuntimeError` when unconfigured is a reasonable fail-fast.
- **Internal-hiding is real and tested** — `test_unhandled_error_hides_internals` verifies the generic handler does not leak exception text.
- **Readiness semantics** — 503 `SERVICE_UNAVAILABLE` for DB-down (not 500) is correct and now properly asserted.
- **Pagination envelope typing** — `PaginatedResponse.items: list[Any]` is loose (`Any`), weakening the "typed response conventions" claim; acceptable for a foundation but the concrete item type should be parameterized once TASK-064 introduces product endpoints.
- **Minor test-fixture redundancy** — `tests/api/conftest.py` `_override` uses `try/finally: pass` (dead), and `create_app(db_settings=DatabaseSettings(url="sqlite://"))` creates an unused engine that the override bypasses.
- **`SELECT 1` in readiness route** — a minimal connectivity probe is appropriate; the "keep query logic out of routes" rule should be enforced for business queries in TASK-064+, not for this probe.
- **Version string duplication** — `0.1.0` is hardcoded in both `app.py` and `health.py` (`_API_VERSION`); a single source (config or a version constant) would reduce drift.

---

## 6. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The foundation is functionally correct, well-scoped, and well-tested (26 passing unit tests, ruff clean, no secrets, no out-of-scope changes). The three Moderate findings — missing `lifespan`/engine disposal, structured errors not covering FastAPI built-in errors, and the configured type-check excluding `services/` — are non-blocking for this foundation but should be addressed before TASK-064+ builds product endpoints on top of it. No Critical or High findings.
