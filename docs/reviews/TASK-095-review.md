# TASK-095 — Pipeline Status Tool — Review

## 1. Review Header

- **Task ID:** TASK-095 — Pipeline Status Tool
- **Review date:** 2026-09-21
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed commit:** `651124d4cdad8e1849d9b795f338b24efdb2bf9a` (`fix(TASK-095): Add Kafka consumer lag, processing rate, and last write timestamp`)
- **Reviewed Git range:** `8d5ffa0ee26c9392e9ce03031789e8f0fd95792f..651124d4cdad8e1849d9b795f338b24efdb2bf9a` (two commits: `dae098d`, `651124d`)
- **Branch:** `feature/TASK-095` (working tree clean except the untracked review file)
- **Scope:** `services/agent/tools.py`, `tests/agent/test_tools.py`
- **Diff stat:** `2 files changed, 724 insertions(+), 4 deletions(-)`
- **Verdict:** `CHANGES REQUIRED`

**Authorities consulted:** `ai/PROJECT.md`, `ai/SPECIFICATION.md` (§16–§18, Metrics/Observability), `ai/tasks/TASK-095-pipeline-status-tool.md`, `ai/tasks/TASK-094-read-only-sql-and-dataset-metadata-tools.md`, `ai/AGENTS.md`, `ai/REVIEWER.md`. `docs/adr/ADR-001-kafka-topic-configuration.md` (Kafka topic/partition config) is not materially relevant to this change.

> Note: a prior partial review of only the first commit (`dae098d`) exists in this file's history. This report supersedes it and covers the full two-commit range up to HEAD `651124d`. The second commit (`651124d`) was authored in response to the prior review and resolves its "missing signals" finding (F1) and its `reasons` string-coercion finding (F4).

---

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
|---|---|---|
| Implement an agent tool reporting current pipeline health | ✅ Met | `get_pipeline_status()` (`services/agent/tools.py:230`) returns `PipelineStatusResult` (overall health, recent runs, total runs, source health, alerts, consumer lag, processing rate, last write). |
| Report **Kafka consumer lag** | ✅ Met (unit-level) | `_aggregate_lag()` (`tools.py:284`) aggregates `get_lag_samples()` into `ConsumerLagSummary` (`tools.py:197`), exposed as `consumer_lag`. Caveat: the provider contract is dict-based and is **not** wired to `KafkaMetrics.lag_snapshot()`, which returns `LagSample` dataclasses — see F2. |
| Report **recent processing rates** | ✅ Met | `_compute_processing_rate()` (`tools.py:296`) derives a rate (`records_loaded / duration`) over completed runs, exposed as `processing_rate` (`tools.py:213`). Minor: a single aggregate float, not per-run "rates" — see N2. |
| Report **last successful write timestamps** | ✅ Met | `_last_successful_write()` (`tools.py:326`) returns `finished_at` of the first `healthy` run with a `finished_at`, exposed as `last_successful_write_at` (`tools.py:214`). Minor semantic caveat — see N3. |
| Report **any active alerts** | ✅ Met | `_derive_alerts()` (`tools.py:352`) derives `pipeline_failure`, `source_degraded`, and `source_stale` alerts. |
| Aggregate from existing metrics/health endpoints **without duplicating logic** | ❌ Not met | The tool declares a new dict-based `PipelineStatusProvider` protocol (`tools.py:217`) that is not backed by the existing `PipelineStatusRepository` (`services/api/repositories/pipeline_status.py`) or the `/pipelines` / `/pipelines/source-health` endpoints, and no concrete implementation exists anywhere in the repository. |
| Reuse existing health/freshness/metrics endpoints | ❌ Not met | Same as above. The tool re-declares a parallel data contract (`list[dict]`) and re-derives status/alert logic that already exists in the repository — see F2/F3. |
| Return structured data for agent reasoning and user display | ✅ Met | Pydantic models `PipelineRunSummary`, `SourceHealthSummary`, `PipelineAlert`, `ConsumerLagSummary`, `PipelineStatusResult` with the `ToolResponse` envelope. |
| No write access to PostgreSQL | ✅ Met | The tool performs no writes; it reads only via the injected provider protocol. |
| Deterministic tests | ✅ Met | 75 tests pass (independently re-run). See §4. |
| No unrelated architecture changes or secrets | ✅ Met | See §3. |

---

## 3. Git Diff Review

- **Scope correctness:** Both commits are confined to `services/agent/tools.py` (adds the pipeline-status tool, models, and derivation/aggregation helpers) and `tests/agent/test_tools.py` (adds pipeline-status tests). Both belong to TASK-095.
- **Diff stat:** `2 files changed, 724 insertions(+), 4 deletions(-)`.
- **Branch/task isolation:** Correct. Two commits (`dae098d`, `651124d`) on `feature/TASK-095`; the range contains only these two commits, both tagged TASK-095. No other TASK-xxx changes are mixed in.
- **Unrelated changes:** None. The only edits to pre-existing code are the module docstring (two lines), the test module docstring, and the import of `Optional`/`Field` — all required by the new code.
- **Architectural changes:** None to service boundaries, event semantics, or data ownership. The LangGraph agent remains read-only over injected providers.
- **Accidental changes / debug code / secrets / generated artifacts:** None found. No new dependencies, no config/infra changes, no secrets, no temporary or dead files.
- **Tests weakened:** No. Existing tests are untouched; new tests are additive.

**Out-of-scope note:** No changed lines are out of scope. However, the *substance* of the tool remains under-scoped relative to one explicit task requirement: it does not reuse the existing health/metrics endpoints or repository (see F2/F3).

---

## 4. Test and Verification Review

### Tests examined

`tests/agent/test_tools.py` adds a `FakePipelineStatusProvider` and the following test classes:

- `TestGetPipelineStatus` — healthy, degraded (failure), degraded source, stale source, empty/unknown, limit pass-through, provider error, multiple alerts.
- `TestDeriveOverallPipelineHealth` — healthy/failed/degraded/stale/unknown derivations.
- `TestDeriveAlerts` — no-alert, pipeline-failure, source-degraded (with reasons), source-stale, stale-unknown-age.
- `TestPipelineStatusModels` — model defaults and serialization.
- `TestConsumerLag` — lag aggregation by topic, empty lag, lag surfaced in `get_pipeline_status`.
- `TestProcessingRate` — rate from completed runs, `None` when no completed runs, rate surfaced in `get_pipeline_status`.
- `TestLastSuccessfulWrite` — last write from healthy run, `None` when no success, last write surfaced in `get_pipeline_status`.

### Test adequacy

- The tests are **deterministic and well-focused on the implemented unit logic** (aggregation, derivation, and model mapping). The second commit's additions specifically cover the three newly-added signals (lag, rate, last write), which addresses the prior review's breadth gap.
- The tests are **still inadequate against the "reuse existing endpoints / do not duplicate logic" requirement**: no test exercises the tool against the real `PipelineStatusRepository` or the existing health/metrics endpoints. The `FakePipelineStatusProvider` returns dicts that conveniently match the tool's expected keys; it does not validate that a real provider actually satisfies the protocol — and, as written, the real repository/`KafkaMetrics` do **not** (they return dataclasses, not dicts). See F2.

### Verification classification

- **Independently verified (executed by reviewer):**
  - `python -m pytest tests/agent/test_tools.py -q` → **75 passed** in 0.60s.
  - `python -m ruff check services/agent/tools.py tests/agent/test_tools.py` → **All checks passed**.
  - `python -m ruff format --check services/agent/tools.py tests/agent/test_tools.py` → **2 files already formatted**.
  - `python -m mypy` (repository-configured check) → **FAILED with 3 errors** (see F6).
- **Not completed:** `python -m pytest -q` (full unit suite) timed out at 120s and was not completed. The change-touching tests (`tests/agent/test_tools.py`) were independently verified as above.
- **Unverified:** No integration tests were run (`python -m pytest -m integration`). This is acceptable for the changed code itself — no Kafka/persistence/MinIO/S3 code was modified; the tool is a pure function over an injected provider. However, because the task objective nominally surfaces "Kafka consumer lag," the fact that no concrete provider wires the tool to `KafkaMetrics.lag_snapshot()` means there is nothing integration-testable yet (see F2).

---

## 5. Findings

### F2 — High: Tool does not reuse the existing health/status endpoints or repository, and is not backed by any concrete data source

- **File / line:** `services/agent/tools.py` — `PipelineStatusProvider` (lines 217–227), `get_pipeline_status()` (line 230), `_aggregate_lag()` (line 284).
- **Problem:** The task requires "aggregate data from existing metrics/health endpoints without duplicating logic" and "reuse existing health/freshness/metrics endpoints." The repository already contains `PipelineStatusRepository` (`services/api/repositories/pipeline_status.py`) with `list_pipeline_runs`, `get_pipeline_run`, `list_source_health`, and derivation helpers (`_derive_overall_status`, `_derive_pipeline_status`), exposed via `GET /pipelines` and `GET /pipelines/source-health`. It also contains `KafkaMetrics.lag_snapshot()` (returns `list[LagSample]`, a frozen dataclass with `topic`/`partition`/`lag`). The tool instead declares a new `PipelineStatusProvider` protocol with dict-based signatures that do **not** match any of these (`list_recent_runs(limit)` vs `list_pipeline_runs(page, page_size, status)`; `get_total_run_count()` has no repository counterpart; `list_source_health()` has no args vs the repository's `list_source_health(source_name, limit)`; `get_lag_samples()` returns `list[dict]` vs `lag_snapshot()` returning `list[LagSample]`). No concrete implementation of the protocol exists anywhere in the repository (confirmed by grep across `services/`). The second commit extended this parallel protocol (`get_lag_samples()`) rather than consuming the existing lag source.
- **Impact:** The tool is effectively orphaned from real platform state: as merged, it cannot be backed by the existing repository or `KafkaMetrics` without an adapter that was never written. It duplicates the data-contract/status-semantics concept rather than reusing it, which is exactly what the task told the implementer to avoid. This remains the primary gap against the task objective.
- **Recommendation:** Wire the tool to the existing `PipelineStatusRepository` (or a thin adapter over it / the `/pipelines` endpoints) and to `KafkaMetrics.lag_snapshot()`, reusing the existing dataclasses and derivation helpers. Either adapt the repository's dataclass returns into the tool's models directly, or redefine the provider protocol to match the existing repository/`KafkaMetrics` signatures so a concrete provider can be written with no duplicated derivation. Add `get_total_run_count()` (or reuse `list_pipeline_runs(...).total`) on the existing repository rather than inventing a new parallel contract. Add a test exercising the tool against the real repository/`KafkaMetrics`.

### F6 — High: Repository mypy check fails on the reviewed change

- **File / line:** `services/agent/tools.py:330` (`return r["finished_at"]` in `_last_successful_write`); `tests/agent/test_tools.py:590` (`test_multiple_alerts`) and `:822` (`test_last_write_from_healthy_run`).
- **Problem:** `python -m mypy` (the repository-configured check) now reports 3 errors, all in files changed by the reviewed range:
  - `services/agent/tools.py:330: Returning Any from function declared to return "str | None"` — `_last_successful_write` returns `r["finished_at"]` (typed `Any` from `dict[str, Any]`).
  - `tests/agent/test_tools.py:590: Argument "runs" ... has incompatible type "list[object]"; expected "list[dict[str, Any]] | None"` — the heterogeneous dict literal in `test_multiple_alerts` is inferred as `list[object]`.
  - `tests/agent/test_tools.py:822: Argument 1 to "_last_successful_write" has incompatible type "list[object]"; expected "list[dict[str, Any]]"` — same inference issue in `test_last_write_from_healthy_run`.
- **Impact:** This fails a required repository quality check and violates AGENTS.md §7/§14 ("repository checks passing"). A CI type-check gate would fail. The regression was introduced by the reviewed range (the first commit introduced `test_multiple_alerts`; the second introduced `_last_successful_write` and `test_last_write_from_healthy_run`).
- **Recommendation:** Annotate the fixture literals with an explicit `list[dict[str, Any]]` type (or `cast`), and coerce the `Any` return (`return str(r["finished_at"])`, or validate/coerce earlier). This is a trivial, mechanical fix but must be done to restore the required check.

### F3 — Moderate: Status/alert derivation logic diverges from the existing repository semantics

- **File / line:** `services/agent/tools.py` — `_derive_overall_pipeline_health()` (line 334), `_derive_alerts()` (line 352) vs `services/api/repositories/pipeline_status.py` — `_derive_pipeline_status()` / `_derive_overall_status()`.
- **Problem:** The repository maps run `status` `running`/`success` → `"healthy"`, `failed` → `"failed"`, else `"unknown"`, and derives source status with a richer degraded-state set (`unreachable`, `rate_limited`, `structurally_changed`, `partially_parseable`, `empty_result`) plus a `stale` freshness override. The new tool introduces its own aggregate vocabulary (`"healthy"` / `"degraded"` / `"unknown"`) and its own alert rules, reacting only to `overall_status == "failed"` (runs) and `"degraded"`/`"stale"` (sources) — values it assumes the (nonexistent) provider already computed.
- **Impact:** Two independent derivations of pipeline/source health now coexist with different vocabularies. A user/agent may receive different health words from `GET /pipelines/source-health` and from this tool — the exact "duplicate business logic" the task directed the implementer to avoid.
- **Recommendation:** Collapse to a single derivation source (the repository's), keeping the tool as a pure aggregation/formatting layer that reuses already-derived statuses rather than re-deriving them.

### F5 — Minor: Inconsistent key access in `get_pipeline_status`

- **File / line:** `services/agent/tools.py` — lines 240–246, 250–255, 268–271.
- **Problem:** Required fields are accessed with direct subscript (`r["run_type"]`, `r["overall_status"]`, `r["started_at"]`, `s["source_name"]`, `s["overall_status"]`, `s["freshness_state"]`), while optional fields use `.get(...)`. A missing required key raises `KeyError`, caught only by the broad `try/except` and returned as an opaque raw error string.
- **Impact:** Cosmetic/robustness inconsistency; a missing key produces an opaque failure rather than a clear contract violation. Low priority.
- **Recommendation:** Validate the provider contract on the input side with Pydantic models, or document the required-key assumption.

### F7 — Minor: `_aggregate_lag` is not robust to non-`int` / `None` lag values

- **File / line:** `services/agent/tools.py` — `_aggregate_lag()` (lines 284–293).
- **Problem:** `s.get("lag", 0)` returns `None` when the `lag` key is present with a `None` value (the default only applies when the key is absent), which would make `0 + None` raise `TypeError`; a float lag would produce a float that Pydantic then rejects against `total_lag: int`. The broad `try/except` in `get_pipeline_status` would mask both as a generic tool failure.
- **Impact:** Low — only manifests with malformed/mismatched provider data, but a single bad sample degrades the whole response.
- **Recommendation:** Coerce with `int(s.get("lag") or 0)` and treat non-numeric lag defensively.

---

## 6. Non-Defect Observations

- **N1 — Test quality is strong for what was implemented.** Aggregation, derivation, and model mapping are well covered with deterministic, readable tests; 75 tests pass and lint/format are clean. The second commit directly addresses the prior review's breadth gap on lag/rate/last-write.
- **N2 — "Processing rate" is a single aggregate, not per-run rates.** The task says "recent processing rates" (plural); the tool returns one `Optional[float]` (`records_loaded / total_seconds` across all completed recent runs). This is a defensible interpretation but narrower than the plural wording implies. Not a defect, but worth confirming intent.
- **N3 — `last_successful_write_at` is a run-finish proxy, not a distinct "write" timestamp.** It is derived as the `finished_at` of the first `healthy` run in list order (and therefore depends on the provider returning newest-first, as the real repository does via `started_at DESC`). If the domain needs a true last-write (Parquet/PostgreSQL) timestamp, a dedicated metric would be required.
- **N4 — Inline import inside `_compute_processing_rate`.** `from datetime import datetime` is declared inside the loop body (`tools.py:311`). Harmless, but inconsistent with the module's top-level imports; `datetime` should be imported at module scope.
- **N5 — The standalone-function-with-`Protocol` pattern is consistent with TASK-094.** `get_pipeline_status` follows the same shape as `execute_read_only_sql` / `get_dataset_metadata` (pure function over a test-double protocol returning `ToolResponse`). The convention is fine and appropriate as a unit-test seam; the TASK-095-specific problem is that a real backing repository/`KafkaMetrics` already exists and was not reused. Being "unwired to the agent graph" is itself expected at this stage (routing is a later task, `TASK-098`), so this is **not** a defect — the defect is the divergent data contract, not the absence of graph wiring.
- **N6 — AGENTS.md vs `pyproject.toml` mypy command mismatch.** AGENTS.md §7 instructs `mypy src/`, but the repository has no `src/` directory; `pyproject.toml` sets `files = ["scripts", "tests", "libs"]`. Running `python -m mypy` (no args) follows imports into `services/` and surfaces the F6 errors. This is a pre-existing governance/config mismatch, not introduced by this task, but it is why the type regression in `services/agent/tools.py` only surfaces transitively.

---

## 7. Verdict

**`CHANGES REQUIRED`**

Blocking findings:

- **F2 (High):** The tool does not aggregate from the existing `PipelineStatusRepository` / health/metrics endpoints or `KafkaMetrics.lag_snapshot()` as the task explicitly requires. It introduces a parallel, dict-based `PipelineStatusProvider` protocol with no concrete implementation, and duplicates status/alert derivation logic. The tool is not backed by any real platform state as merged.
- **F6 (High):** The repository's configured `mypy` check fails with 3 errors, all in files changed by the reviewed range (a type-check regression that violates AGENTS.md's "repository checks passing" DoD criterion).

Non-blocking but should be addressed with the same change: F3 (divergent derivation semantics), F5 and F7 (minor robustness issues).

Resolved from the prior (partial) review: F1 (missing Kafka lag / processing rate / last-write signals) is now implemented and unit-tested; F4 (`reasons.values()` string coercion) is fixed.

The change is cleanly scoped to TASK-095, on the correct branch, with no secrets, no unrelated changes, and passing unit/lint/format checks. The second commit meaningfully closes the "missing signals" gap. It should not be accepted until the tool is wired to the existing endpoints/repository/metrics source rather than a duplicated contract, and the type-check regression is repaired.
