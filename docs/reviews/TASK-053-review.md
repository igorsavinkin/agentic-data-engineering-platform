# TASK-053 Review — Source Degradation Detection

## 1. Review Header

- **Task:** TASK-053 — Source Degradation Detection
- **Review date:** 2026-09-17
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `8384801c17f9b8fcb4853f8eff5d9ae6e400fa5c...cdf0fd65d4f094c33b60d49e812ec3924e5e5bc3`
  - `cdf0fd65d4f094c33b60d49e812ec3924e5e5bc3` — `feat(TASK-053): Add source degradation detection`
- **Reviewed HEAD:** `cdf0fd65d4f094c33b60d49e812ec3924e5e5bc3` on `feature/TASK-053`
- **Scope:** `libs/observability/health_assessment.py` (new), `libs/adapters/difficult_retailer/adapter.py`, `services/ingestion/runner.py`, `tests/test_observability/test_health_assessment.py` (new). 4 files, +890/−3. No existing tests removed or weakened.
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

---

## 2. Requirements Coverage

Sources: `ai/tasks/TASK-053-source-degradation-detection.md`, `ai/PROJECT.md` §9/§10, `ai/SPECIFICATION.md` §4.2/§4.5, `ai/ROADMAP.md` §12.

| Requirement | Status | Implementation evidence |
|---|---|---|
| Define explicit degradation states using existing source-health abstractions | Met | New `SourceDegradationState` StrEnum (`healthy`, `unreachable`, `rate_limited`, `structurally_changed`, `partially_parseable`, `empty_result`). Reuses `SourceMetrics` for counters; `record_partial_failure()` wired into the difficult-retailer adapter. |
| Distinguish healthy / unreachable / rate limited / structurally changed / partially parseable / empty | Met | `SourceHealthAssessor.assess()` implements a priority order over these six states from fetch outcomes and signals. (See Finding #1 for an edge-case conflation.) |
| Use measurable signals (fetch outcomes, parse success ratio, malformed count, emitted count, structural failures) | Met | `assess()` computes `success_ratio`, `malformed_ratio`, `total_records`, `total_malformed`, `total_events`, `failed_fetches`, `consecutive_empty_fetches`. Structural failures arrive via the adapter's `structural_change` → `SourceFetchError` path. |
| Avoid brittle hard-coded thresholds unless justified/configurable | Met | `SourceHealthConfig` exposes `min_success_ratio`, `max_malformed_ratio`, `max_empty_fetches`, `min_expected_records`. (See Finding #4/#5.) |
| Preserve diagnostic reason categories without high-cardinality metric labels | Met | `signals` dict contains only counts/ratios; free-text failure reasons live in `reasons` (diagnostic log/state), not metric labels. |
| A degraded source must not silently report healthy merely because HTTP returned 200 | Met | `test_http_200_with_structural_failure_not_healthy`, `test_empty_result_scenario`, and `test_partially_parseable_source` verify 200-response degradation is classified non-healthy. |
| Degradation detection must not mutate canonical downstream data | Met | Tracker is read-only with respect to `FetchResult.events`; `record_fetch_success` runs after the result is produced. `test_health_assessment_does_not_mutate_data` asserts event identity is unchanged. |
| Add structured diagnostic logging and metrics/state suitable for later Airflow/data-quality checks | Met | `_log_health_if_degraded` emits `source_degradation_detected`; `IngestionRunner.get_source_health()` exposes per-source state; `PARTIAL_FAILURES` metric now recorded on malformed output. |
| Do not implement Airflow or alert delivery here | Met | No Airflow DAGs, alerting, or delivery code introduced. |

**Tests required by the task** — all present:

| Required test | Status | Test(s) |
|---|---|---|
| healthy source | ✅ | `test_healthy_source`, `test_all_successful_with_data_is_healthy` |
| HTTP success + parser structural failure | ✅ | `test_structural_change_detected`, `test_http_200_with_structural_failure_not_healthy` |
| partially parseable response | ✅ | `test_partially_parseable_source`, `test_high_malformed_ratio_is_partially_parseable` |
| rate-limited state | ✅ | `test_rate_limited_state`, `test_rate_limited_detected` |
| unreachable state | ✅ | `test_unreachable_source`, `test_low_success_ratio_is_unreachable` |
| empty-result scenario | ✅ | `test_empty_result_scenario`, `test_consecutive_empty_results`, `test_below_min_expected_records` |
| recovery from degraded to healthy | ✅ | `test_recovery_from_degraded`, `test_recovery_from_degraded_to_healthy` |
| metric/state classification | ✅ | `test_metric_state_classification`, `test_signals_include_all_metrics` |

---

## 3. Git Diff Review

- **Scope correctness:** Correct. All four files belong to TASK-053. The `health_assessment.py` module is new and generic, but consumed only by the difficult-retailer adapter as required.
- **Unrelated changes:** None.
- **Architectural changes:** None. Confined to the difficult-retailer adapter's health tracking plus a new observability module and a read-only `IngestionRunner.get_source_health()` accessor. No Kafka/processor/lake/warehouse/schema changes.
- **Accidental/debug/dead code:** No debugging artifacts, temporary files, generated artifacts, or secrets. No new dependencies (`health_assessment.py` uses only the standard library).
- **Dependency/configuration changes:** None. No new Python packages, env vars, or infra files.
- **Tests weakened?** No. The only test change is the new `test_health_assessment.py`. Pre-existing `test_difficult_retailer_adapter.py` and `test_difficult_retailer_backoff.py` are untouched and still pass.
- **Branch/task isolation:** Reviewed HEAD is on `feature/TASK-053`; the range contains exactly one commit. No cross-task contamination.

---

## 4. Test and Verification Review

### Tests examined

`tests/test_observability/test_health_assessment.py` (new, 476 lines) — unit tests for `SourceHealthAssessor` and `SourceHealthTracker`, plus adapter-level integration tests using mocked `httpx.AsyncClient` and fixture HTML. Also re-ran `test_difficult_retailer_adapter.py`, `test_difficult_retailer_backoff.py`, and `test_source_metrics.py` for regression.

### Test adequacy

Good breadth; all eight task-required scenarios are covered and the adapter-level tests exercise the real `fetch() → health_assessment()` path rather than only the stateless assessor. The mocked-HTTP design is deterministic and injects `sleep_fn`/sub-10 ms backoff to avoid real waits.

### Verification status

| Check | Result | Status |
|---|---|---|
| `python -m pytest tests/test_observability/test_health_assessment.py -q` | **28 passed** | Independently verified |
| `python -m pytest tests/test_adapters/test_difficult_retailer_adapter.py tests/test_adapters/test_difficult_retailer_backoff.py tests/test_observability/test_source_metrics.py tests/test_observability/test_health_assessment.py -q` | **172 passed** | Independently verified |
| `python -m ruff check` (4 changed files) | All checks passed | Independently verified |
| `python -m ruff format --check` (4 changed files) | 4 files already formatted | Independently verified |
| `python -m mypy libs/observability/health_assessment.py libs/adapters/difficult_retailer/adapter.py` | Success: no issues found | Independently verified |
| `python -m mypy services/ingestion/runner.py` | Not checked by project config — `services/` is not in `[tool.mypy].files` (`scripts`, `tests`, `libs` only). A direct invocation raised only a duplicate-module-path error, not a type error. | Implementation evidence reviewed (config-limited) |
| `python -m pytest -m integration` | Not run — TASK-053 introduces no Kafka/persistence/MinIO/infrastructure code; it is a mocked-HTTP adapter/observability change. | Unverified (out of scope) |

### Independent empirical checks

1. **StrEnum vs string comparison.** Confirmed `SourceDegradationState.HEALTHY == "healthy"` is `True` and `STRUCTURALLY_CHANGED != "healthy"` is `True`, so `_log_health_if_degraded`'s `assessment.state != "healthy"` gate is correct.
2. **All-malformed classification (Finding #1).** Reproduced: three fetches each with `events_emitted=0, total_records=5, malformed_count=5` are classified `empty_result` (`malformed_ratio == 1.0`), not `partially_parseable`.

---

## 5. Findings

### Finding #1 — All-malformed responses are misclassified as `empty_result` instead of `partially_parseable`
- **Severity:** Moderate
- **File/line:** `libs/observability/health_assessment.py:155-158` (`record_fetch_success`), `assess()` empty-result branch
- **Problem:** The empty-result signal uses `events_emitted == 0` (number of successfully emitted canonical events) rather than `total_records == 0` (number of records received). A response where every record is malformed has `total_records > 0`, `malformed_count > 0`, but `events_emitted == 0`; it therefore increments `_consecutive_empty` and, after `max_empty_fetches`, is classified `empty_result` even though `malformed_ratio == 1.0` indicates parse degradation. This blurs the exact distinction the task requires ("partially parseable" vs "successful but unexpectedly empty").
- **Impact:** A source that consistently returns structurally valid but unparseable records is reported as "empty" rather than "parse-degraded", misleading later Airflow/data-quality checks.
- **Recommendation:** Base the empty/consecutive-empty signal on `total_records == 0` (no records received), and let `malformed_ratio` drive `partially_parseable`. Add a test for the all-malformed case (`events_emitted=0`, `total_records>0`, `malformed_count>0`).

### Finding #2 — Degradation classification relies on substring matching of human-readable error text
- **Severity:** Moderate
- **File/line:** `libs/observability/health_assessment.py:241-256`, `280-290` (`reason_lower`, `"rate" in ... and "limit" in ...`, `"structural"/"structure"`)
- **Problem:** `SourceFetchError` carries only a `source` and a free-text message; the client/adapter already classify responses into a structured `ResponseKind` and a `structural_change` flag, but that structured information is discarded when the exception is raised. The assessor reconstructs rate-limit vs structural-change vs unreachable by matching substrings of `str(exc)`. Any rewording of the client/adapter error messages silently changes (or breaks) classification.
- **Impact:** Fragile coupling to error-message wording; a maintainability risk and a latent correctness risk if messages are reworded.
- **Recommendation:** Attach a structured reason/category (e.g. reuse `ResponseKind`, or a dedicated `failure_kind`) to `SourceFetchError`, and have the assessor consume that structured field instead of matching text.

### Finding #3 — `SourceHealthTracker` claims thread-safety that is not implemented
- **Severity:** Moderate
- **File/line:** `libs/observability/health_assessment.py:115` (docstring), `131`, `155-158`
- **Problem:** The class docstring states "Thread-safe for concurrent outcome recording," but `_outcomes` (a plain `list`) and `_consecutive_empty` (a plain `int`) are mutated without any lock. The sibling `SourceMetrics` explicitly uses `threading.Lock`. The ingestion runner currently records outcomes sequentially on a single async path, so no live race exists today.
- **Impact:** A false concurrency guarantee that could mislead a future caller running adapters concurrently (threads); unsynchronized `list.append`/`+=` would then race.
- **Recommendation:** Either add a `threading.Lock` (as `SourceMetrics` does) or remove the thread-safety claim and document the single-threaded assumption.

### Finding #4 — `max_freshness_age_seconds` is declared and documented but never used
- **Severity:** Moderate
- **File/line:** `libs/observability/health_assessment.py:58`, `69`
- **Problem:** `SourceHealthConfig.max_freshness_age_seconds` is documented as "Maximum age of last successful fetch before the source is considered stale. None disables this check," but `assess()` never reads it. A caller setting this value would reasonably expect staleness detection that does not exist.
- **Impact:** Misleading dead configuration that implies unimplemented functionality. (Freshness scenarios are explicitly deferred to TASK-054, so the field is a plausible placeholder, but it should not claim to be active.)
- **Recommendation:** Remove the field until freshness is implemented, or annotate it as not-yet-active and assert/ignore it explicitly.

### Finding #5 — `SourceHealthConfig` thresholds are not range-validated
- **Severity:** Minor
- **File/line:** `libs/observability/health_assessment.py:66-71`
- **Problem:** No validation that `0 < min_success_ratio <= 1`, `0 <= max_malformed_ratio <= 1`, or `max_empty_fetches >= 1`. For example, `max_empty_fetches=0` makes `consecutive_empty >= 0` always true, so any successful non-empty fetch can be classified `empty_result`.
- **Impact:** Misconfiguration yields silently degenerate classifications; low-risk in normal operation.
- **Recommendation:** Validate ranges in `SourceHealthConfig.__post_init__` (or the tracker constructor) and raise on invalid values.

### Finding #6 — `BLOCKED_HTML` fixture is loaded but unused
- **Severity:** Minor
- **File/line:** `tests/test_observability/test_health_assessment.py:44`
- **Problem:** `BLOCKED_HTML = _load_fixture("blocked_page.html")` is never referenced by any test.
- **Impact:** Dead test code; trivial.
- **Recommendation:** Remove the unused constant, or add a "blocked → unreachable" classification test that uses it.

### Finding #7 — `IngestionRunner.get_source_health` has no test coverage
- **Severity:** Minor
- **File/line:** `services/ingestion/runner.py:123`
- **Problem:** The new `get_source_health()` accessor is untested and relies on duck-typing (`hasattr(adapter, "health_assessment")` plus `adapter.source_name`). It is also outside the configured mypy file set (`services/` is not type-checked).
- **Impact:** No regression protection for the new accessor; the "sources without health trackers are omitted" behavior is unverified.
- **Recommendation:** Add a small unit test covering `get_source_health()` for a tracked adapter and an untracked adapter.

---

## 6. Non-Defect Observations

- **Well-scoped, side-effect-free design.** The tracker only observes outcomes after `_fetch_single` returns and never touches `FetchResult.events`; the non-mutation requirement is explicitly tested. This is the right separation for a diagnostic layer.
- **`record_partial_failure()` wiring resolves a prior TASK-051 review point.** TASK-051's review noted that partial parseability did not increment `PARTIAL_FAILURES`. This change adds the call in the difficult-retailer adapter, closing that gap in a targeted way.
- **Threshold configurability is genuine.** `min_expected_records` and `max_malformed_ratio` let the empty/partial distinction be tuned per source; the defaults are conservative and documented.
- **StrEnum state modeling is clean.** Using `StrEnum` keeps `state` directly comparable/loggable while retaining `.value` for wire/JSON output.
- **No high-cardinality labels.** `signals` is strictly numeric; free-text failure reasons are confined to `reasons`, satisfying the metric-label cardinality rule.
- **Runner accessor is a reasonable extension point.** `get_source_health()` gives later Airflow/data-quality and the LangGraph source-health tool a clean read path without coupling ingestion to those components.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The single-commit change set satisfies the task's acceptance criteria: it introduces explicit, configurable degradation states; distinguishes availability from data quality; never reports a degraded (HTTP-200) source as healthy; does not mutate downstream data; and adds structured logging plus a state accessor for later Airflow/data-quality checks. All eight task-required test scenarios are present, and the change is correctly isolated to `feature/TASK-053` with no unrelated or architectural changes.

Independently verified: 28 new tests pass (172 across the affected suites), `ruff check` and `ruff format --check` pass, and `mypy` is clean on the new/updated `libs` files.

The six findings are non-blocking: the all-malformed→empty misclassification (Moderate), the string-matching classification fragility (Moderate), the unsupported thread-safety claim (Moderate), and three Minor items (dead `max_freshness_age_seconds` config, missing config validation, an unused fixture, and untested `get_source_health`). These are recommended follow-ups, not acceptance blockers.
