# TASK-069 Review — API Tests (Milestone Gate)

## 1. Review Header

- **Task ID:** TASK-069 — API Tests
- **Review date:** 2026-09-19
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set (three-dot diff):** `d7e741a7625ba5ba9a192eda45a6306efc93d61c...732ad905c897ecdd52e7fcdb2885d2c331819d87`
- **Reviewed HEAD:** `732ad905c897ecdd52e7fcdb2885d2c331819d87` (`732ad90`) on `feature/TASK-069`
- **Commits in range (2-dot `d7e741a..732ad90` = 1 commit):**
  - `732ad90` feat(TASK-069): API milestone gate test covering all endpoints
- **Scope:** `tests/api/test_milestone_gate.py` (new) — 1 file, 604 insertions.
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

> **Note on the base commit.** The base `d7e741a` ("Merge pull request #81 from igorsavinkin/feature/TASK-068") is the direct parent of `732ad90`, so the history is linear and the three-dot diff is identical to the two-dot diff. Both show only the single task-relevant test file; there is no cross-task contamination.

---

## 2. Requirements Coverage

Task objective: create the FastAPI milestone gate covering health/readiness, OpenAPI, products, history, analytics, pipeline status, quality, validation/errors, pagination bounds, and DB failures using deterministic migrated DB fixtures.

| Requirement | Status | Evidence |
|---|---|---|
| Health / readiness | ✅ Met | `TestHealthMilestone` asserts `GET /health` → 200/`healthy`, `GET /ready` → `connected`, and `503` + `SERVICE_UNAVAILABLE` on DB failure. |
| OpenAPI schema complete | ✅ Met | `test_openapi_schema_lists_all_v1_paths` asserts all 13 implemented v1 paths; `test_docs_ui_available` checks `/api/docs`. |
| Products | ✅ Met | List (`total == 3`), pagination, beyond-range page, detail (`source_count == 2`), 404 (`PRODUCT_NOT_FOUND`). |
| History | ✅ Met | `test_product_history` asserts `total == 4` for product 100; 404 path covered. |
| Analytics | ⚠️ Partial | `price-changes` covered with real data (`total >= 1`); `price-movers` and `price-statistics` are exercised only vacuously (see Finding F1). |
| Pipeline status | ✅ Met | List (`total == 3`), status filter, single run, 404, source-health (list + filter). |
| Quality | ✅ Met | List (`total == 3`), `check_name`/`passed` filters, summary (2 check names). |
| Validation / errors | ✅ Met | `VALIDATION_ERROR` on `page=0`, `page_size=0`, `page_size=101`, `page=-1`; structured 404 and non-leaking 503. |
| Pagination bounds | ✅ Met | Lower/upper bounds rejected with 422 across all five paginated endpoints. |
| DB failures | ⚠️ Partial | Readiness 503 + no-leak covered; other endpoints' DB-failure path untested (Finding F3). |
| Deterministic **migrated** DB fixtures | ⚠️ Partial | Fixture is deterministic and seeds every table, but schema is built via ORM `Base.metadata.create_all`, not Alembic migrations (Finding F2). |
| No unrelated changes | ✅ Met | See §3. |

---

## 3. Git Diff Review

- **Branch / isolation:** On `feature/TASK-069`; working tree clean; single linear commit. No cross-task contamination.
- **Files changed (1):** `tests/api/test_milestone_gate.py` (new, 604 lines) — a single consolidated, deterministic end-to-end smoke test of the full API surface.
- **Out-of-scope / unrelated changes:** None.
- **Architectural changes:** None. Test-only; no application code, schema, config, or dependency changes.
- **Accidental / debug / secrets / generated artifacts:** None found.
- **New dependencies:** None. Uses already-present `fastapi.testclient`, `sqlalchemy`, `pytest`, and stdlib imports only.
- **Test weakening:** No existing tests modified, removed, or weakened. The new file is additive.

---

## 4. Test and Verification Review

### Tests examined

`tests/api/test_milestone_gate.py` — 44 collected tests across seven classes:

- `TestOpenAPIMilestone` (2): schema path completeness, docs UI.
- `TestHealthMilestone` (3): health, readiness connected, readiness 503 on failure.
- `TestProductsMilestone` (7): list, pagination, beyond-range, detail, 404, history, history-404.
- `TestAnalyticsMilestone` (4): price-changes, price-changes pagination, price-movers, price-statistics.
- `TestPipelinesMilestone` (6): list, status filter, single run, 404, source-health, source-health filter.
- `TestQualityMilestone` (4): list, `check_name` filter, `passed` filter, summary.
- `TestValidationBounds` (15; 3 parametrized × 5 paths): `page=0`, `page_size=0`, `page_size=101`.
- `TestErrorContract` (3): structured 404, structured 422, DB-failure non-leak.

### Verification status

| Check | Result | Classification |
|---|---|---|
| `python -m pytest tests/api/test_milestone_gate.py -v` | 44 passed | **Independently verified** |
| `python -m pytest tests/api -q` | 144 passed | **Independently verified** |
| `python -m ruff check tests/api/test_milestone_gate.py` | All checks passed | **Independently verified** |
| `python -m ruff format --check tests/api/test_milestone_gate.py` | 1 file already formatted | **Independently verified** |
| `python -m mypy tests/api/test_milestone_gate.py` | Success: no issues found | **Independently verified** |
| `python -m pytest -m integration` | Not run | **Not required** — this is a hermetic SQLite + mock gate, not a PostgreSQL/Kafka/MinIO integration test |

### Test adequacy notes

- The gate uses **in-memory SQLite** (`Base.metadata.create_all`) plus a `MagicMock` session for the failure path, so it runs in the default non-`integration` suite (hermetic; no Docker prerequisite). That is appropriate for a milestone smoke gate.
- Independently confirmed defect: `GET /analytics/price-movers` returns `{"items": []}` and `GET /analytics/price-statistics` returns two rows with `currency=null`, `observation_count=0`, `min/max/avg=null` against the seed data, because the fixed seed timestamps fall outside the repository's `days_back=30` window. The corresponding assertions (`"items" in body` and `len(items) >= 1`) still pass, so these two tests do not exercise the analytics logic (Finding F1).
- `test_price_changes` asserts only `total >= 1` (real result is `5`); acceptable for a smoke test but weak — see Non-Defect Observations.
- DB-failure coverage is limited to the readiness endpoint; no test drives a query endpoint through a failing session (Finding F3).

---

## 5. Findings

### F1 — Moderate: `price-movers` and `price-statistics` are covered only vacuously (fixed timestamps fall outside the `days_back` window)

- **File / line:** `tests/api/test_milestone_gate.py` — `NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)` (line 39); `test_price_movers` (line 435); `test_price_statistics` (line 441).
- **Problem:** `AnalyticsRepository.list_price_movers` and `.list_price_statistics` filter on `datetime.now(timezone.utc) - timedelta(days=days_back)` (default `days_back=30`). The fixture anchors all observation timestamps to the fixed date `2025-06-15`, which is more than a year before the actual runtime date (2026-09-19). Every seeded observation is therefore excluded by the cutoff. Independently confirmed:
  - `GET /api/v1/analytics/price-movers` → `{"items": []}`.
  - `GET /api/v1/analytics/price-statistics` → two rows, each `currency=null`, `observation_count=0`, `min/max/avg=null` (the `OUTER JOIN` keeps source rows but no observation data).
  - `test_price_movers` asserts only `"items" in body`, and `test_price_statistics` asserts only `len(body["items"]) >= 1`, so both pass regardless.
- **Impact:** Two of the three analytics endpoints the milestone gate claims to cover are not actually exercised with data. A regression in the price-movers ranking or price-statistics aggregation logic would not be caught by this gate. The `>= 1` statistics assertion is additionally misleading because it passes on rows with null currency and zero counts.
- **Recommendation:** Follow the existing convention in `tests/api/routes/v1/test_analytics.py`, which already anchors data to `datetime.now(timezone.utc)` via a relative `_ts(days_ago)` helper. Seed the milestone gate's observation timestamps relative to `now` (or pass an explicit `days_back` that spans the seed), and strengthen assertions to check concrete values (e.g. non-null `currency`, `observation_count >= 1`, a known `first_price`/`last_price`).

### F2 — Minor: fixture builds schema via ORM `create_all`, not the Alembic migration chain

- **File / line:** `tests/api/test_milestone_gate.py` — `Base.metadata.create_all(engine)` (line 52).
- **Problem:** The task objective states "deterministic **migrated** DB fixtures". The fixture derives the schema from the API's SQLAlchemy `Base.metadata` (`services/api/models.py`) rather than running the repository's Alembic migrations (`warehouse/migrations/versions/001…006`). As a result, drift between the API's read-only ORM models and the actual migrated warehouse schema would not be detected by this gate.
- **Impact:** Minor — this matches the existing `tests/api/conftest.py` convention (`create_all`), and the API models were separately validated against migrations in the TASK-064 review. But it does not literally satisfy the "migrated" wording, and it leaves the model↔migration fidelity check to other suites.
- **Recommendation:** Either align the task wording (if `create_all` is the intended API-suite convention) or, if migration fidelity is desired, run `alembic upgrade head` against a test DB (e.g. SQLite/PostgreSQL) in a dedicated `integration`-marked fixture. At minimum, document why `create_all` is used.

### F3 — Minor: DB-failure path is only exercised for readiness, not query endpoints

- **File / line:** `tests/api/test_milestone_gate.py` — `failing_client` (line 289); `test_db_failure_does_not_leak_internals` (line 599).
- **Problem:** The `failing_client` mock makes `session.execute` raise, but it is used only by `test_readiness_returns_503_on_db_failure` and `test_db_failure_does_not_leak_internals` (both hit `/ready`, which has explicit try/except). No test verifies that a query endpoint (products, analytics, pipelines, quality) returns the generic non-leaking `500 INTERNAL_ERROR` when the DB session fails.
- **Impact:** The task lists "DB failures" as a coverage area, but the coverage is narrower than the objective suggests; the generic 500 path for data endpoints is unverified.
- **Recommendation:** Add one test driving a data endpoint (e.g. `GET /api/v1/products`) through `failing_client` and assert a 500 with `INTERNAL_ERROR` code and no internal message/traceback.

---

## 6. Non-Defect Observations

- **Clean, well-isolated scope.** Single additive test file, no application-code, config, schema, or dependency changes; no secrets or debug artifacts.
- **Good milestone coverage overall.** Health/readiness, OpenAPI, products, history, pipeline status, quality, validation, pagination bounds, and error-contract behavior are all genuinely exercised and asserted with concrete values.
- **Correct schema usage in the seed.** The fixture seeds all eight warehouse tables (`Source`, `Product`, `SourceProduct`, `ProductObservation`, `PipelineRun`, `IngestionHealthResult`, `DataQualityResult`) with FK relationships consistent with the ORM models; the product/history/detail counts (e.g. `source_count == 2`, history `total == 4`) are internally correct.
- **Deterministic but not time-relative.** The fixture is deterministic, but anchoring to a fixed absolute date (`2025-06-15`) is what causes Finding F1; the existing analytics tests avoid this by using `datetime.now(timezone.utc)`-relative timestamps.
- **Weak smoke assertions.** `test_price_changes` (`total >= 1`, real value 5), `test_price_movers` (`"items" in body`), and `test_price_statistics` (`len(items) >= 1`) are smoke-level shape checks. This is defensible for a gate, but the two windowed endpoints should at least assert non-empty/non-null data (see F1).
- **Fixture duplication with conftest.** The file defines its own `seeded_session`/`client`/`failing_client` rather than reusing `tests/api/conftest.py`'s `db_session`/`client`. Acceptable because the gate needs a seeded dataset the shared fixture does not provide, but the `create_app` + `dependency_overrides[get_db]` scaffolding is duplicated.
- **Route ordering is correct.** `GET /pipelines/source-health` is registered before `GET /pipelines/{run_id}`, so the OpenAPI path set and the source-health tests are unambiguous.
- **No `/api/agent/query` path asserted.** Correct — the LangGraph agent endpoint is not implemented yet (M11 / TASK-099), so its absence from the gate is appropriate.
- **SQLite-only semantics.** The gate exercises endpoint SQL under SQLite, not the real PostgreSQL warehouse (`TIMESTAMPTZ`, `JSONB`, collation, boolean `CAST`). Real-warehouse behavior remains covered by `tests/warehouse/*` and the existing `integration` suites, which are out of scope for this hermetic gate.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The change is cleanly isolated to TASK-069, additive, and architecturally neutral (test-only). All 44 milestone-gate tests and the full 144-test API suite pass, and `ruff check`, `ruff format --check`, and `mypy` all pass on the new file — all independently executed. The gate genuinely covers health/readiness, OpenAPI, products, history, pipeline status, quality, validation, pagination bounds, and the error contract with concrete assertions.

Remaining findings are non-blocking:

- **F1 (Moderate)** — `price-movers` and `price-statistics` are exercised only vacuously because the fixed seed timestamps (`2025-06-15`) fall outside the `days_back=30` window; use now-relative timestamps and strengthen the assertions.
- **F2 (Minor)** — the fixture builds schema via ORM `create_all` rather than the Alembic migrations named in the task objective (consistent with the existing API-test convention).
- **F3 (Minor)** — the DB-failure path is only tested for the readiness endpoint, not for data query endpoints.

PostgreSQL `-m integration` verification was not run and is not required for this hermetic SQLite/mock gate.
