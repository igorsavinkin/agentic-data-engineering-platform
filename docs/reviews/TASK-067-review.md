# TASK-067 Review — Pipeline Status API

## 1. Review Header

- **Task ID:** TASK-067 — Pipeline Status API
- **Review date:** 2026-09-19
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set (three-dot diff):** `1cdda86eec4463b6a1aa084a15cc22c368eb62dc...3ebcbcb55d46402813e04c4c050115e8133202be`
- **Reviewed HEAD:** `3ebcbcb55d46402813e04c4c050115e8133202be` on `feature/TASK-067`
- **Commits in range (2-dot `1cdda86..3ebcbcb` = 1 commit):**
  - `3ebcbcb` feat(TASK-067): pipeline status API endpoints
- **Scope:** `services/api/models.py`, `services/api/repositories/pipeline_status.py` (new), `services/api/routes/v1/pipelines.py` (new), `services/api/routes/v1/router.py`, `services/api/schemas.py`, `tests/api/routes/v1/test_pipelines.py` (new) — 6 files, 595 insertions / 1 deletion.
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

> **Note on the base commit.** The base `1cdda86` ("Merge pull request #79 from igorsavinkin/feature/TASK-066") is the direct parent of `3ebcbcb`, so the history is linear and the three-dot diff is identical to the two-dot diff. Both show only the six task-relevant files; there is no cross-task contamination.

---

## 2. Requirements Coverage

Task objective: expose read-only pipeline/source status from persisted runs, health, degradation and freshness state; distinguish `unknown`, `healthy`, `degraded`, `stale`, and `failed` using existing semantics; do not trigger ingestion/Airflow.

| Requirement | Status | Evidence |
|---|---|---|
| Read-only pipeline/source status | ✅ Met | `PipelineStatusRepository` performs only `SELECT` queries; no writes. |
| Persisted runs | ✅ Met | `GET /pipelines`, `GET /pipelines/{run_id}` over `pipeline_runs`. |
| Source health / degradation / freshness | ✅ Met | `GET /pipelines/source-health` over `ingestion_health_results`. |
| Distinguish `unknown`/`healthy`/`degraded`/`stale`/`failed` | ✅ Met (partial test coverage) | `_derive_overall_status` / `_derive_pipeline_status` map the persisted values into the five categories; but the `degraded` and `unknown` branches are untested — Finding F3. |
| Use existing semantics | ✅ Met | Reuses the exact value strings of `SourceDegradationState` and `FreshnessState` (`healthy`, `unreachable`, `rate_limited`, `structurally_changed`, `partially_parseable`, `empty_result`, `stale`, `fresh`, `never_collected`) from `libs/observability/health_assessment.py`. |
| Do not trigger ingestion/Airflow | ✅ Met | Pure read-only ORM layer; no side effects. |
| Typed FastAPI/Pydantic/Python | ✅ Met | Typed dataclasses + Pydantic response models; mypy config caveat — Finding F4. |
| Thin handlers; logic in reusable layer | ✅ Met | Routes only map dataclass → response schema; derivation logic lives in the repository. |
| Bound queries / pagination | ⚠️ Partial | `page_size`/`limit` capped at 100 and `page`/`limit` at ≥1; but `list_source_health` uses a `limit*10` fetch + Python dedup heuristic that is both over-fetching and incorrect under accumulation — Finding F1. |
| Never expose secrets / internal stack traces | ✅ Met | Structured error handlers; no secret handling. |
| Do not weaken tests | ✅ Met | 17 new tests; no existing tests removed or weakened. |
| No unrelated changes | ✅ Met | See §3. |

Scope note: SPECIFICATION.md §16 lists only `GET /pipelines` and `GET /pipelines/{id}`. The extra `GET /pipelines/source-health` endpoint is justified by the TASK-067 objective ("pipeline/source status … health, degradation and freshness state") and is within scope.

---

## 3. Git Diff Review

- **Branch / isolation:** On `feature/TASK-067`; working tree clean; single linear commit. No cross-task contamination.
- **Files changed (6):**
  - `services/api/models.py` (+35/-1) — adds `PipelineRun` and `IngestionHealthResult` read-only ORM models; imports `Float` and `JSON`.
  - `services/api/repositories/pipeline_status.py` (new, 188 lines) — `PipelineStatusRepository` + frozen dataclasses + status derivation.
  - `services/api/routes/v1/pipelines.py` (new, 98 lines) — three `GET` handlers.
  - `services/api/routes/v1/router.py` (+2) — registers the pipelines router.
  - `services/api/schemas.py` (+40) — four new Pydantic response models.
  - `tests/api/routes/v1/test_pipelines.py` (new, 232 lines) — 17 tests.
- **Out-of-scope / unrelated changes:** None.
- **Architectural changes:** None. The API remains read-only; the "warehouse-loader-owns-writes" boundary is preserved (the ORM models are query-only, per the module docstring).
- **Accidental / debug / secrets / generated artifacts:** None found.
- **New dependencies:** None — only `sqlalchemy` types/`select`/`desc`/`func` and stdlib imports, all already present.
- **Schema fidelity:** The two models accurately reflect the real warehouse schema — `pipeline_runs` matches `warehouse/migrations/versions/001_initial_schema.py` (`id`, `run_type`, `status`, `started_at`, `finished_at`, `records_loaded`, `error_message`, `metadata`) and `ingestion_health_results` matches `warehouse/migrations/versions/005_ingestion_health_results.py` (`source_name`, `state`, `freshness_state`, `reasons`, `signals`, `freshness_age_seconds`, `assessed_at`, …). This is correct: the API reads the actual persisted schema, not the aspirational field list in SPECIFICATION.md §13 (see Non-Defect Observations).

---

## 4. Test and Verification Review

### Tests examined
`tests/api/routes/v1/test_pipelines.py` — 17 tests across three classes:
- `TestListPipelineRuns` (7): empty, returns all, pagination, status filter, overall-status mapping, invalid `page`, invalid `page_size`.
- `TestGetPipelineRun` (3): not found (404), returns run, failed run.
- `TestSourceHealth` (7): empty, latest-per-source, healthy mapping, stale mapping, source filter, limit, invalid limit.

### Verification status

| Check | Result | Classification |
|---|---|---|
| `python -m pytest tests/api/routes/v1/test_pipelines.py -q` | 17 passed | **Independently verified** |
| `python -m pytest tests/api -q` | 86 passed | **Independently verified** |
| `python -m ruff check services/api` | All checks passed | **Independently verified** |
| `python -m ruff format --check services/api` | 21 files already formatted | **Independently verified** |
| `python -m mypy` | Success: no issues in 164 source files | **Independently verified** (but excludes `services/` — Finding F4) |
| `python -m pytest -m integration` | Not run (Docker PostgreSQL required) | **Unverified** |

### Test adequacy notes
- Tests use in-memory **SQLite** via `tests/api/conftest.py` (`Base.metadata.create_all`), not PostgreSQL. `TIMESTAMP(timezone=True)`, `JSON`, and ordering behavior differ between SQLite and PostgreSQL; there is no integration-marked test exercising these endpoints against the real warehouse. Since this task reads persisted PostgreSQL state, this is a coverage gap (not a defect).
- The task's headline requirement — distinguish `degraded` and `unknown` — is **not** exercised by any test. The seeded `best_buy` row (`state="unreachable"`, `freshness_state="stale"`) only hits the stale-over-degraded path; no seed row produces `overall_status == "degraded"` and none produces `"unknown"` (Finding F3).
- The "stale wins over degraded" precedence is deliberately asserted (`test_status_mapping_stale`), so that design choice is pinned down.

---

## 5. Findings

### F1 — Moderate: `list_source_health` uses a `limit*10` fetch + Python dedup that can return incomplete results

- **File / line:** `services/api/repositories/pipeline_status.py` — `list_source_health` (lines 144–187), specifically `.limit(limit * 10)` at line 158 and the `seen` dedup loop at lines 163–177.
- **Problem:** To produce "latest assessment per source", the query orders by `source_name ASC, assessed_at DESC` and fetches up to `limit * 10` rows, then deduplicates in Python keeping the first row per source. Because the ordering is by `source_name` first, a source that sorts early with more than `limit * 10` historical rows will consume the entire fetch budget and later-sorted sources will never appear — so the endpoint silently returns incomplete results. `ingestion_health_results` accumulates one row per source per DAG interval, so the condition is realistic over time.
- **Impact:** Correctness degradation (missing sources) as health history accumulates; also contradicts the "bound queries" rule in spirit by over-fetching `limit * 10` rows only to discard most of them.
- **Recommendation:** Use a window function that selects only the latest row per source and bounds the result, e.g. `ROW_NUMBER() OVER (PARTITION BY source_name ORDER BY assessed_at DESC) AS rn` with `rn = 1` and then `.limit(limit)` (or `DISTINCT ON (source_name)` on PostgreSQL). This is both correct and bounded.

### F2 — Moderate: 404 uses `HTTPException` instead of the project's structured `APIError`

- **File / line:** `services/api/routes/v1/pipelines.py` — `get_pipeline_run` raises `HTTPException(status_code=404, detail="Pipeline run not found")` (lines ~88–91).
- **Problem:** The API has an established structured-error convention (`services/api/errors.py` + `APIError`), used by `products.py` (`APIError(status_code=404, error_code="PRODUCT_NOT_FOUND", …)`). The pipelines route bypasses it, so the client receives the generic `{"error": {"code": "HTTP_404", …}}` instead of a semantic code such as `PIPELINE_RUN_NOT_FOUND`.
- **Impact:** Inconsistent error contract; clients cannot programmatically distinguish "pipeline run not found" from other 404s. Not functionally broken (the `HTTPException` handler is registered), but violates the project's own convention.
- **Recommendation:** Raise `APIError(status_code=404, error_code="PIPELINE_RUN_NOT_FOUND", message=f"Pipeline run {run_id} not found")` and add a body-shape assertion to the existing `test_not_found` test.

### F3 — Moderate: `degraded` and `unknown` mappings are untested

- **File / line:** `tests/api/routes/v1/test_pipelines.py` — `TestSourceHealth` (lines 186–232) and `TestListPipelineRuns.test_overall_status_mapping` (lines 142–148).
- **Problem:** The task's objective is to "distinguish unknown, healthy, degraded, stale and failed". `healthy`, `stale`, and `failed` are asserted, but no test seed produces `overall_status == "degraded"` (a degraded `state` with non-stale freshness) or `overall_status == "unknown"` (e.g. `state="healthy"` with `freshness_state="never_collected"`, or an unrecognized pipeline `status`). The `_DEGRADED_STATES → "degraded"` branch and both `"unknown"` fallbacks are entirely uncovered.
- **Impact:** The two most novel aggregation categories are unprotected against regression; a future edit to `_derive_overall_status`/`_derive_pipeline_status` could silently change them.
- **Recommendation:** Add seeds/tests for: (a) a degraded-but-fresh source (e.g. `state="unreachable"`, `freshness_state="fresh"` → `degraded`), and (b) an unknown case (e.g. `state="healthy"`, `freshness_state="never_collected"`, or pipeline `status="cancelled"` → `unknown`).

### F4 — Moderate: `mypy` configuration does not type-check the reviewed code (pre-existing)

- **File / line:** `pyproject.toml` — `[tool.mypy] files = ["scripts", "tests", "libs"]`.
- **Problem:** `python -m mypy` reports success while excluding `services/` (all of TASK-067's repository/routes/models/schemas). Only the new *test* file (under `tests/`) is type-checked. This is the same gap noted in TASK-065/066 and is not introduced by this diff, but it weakens the "typed code / type checks pass" Definition of Done for the API service.
- **Impact:** The typed-code guarantee for `pipeline_status.py`, `pipelines.py`, `models.py`, and `schemas.py` is unsupported by CI.
- **Recommendation:** Extend the mypy config to cover `services/` (resolving the module-base collision, e.g. via `explicit_package_bases` or `MYPYPATH`), so the API service is genuinely type-checked.

### F5 — Minor: `running` pipeline status maps to `healthy`

- **File / line:** `services/api/repositories/pipeline_status.py` — `_derive_pipeline_status` (lines 40–45).
- **Problem:** A still-`running` pipeline run is classified as `healthy`. The task's vocabulary is `unknown`/`healthy`/`degraded`/`stale`/`failed`, so `running` must be folded somewhere, and "not failed" is defensible; but "healthy" is arguably misleading for an in-flight run with no result yet.
- **Impact:** API consumers may interpret an unfinished run as a successful one.
- **Recommendation:** Either document this mapping explicitly (e.g. in the endpoint docstring / OpenAPI description) or map `running` to `unknown` to avoid implying success.

### F6 — Minor: pagination schema duplication and no pagination metadata on source-health

- **File / line:** `services/api/schemas.py` — `PipelineRunListResponse` (re-declares `items`/`total`/`page`/`page_size` already on `PaginatedResponse`); `SourceHealthListResponse` (returns only `items` despite a `limit` query parameter).
- **Problem:** Recurrence of the TASK-064/065/066 finding — `PaginatedResponse` is not reused, so pagination fields drift. The source-health endpoint has a `limit` parameter but returns no `total`/`page` metadata, so callers cannot tell whether more sources exist.
- **Impact:** Schema drift risk and incomplete pagination semantics.
- **Recommendation:** Make `PaginatedResponse` generic over the item type and reuse it; decide and document whether source-health is a bounded list (add `total`) or a capped overview.

### F7 — Minor: missing deterministic ordering tiebreakers

- **File / line:** `services/api/repositories/pipeline_status.py` — `list_pipeline_runs` `order_by(desc(PipelineRun.started_at))` (line ~114) and `list_source_health` `order_by(source_name, desc(assessed_at))` (lines 153–157).
- **Problem:** Neither orders by `id` as a tiebreaker. Two runs with the same `started_at`, or two assessments for the same source with the same `assessed_at`, can be returned in non-deterministic order (and page boundaries can shift). The existing `list_observations` in `product.py` already uses `collected_at.desc(), id.desc()`; these new queries do not.
- **Impact:** Minor correctness/stability risk; currently masked by unique timestamps in the test seed.
- **Recommendation:** Add `PipelineRun.id` / `IngestionHealthResult.id` as a secondary sort key.

### F8 — Minor: `pipeline_runs.metadata` mapped as generic `JSON` while the column is `JSONB`

- **File / line:** `services/api/models.py` — `PipelineRun.metadata_` uses `mapped_column("metadata", JSON)` (line ~107).
- **Problem:** The actual warehouse column is `JSONB` (`warehouse/migrations/versions/001_initial_schema.py` uses `sa.dialects.postgresql.JSONB()`; `init.sql` uses `JSONB`), but the model maps it to generic `JSON`. For read-only queries this is functionally harmless (SQLAlchemy deserializes both), but it is a fidelity drift from the schema the model docstring claims to map.
- **Impact:** No behavioral defect; minor schema-mapping inconsistency.
- **Recommendation:** Map the column with the PostgreSQL JSONB variant (e.g. `JSON().with_variant(JSONB, "postgresql")`) for accuracy.

---

## 6. Non-Defect Observations

- **Clean, well-isolated scope.** Single linear commit, six task-relevant files, no unrelated edits, no new dependencies, no secrets or debug artifacts.
- **Architecturally compliant.** Thin route handlers, reusable read-only repository, query-only ORM models — consistent with the established TASK-063/064/066 API pattern and the "warehouse-loader-owns-writes" boundary.
- **Route ordering is correct.** `/pipelines/source-health` is declared before `/pipelines/{run_id}`; because `run_id` is `int`, the two cannot collide, but the order is the safe pattern.
- **`metadata` column-name collision handled idiomatically.** The attribute is `metadata_` with an explicit `"metadata"` column name, avoiding `Base.metadata` shadowing.
- **Stale-wins-over-degraded precedence is intentional and tested.** A source that is both `unreachable` (degraded) and freshness-`stale` reports `"stale"` (asserted by `test_status_mapping_stale`). This is a defensible reading of "distinguish … stale"; worth a one-line doc note.
- **SPECIFICATION.md §13 drift (pre-existing).** The §13 logical entity for `pipeline_runs` lists `run_id`, `pipeline_name`, `source`, `records_received`, `records_processed`, `records_failed`, whereas the implemented warehouse schema (migrations 001/005 and `init.sql`) uses `run_type`, `records_loaded`, `metadata`. The implementation correctly follows the *actual* schema; the specification's §13 field list is stale relative to earlier tasks and is not a TASK-067 defect.
- **Deterministic seed strategy.** Module-level `_NOW = datetime.now(timezone.utc)` and relative `_ts()` helper keep the tests hermetic; no timestamp is asserted, so the wall-clock seed is harmless.
- **`signals` and `evaluated_at`/`logical_date`/`replay_key` are not exposed.** This is a reasonable API surface decision (the response exposes `reasons`, `freshness_age_seconds`, and the two states, which cover the status use case).

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The implementation is cleanly scoped, isolated to TASK-067, architecturally compliant (read-only repository layer, no writes, no new dependencies), and passes all unit tests (17 pipeline-status tests, 86 API-suite tests), `ruff check`, and `ruff format --check` — all independently executed. The two ORM models correctly map the actual persisted warehouse schema, and the status derivation reuses the existing `SourceDegradationState`/`FreshnessState` value strings as required.

Remaining findings are non-blocking:

- **F1 (Moderate)** — `list_source_health`'s `limit*10` fetch + Python dedup can return incomplete results once an early-sorting source accumulates more than `limit*10` health rows; use a window/`DISTINCT ON` query instead.
- **F2 (Moderate)** — the 404 uses `HTTPException` instead of the project's structured `APIError` convention.
- **F3 (Moderate)** — the headline `degraded` and `unknown` mappings are not covered by any test.
- **F4 (Moderate)** — pre-existing mypy config excludes `services/`, so the reviewed code is not type-checked by CI.
- **F5–F8 (Minor)** — `running→healthy` semantics, pagination-schema duplication / missing source-health metadata, missing ordering tiebreakers, and `JSON` vs `JSONB` column-mapping drift.

PostgreSQL integration verification for these endpoints was not evidenced and remains unverified (requires Docker); the unit suite exercises the SQL semantics only under SQLite.
