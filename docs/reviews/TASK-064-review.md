# TASK-064 Review — Product Endpoints

## 1. Review Header

- **Task ID:** TASK-064 — Product Endpoints
- **Review date:** 2026-09-19
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `cbf2d5b21f1c9b756677fb4b643e4a48f8013908...8349c1152b88ee77cb37c1906baccdfee634805a`
- **Reviewed HEAD:** `8349c1152b88ee77cb37c1906baccdfee634805a` on `feature/TASK-064`
- **Commits in range:** `8349c11 feat(TASK-064): product list/detail endpoints with repository layer` (single commit)
- **Scope:** `services/api/` (models, repository, routes, schemas, error handlers) and `tests/api/`
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

---

## 2. Requirements Coverage

Task objective: add read-only paginated product list/detail endpoints backed by repository/query layers, with stable typed responses, bounded pagination, justified filters, consistent 404/validation handling, and no N+1 queries.

| Requirement | Status | Evidence |
|---|---|---|
| Read-only paginated list endpoint (`GET /products`) | ✅ Met | `services/api/routes/v1/products.py::list_products`, `ProductRepository.list_products` |
| Read-only detail endpoint (`GET /products/{id}`) | ✅ Met | `services/api/routes/v1/products.py::get_product`, `ProductRepository.get_product` |
| Repository/query layer, thin handlers | ✅ Met | Query logic lives in `services/api/repositories/product.py`; handlers only map dataclass → response schema |
| Stable typed responses | ✅ Met | `ProductListResponse`, `ProductSummaryResponse`, `ProductDetailResponse` (Pydantic) in `schemas.py` |
| Bounded pagination | ✅ Met (with caveat) | `page` (`ge=1`), `page_size` (`ge=1`, `le=100`); caveat in Finding 1 |
| Justified filters | ✅ Met | `category` (exact match) and `source` (name) filters |
| Consistent 404 / validation handling | ✅ Met | `APIError` → `PRODUCT_NOT_FOUND`; `RequestValidationError` → `VALIDATION_ERROR` 422 |
| Avoid N+1 queries | ✅ Met | One aggregate list query + one count query; one detail query |
| No secrets / internal stack traces exposed | ✅ Met | Error handlers return structured JSON; unhandled handler hides internals |
| No new dependencies | ✅ Met | SQLAlchemy already present since TASK-063 |
| No unrelated changes | ✅ Met | Diff limited to `services/api/` and `tests/api/` |

Scope boundary is respected: history (`GET /products/{id}/history`) is TASK-065 and analytics is TASK-066; neither is implemented here. This matches the ROADMAP milestone 7 sequence.

---

## 3. Git Diff Review

- **Branch / isolation:** On `feature/TASK-064`; working tree clean; single commit `8349c11` in the reviewed range. No cross-task contamination. ✅
- **Files changed (9):**
  - `services/api/errors.py` — added `HTTPException` and `RequestValidationError` handlers (in-scope; needed for 404/422 responses).
  - `services/api/models.py` (new) — read-only SQLAlchemy ORM models for `sources`, `products`, `source_products`, `product_observations`.
  - `services/api/repositories/__init__.py` (new, empty).
  - `services/api/repositories/product.py` (new) — `ProductRepository` + frozen dataclasses.
  - `services/api/routes/v1/products.py` (new) — list/detail route handlers.
  - `services/api/routes/v1/router.py` — registers the products router.
  - `services/api/schemas.py` — adds three product response schemas.
  - `tests/api/conftest.py` — adds `Base.metadata.create_all(engine)` so the ORM tables exist in the SQLite test DB.
  - `tests/api/routes/v1/test_products.py` (new) — 13 tests.
- **Out-of-scope / unrelated changes:** None found.
- **Architectural changes:** None. The ORM models are documented read-only ("Write operations remain in the warehouse loader"), which preserves the warehouse-loader-owns-writes boundary from `PROJECT.md` §4 / `SPECIFICATION.md` §6.5.
- **Accidental / debug / secrets:** None found.
- **Schema fidelity:** The ORM models were checked against the current Alembic migrations (`warehouse/migrations/versions/001…006`), including `product_observations.event_id` (added in migration 002), `canonical_name`, and the `source_products` join table. Columns, types, nullability, FKs and `ondelete` behavior match. (Note: `warehouse/schema/init.sql` is stale relative to migrations 002–006 and should not be used as the schema authority.)

---

## 4. Test and Verification Review

### Tests examined
- `tests/api/routes/v1/test_products.py` — 13 tests covering: empty list, full list, pagination, category filter, source filter, invalid `page`, invalid `page_size`, latest-observation selection, validation-error shape, detail hit, 404, 404 shape, single-source product.
- Existing API suite (`tests/api/test_*.py`, `test_health.py`, `test_errors.py`, `test_schemas.py`, `test_config.py`, `test_database.py`, `test_app.py`) — 26 additional tests.

### Verification status

| Check | Result | Classification |
|---|---|---|
| `python -m pytest tests/api -v` | 39 passed | Independently verified |
| `python -m pytest tests/api/routes/v1/test_products.py -v` | 13 passed | Independently verified |
| `python -m ruff check .` | All checks passed | Independently verified |
| `python -m ruff format --check .` | 336 files already formatted | Independently verified |
| `python -m mypy` | Success (162 source files) | Independently verified |
| `python -m pytest -m integration` | Not run (Docker PostgreSQL required) | Unverified |

### Test adequacy notes
- Tests use an in-memory **SQLite** database (via `Base.metadata.create_all`), not PostgreSQL. The SQL is standard SQLAlchemy and should port, but SQLite's `TIMESTAMP(timezone=True)` and `NUMERIC` handling differ from PostgreSQL, and no integration-marked test exercises these endpoints against the real warehouse. This is a coverage gap, not a defect.
- Tests derive the schema from the ORM models themselves, so they would not catch model-vs-migration drift (the drift was checked manually during this review and none was found).
- No test covers the `collected_at` timestamp-tie case (see Finding 1), nor the `page_size=100` upper-bound acceptance.
- `_decimal_to_float` / `pytest.approx` tolerate float imprecision, consistent with the float-typed price (Finding 2).

---

## 5. Findings

### Finding 1 — Moderate: list query returns duplicate rows when a product has multiple observations sharing the latest `collected_at`

- **File / line:** `services/api/repositories/product.py` — `ProductRepository.list_products` (`latest_obs_subq` + `ProductObservation` join, lines ~92–118).
- **Problem:** The "latest observation" is resolved by joining on `ProductObservation.collected_at == max(collected_at)`. When two listings of the same canonical product (or two observations of one listing) share the identical maximum `collected_at`, the join matches both rows and the list emits the same product twice. The pagination `total` counts distinct products, so `total` then disagrees with the number of emitted rows.
- **Impact:** Duplicate product entries and inconsistent `total`/`items` under timestamp ties; pagination is no longer deterministic or correct. Independently reproduced against SQLite: `total=1` but `items=2`, both with `id=1`.
- **Recommendation:** Resolve the latest observation with a deterministic tie-breaker, e.g. `DISTINCT ON (product_id) … ORDER BY collected_at DESC` (PostgreSQL) or `ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY collected_at DESC, <tiebreaker>) = 1`. The `get_product` query has the same tie ambiguity but masks it with `.limit(1)` + `ORDER BY collected_at DESC`, which makes the picked row non-deterministic on a tie.

### Finding 2 — Minor: monetary values returned as binary `float`

- **File / line:** `services/api/routes/v1/products.py` (`_decimal_to_float`), `services/api/schemas.py` (`latest_price: Optional[float]`).
- **Problem:** Prices are stored as `NUMERIC(12,2)` (exact) but converted to `float` at the API boundary, losing exactness and scale (e.g. `10.99` → binary float). `SPECIFICATION.md` §13 and `PROJECT.md` emphasize exact numeric money.
- **Impact:** Potential display/precision artifacts and lost scale for downstream JSON consumers.
- **Recommendation:** Return `Decimal` (Pydantic serializes it as a string/number) or a formatted string; avoid float for money.

### Finding 3 — Minor: `ProductListResponse` re-declares fields already in `PaginatedResponse`

- **File / line:** `services/api/schemas.py` (`PaginatedResponse` vs `ProductListResponse`).
- **Problem:** `items`, `total`, `page`, `page_size` are duplicated instead of reusing/parameterizing the existing `PaginatedResponse` base.
- **Impact:** Schema drift risk across future paginated endpoints (TASK-065/066/067/068).
- **Recommendation:** Make `PaginatedResponse` generic over the item type (e.g. `PaginatedResponse[T]`) and reuse it.

### Finding 4 — Minor: representation conversion split between repository and route layer

- **File / line:** `services/api/repositories/product.py` (dataclasses carry `latest_collected_at: Optional[str]` via `.isoformat()`) and `services/api/routes/v1/products.py` (`_decimal_to_float`).
- **Problem:** The repository converts `datetime → str` while the route converts `Decimal → float`. This mixes serialization concerns across layers and makes the repository's dataclass timestamps stringly-typed.
- **Impact:** Reduced type fidelity and harder reuse of the repository.
- **Recommendation:** Keep `datetime`/`Decimal` in the dataclasses and let Pydantic serialize at the boundary (or centralize all conversion in the response-mapping helpers).

---

## 6. Non-Defect Observations

- **Schema mapping is correct** against the actual Alembic migration chain (001–006), including `event_id` (added in 002). The stale `warehouse/schema/init.sql` predates migrations 002–006 and should not be treated as the current schema.
- **`source` filter semantics:** filtering by `source` restricts *which products* are listed, but the displayed "latest" observation is still the latest across *all* sources of the product. This is defensible and codified by `test_list_filter_by_source`, but may surprise clients expecting the latest from the filtered source only. Worth confirming intent before TASK-065/066 build on it.
- **Validation-error handler** echoes `exc.errors()`, which includes the client's own `input` value. Independently checked that non-integer `product_id` (`/products/abc`) and `page=abc` return clean 422 JSON without a serialization crash and without leaking secrets/stack traces. No change required.
- **`errors.py`** gains `HTTPException`/`RequestValidationError` handlers with an `HTTP_<status>` code scheme; minor inconsistency with the existing `APIError` code style (`SERVICE_UNAVAILABLE`, etc.), but not a defect.
- The ORM models are explicitly read-only; no write path is introduced in the API, preserving the warehouse-loader boundary.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The implementation satisfies TASK-064's requirements: typed, read-only, paginated product list/detail endpoints behind a proper repository layer, with bounded pagination, justified filters, consistent 404/422 handling, no N+1 queries, and no secrets or stack-trace leakage. Unit tests (39), `ruff check`, `ruff format --check`, and `mypy` all pass and were independently executed. The diff is clean, isolated to the task, and the ORM correctly maps the migrated warehouse schema.

No blocking defect was found. Finding 1 is a genuine correctness gap in pagination/latest-observation under `collected_at` timestamp ties and should be fixed in a follow-up; Findings 2–4 are minor quality/consistency improvements. PostgreSQL integration verification for these endpoints was not evidenced and remains unverified (requires Docker).
