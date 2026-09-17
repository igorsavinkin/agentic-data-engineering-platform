# TASK-054 Review — Freshness Failure Scenarios

## 1. Review Header

- **Task:** TASK-054 — Freshness Failure Scenarios
- **Review date:** 2026-09-17
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `b52368e1ac9ab78bf919dba7b00c6144395d8ee8...0e6cfcf5c95a29cab7472ab1994e7124037d6634`
  - `0e6cfcf5c95a29cab7472ab1994e7124037d6634` — `feat(TASK-054): Add source degradation detection for freshness failures`
- **Reviewed HEAD:** `0e6cfcf5c95a29cab7472ab1994e7124037d6634` on `feature/TASK-054`
- **Scope:** `libs/observability/__init__.py`, `libs/observability/health_assessment.py`, `libs/observability/source_metrics.py`, `tests/test_observability/test_freshness_failures.py` (new). 4 files, +698/−16. No existing tests removed or weakened.
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

---

## 2. Requirements Coverage

Sources: `ai/tasks/TASK-054-freshness-failure-scenarios.md`, `ai/PROJECT.md` §9/§10, `ai/SPECIFICATION.md` §4.5, `ai/tasks/TASK-040-*.md`, `ai/tasks/TASK-053-*.md`.

| Requirement | Status | Implementation evidence |
|---|---|---|
| Define freshness using established collection/observation timestamp semantics | Met | `SourceFreshness` (TASK-040) records `last_successful_fetch`; TASK-054 adds a clock-injectable `SourceFreshness` and reuses `calculate_freshness_age_seconds()` as the freshness signal. |
| Track last successful usable observation/collection as appropriate to existing source-health design | Met (partial) | `SourceMetrics.record_fetch_success()` now refreshes `last_successful_fetch` only when `records_emitted > 0`. The source-health tracker gains `update_freshness_age()`, but nothing in production feeds it (see Finding #1). |
| Add configurable freshness thresholds rather than hard-coding environment-specific values | Met | `SourceHealthConfig.max_freshness_age_seconds` (added in TASK-053) is now read by both `get_freshness_state()` and `assess()`; `None` disables the check. Defaults remain `None`, and tests configure explicit thresholds. |
| Distinguish failing-but-fresh / stale / never-collected / zero-result / recovery | Met | `FreshnessState` (`FRESH`/`STALE`/`NEVER_COLLECTED`) plus `SourceDegradationState.STALE`; zero-result is `FETCH_SUCCESS` + `ZERO_RECORD_FETCHES` without freshness refresh; recovery covered by `test_scenario_recovery_refreshes_state`. |
| Ensure retries do not falsely refresh freshness when no usable data was obtained | Met | `record_fetch_success` gates freshness on `records_emitted > 0`; `test_scenario_retry_without_usable_data` asserts the timestamp is unchanged. |
| Expose freshness state programmatically for later `ingestion_health`/data-quality Airflow work | Met (partial) | `FreshnessState` enum, `get_freshness_state()`, and `freshness_age_seconds`/`max_freshness_age_seconds` signals are public and exported from `libs.observability`. No production consumer yet (see Finding #1). |
| Use deterministic clock injection/freezing in tests | Met | `clock` callable injected into `SourceFreshness`, `SourceMetrics`, `SourceHealthTracker`, and `SourceHealthAssessor`; all 27 new tests use a frozen/mutable clock. |
| Do not implement Airflow DAGs or alert notifications | Met | No Airflow, alerting, or delivery code introduced. |

**Tests required by the task** — all present:

| Required test | Status | Test(s) |
|---|---|---|
| fresh source | ✅ | `test_scenario_fresh_source`, `test_fresh_source_within_threshold` |
| threshold boundary | ✅ | `test_scenario_threshold_boundary`, `test_threshold_boundary_exactly_at_threshold` |
| stale source | ✅ | `test_scenario_stale_source`, `test_stale_source_exceeds_threshold` |
| never-successful source | ✅ | `test_scenario_never_successful`, `test_never_collected_freshness_state` |
| failed run after prior success | ✅ | `test_scenario_failed_run_after_prior_success` |
| zero-result semantics | ✅ | `test_scenario_zero_result_semantics`, `test_zero_result_does_not_set_freshness` |
| recovery refreshes state | ✅ | `test_scenario_recovery_refreshes_state` |
| retry without usable data does not refresh freshness | ✅ | `test_scenario_retry_without_usable_data` |

---

## 3. Git Diff Review

- **Scope correctness:** Correct. All four files belong to TASK-054. The change activates the previously-dead `max_freshness_age_seconds` config (flagged in the TASK-053 review as Finding #4) and adds freshness classification. The new test module is source-agnostic but uses `source_name="premium_retailer"` (the difficult source) for the scenario tests, as required.
- **Unrelated changes:** None.
- **Architectural changes:** None. No Kafka/processor/lake/warehouse/schema changes; no source-adapter isolation or canonical contract changes.
- **Accidental/debug/dead code:** No debugging artifacts, temporary files, generated artifacts, or secrets. No new dependencies (only stdlib `collections.abc.Callable`).
- **Dependency/configuration changes:** None. No new Python packages, env vars, or infra files.
- **Behavior change beyond the difficult source:** `SourceMetrics.record_fetch_success()` is shared by *all* adapters, so gating freshness on `records_emitted > 0` is a global semantic change. It is a correct alignment with TASK-040's "distinguish reachable-with-zero-records vs failed vs stale" and with this task's retry requirement; see Non-Defect Observations.
- **Tests weakened?** No. No existing test was modified. Existing `test_source_metrics.py` and `test_health_assessment.py` still pass unchanged.
- **Branch/task isolation:** Reviewed HEAD is on `feature/TASK-054`; the range contains exactly one commit. No cross-task contamination.

---

## 4. Test and Verification Review

### Tests examined

`tests/test_observability/test_freshness_failures.py` (new, 583 lines, 27 tests) — unit tests for `SourceFreshness` clock injection, zero-result freshness semantics, `SourceHealthAssessor` STALE detection, `SourceHealthTracker` freshness integration, and eight end-to-end scenario tests using the full tracker+metrics stack with deterministic clocks. Also re-ran `test_source_metrics.py`, `test_health_assessment.py`, `test_difficult_retailer_adapter.py`, and `test_difficult_retailer_backoff.py` for regression.

### Test adequacy

Strong. All eight task-required scenarios are covered, plus boundary (exactly-at-threshold), disabled-threshold (`None`), missing-freshness-data, and active-failure-takes-priority-over-stale cases. The deterministic-clock design is clean and reproducible; no wall-clock timing is relied on.

### Verification status

| Check | Result | Status |
|---|---|---|
| `python -m pytest tests/test_observability/test_freshness_failures.py tests/test_observability/test_source_metrics.py tests/test_observability/test_health_assessment.py -q` | **88 passed** | Independently verified |
| `python -m pytest tests/test_adapters/test_difficult_retailer_adapter.py tests/test_adapters/test_difficult_retailer_backoff.py -q` | **111 passed** | Independently verified |
| `python -m ruff check libs/observability tests/test_observability/test_freshness_failures.py` | All checks passed | Independently verified |
| `python -m ruff format --check libs/observability tests/test_observability/test_freshness_failures.py` | 7 files already formatted | Independently verified |
| `python -m mypy libs/observability` | Success: no issues found in 5 source files | Independently verified |
| `python -m pytest -m integration` | Not run — TASK-054 introduces no Kafka/persistence/MinIO/infrastructure code; it is a pure observability/source-health change. | Unverified (out of scope) |
| Full `python -m pytest` (non-integration) | Timed out at 300s without completing; the affected observability and difficult-retailer suites were run separately and pass. | Partially verified (targeted) |

---

## 5. Findings

### Finding #1 — Freshness age is never fed into the source-health tracker, so `STALE` is unreachable in production
- **Severity:** Moderate
- **File/line:** `libs/observability/health_assessment.py:158` (`update_freshness_age`); no caller in `libs/adapters/difficult_retailer/adapter.py` or `services/ingestion/runner.py`
- **Problem:** The new `SourceHealthTracker.update_freshness_age()` / `get_freshness_state()` and the `STALE` assessment branch are fully implemented and unit-tested, but the adapter never calls `update_freshness_age(self._metrics.get_freshness_age_seconds())`. Consequently `adapter.health_assessment()` can never return `STALE`, and `health_tracker.get_freshness_state()` remains `NEVER_COLLECTED` in real operation. `IngestionRunner.get_source_health()` likewise reports `signals["freshness_age_seconds"] = None` and `max_freshness_age_seconds = None`. The freshness logic exists only as a standalone API exercised by tests.
- **Impact:** Freshness failure detection is demonstrated but not operational end-to-end; a genuinely stale difficult source will not be surfaced as stale through the source-health path. This is the remaining gap before TASK-055's "freshness becomes stale" / "recovery from stale" integration scenarios can pass against the real adapter.
- **Recommendation:** In `DifficultRetailerAdapter.fetch()` after recording the fetch outcome (success and failure paths), call `self._health_tracker.update_freshness_age(self._metrics.get_freshness_age_seconds())`; optionally surface `get_freshness_state()` in `IngestionRunner.get_source_health()`.

### Finding #2 — No-history assessment returns `HEALTHY`, not a "never collected" signal
- **Severity:** Minor
- **File/line:** `libs/observability/health_assessment.py` `assess()` early return (`if not outcomes: ... state=HEALTHY, reasons=["no fetch history"]`)
- **Problem:** The task requires distinguishing "never successfully collected." This is modeled only by `FreshnessState.NEVER_COLLECTED` via `get_freshness_state()`; the health assessment path still returns `HEALTHY` with "no fetch history" for an empty outcome history. This is inherited from TASK-053 (`test_no_history_is_healthy`) but now leaves a slight semantic mismatch: a caller of `get_source_health()` sees `healthy` for a source that has never been collected.
- **Impact:** Minor diagnostic ambiguity; low risk.
- **Recommendation:** Either keep the TASK-053 behavior and document that "never collected" is a freshness-level (not health-level) classification, or include a `freshness_state`/`never_collected` flag in the no-history assessment signals.

### Finding #3 — `_make_clock` test helper defines an unused `clock_fn` with a misleading docstring
- **Severity:** Minor
- **File/line:** `tests/test_observability/test_freshness_failures.py:26-40`
- **Problem:** `_make_clock` defines `clock_fn()` but returns the mutable `container` list; its docstring says "Call `clock_fn()` to get the current time" even though `clock_fn` is never returned or used. All tests pass `clock=lambda: clock_list[0]` directly.
- **Impact:** Dead code and a confusing helper contract in the test module only; no runtime impact.
- **Recommendation:** Return the callable (or a small `Clock` holder) and delete the dead function, aligning the docstring with the actual API.

### Finding #4 — `SourceHealthTracker` thread-safety claim remains unsupported; new freshness state is unguarded
- **Severity:** Minor
- **File/line:** `libs/observability/health_assessment.py:126` (docstring), `:150` (`self._freshness_age_seconds`), `:158`/`:167`
- **Problem:** The class docstring still claims "Thread-safe for concurrent outcome recording," but neither `_outcomes`/`_consecutive_empty` (pre-existing) nor the new `_freshness_age_seconds` is protected by a lock (unlike `SourceMetrics`, which uses `threading.Lock`). The new freshness read/write is a single float assignment (atomic in CPython) so real risk is low today, but the claim is misleading for future concurrent callers.
- **Impact:** A false concurrency guarantee; latent race if adapters run concurrently in threads.
- **Recommendation:** Add a `threading.Lock` for the new state (or the whole tracker) or soften the docstring to state the single-threaded assumption.

---

## 6. Non-Defect Observations

- **Resolves the TASK-053 review's Finding #4.** The prior review flagged `max_freshness_age_seconds` as declared-but-unused. TASK-054 now reads it in both `get_freshness_state()` and `assess()`, closing that gap at the logic level (the production wiring remains Finding #1 above).
- **Correct "usable data" criterion.** Gating freshness on `records_emitted > 0` (not `records_collected > 0`) correctly treats an all-malformed fetch (records received but nothing emitted) as non-usable, which is exactly the retry-freshness requirement.
- **Priority ordering is a defensible design choice.** Active failures (`UNREACHABLE`/`RATE_LIMITED`/`STRUCTURALLY_CHANGED`) take precedence over `STALE`, so a currently-failing source is not masked by staleness; `test_active_failure_takes_priority_over_stale` documents this.
- **The global `SourceMetrics` change is intentional and consistent.** Because `record_fetch_success` is shared, the zero-result freshness semantics now apply uniformly to all adapters — which aligns with TASK-040 ("distinguish zero records / failed / stale") and does not regress existing tests.
- **Package exports improved.** `libs/observability/__init__.py` now exports the TASK-053 health-assessment symbols alongside the new `FreshnessState`, making the programmatic surface cleaner for downstream consumers.
- **Deterministic testing is thorough.** Clock injection reaches the freshness calculation (not just the assessment timestamp), so age/threshold boundary assertions are exact rather than timing-dependent.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The single-commit change set satisfies the task's acceptance criteria at the unit level: it activates the configurable freshness threshold, adds `FreshnessState` and the `STALE` degradation state, ensures zero-result/retry fetches do not falsely refresh freshness, uses deterministic clock injection throughout, and covers all eight task-required scenarios. The change is correctly isolated to `feature/TASK-054` with no unrelated, architectural, or dependency changes, and no secrets or debug artifacts.

Independently verified: 88 observability tests pass (plus 111 difficult-retailer adapter tests for regression), `ruff check` and `ruff format --check` pass, and `mypy` is clean on the updated `libs` files.

The four findings are non-blocking: the primary gap (Finding #1, Moderate) is that the new freshness state is exposed and tested but not yet wired into the adapter/runner, so `STALE` is not reachable through the production source-health path — this is the natural integration boundary that TASK-055 will exercise. The remaining items are Minor (no-history assessment semantics, a dead test helper, and an inherited thread-safety claim). These are recommended follow-ups, not acceptance blockers.
