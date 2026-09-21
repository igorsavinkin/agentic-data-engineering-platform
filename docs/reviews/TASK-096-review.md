# TASK-096 Review — Data Quality Tool

## 1. Review Header

- **Task ID:** TASK-096 — Data Quality Tool
- **Review date:** 2026-09-21
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:** `3e5b29c57d91e312086556ca310b0e290e2903c0...1a729579fd79ee7e4f44e40363ed2dc58f15b3d8` (single commit `1a72957 feat(TASK-096): Add data quality agent tool`)
- **Reviewed HEAD:** `1a729579fd79ee7e4f44e40363ed2dc58f15b3d8` on `feature/TASK-096`
- **Scope:** `services/agent/quality_adapter.py` (new), `services/agent/tools.py`, `tests/agent/test_quality_adapter.py` (new), `tests/agent/test_tools.py`
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

Sources of authority consulted: `ai/tasks/TASK-096-data-quality-tool.md`, `ai/PROJECT.md` (§2, §4, §11), `ai/SPECIFICATION.md` (§14 Data Quality, §17 LangGraph Data Engineer Agent, §18 Agent State), `ai/ROADMAP.md` (Milestone 11), `ai/AGENTS.md`, `ai/REVIEWER.md`, the existing quality persistence layer (`services/api/repositories/quality.py`, `services/api/models.py`, `services/api/routes/v1/quality.py`), the analogous `services/agent/pipeline_status_adapter.py`, and prior reviews (`docs/reviews/TASK-068-review.md`, `TASK-094-review.md`, `TASK-095-review.md`). The sole ADR (`docs/adr/ADR-001-kafka-topic-configuration.md`) concerns Kafka configuration and is not applicable.

---

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
|---|---|---|
| Implement an agent tool retrieving data quality check results | ✅ Met | `get_data_quality()` (`services/agent/tools.py:446`) returns a `ToolResponse` wrapping `DataQualityStatusResult` with `recent_checks`, `summary`, `overall_status`. |
| Retrieve failure counts | ✅ Met | `total_failures` (sum of `failed_runs`), `checks_with_failures`, per-check `failed_runs`, and per-check `failed_records` are all surfaced. |
| Retrieve quality trends | ✅ Met (interpreted as aggregate + recent history) | `QualityCheckSummary.pass_rate`, `total_runs`/`passed_runs`/`failed_runs`, `last_checked_at`, plus the ordered recent-check list with per-check `checked_at`/`passed`/`failed_records`. |
| Surface meaningful info without exposing internal implementation details | ✅ Met | The tool exposes Pydantic models (`QualityCheckDetail`, `QualityCheckSummary`, `DataQualityStatusResult`), not SQLAlchemy rows or repository internals. |
| Reuse existing data-quality framework/persistence; do not duplicate logic | ✅ Met | `RepositoryDataQualityProvider` (`services/agent/quality_adapter.py`) delegates to the existing `DataQualityRepository.list_quality_checks()` / `list_quality_summary()`; no SQL or aggregation is reimplemented. |
| Return structured results suitable for agent reasoning | ✅ Met | Typed Pydantic result model with `model_dump()` in the `ToolResponse.data` envelope, consistent with the other agent tools. |
| Agent must not have write access to PostgreSQL | ✅ Met | The tool only reads via `DataQualityRepository`, which is read-only by construction; no write path is introduced. |

---

## 3. Git Diff Review

- **Files changed:** 4 files, +537 / −3 lines. All belong to TASK-096.
  - `services/agent/quality_adapter.py` (+48, new) — concrete provider adapting `DataQualityRepository`.
  - `services/agent/tools.py` (+150) — data-quality models, `DataQualityProvider` protocol, `get_data_quality()`, `_worst_severity()`, `_derive_overall_quality()`.
  - `tests/agent/test_quality_adapter.py` (+70, new) — adapter unit tests.
  - `tests/agent/test_tools.py` (+272) — tool unit tests.
- **Scope correctness:** All changes are confined to the agent data-quality tool and its tests. No unrelated files modified.
- **Unrelated changes:** None.
- **Architectural changes:** None. Service boundaries, event semantics, data-lake/warehouse ownership, and agent read-only posture are unchanged.
- **Accidental changes / debugging code / secrets:** None. No debug prints, temporary files, dead code, generated artifacts, or secrets.
- **Dependency/config changes:** None. `pyproject.toml`, `requirements*.txt`, and infra config are untouched; only `pydantic` (already a runtime dependency) is used.
- **Branch/task isolation:** ✅ Single commit on `feature/TASK-096`; no changes from another TASK-xxx are included.

---

## 4. Test and Verification Review

### Tests examined

- `tests/agent/test_quality_adapter.py` — 4 tests: recent-checks mapping, filter pass-through (`page=1, page_size=limit, check_name=...`), summary mapping, empty results.
- `tests/agent/test_tools.py` — added `FakeDataQualityProvider` and 16 new tests across `TestGetDataQuality`, `TestWorstSeverity`, `TestDeriveOverallQuality`: healthy, degraded (error), degraded (warning), unknown/empty, limit/filter pass-through, provider error, pass-rate computation, multi-check aggregation, and worst-severity/overall-status derivation.

### Test adequacy

Strong and focused. The tests exercise the tool's full requirement surface deterministically (no DB/Kafka/network) and correctly assert the structured output by re-parsing `ToolResponse.data` into `DataQualityStatusResult`. They cover the pass/fail/unknown branches and error propagation.

Gaps (minor): no test asserts the `overall_status="degraded"` + `total_failures>0` + `worst_severity=None` combination (see F1), and the adapter is only exercised against a `MagicMock` fake, not the real `DataQualityRepository` (see F4).

### Verification results

- **Independently verified (reviewer executed):**
  - `python -m pytest tests/agent/test_quality_adapter.py tests/agent/test_tools.py -q` → **94 passed** in 0.65s.
  - `python -m pytest tests/agent/ -q` → **134 passed** in 0.94s.
  - `python -m ruff check services/agent/quality_adapter.py services/agent/tools.py tests/agent/test_quality_adapter.py tests/agent/test_tools.py` → **All checks passed**.
  - `python -m ruff format --check services/agent/quality_adapter.py services/agent/tools.py tests/agent/test_quality_adapter.py tests/agent/test_tools.py` → **4 files already formatted**.
  - `python -m mypy tests/agent` → **Success: no issues found in 6 source files**.
- **Not run / unverified:**
  - Full repository `python -m pytest -q` and `python -m mypy` (whole configured gate `scripts/tests/libs`) were **not** rerun. The change is purely additive to `tests/agent` (in-gate, passed) and `services/agent` (outside the configured `[tool.mypy] files = ["scripts", "tests", "libs"]` scope), so regression risk to `scripts/` and `libs/` is negligible.
  - Integration tests are **not** applicable: TASK-096 is a read-only aggregation over the existing repository and does not touch Kafka, persistence writes, or S3/MinIO infrastructure boundaries.

---

## 5. Findings

### F1 — Moderate: `worst_severity` is derived only from recent checks, not the aggregate summary

- **File / line:** `services/agent/tools.py` — `get_data_quality()` (`worst = _worst_severity(recent_raw)`) and `_worst_severity()`.
- **Problem:** `worst_severity` is computed solely from `recent_raw` (the latest `limit` individual checks), while `overall_status` and `total_failures` are derived from the aggregate `summary`. If a check has historical failures (`failed_runs > 0` in the summary) but its most recent `limit` results all passed, the tool reports `overall_status="degraded"` and `total_failures>0` with `worst_severity=None`. The fields disagree, which can mislead agent reasoning about the severity of the degradation.
- **Impact:** Inconsistent structured output for a core use case (recently recovered but still historically failing checks).
- **Recommendation:** Derive `worst_severity` from the failure-bearing checks in both `summary` and `recent_checks` (or from `summary.severity` for entries with `failed_runs > 0`), and add a test covering the "summary has failures but recent checks pass" case.

### F2 — Moderate (pre-existing, surfaced here): summary `severity` inherits the lexicographic `MAX(severity)` bug

- **File / line:** `services/api/repositories/quality.py` — `func.max(DataQualityResult.severity)` (unchanged by TASK-096); consumed by `QualityCheckSummary.severity` and `_derive_overall_quality()`'s `s.severity == "error"` branch in `services/agent/tools.py`.
- **Problem:** The repository aggregates a check's severity with textual `MAX`, which orders `"error" < "info" < "warning"` — the inverse of the established `error > warning > info` vocabulary (`libs/quality/models.py`). This is already documented as F1 in `docs/reviews/TASK-068-review.md` and is not introduced by this diff, but TASK-096 now surfaces it directly to the agent: a check that has ever produced an `error` result can be summarized as `warning` or `info`.
- **Impact:** The `severity` shown in `QualityCheckSummary` can understate failures. `_derive_overall_quality()`'s error-severity branch is unreliable for that reason, though its practical effect on `overall_status` is currently masked because every failure branch returns `"degraded"`.
- **Recommendation:** Fix the repository aggregation to use an order-preserving severity expression (e.g. `MAX(CASE severity WHEN 'error' THEN 3 WHEN 'warning' THEN 2 ELSE 1 END)`) and add a mixed-severity test; until then, treat the summary `severity` field as best-effort in the agent.

### F3 — Minor: adapter repository is typed `Any`

- **File / line:** `services/agent/quality_adapter.py` — `def __init__(self, repository: Any)`.
- **Problem:** The concrete adapter is the one place the real `DataQualityRepository` contract is exercised, but the injected dependency is `Any`, so neither mypy nor the type checker validates the method names/signatures (`list_quality_checks(page=..., page_size=..., check_name=...)`, `list_quality_summary()`) or return shapes (`.items` of dataclasses).
- **Impact:** The contract is enforced only by tests, which use `MagicMock`. This is consistent with the existing `pipeline_status_adapter.py` (`repository: Any`) and the cross-service decoupling intent, so it is a low-risk maintainability note rather than a defect.
- **Recommendation:** Optionally define a narrow structural `Protocol` (or `Protocol`-based typing) for the two repository methods so the adapter is checked against the real interface without importing `services.api` internals.

### F4 — Minor: adapter is not tested against the real `DataQualityRepository`

- **File / line:** `tests/agent/test_quality_adapter.py` — `FakeRepo` uses `MagicMock` return values.
- **Problem:** The adapter tests would pass even if the real `DataQualityRepository` method names, keyword arguments, or `.items` structure changed, because the fake is a `MagicMock`. The task's central requirement ("reuse existing data-quality framework and persistence") is therefore not protected by an integration-style test.
- **Impact:** A future refactor of the repository interface could silently break the agent tool without a failing test. (The repository itself is separately covered by the API tests in `tests/api/routes/v1/test_quality.py` and `tests/api/test_milestone_gate.py`.)
- **Recommendation:** Add a test that instantiates `RepositoryDataQualityProvider` over the real repository backed by an in-memory SQLite session (the pattern already used by the API-side tests) and asserts the mapping, or at minimum assert against a hand-written fake whose attribute shape mirrors the real dataclasses.

---

## 6. Non-Defect Observations

- **N1 — Tool not yet wired into a LangGraph graph.** `get_data_quality()` is a standalone function with an injected provider, mirroring `get_pipeline_status()`. Routing/tool binding is explicitly deferred to TASK-098 (LangGraph routing) per `ai/ROADMAP.md` Milestone 11, so this is correct scope, not a gap.
- **N2 — "Quality trends" are point-in-time aggregates plus a recent-check list, not a time series.** `pass_rate`, `total_runs`, and `last_checked_at` give a trend summary, and `recent_checks` gives the latest `limit` results. This is a reasonable reading of the thin task spec; a true time-series trend view would be a follow-up.
- **N3 — `services/agent/` remains outside the configured mypy gate.** `pyproject.toml` sets `[tool.mypy] files = ["scripts", "tests", "libs"]`, so `tools.py`/`quality_adapter.py` are not type-checked by the repository gate. Consistent with TASK-092/093/094/095 and not introduced here; the in-gate test files pass (`mypy tests/agent` → success).
- **N4 — Broad `except Exception` in `get_data_quality()`.** This matches the existing tool conventions (`execute_read_only_sql`, `get_dataset_metadata`, `get_pipeline_status`) and returns a structured `ToolResponse(success=False, error=...)` rather than failing silently, so it is acceptable for a tool boundary.
- **N5 — Pass-rate guards against division by zero.** `pass_rate` computes `round(passed/total, 4)` only when `total_runs > 0`, otherwise `0.0`, which is correct and tested.

---

## 7. Verdict

`APPROVED WITH NON-BLOCKING FINDINGS`

The implementation satisfies the TASK-096 objective and acceptance behavior, reuses the existing `DataQualityRepository` (no duplicated SQL/aggregation), returns typed, structured results, and introduces no write access, secrets, dependencies, or architectural changes. All focused tests and repository checks pass when independently executed (94 targeted tests, 134 agent tests, `ruff check`, `ruff format --check`, `mypy tests/agent`).

The four findings are non-blocking. F1 (inconsistent `worst_severity`) and F2 (pre-existing severity aggregation bug now surfaced to the agent) are Moderate and worth addressing to improve the reliability of the surfaced quality signal; F3 and F4 are Minor maintainability/test-robustness notes.
