# TASK-106 Post-Merge Review — Source Freshness Failure Test

## 1. Review Header

- **Task ID:** TASK-106 — Source Freshness Failure
- **Review date:** 2026-09-24
- **Reviewer:** Qwen Code (independent post-merge review, no code modified)
- **Review type:** Post-merge review of the final merged state on `main`
- **Reviewed change set / Git range:** `7d9067d853f83f28f448d48744aa72ce1075f5a6..d7476b9425d5ecf328d304d23cab21060a43780b`
- **Reviewed commit:** `d7476b9` — `feat(TASK-106): add source freshness failure integration tests`
- **Branch:** `main` (code already merged; post-merge review)
- **Scope:** one new test file `tests/test_observability/test_source_freshness_failure.py` (304 lines). No production code changes.
- **Verdict:** APPROVED WITH NON-BLOCKING FINDINGS

The reviewed range resolves to a **single commit**, `d7476b9` (parent `7d9067d`, the TASK-105
merge). Its diff is exactly the one new test file — no production, configuration, migration, or
infrastructure files were touched.

---

## 2. Requirements Coverage

Source of truth: `ai/tasks/TASK-106-source-freshness-failure.md` (objective, Failure Engineering
Rules, Engineering Rules, Definition of Done), `ai/SPECIFICATION.md` §4.5 (Source Health and
Freshness), and the production modules under test: `libs/observability/health_assessment.py`,
`libs/observability/source_metrics.py`, `services/agent/tools.py::_derive_alerts`, and
`services/api/repositories/pipeline_status.py::_derive_overall_status`.

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Source stops producing → freshness detects staleness | Met | `TestSourceStopsProducing::test_source_staleness_detected_after_producer_stops` (line 93) drives 3 producing cycles then 5 zero-result cycles through a shared deterministic clock; asserts `assessment.state == STALE`, `get_freshness_state() == STALE`, and `age > 3600`. |
| Alerts are raised when a source goes stale | Met | `TestStaleAlerts::test_stale_source_produces_alert` (line 136) builds the source-health dict from a real tracker assessment and asserts `_derive_alerts` emits exactly one `source_stale` alert with severity `medium`; the negative case (line 168) asserts a fresh source produces none. |
| Downstream does not serve stale data as current | Partially met | `TestDownstreamProtection` (line 194) verifies `_derive_overall_status` maps stale freshness/state → `"stale"` (never `"healthy"`). This is the production function used by `PipelineStatusRepository.list_source_health`, but it is exercised directly rather than through the public serving path (see F1). |
| Failure → Detection → Metric/log → Alert → Recovery → No silent data loss | Partially met | Detection, Alert, Recovery (`TestRecovery`, line 220), and No-silent-data-loss (`TestZeroResultsDoNotMaskStaleness`, line 270) arms are demonstrated. The "Metric/log" arm is only the freshness-age signal; no counter or log is asserted (F3). |
| Reuse existing source-health / freshness semantics | Met | No production code changed. Tests reuse `SourceMetrics`, `SourceHealthTracker`, `SourceHealthConfig`, `_derive_alerts`, and `_derive_overall_status` as-is. |
| Tests repeatable and deterministic | Met | Deterministic clock injection (`clock=lambda: clock_list[0]`) throughout; no wall-clock, network, Kafka, PostgreSQL, or MinIO dependency. |
| Document the freshness failure scenario | Met | Module docstring documents the full `Failure → Detection → Metric/log → Alert → Recovery → No silent data loss` lifecycle and the exact stack under test. |
| No unrelated architecture changes / secrets | Met | Test-only change; no secrets, no new dependencies, no production edits. |

---

## 3. Git Diff Review

Net diff of `7d9067d..d7476b9`:

- `tests/test_observability/test_source_freshness_failure.py` — added (304 lines, 9 tests).

- **Scope correctness:** All changes belong to TASK-106. No production, config, infrastructure, or migration code was modified.
- **Unrelated changes:** None.
- **Architectural changes:** None. The observability stack (`SourceMetrics` → `SourceHealthTracker` → `SourceHealthAssessor` → `_derive_alerts` → `_derive_overall_status`) is exercised, not altered.
- **Accidental changes:** None — no debugging code, temporary files, generated artifacts, dead code, or secrets.
- **Dependencies/configuration:** No new dependencies. Imports `datetime`/`timedelta`/`timezone` and the existing observability/service modules only.
- **Branch/task isolation:** Correct. `d7476b9` contains only TASK-106 changes; no changes from another TASK-* branch are included.

---

## 4. Test and Verification Review

### Tests examined

Nine tests, no `pytest.mark.integration` marker on the module (see F5), so they run under the
default pytest configuration rather than being opt-in:

1. `TestSourceStopsProducing::test_source_staleness_detected_after_producer_stops` (line 93)
2. `TestStaleAlerts::test_stale_source_produces_alert` (line 136)
3. `TestStaleAlerts::test_fresh_source_produces_no_stale_alert` (line 168)
4. `TestDownstreamProtection::test_stale_freshness_maps_to_stale_status` (line 197)
5. `TestDownstreamProtection::test_healthy_state_with_fresh_freshness_is_healthy` (line 201)
6. `TestDownstreamProtection::test_stale_assessment_maps_to_stale_status` (line 206)
7. `TestDownstreamProtection::test_degraded_states_map_to_degraded_status` (line 211)
8. `TestRecovery::test_recovery_after_staleness` (line 220)
9. `TestZeroResultsDoNotMaskStaleness::test_zero_results_keep_freshness_aging` (line 270)

### Verification status — Independently verified (executed by this reviewer)

All nine tests are pure in-memory (deterministic clock injection), so they were run in full with no
Docker prerequisite. Results:

| Command | Result |
|---------|--------|
| `python -m pytest tests/test_observability/test_source_freshness_failure.py -v` | **9 passed** (1.30s) |
| `python -m ruff check tests/test_observability/test_source_freshness_failure.py` | All checks passed |
| `python -m ruff format --check tests/test_observability/test_source_freshness_failure.py` | 1 file already formatted |
| `python -m mypy tests/test_observability/test_source_freshness_failure.py` | Success: no issues found in 1 source file |

The reviewer traced the assertions against the production logic and confirmed they are non-vacuous:

- `SourceMetrics.record_fetch_success` refreshes freshness only when `records_emitted > 0`
  (`source_metrics.py`), so zero-result fetches correctly leave the freshness clock advancing — the
  property asserted by tests 1, 8, and 9.
- `SourceHealthAssessor.assess` checks STALE before `EMPTY_RESULT`
  (`health_assessment.py`), so a source with stale freshness classifies as `STALE` even when it has
  consecutive empty fetches — asserted by test 1.
- `_derive_alerts` (`services/agent/tools.py:347`) emits `source_stale` (severity `medium`) only when
  `overall_status == "stale"`, and `_derive_overall_status`
  (`services/api/repositories/pipeline_status.py:24`) returns `"stale"` on stale freshness/state and
  `"degraded"` for the `_DEGRADED_STATES` set — matching tests 2–7.

---

## 5. Findings

No blocking findings. Five non-blocking findings (F1–F5), two Moderate and three Minor.

### F1 — MODERATE — Alert and downstream-status behavior is verified via private helpers, not the public serving path

- **File/line:** `tests/test_observability/test_source_freshness_failure.py:23-24` (imports), `TestStaleAlerts` (133), `TestDownstreamProtection` (194)
- **Problem:** The task objective is "alerts are raised, and downstream components do not serve stale data as current." The tests import the underscore-private `_derive_alerts` (from `services.agent.tools`) and `_derive_overall_status` (from `services.api.repositories.pipeline_status`) and call them directly with hand-built dicts. They do not exercise the public wiring — `get_pipeline_status()` for alert derivation or `PipelineStatusRepository.list_source_health()` for the serving status — so the end-to-end claim ("the serving layer actually surfaces `stale` to a consumer") is not demonstrated, only the derivation functions in isolation.
- **Impact:** Coverage nuance, not a correctness defect. The private functions are the real production logic and are each asserted correctly, but a refactor of the public call sites would not be caught.
- **Recommendation:** Optionally add one scenario going through `get_pipeline_status` / `list_source_health` (or accept the derivation-level coverage as a documented scope decision, consistent with how TASK-104 treated its "connected flow" gap).

### F2 — MODERATE — Substantial overlap with existing coverage; the genuinely new surface is narrower than the file suggests

- **File/line:** `TestSourceStopsProducing` (90), `TestRecovery` (217), `TestZeroResultsDoNotMaskStaleness` (267), `TestStaleAlerts` (133)
- **Problem:** The staleness-detection, zero-result, and recovery scenarios largely re-implement scenarios already covered by `tests/test_observability/test_freshness_failures.py` (TASK-054, e.g. `test_scenario_stale_source`, `test_scenario_zero_result_semantics`, `test_scenario_recovery_refreshes_state`). The `source_stale` alert path is also already covered by `tests/agent/test_tools.py::test_source_stale_alert` (line 665) and `test_stale_source_unknown_age` (line 677). The net-new coverage is `TestDownstreamProtection` (`_derive_overall_status` mapping — not tested anywhere else) plus the connected tracker→status→alert flow in `_build_source_health_dict`.
- **Impact:** Maintainability/drift risk and duplicated effort; not a functional problem. Two alert tests and two staleness tests duplicate assertions that already exist elsewhere.
- **Recommendation:** Accept as-is for a dedicated task (each TASK-xxx is a focused demonstration), or consolidate the overlapping staleness lifecycle into the TASK-054 file and keep only the alert/status-mapping additions here.

### F3 — MINOR — "Metric/log" arm of the failure lifecycle is only partially asserted

- **File/line:** `tests/test_observability/test_source_freshness_failure.py` (no `caplog`, no counter assertion)
- **Problem:** The Failure Engineering Rules require `Detection -> Metric/log`. The tests assert the freshness-age signal (`get_freshness_age_seconds()`) but never assert a concrete metric counter (e.g. `SourceMetric.ZERO_RECORD_FETCHES`) nor any log record. `SourceMetrics.record_fetch_success` increments `FETCH_SUCCESS`, `ZERO_RECORD_FETCHES`, etc., but none are read back.
- **Impact:** The requirement is effectively satisfied by the freshness-age signal; the explicit counter/log arm is undocumented rather than broken. Same pattern noted in the TASK-104 and TASK-105 reviews.
- **Recommendation:** Either accept "metric" as satisfied by the freshness-age signal (and note it), or add a `snapshot()` assertion on `ZERO_RECORD_FETCHES` / `FETCH_SUCCESS`.

### F4 — MINOR — Degraded-state mapping test omits two `_DEGRADED_STATES` members

- **File/line:** `tests/test_observability/test_source_freshness_failure.py:211-214`
- **Problem:** `test_degraded_states_map_to_degraded_status` iterates `("unreachable", "rate_limited", "structurally_changed")`, but `_derive_overall_status`'s `_DEGRADED_STATES` also contains `"partially_parseable"` and `"empty_result"`, which are not asserted.
- **Impact:** Minor coverage gap in the mapping table; the three tested values are a representative subset and the mapping is a simple set membership.
- **Recommendation:** Extend the tuple to cover all five degraded states (or iterate `_DEGRADED_STATES` directly).

### F5 — MINOR — File labeled "integration test" but carries no `integration` marker and is in-memory

- **File/line:** `tests/test_observability/test_source_freshness_failure.py:1` (docstring) and commit message
- **Problem:** The module docstring and commit title call this an "integration test", but it has no `pytestmark = pytest.mark.integration` and uses no Kafka/PostgreSQL/MinIO — it is a deterministic in-memory component test that runs under the default `addopts = "-m 'not integration'"` suite.
- **Impact:** Labeling inconsistency only. Running in the default suite is actually desirable (it executes in CI without Docker and cannot be silently deselected). The "integration" wording overstates the boundary touched.
- **Recommendation:** Rename the docstring/commit wording to "component" or "observability stack" test, or keep it but drop the "integration" claim for accuracy.

---

## 6. Non-Defect Observations

- **Scope and hygiene are clean.** Test-only change, no production edits, no new dependencies, no secrets, no weakening of existing suites. `ruff check`, `ruff format --check`, and `mypy` all pass on the file.
- **Deterministic clock injection is idiomatic.** The `_make_clock` / `_advance` helper pattern and `FROZEN_TIME` constant match the established convention in `tests/test_observability/test_freshness_failures.py` (TASK-054), which aids readability.
- **`_derive_overall_status` mapping is genuinely new coverage.** A repository-wide search found no prior test of this function; `TestDownstreamProtection` closes that gap, and it correctly reflects the production precedence (stale freshness/state beats healthy, degraded states map to `degraded`).
- **The connected flow is a small but real improvement.** `_build_source_health_dict` derives `overall_status` from a live `tracker.assess()` result and feeds the same dict to both `_derive_overall_status` and `_derive_alerts`, which is slightly more integrated than the fully hand-built dicts in `tests/agent/test_tools.py`.
- **Import weight.** `services.api.repositories.pipeline_status` transitively imports SQLAlchemy and `services.api.models` (ORM), and `services.agent.tools` imports `pydantic`, so this test module pulls in heavier production dependencies than its pure-string mapping target strictly requires. Harmless (no connection is opened at import time), but worth noting.
- **`_build_source_health_dict` returns keys not consumed by `_derive_alerts`** (`degradation_state`, `signals`, `assessed_at`). Harmless; the dict is shaped for a broader source-health consumer than the single function it is fed to.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The TASK-106 objective is satisfied at the merged state on `main`: the test deterministically
demonstrates that a source adapter stopping production is detected as stale (freshness age exceeding
threshold), that a `source_stale` alert is derived, that downstream status is mapped to `stale`
(never `healthy`), that recovery restores a healthy/fresh state, and that zero-result fetches do not
mask staleness. The change set is correctly scoped (test-only), introduces no new dependencies or
secrets, and reuses the existing source-health/freshness semantics without altering them.

This reviewer independently executed the full suite: **9 passed** (1.30s), with `ruff check`,
`ruff format --check`, and `mypy` all clean, and traced the assertions against the production
`SourceMetrics`, `SourceHealthAssessor`, `_derive_alerts`, and `_derive_overall_status` logic to
confirm the tests are non-vacuous.

The five findings are non-blocking: two Moderate (verification through private helpers rather than the
public serving path, and partial overlap with pre-existing TASK-054 / `test_tools.py` coverage) and
three Minor (metric/log arm only partially asserted, incomplete degraded-state mapping coverage, and
"integration test" labeling with no integration marker). None invalidates the task's objective or
blocks the already-completed merge.
