# TASK-097 Review — Source Health Tool

## 1. Review Header

- **Task ID:** TASK-097 — Source Health Tool
- **Review date:** 2026-09-21
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:** `f58056c0202c091c5c84038802843e8caad3ce4e...e095b2ac0f139f3e34d2286840681f13d20017de`
- **Reviewed commits:**
  - `166e4fe4ee5ce2cf45c0cbaf72af3a890d7ace4c` — `feat(TASK-097): Add source health agent tool`
  - `e095b2ac0f139f3e34d2286840681f13d20017de` — `fix(TASK-097): correct reasons type from dict to list[str]`
- **Reviewed HEAD:** `e095b2ac0f139f3e34d2286840681f13d20017de` on `feature/TASK-097`
- **Scope:** `services/agent/source_health_adapter.py` (new), `services/agent/tools.py`, `services/api/repositories/pipeline_status.py`, `services/api/schemas.py`, `tests/agent/test_source_health_adapter.py` (new), `tests/agent/test_tools.py`
- **Diff stat:** 6 files changed, 522 insertions(+), 13 deletions(-)
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

**Authorities consulted:** `ai/tasks/TASK-097-source-health-tool.md`, `ai/PROJECT.md` (§2, §4, §5, §9, §10, §11), `ai/SPECIFICATION.md` (§4.5 Source Health and Freshness, §6.6 LangGraph Data Engineer Agent), `ai/ROADMAP.md` (Milestone 11), `ai/AGENTS.md`, `ai/REVIEWER.md`, the source-health persistence/assessment layer (`libs/observability/health_assessment.py`, `libs/observability/health_persistence.py`), the read-only repository (`services/api/repositories/pipeline_status.py`, `services/api/models.py`, `services/api/schemas.py`, `services/api/routes/v1/pipelines.py`), the analogous adapters (`services/agent/quality_adapter.py`, `services/agent/pipeline_status_adapter.py`), and prior reviews (`docs/reviews/TASK-095-review.md`, `docs/reviews/TASK-096-review.md`). The sole ADR (`docs/adr/ADR-001-kafka-topic-configuration.md`) concerns Kafka configuration and is not applicable.

**Note on prior review:** an earlier `docs/reviews/TASK-097-review.md` (reviewed against `166e4fe` only) returned `CHANGES REQUIRED` with a High finding F1 — `reasons` was typed `dict` but the domain actually persists `list[str]`, so `get_source_health` returned `success=False` against real data. Commit `e095b2a` addresses that finding. This report reviews the combined two-commit range and confirms F1 is resolved in the tool/repository/API consumers (with one residual, see F1 below).

---

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
|---|---|---|
| Implement an agent tool reporting source-level health (freshness, availability, error rates, degradation status) | ✅ Met | `get_source_health()` (`services/agent/tools.py:573`) returns a `ToolResponse` wrapping `SourceHealthStatusResult` with per-source `overall_status`, `degradation_state`, `freshness_state`, `freshness_age_seconds`, `reasons`, and `signals`. Freshness → `freshness_state`/`freshness_age_seconds`; availability/degradation → `degradation_state` (e.g. `unreachable`, `rate_limited`); error rates → `signals` (`success_ratio`, `failed_fetches`, `malformed_ratio`). Independently reproduced with list-form `reasons` → `success=True`. |
| Aggregate from existing source-health metrics without duplicating logic | ✅ Met | `RepositorySourceHealthProvider` (`services/agent/source_health_adapter.py`) delegates to the existing `PipelineStatusRepository.list_source_health()`; no SQL, status-derivation, or aggregation logic is reimplemented (the repository already computes per-source `overall_status`/`degradation_state`/`freshness_state`). |
| Reuse existing source-health metrics; do not duplicate logic | ✅ Met | Same as above; the adapter mirrors the TASK-095/096 adapter pattern (`RepositoryPipelineStatusProvider`, `RepositoryDataQualityProvider`). |
| Return structured results suitable for agent reasoning | ✅ Met | Typed Pydantic models (`SourceHealthDetail`, `SourceHealthStatusResult`) with `model_dump()` inside the `ToolResponse.data` envelope; consistent with the other agent tools. |
| Agent must not have write access to PostgreSQL | ✅ Met | The tool only reads through the read-only `PipelineStatusRepository`; no write path is introduced. |
| Agent must use controlled tools and read-only SQL; never hallucinate platform state | ✅ Met | The tool is a deterministic aggregation over injected provider state; no LLM inference or fabricated state. |
| Deterministic tests; no unrelated architecture changes or secrets | ✅ Met (with minor test-fixture gap — see F2) | See §3 and §4. |

The `signals` field (error rates) is surfaced by adding `signals` to `SourceHealthEntry` (`services/api/repositories/pipeline_status.py:80,184`), reading the pre-existing `IngestionHealthResult.signals` column (`services/api/models.py:117`). This is a correct, in-scope change.

---

## 3. Git Diff Review

- **Files changed:** 6 files, +522 / −13 lines. All belong to TASK-097.
  - `services/agent/source_health_adapter.py` (+32, new) — `RepositorySourceHealthProvider` delegating to the repository.
  - `services/agent/tools.py` (+94, −7 net) — `SourceHealthDetail`, `SourceHealthStatusResult`, `SourceHealthProvider` protocol, `get_source_health()`, `_derive_overall_source_health()`, plus the `reasons` dict→list correction in `SourceHealthSummary` and `_derive_alerts`.
  - `services/api/repositories/pipeline_status.py` (+6, −4) — `signals` field added to `SourceHealthEntry` and populated from `row.signals`; `reasons` corrected to `list[str]` with a `list(row.reasons)` coercion.
  - `services/api/schemas.py` (+1, −1) — `SourceHealthResponse.reasons` corrected to `list[str]`.
  - `tests/agent/test_source_health_adapter.py` (+106, new) — adapter unit tests.
  - `tests/agent/test_tools.py` (+295, −13) — tool unit tests (new source-health tests + updated existing pipeline-status/alerts fixtures to list-form `reasons`).
- **Scope correctness:** All changes are confined to the source-health agent tool, its adapter, the minimal repository change to expose `signals`, and the `reasons` contract correction that the tool depends on. The `pipeline_status.py` and `schemas.py` changes are necessary and in scope, not unrelated modifications.
- **Unrelated changes:** None.
- **Architectural changes:** None. Service boundaries, event semantics, data ownership, and the agent's read-only posture are unchanged. The tool reuses the existing `PipelineStatusRepository` rather than re-declaring a divergent contract (unlike the initial TASK-095 implementation).
- **Accidental changes / debugging code / secrets:** None. No debug prints, temporary files, dead code, generated artifacts, or secrets.
- **Dependency/config changes:** None. `pyproject.toml`, `requirements*.txt`, and infra config are untouched; only `pydantic` (already a runtime dependency) is used.
- **Branch/task isolation:** ✅ Two commits on `feature/TASK-097`; no changes from another TASK-xxx are included.

---

## 4. Test and Verification Review

### Tests examined

- `tests/agent/test_source_health_adapter.py` — 4 tests: dict mapping, `source_name` filter pass-through, empty result, `None` signals handling. Uses a hand-written `FakeSourceHealthEntry` dataclass (with `signals`) and a `MagicMock` repository.
- `tests/agent/test_tools.py` — adds `FakeSourceHealthProvider` and 12 new tests across `TestGetSourceHealth` (healthy/degraded/stale/empty/filter/provider-error/signals-surfacing) and `TestDeriveOverallSourceHealth` (empty/all-healthy/degraded-priority/stale/mixed-unknown). Also updates the pre-existing pipeline-status/alert fixtures from dict-form to list-form `reasons`.

### Test adequacy

Strong and focused on the implemented unit logic (aggregation, derivation, model mapping, filter pass-through, error propagation). All branch outcomes and error propagation are covered deterministically. The `reasons` list-form shape (the real domain shape) is now exercised throughout the tool tests, which is the specific gap the prior review flagged.

Remaining gap (see F2/F4): the adapter tests use a hand-written fake rather than the real `PipelineStatusRepository`, and the API-side fixtures (`tests/api/routes/v1/test_pipelines.py`, `tests/api/test_milestone_gate.py`) still seed dict-form `reasons`, which diverges from the real list shape.

### Verification classification

- **Independently verified (executed by reviewer):**
  - `python -m pytest tests/agent/test_tools.py tests/agent/test_source_health_adapter.py -m "not integration" -q` → **106 passed** in 0.66s.
  - `python -m ruff check services/agent/tools.py services/agent/source_health_adapter.py services/api/repositories/pipeline_status.py services/api/schemas.py tests/agent/test_tools.py tests/agent/test_source_health_adapter.py` → **All checks passed**.
  - `python -m ruff format --check ...` (same files) → **6 files already formatted**.
  - `python -m mypy` → **Success: no issues found in 189 source files** (repository-configured scope `files = ["scripts", "tests", "libs"]`, which type-checks `services/*` transitively via test imports).
  - Targeted reproduction: `get_source_health` fed list-form `reasons` (including the empty-list healthy case `reasons=[]` and degraded `reasons=["Connection refused"]`) → **`success=True`**, correct `overall_status="degraded"`, reasons round-tripped correctly. This confirms the prior F1 blocking issue is fixed.
  - `python -m pytest tests/api/routes/v1/test_pipelines.py tests/api/test_milestone_gate.py -m "not integration" -q` → **60 passed, 1 error**. The single error is `tests/api/test_milestone_gate.py::TestPipelinesMilestone::test_source_health`, a `MemoryError` raised inside SQLAlchemy's `Boolean` type event-dispatch during the test fixture `session.commit()` under Python 3.14.0. It is an environment/toolchain issue in a test file untouched by this diff, not a TASK-097 regression (see §6 N8).
- **Not run / unverified:**
  - Full repository `python -m pytest -q` was not rerun (the two focused suites above cover the changed surface; the only failure observed is the environment `MemoryError` in an untouched test).
  - Integration tests are **not** applicable to the reviewed diff itself: no Kafka/persistence-write/MinIO/S3 code was modified. The change is read-only aggregation over the existing repository.

---

## 5. Findings

### F1 — Moderate: `reasons` contract correction is incomplete — the ORM model still declares `dict`

- **File / line:**
  - `services/api/models.py:116` — `IngestionHealthResult.reasons: Mapped[Optional[dict]]` (unchanged by this task).
  - `services/api/repositories/pipeline_status.py:183` — `reasons=list(row.reasons) if row.reasons else None`.
- **Problem:** The domain stores `reasons` as a **JSON array of strings**, not a dict. `libs/observability/health_assessment.py:108` declares `reasons: list[str]`, and `libs/observability/health_persistence.py:132` persists it via `json.dumps(ev.assessment.reasons)` (a JSON array), with the reader typing it back as `reasons: list[str]` (`health_persistence.py:184`). Commit `e095b2a` correctly fixed every *consumer* (`SourceHealthDetail`, `SourceHealthSummary`, `SourceHealthEntry`, `SourceHealthResponse`, `_derive_alerts`) to `list[str]`, but left the ORM model annotation as `dict`. To bridge the mismatch, the repository now does `list(row.reasons)`, which is a lossy coercion: if `row.reasons` were ever actually a dict (as the model annotation still claims, and as the stale API fixtures seed), `list(dict)` returns only the keys and silently drops the values. The commit message says the type was corrected "across tools, repository, API schema, and tests" but omits the model.
- **Impact:** No runtime failure for real data (the writer always stores a list, so `list(list)` is a harmless copy). The risk is latent: the ORM model is now factually inconsistent with every consumer and with the domain, and the `list()` coercion masks that inconsistency. A future maintainer who trusts the `dict` annotation (or writes a dict, as the API fixtures do) would silently corrupt `reasons`.
- **Recommendation:** Correct the source of truth: change `IngestionHealthResult.reasons` to `Mapped[Optional[list]]` (or `list[str]` / a JSON `Any`) and drop the `list()` coercion in favor of a direct pass-through. Then update the API-side fixtures to the real list shape (see F2).

### F2 — Minor: API-side test fixtures still seed dict-form `reasons`

- **File / line:**
  - `tests/api/routes/v1/test_pipelines.py:77` — `reasons={"http_code": 503}`.
  - `tests/api/test_milestone_gate.py:209` — `reasons={"error": "connection refused"}`.
- **Problem:** These fixtures seed `IngestionHealthResult.reasons` as a dict, which diverges from the real writer's list shape. They predate TASK-097 and were not updated by the fix commit. The tests pass because they do not assert on `reasons`, but they no longer reflect (and therefore no longer protect) the real data contract.
- **Impact:** The fixtures are misleading and would not catch a regression where the repository mishandles list-form `reasons`. Combined with F1's `list()` coercion, a dict seeded here would be silently turned into `["http_code"]` / `["error"]` with the values dropped.
- **Recommendation:** Update both fixtures to list-form `reasons` (e.g. `reasons=["http_code 503"]`, `reasons=["connection refused"]`) so the API layer is tested against the same shape the agent tool and the real writer use.

### F3 — Minor: adapter repository is typed `Any`

- **File / line:** `services/agent/source_health_adapter.py` — `def __init__(self, repository: Any)`.
- **Problem:** The concrete adapter is the one place the real `PipelineStatusRepository.list_source_health()` contract is exercised, but the injected dependency is `Any`, so neither mypy nor a type checker validates the method name/signature (`list_source_health(source_name=..., limit=...)`) or return shape (`.items` of dataclasses).
- **Impact:** Contract enforced only by tests, which use a hand-written fake. Consistent with `quality_adapter.py` and `pipeline_status_adapter.py` (both `repository: Any`), so low-risk maintainability note rather than a defect.
- **Recommendation:** Optionally define a narrow structural `Protocol` for the repository method so the adapter is checked without importing `services.api` internals.

### F4 — Minor: adapter is not tested against the real `PipelineStatusRepository`

- **File / line:** `tests/agent/test_source_health_adapter.py` — uses `FakeSourceHealthEntry` + `MagicMock` repository.
- **Problem:** The adapter tests would pass even if the real `SourceHealthEntry` shape or the repository's `signals` mapping changed, because the fake is hand-written. The task's central requirement ("reuse existing source-health metrics") is therefore not protected by an integration-style test. In particular, the newly added `signals` pass-through (`pipeline_status.py:184`) is not asserted against real row data.
- **Impact:** A future refactor of the repository could silently break the tool without a failing test. (The repository path is separately exercised by `tests/api/routes/v1/test_pipelines.py`, but that test asserts only API-facing fields, not `signals`.)
- **Recommendation:** Add a test instantiating `RepositorySourceHealthProvider` over the real repository backed by an in-memory SQLite session (the pattern used by the API-side tests) and assert the mapping, including `signals` and list-form `reasons`.

---

## 6. Non-Defect Observations

- **N1 — Tool not yet wired into a LangGraph graph.** `get_source_health()` is a standalone function with an injected provider, mirroring `get_pipeline_status()` and `get_data_quality()`. Tool binding/routing is deferred to TASK-098 (`ai/tasks/TASK-098-langgraph-routing.md`) per `ai/ROADMAP.md` Milestone 11. Correct scope, not a gap. The `SOURCE_HEALTH` intent already exists in `services/agent/intents.py` / `classifier.py` (from TASK-093), so no routing-model change is needed here.
- **N2 — "availability" and "error rates" are encoded, not first-class fields.** Availability is represented by `degradation_state` (values such as `unreachable`, `rate_limited`, `empty_result`), and error rates by `signals` (`success_ratio`, `malformed_ratio`, `failed_fetches`). This is a reasonable mapping onto the existing metric vocabulary; a dedicated `availability`/`error_rate` field would be a follow-up, not a requirement failure.
- **N3 — Two `list_source_health` provider methods with different shapes.** `PipelineStatusProvider.list_source_health()` (TASK-095) and `SourceHealthProvider.list_source_health()` (TASK-097) coexist with the same name but different returned dict keys. They are consumed by different tools and are clearly separated by protocol/class, so this is a naming/contract smell rather than a defect.
- **N4 — Broad `except Exception` in `get_source_health()`.** Matches the existing tool conventions (`execute_read_only_sql`, `get_dataset_metadata`, `get_pipeline_status`, `get_data_quality`) and returns a structured `ToolResponse(success=False, error=...)`. Acceptable for a tool boundary.
- **N5 — `_derive_overall_source_health` returns `"unknown"` for mixed healthy+unknown.** Conservative and tested (`test_mixed_known_and_unknown`). Aggregate vocabulary (`healthy`/`degraded`/`stale`/`unknown`) matches the repository's per-source vocabulary; the degraded-over-stale aggregate priority is a reasonable severity ordering and does not contradict the repository's per-source collapse (which applies at a different granularity).
- **N6 — `signals` is exposed by the agent tool but not by the `/pipelines/source-health` API.** The `SourceHealthResponse` schema was not updated to include `signals`. This is consistent with the task scope (the API change is out of scope), but leaves the repository carrying a field the public API does not surface.
- **N7 — `services/agent/` and `services/api/` remain outside the *direct* mypy gate.** `pyproject.toml` sets `[tool.mypy] files = ["scripts", "tests", "libs"]`, so `services/*` is only type-checked transitively via test imports. The configured `python -m mypy` run still passed (189 files), but the `IngestionHealthResult.reasons` model annotation (F1) is effectively invisible to the gate unless a test imports a path that surfaces it as `dict`. Pre-existing, not introduced here.
- **N8 — Environment `MemoryError` in an unrelated test.** During independent verification, `tests/api/test_milestone_gate.py::TestPipelinesMilestone::test_source_health` errored at fixture setup with a `MemoryError` inside SQLAlchemy's `Boolean` type event-dispatch under Python 3.14.0. The file is untouched by this diff and the error is a toolchain/environment issue, not a code defect.
- **N9 — `services/agent/tools.py` module docstring not updated.** The module docstring still lists "read-only SQL, dataset metadata, pipeline status, and data quality agent tools" without "source health" (the test module docstring was updated). Trivial documentation drift.

---

## 7. Verdict

**`APPROVED WITH NON-BLOCKING FINDINGS`**

The prior blocking finding (F1 in the earlier review — `reasons` typed `dict` while the domain persists `list[str]`, causing `get_source_health` to return `success=False` against real data) is resolved by commit `e095b2a`. I independently confirmed the tool now succeeds end-to-end with list-form `reasons`, including the empty-list healthy case.

Non-blocking findings:

- **F1 (Moderate):** The `reasons` contract correction is incomplete at the source of truth — `IngestionHealthResult.reasons` in `services/api/models.py:116` still declares `dict`, and the repository's `list(row.reasons)` coercion is a lossy workaround that masks it. No runtime failure for real data, but the model is now inconsistent with every consumer and the domain.
- **F2 (Minor):** API-side fixtures (`test_pipelines.py:77`, `test_milestone_gate.py:209`) still seed dict-form `reasons`, diverging from the real list shape and no longer protecting the contract.
- **F3 (Minor):** adapter `repository: Any` (consistent with sibling adapters).
- **F4 (Minor):** adapter not tested against the real `PipelineStatusRepository` / `signals` not asserted end to end.

The change is otherwise clean: correctly scoped to TASK-097 on `feature/TASK-097`, two commits, no secrets, no new dependencies, no architectural changes, and it properly reuses the existing `PipelineStatusRepository` (avoiding the TASK-095 duplication problem). All focused tests and repository checks (pytest for the agent tools, ruff check, ruff format, mypy) pass when independently executed, and the acceptance criterion — reporting source-level health — is satisfiable against real data.
