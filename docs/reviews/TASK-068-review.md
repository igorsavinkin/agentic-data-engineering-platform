# TASK-068 Review — Data Quality API

## 1. Review Header

- **Task ID:** TASK-068 — Data Quality API
- **Review date:** 2026-09-19
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set (three-dot diff):** `5f687f9afc7023a8f1fc16b16887a78d7f3a9a06...6fbf422cfafdfa48c48d45218cefbb3371bddfa0`
- **Reviewed HEAD:** `6fbf422cfafdfa48c48d45218cefbb3371bddfa0` on `feature/TASK-068`
- **Commits in range (2-dot `5f687f9..6fbf422` = 1 commit):**
  - `6fbf422` feat(TASK-068): data quality API endpoints
- **Scope:** `services/api/models.py`, `services/api/repositories/quality.py` (new), `services/api/routes/v1/quality.py` (new), `services/api/routes/v1/router.py`, `services/api/schemas.py`, `tests/api/routes/v1/test_quality.py` (new) — 6 files, 492 insertions / 1 deletion.
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

> **Note on the base commit.** The base `5f687f9` ("Merge pull request #80 from igorsavinkin/feature/TASK-067") is the direct parent of `6fbf422`, so the history is linear and the three-dot diff is identical to the two-dot diff. Both show only the six task-relevant files; there is no cross-task contamination.

---

## 2. Requirements Coverage

Task objective: expose persisted latest/historical data-quality results with bounded filters by check/source/dataset/status/time where supported; preserve established quality severity/status semantics; do not execute checks in request handlers.

| Requirement | Status | Evidence |
|---|---|---|
| Expose persisted latest/historical results | ✅ Met | `GET /quality` (list, newest-first via `checked_at DESC`) and `GET /quality/summary` (aggregate with `last_checked_at`) read `data_quality_results`. |
| Bounded filters by check / status / time | ✅ Met | `check_name`, `severity`, `passed`, `pipeline_run_id`, `from_date` filters; `page`/`page_size` bounded (`page_size ≤ 100`). |
| `source` / `dataset` filters "where supported" | ✅ Met (N/A) | Correctly omitted: the persisted `data_quality_results` table has no `source` or `dataset` column (TASK-027/057 schema). See Non-Defect Observations. |
| Preserve severity/status semantics | ⚠️ Partial | Uses the established `severity` (`info`/`warning`/`error`) and `passed` (bool) values from `libs/quality/models.py`; but the summary's severity is aggregated with lexicographic `MAX()` — Finding F1. |
| Do not execute checks in request handlers | ✅ Met | Both handlers only call read-only repository methods; no `libs.quality.checks` execution, no writes. |
| Typed FastAPI/Pydantic/Python | ✅ Met (config caveat) | Typed dataclasses + Pydantic response models; but `services/` is excluded from the configured `mypy` `files` — Finding F2. |
| Thin handlers; logic in reusable layer | ✅ Met | Routes only map dataclass → response schema; filtering/aggregation lives in `DataQualityRepository`. |
| Bound queries and pagination | ✅ Met | List is offset-paginated with `page_size` capped at 100; summary is naturally bounded by distinct check names. |
| Never expose secrets / internal stack traces | ✅ Met | Read-only ORM; `details` exposes check diagnostics, not secrets; structured error handling inherited from the app. |
| Do not weaken tests | ✅ Met | 14 new tests; no existing tests removed or weakened. |
| No unrelated changes | ✅ Met | See §3. |

---

## 3. Git Diff Review

- **Branch / isolation:** On `feature/TASK-068`; working tree clean; single linear commit. No cross-task contamination.
- **Files changed (6):**
  - `services/api/models.py` (+25/-1) — adds the `DataQualityResult` read-only ORM model; imports `Boolean`.
  - `services/api/repositories/quality.py` (new, 142 lines) — `DataQualityRepository` + frozen dataclasses for list and summary.
  - `services/api/routes/v1/quality.py` (new, 91 lines) — two `GET` handlers (`""` and `"/summary"`).
  - `services/api/routes/v1/router.py` (+2) — registers the quality router.
  - `services/api/schemas.py` (+42) — four new Pydantic response models.
  - `tests/api/routes/v1/test_quality.py` (new, 191 lines) — 14 tests.
- **Out-of-scope / unrelated changes:** None.
- **Architectural changes:** None. The API remains read-only; the "warehouse-loader-owns-writes" boundary is preserved (the ORM model is query-only, per the module docstring). No checks are executed in handlers.
- **Accidental / debug / secrets / generated artifacts:** None found.
- **New dependencies:** None — only `sqlalchemy` types/`select`/`desc`/`func` and stdlib imports, all already present.
- **Schema fidelity:** The `DataQualityResult` model accurately reflects the actual warehouse schema. It matches `warehouse/migrations/versions/001_initial_schema.py` (`id`, `pipeline_run_id`, `observation_id`, `check_name`, `severity`, `passed`, `message`, `checked_at`) plus `warehouse/migrations/versions/004_quality_result_persistence.py` (`records_checked`, `failed_records`, `details`, `replay_key`). This is correct: the API reads the real persisted schema, not the aspirational field list in SPECIFICATION.md §13 (see Non-Defect Observations).

---

## 4. Test and Verification Review

### Tests examined
`tests/api/routes/v1/test_quality.py` — 14 tests across two classes:
- `TestListQualityChecks` (10): empty, returns all, pagination, `check_name` filter, `severity` filter, `passed` filter, `pipeline_run_id` filter, field contents, invalid `page`, invalid `page_size`.
- `TestQualitySummary` (4): empty, returns summary, summary values, all-passed summary.

### Verification status

| Check | Result | Classification |
|---|---|---|
| `python -m pytest tests/api/routes/v1/test_quality.py -v` | 14 passed | **Independently verified** |
| `python -m pytest tests/api -q` | 100 passed | **Independently verified** |
| `python -m ruff check` (5 changed files) | All checks passed | **Independently verified** |
| `python -m ruff format --check` (5 changed files) | 5 files already formatted | **Independently verified** |
| `python -m mypy` (reviewed `services/` files) | Not meaningful — `services/` excluded by config (Finding F2); explicit-file invocation hits a module-base collision | **Unverified for `services/`** |
| `python -m pytest -m integration` | Not run (Docker PostgreSQL required) | **Unverified** |

### Test adequacy notes
- Tests use in-memory **SQLite** via `tests/api/conftest.py` (`Base.metadata.create_all`), not PostgreSQL. `TIMESTAMP(timezone=True)`, `JSON`, boolean-`CAST`, and text ordering behave differently across engines; there is no integration-marked test exercising these endpoints against the real warehouse. Since this task reads persisted PostgreSQL state, this is a coverage gap (not a defect).
- The `from_date` filter is a documented query parameter but has **no test** — Finding F3.
- The summary aggregation bug in F1 is latent specifically because the seed keeps `severity` constant per `check_name`; no seed exercises mixed severities for a single check — Finding F3.
- No test asserts the newest-first ordering of the list endpoint.

---

## 5. Findings

### F1 — Moderate: summary `severity` is aggregated with lexicographic `MAX()`, misrepresenting severity order

- **File / line:** `services/api/repositories/quality.py` — `list_quality_summary`, `func.max(DataQualityResult.severity).label("severity")` (line 122).
- **Problem:** The summary endpoint collapses a check's rows into a single `severity` using `MAX(severity)`, i.e. lexicographic text ordering. The established severity vocabulary is `error` > `warning` > `info` (`libs/quality/models.py:CheckSeverity`), but text ordering sorts `"error" < "info" < "warning"`. Independently confirmed on SQLite: `MAX` over `{'error','warning','info'}` returns `'warning'`, and over `{'error','info'}` returns `'info'`. So a check that has ever produced an `error`-severity result can be summarized as `warning` (or `info`), understating its severity. This directly touches the task's "preserve established quality severity/status semantics" requirement.
- **Impact:** The summary's `severity` can be semantically wrong whenever a single `check_name` has results with differing severities (possible because the DAG config can override severity per check; `daily_data_quality_dag.py:_build_checks`). Currently masked because the seed keeps severity constant per check.
- **Recommendation:** Use an order-preserving expression rather than text `MAX`, e.g. a `CASE` mapping `error=3, warning=2, info=1` wrapped in `MAX`, or `ARRAY_POSITION`-style ordering, and add a test with mixed severities for one check name. At minimum, document that `severity` reflects the lexicographic max if a stable per-check severity is assumed.

### F2 — Moderate: `mypy` configuration does not type-check the reviewed code (pre-existing)

- **File / line:** `pyproject.toml` — `[tool.mypy] files = ["scripts", "tests", "libs"]`.
- **Problem:** `python -m mypy` reports success while excluding `services/` — all of TASK-068's repository/routes/models/schemas. Only the new *test* file (under `tests/`) is in scope. This is the same gap noted in TASK-065/066/067 and is not introduced by this diff, but it weakens the "typed code / type checks pass" Definition of Done for the API service.
- **Impact:** The typed-code guarantee for `quality.py`, `models.py`, and `schemas.py` is unsupported by CI.
- **Recommendation:** Extend the mypy config to cover `services/` (resolving the module-base collision, e.g. via `explicit_package_bases` or `MYPYPATH`), so the API service is genuinely type-checked.

### F3 — Minor: `from_date` filter and result ordering are untested

- **File / line:** `tests/api/routes/v1/test_quality.py` — `TestListQualityChecks` (no `from_date` test; no ordering assertion).
- **Problem:** `from_date` is a documented query parameter of `GET /quality` but is not exercised by any test, so a regression in the `checked_at >= from_date` predicate would go unnoticed. Likewise, the newest-first ordering (`order_by(desc(checked_at))`) that makes the endpoint satisfy "latest … results" is not asserted anywhere.
- **Impact:** Unprotected behavior; the "latest-first" guarantee is load-bearing for the task objective but unverified.
- **Recommendation:** Add a test that seeds rows with distinct `checked_at` values, filters via `from_date`, and asserts the returned ordering and subset.

### F4 — Minor: missing deterministic ordering tiebreaker in the list query

- **File / line:** `services/api/repositories/quality.py` — `list_quality_checks`, `order_by(desc(DataQualityResult.checked_at))` (line 92).
- **Problem:** No secondary `id` sort key. Two results with the same `checked_at` can be returned in non-deterministic order, and page boundaries can shift across calls. This repeats the TASK-067 F7 pattern.
- **Impact:** Minor stability/correctness risk; currently masked by distinct timestamps in the seed.
- **Recommendation:** Add `DataQualityResult.id` as a secondary sort key (`desc(checked_at), desc(id)`).

### F5 — Minor: `details` mapped as generic `JSON` while the column is `JSONB`

- **File / line:** `services/api/models.py` — `DataQualityResult.details: Mapped[Optional[dict]] = mapped_column(JSON)` (line 143).
- **Problem:** The actual warehouse column is `JSONB` (`warehouse/migrations/versions/004_quality_result_persistence.py` uses `sa.dialects.postgresql.JSONB()`), but the model maps it to generic `JSON`. For read-only queries this is functionally harmless (SQLAlchemy deserializes both), but it is a fidelity drift from the schema the model claims to map. This repeats the TASK-067 F8 pattern and is also consistent with the existing `PipelineRun.metadata_` / `IngestionHealthResult.reasons` mappings.
- **Impact:** No behavioral defect; minor schema-mapping inconsistency.
- **Recommendation:** Map the column with the PostgreSQL JSONB variant (e.g. `JSON().with_variant(JSONB, "postgresql")`) for accuracy, ideally repo-wide for all JSONB columns.

---

## 6. Non-Defect Observations

- **Clean, well-isolated scope.** Single linear commit, six task-relevant files, no unrelated edits, no new dependencies, no secrets or debug artifacts.
- **Architecturally compliant.** Thin route handlers, reusable read-only repository, query-only ORM model — consistent with the established TASK-063/064/066/067 API pattern and the "warehouse-loader-owns-writes" boundary. No check execution in handlers, per the task's explicit requirement.
- **Schema fidelity is correct.** The model matches the real `data_quality_results` schema (migrations 001 + 004), which is what actually gets persisted by `libs/quality/persistence.py` (TASK-057) and the `daily_data_quality` DAG (TASK-060).
- **`source`/`dataset` filters correctly absent.** SPECIFICATION.md §13 lists `source` and `status` for `data_quality_results`, but the persisted table has neither a `source` nor a `dataset` column (`libs.quality.persistence.py` drops `QualityResult.source` at write time; only `replay_key` retains it). The task's "where supported" qualifier therefore makes omitting these filters correct.
- **SPECIFICATION.md §13 drift (pre-existing).** §13 lists `data_quality_results` fields as `id`, `run_id`, `check_name`, `source`, `status`, `checked_at`, `records_checked`, `failed_records`, `details`, whereas the implemented warehouse schema uses `pipeline_run_id`, `observation_id`, `severity`, `passed`, `message`, `replay_key`. The implementation correctly follows the *actual* schema; the specification's §13 field list is stale relative to TASK-027/057 and is not a TASK-068 defect.
- **Summary endpoint is naturally bounded.** It groups by `check_name`, whose cardinality is the small fixed set of defined checks; the absence of a `limit` there is consistent with the aggregate nature of the endpoint and does not violate the bounding rule.
- **No `GET /quality/{id}` endpoint.** Not required by the task objective; the list (historical, newest-first) and summary (aggregate latest) together cover "latest/historical".
- **`passed` boolean is preserved verbatim** (not flattened into a `status` string), matching `QualityResult.passed` and the `passed` column, so consumers can apply the established `CheckStatus` semantics themselves.
- **Deterministic seed strategy.** Module-level `_NOW = datetime.now(timezone.utc)` and relative `_ts()` helper keep tests hermetic; no absolute timestamp is asserted.
- **SQLite-only coverage.** The unit suite exercises these endpoints against SQLite, not PostgreSQL; the real warehouse (PostgreSQL `JSONB`, `TIMESTAMPTZ`, boolean→integer `CAST`, text collation) is not integration-tested here. This is a coverage gap, not a defect in the diff.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The implementation is cleanly scoped, isolated to TASK-068, architecturally compliant (read-only repository layer, no writes, no check execution in handlers, no new dependencies), and passes all unit tests (14 quality tests, 100 API-suite tests), `ruff check`, and `ruff format --check` — all independently executed. The `DataQualityResult` model accurately maps the actual persisted warehouse schema, and the endpoints correctly reuse the established `severity`/`passed` semantics from `libs/quality`.

Remaining findings are non-blocking:

- **F1 (Moderate)** — the summary's `severity` is aggregated via lexicographic `MAX()`, which understates severity when a check has mixed severities (`error` sorts below `warning`); use an order-preserving expression and test mixed severities.
- **F2 (Moderate)** — pre-existing mypy config excludes `services/`, so the reviewed code is not type-checked by CI.
- **F3 (Minor)** — the `from_date` filter and the newest-first ordering are untested.
- **F4 (Minor)** — missing `id` tiebreaker in the list ordering.
- **F5 (Minor)** — `details` mapped as generic `JSON` vs the actual `JSONB` column.

PostgreSQL integration verification for these endpoints was not evidenced and remains unverified (requires Docker); the unit suite exercises the SQL semantics only under SQLite.
