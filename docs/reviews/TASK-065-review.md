# TASK-065 Review — Product History

## 1. Review Header

- **Task ID:** TASK-065 — Product History
- **Review date:** 2026-09-19
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `3f87d5c9cf0616eabc413eb1242064a31bca2e31...5e972b47b8c5513c99418b60ef7e4a787730a29a`
- **Reviewed HEAD:** `5e972b47b8c5513c99418b60ef7e4a787730a29a` on `feature/TASK-065`
- **Commits in range:** `5e972b4 feat(TASK-065): product history endpoint with date filtering and pagination` (single commit)
- **Scope:** `services/api/` (repository, routes, schemas) and `tests/api/`
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

---

## 2. Requirements Coverage

Task objective: expose bounded historical product observations with deterministic ordering, timestamps, price/currency, availability, and source/listing traceability; support date filtering/pagination; do not implement analytics here.

| Requirement | Status | Evidence |
|---|---|---|
| Historical observation endpoint | ✅ Met | `GET /products/{product_id}/observations` in `services/api/routes/v1/products.py::list_observations` |
| Deterministic ordering | ✅ Met | `order_by(collected_at DESC, id DESC)` — `id` is a unique primary key, providing a deterministic tie-breaker |
| Timestamps | ✅ Met | `collected_at` returned as ISO-8601 string via `.isoformat()` |
| Price / currency | ✅ Met | `price` (`Decimal` → `float`), `currency` exposed |
| Availability | ✅ Met | `availability` exposed |
| Source / listing traceability | ✅ Met | `source` (via `Source.name`) and `url` (via `SourceProduct.url`) |
| Date filtering | ✅ Met | `from_date` / `to_date` query params applied as `collected_at >=` / `<=` |
| Pagination (bounded) | ✅ Met | `page` (`ge=1`), `page_size` (`ge=1`, `le=100`) |
| No analytics implemented | ✅ Met | No aggregation/analytics logic; purely a filtered history listing |
| Typed FastAPI/Pydantic | ✅ Met | `ObservationResponse`, `ObservationListResponse` (Pydantic) |
| Thin handler, query in repository layer | ✅ Met | Query logic in `ProductRepository.list_observations`; handler maps dataclass → response schema |
| No secrets / internal stack traces | ✅ Met | Reuses existing structured error handlers |
| No unrelated changes | ✅ Met | Diff limited to product repository/routes/schemas + product tests |

---

## 3. Git Diff Review

- **Branch / isolation:** On `feature/TASK-065`; working tree clean; single commit `5e972b4` in the reviewed range. No cross-task contamination. ✅
- **Files changed (4):**
  - `services/api/repositories/product.py` — adds `ObservationSummary`/`ObservationListResult` dataclasses and `ProductRepository.list_observations`.
  - `services/api/routes/v1/products.py` — adds `GET /{product_id}/observations` handler; updates module docstring.
  - `services/api/schemas.py` — adds `ObservationResponse` and `ObservationListResponse`.
  - `tests/api/routes/v1/test_products.py` — adds `TestProductObservations` (9 tests).
- **Out-of-scope / unrelated changes:** None found.
- **Architectural changes:** None. The API remains read-only; the warehouse-loader-owns-writes boundary is preserved.
- **Accidental / debug / secrets:** None found.
- **New dependencies:** None. `datetime` and existing `func`/`select` are the only new imports, both already available.

---

## 4. Test and Verification Review

### Tests examined
- `tests/api/routes/v1/test_products.py::TestProductObservations` — 9 new tests: full list + ordering, source traceability, pagination, `from_date`, `to_date`, date range, 404, invalid `page`, single-source product.
- Pre-existing product list/detail tests (13) remain intact and unweakened.

### Verification status

| Check | Result | Classification |
|---|---|---|
| `python -m pytest tests/api/routes/v1/test_products.py -v` | 22 passed | Independently verified |
| `python -m pytest tests/api -q` | 48 passed | Independently verified |
| `python -m ruff check .` | All checks passed | Independently verified |
| `python -m ruff format --check .` | 336 files already formatted | Independently verified |
| `python -m mypy` | Success: 162 source files | Independently verified (see Finding 5) |
| `python -m mypy services/api` | Fails with module-name collision (config issue) | Independently verified (see Finding 5) |
| `python -m pytest -m integration` | Not run (Docker PostgreSQL required) | Unverified |

### Test adequacy notes
- Tests use in-memory **SQLite** via `Base.metadata.create_all`, not PostgreSQL. The date filtering, `TIMESTAMP(timezone=True)`, and `NUMERIC` behavior differ from PostgreSQL, and no integration-marked test exercises this endpoint against the real warehouse. CI's only integration step is `tests/warehouse/test_migrations.py -m integration`; it does **not** run API endpoints against PostgreSQL. Coverage gap, not a defect.
- Date-filter tests pass naive-free UTC strings with a `Z` suffix; no test covers naive (offset-less) `from_date`/`to_date` inputs or `from_date > to_date`.
- The date-filter assertion `item["collected_at"] >= "2025-06-10"` is a string comparison; it works for ISO-8601 UTC but is a weak assertion (timezone-offset differences would still pass).

---

## 5. Findings

### Finding 1 — Moderate: product that exists but has zero observations returns 404 instead of an empty history

- **File / line:** `services/api/routes/v1/products.py` — `list_observations` existence check (`if repo.get_product(product_id) is None`, lines ~77–83); root cause in `services/api/repositories/product.py::get_product` (inner joins on `SourceProduct`, `latest_obs_subq`, and `ProductObservation`).
- **Problem:** `get_product` uses inner joins that require at least one observation, so it returns `None` for a product that has a `products` row (and even a `source_products` row) but no observations. Reusing it as the existence check for the history endpoint conflates "product not found" with "product exists but has empty history".
- **Impact:** `GET /products/{id}/observations` returns `404 PRODUCT_NOT_FOUND` for an existing product with no observations, instead of `200` with `total=0` and `items=[]`. Independently reproduced against SQLite: a product with a `source_products` row but no observations yields `404 {"error":{"code":"PRODUCT_NOT_FOUND", ...}}`. This is also an inefficient existence check (full aggregate/join query) compared to a lightweight `SELECT id FROM products WHERE id = …`.
- **Recommendation:** Replace the `get_product` existence check with a direct product existence query (e.g. `select(Product.id).where(Product.id == product_id)`), and return an empty `ObservationListResponse` when no observations match.

### Finding 2 — Moderate: endpoint path diverges from the specification

- **File / line:** `services/api/routes/v1/products.py` — `@router.get("/{product_id}/observations")` vs `ai/SPECIFICATION.md` §16, which lists `GET /products/{id}/history`.
- **Problem:** The authoritative specification names the history endpoint `/products/{id}/history`; the implementation exposes it as `/products/{product_id}/observations`. Per `ai/REVIEWER.md` precedence (`SPECIFICATION.md` > `TASK-xxx.md`), the spec's path is normative unless an ADR/spec change supersedes it. The TASK-064 review likewise expected the history endpoint at `/history`.
- **Impact:** A downstream consumer (or the LangGraph agent) following the specification would call `/history` and receive 404/422. Interface contract inconsistency.
- **Recommendation:** Either rename the route to `/{product_id}/history` (updating tests and OpenAPI), or explicitly update `SPECIFICATION.md` if `/observations` is the intended contract. Confirm the intended path with the owner before it is relied upon by TASK-066+.

### Finding 3 — Minor: date-filter parameters accept naive datetimes with no normalization or range validation

- **File / line:** `services/api/routes/v1/products.py` — `from_date`/`to_date` `Query` params (lines ~74–82); `services/api/repositories/product.py::list_observations` comparisons.
- **Problem:** FastAPI parses offset-less ISO strings (e.g. `2025-06-10T00:00:00`) into naive `datetime` objects; these are compared directly against the timezone-aware `collected_at` (`TIMESTAMP(timezone=True)`). The comparison is only tested with `Z`-suffixed UTC inputs. There is also no validation that `from_date <= to_date`.
- **Impact:** On PostgreSQL, comparing a naive bound value against `timestamptz` may interpret the value in the session timezone and shift results by the offset; `from_date > to_date` silently returns an empty result. Timezone ambiguity is a real risk for a date-filtering contract.
- **Recommendation:** Normalize naive inputs to UTC (or reject them with 422) and/or validate `from_date <= to_date`. Add a test for a naive input and for `from_date > to_date`.

### Finding 4 — Minor: `ObservationListResponse` re-declares fields already in `PaginatedResponse`

- **File / line:** `services/api/schemas.py` — `PaginatedResponse` vs `ObservationListResponse`.
- **Problem:** `items`, `total`, `page`, `page_size` are duplicated instead of reusing/parameterizing the existing `PaginatedResponse` base. This is the same issue raised as TASK-064 Finding 3 and is now recurring.
- **Impact:** Schema drift risk across the growing set of paginated endpoints (TASK-066/067/068).
- **Recommendation:** Make `PaginatedResponse` generic over the item type (e.g. `PaginatedResponse[T]`) and reuse it.

### Finding 5 — Moderate: `mypy` configuration does not type-check the reviewed code

- **File / line:** `pyproject.toml` — `[tool.mypy] files = ["scripts", "tests", "libs"]`.
- **Problem:** The CI command `mypy` (and `ai/AGENTS.md` §7's `mypy src/`, which targets a non-existent `src/`) do not include `services/`. `python -m mypy` reports "Success … in 162 source files" while the reviewed production code in `services/api/` is excluded. Running `python -m mypy services/api` independently fails on a module-name collision ("api.models" vs "services.api.models"), confirming the `services/` tree is not cleanly type-checkable under the current config.
- **Impact:** The "type checks pass" verification is not actually covering this task's production code, so typed-code claims for `services/api/` are unsupported by CI. This is a pre-existing config gap (not introduced by this diff), but it directly weakens the Definition of Done for a typed-API task.
- **Recommendation:** Extend the mypy config to cover `services/` (resolving the module-base collision) so the API service is genuinely type-checked in CI.

---

## 6. Non-Defect Observations

- **Deterministic ordering is correctly implemented.** `order_by(collected_at DESC, id DESC)` gives a unique, stable ordering even under equal `collected_at` timestamps, unlike the `list_products`/`get_product` latest-observation tie ambiguity noted in TASK-064 Finding 1.
- **Count is accurate.** `list_observations` counts `func.count()` over the joined subquery; each observation maps to exactly one `source_product`/`source` (FK-constrained), so no row multiplication inflates `total`.
- **No N+1 queries.** The handler issues at most three queries (existence check, count, page). The existence check itself is heavier than necessary (see Finding 1).
- **Consistent with existing style.** The implementation reuses TASK-064's `_decimal_to_float` helper and the repository-layer `.isoformat()` string-timestamp convention. This means TASK-064's open Findings 2 (float money) and 4 (stringly-typed timestamps) carry over into this endpoint as well; no new regression, but the underlying concerns remain.
- **Route ordering is safe.** `/{product_id}` (single segment) cannot match `/{product_id}/observations` (two segments), so the declaration order does not cause a path collision.
- **`from_date > to_date`** silently yields an empty result set; reasonable behavior, but currently undocumented and untested (folded into Finding 3).

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The implementation satisfies TASK-065's functional requirements: a typed, read-only, paginated historical-observation endpoint with deterministic ordering, timestamps, price/currency, availability, source/listing traceability, and date filtering, implemented behind the repository layer with no analytics and no unrelated changes. Unit tests (22 in the product module; 48 across the API suite), `ruff check`, and `ruff format --check` all pass and were independently executed. The diff is clean and isolated to the task.

No blocking defect was found. Finding 1 (404 vs empty history) and Finding 2 (endpoint path vs specification) are genuine correctness/contract issues that should be resolved before the endpoint is depended upon by downstream work; Finding 5 is a pre-existing verification gap that weakens the typed-code guarantee. Findings 3 and 4 are minor robustness/consistency improvements. PostgreSQL integration verification for these endpoints was not evidenced and remains unverified (requires Docker).
