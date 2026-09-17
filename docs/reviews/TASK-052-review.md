# TASK-052 Review — Rate-Limit / Backoff Strategy

## 1. Review Header

- **Task:** TASK-052 — Rate-Limit / Backoff Strategy
- **Review date:** 2026-09-17
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `7b36e01206ee4481b80d554888d8710c17c73b44...884bc992d5354dbc57e9da524d7967fb14c24077`
  - `63766b9aaa94728b1f221b846502836226a1667d` — `feat(TASK-052): Add rate-limit / backoff strategy for difficult source`
  - `884bc992d5354dbc57e9da524d7967fb14c24077` — `fix(TASK-052): Address Qwen review findings #1-#7`
- **Reviewed HEAD:** `884bc992d5354dbc57e9da524d7967fb14c24077` on `feature/TASK-052`
- **Scope:** `libs/adapters/difficult_retailer/client.py` and `tests/test_adapters/test_difficult_retailer_backoff.py` (new). 2 files, +900/−16. No removed tests.
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

This is a re-review. A prior Qwen review of the sole `feat` commit (`63766b9`) returned `CHANGES REQUIRED` with 7 findings. Commit `884bc99` was produced to address those findings. This report reviews the combined two-commit change set and records the disposition of the prior findings.

---

## 2. Requirements Coverage

Sources: `ai/tasks/TASK-052-rate-limit-backoff-strategy.md`, `ai/SPECIFICATION.md` §4.2 / §4.5, `ai/PROJECT.md` §9.

| Requirement | Status | Implementation evidence |
|---|---|---|
| Classify retryable and non-retryable failures explicitly | Met | Retryable: `_TransientHttpError` for 429, `{500, 502, 503, 504}`, `httpx.TimeoutException`, `httpx.ConnectError`. Non-retryable: `_ClassifiedError` for BLOCKED / UNKNOWN_ERROR / STRUCTURAL_CHANGE, plus 501/505 (excluded from `_TRANSIENT_5XX_STATUSES`). Parser/config errors are never retried — parsing happens only after a successful fetch. |
| Handle 429/rate-limit and respect `Retry-After` | Met | `_do_request` parses `Retry-After`, caps it via `_cap_retry_after` (`max_retry_after`), logs, sleeps, then raises a retryable error. |
| Bounded exponential backoff with jitter | Met | `wait_random_exponential(multiplier, min, max)` (full jitter). Default `min=0.5` produces genuine jitter from the first retry (independently verified — see §4). |
| Configure maximum attempts and maximum wait bounds | Met | `max_retries`, `backoff_multiplier`, `backoff_min`, `backoff_max`, `max_retry_after` all configurable via constructor + env vars, and validated for consistency. |
| Avoid synchronized retry storms | Met | Full jitter via `wait_random_exponential`. Empirically verified that default parameters yield varying waits from attempt 1 (no lockstep). |
| Do not retry deterministic parser/schema/configuration errors | Met | 501/505 (deterministic server misconfiguration) are now non-retryable; parser errors occur post-fetch and are not in the retry predicate. |
| Preserve partial-success behavior | Met (single-page scope) | Adapter is single-page; partial parse preserves valid events plus malformed. The retry path never emits partial results, so no valid work is lost. (Multi-page partial success is not exercised — see Observations.) |
| Retries/replays do not create duplicate logical events | Met | Retries occur at the HTTP-fetch level before parsing/event creation; tests verify stable `external_id`s across retry and replay. |
| Expose retry/rate-limit outcomes through existing metrics/logging | Met | `source_retry_attempts_total` via `_on_retry` → `record_retry()`; structured `rate_limited_waiting` and `retry_budget_exhausted` log events. |
| Tests inject/mock clocks/sleep; no long real waits in CI | Met | Injectable `sleep_fn`; tests use `backoff_min=0.001`, `backoff_max=0.01` so tenacity waits are sub-10 ms. |
| Do not claim backoff guarantees source availability | Met | No such claim made in code or docs. |

**Tests required by the task** — all present: 429 + Retry-After, 429 without Retry-After, transient 5xx then recovery, timeout/connection retry, exhausted retry budget, non-retryable failure, bounded maximum wait/attempts, partial success, replay/idempotency, retry metrics/logging.

---

## 3. Git Diff Review

- **Scope correctness:** Correct. Both changed files belong to TASK-052. No unrelated files touched.
- **Unrelated changes:** None.
- **Architectural changes:** None. The change is confined to the `DifficultRetailerClient` retry/backoff implementation and its tests; no Kafka/processor/lake/warehouse/schema changes.
- **Accidental/debug/dead code:** No debugging artifacts, temporary files, generated artifacts, or secrets. The dead `backoff_jitter` configuration introduced by the `feat` commit was removed by the `fix` commit.
- **Dependencies/configuration:** No new dependencies — reuses `tenacity` (already used by sibling adapters). New `DIFFICULT_RETAILER_BACKOFF_*` and `DIFFICULT_RETAILER_MAX_RETRY_AFTER` env vars follow the existing constructor > env > default resolution convention.
- **Tests weakened?** No. The `fix` commit *strengthened* assertions: retry-metric tests changed from `!= 0` to exact counts (`== 1`, `== 2`), and added non-retryable 501/505 and negative/zero `Retry-After` tests. The pre-existing `test_difficult_retailer_adapter.py` is untouched and still passes.
- **Branch/task isolation:** Reviewed HEAD sits on `feature/TASK-052`; the two commits are the only commits in the range. No cross-task contamination.

---

## 4. Test and Verification Review

### Tests examined

`tests/test_adapters/test_difficult_retailer_backoff.py` (new) plus `tests/test_adapters/test_difficult_retailer_adapter.py` (regression). The new suite covers Retry-After (with/without/invalid/negative/zero/capped), 5xx recovery (500/503) and non-retryable 501/505, timeout/connection recovery, exhausted budget, non-retryable failures (403/404/captcha/maintenance), backoff parameter validation, partial parse, replay/idempotency, retry metrics (exact counts), env-var config, and injectable sleep.

### Test adequacy

Good breadth; deterministic fixtures/mocks and injectable sleep avoid real waits. Remaining gaps (non-blocking):

- No test asserts the *actual wait values* produced by `wait_random_exponential`, so a regression of the default-jitter behavior (the prior Finding #1) would not be caught by an assertion. The fix changes the default (`min=0.5`), but only the reviewer's empirical check confirms jitter is now present.
- "Partial success" is tested only as single-page partial parsing (TASK-051 behavior), not as a bounded multi-page collection interrupted mid-way by a transient failure. The adapter is single-page, so this is a scope limitation rather than a defect (see Observations).

### Verification status

| Check | Result | Status |
|---|---|---|
| `python -m pytest tests/test_adapters/test_difficult_retailer_backoff.py tests/test_adapters/test_difficult_retailer_adapter.py -q` | **111 passed** | Independently verified |
| `python -m ruff check libs/adapters/difficult_retailer/client.py tests/test_adapters/test_difficult_retailer_backoff.py` | All checks passed | Independently verified |
| `python -m ruff format --check ...` (same two files) | 2 files already formatted | Independently verified |
| `python -m mypy libs/adapters/difficult_retailer/client.py tests/test_adapters/test_difficult_retailer_backoff.py` | Success: no issues found | Independently verified |
| `python -m pytest -m integration` | Not run — TASK-052 is a pure HTTP-adapter retry/backoff change with mocked HTTP; it introduces no Kafka/persistence/MinIO/infrastructure code. | Unverified (out of scope for this task) |

### Independent empirical checks

1. **Default jitter (prior Finding #1) is fixed.** Sampled `wait_random_exponential(multiplier=1.0, min=0.5, max=30.0)` across attempts:

   ```
   attempt=1: [0.82, 0.513, 0.638, 0.612, 0.868]
   attempt=2: [1.515, 1.838, 0.63, 1.133, 0.545]
   attempt=3: [1.265, 2.269, 0.593, 1.196, 2.775]
   ```

   Values vary within a real range from the first retry — no deterministic lockstep remains.

2. **`max_retry_after` positivity gap confirmed.** `DifficultRetailerClient(max_retry_after=0)` and `(max_retry_after=-3)` are both accepted; `_cap_retry_after(5.0)` returns `0.0` and `-3.0` respectively (see Finding #2).

---

## 5. Findings

### Disposition of prior review findings (#1–#7)

| # | Prior severity | Status |
|---|---|---|
| #1 — Default backoff had no jitter for the first two retries | High | **Resolved.** `DEFAULT_BACKOFF_MIN` changed `2.0 → 0.5`; jitter now present from attempt 1. |
| #2 — `backoff_jitter` was dead/unused configuration | Moderate | **Resolved.** Parameter, env var, validation, default, and tests all removed. |
| #3 — Retry predicate broadened to all `>= 500` | Moderate | **Resolved.** Now `_TRANSIENT_5XX_STATUSES = frozenset({500, 502, 503, 504})`; 501/505 are non-retryable with new tests. |
| #4 — Double wait on 429 (Retry-After + backoff) | Moderate | **Not addressed.** See Finding #1 below. |
| #5 — Negative/non-positive `Retry-After` and `max_retry_after` not sanitized | Minor | **Partially addressed.** `_cap_retry_after` now returns `None` for non-positive `Retry-After`; `max_retry_after` still lacks positivity validation. See Finding #2 below. |
| #6 — Docstring drift on retryable error scope | Minor | **Resolved.** Module and `_TransientHttpError` docstrings now include 429. |
| #7 — Retry-metric tests asserted only `!= 0` | Minor | **Resolved.** Tests now assert exact counts (`== 1`, `== 2`). |

### Finding #1 — 429 double wait persists; `Retry-After` slept even on the final (non-retried) attempt
- **Severity:** Moderate
- **File/line:** `libs/adapters/difficult_retailer/client.py:348-372` (`_do_request`), `359` (`await self._sleep(capped_retry_after)`)
- **Problem:** On a 429 with `Retry-After`, `_do_request` sleeps the (capped) `Retry-After` and *then* raises `_TransientHttpError`, which triggers tenacity's `wait_random_exponential` backoff on top. Two waits are therefore stacked for every retried 429. Separately, because the `Retry-After` sleep happens unconditionally inside `_do_request`, it also fires on the **final** attempt where no retry follows — so a persistent 429 with `Retry-After` capped at the default 60 s sleeps up to 60 s before the failure is raised.
- **Impact:** Effective per-cycle wait exceeds `Retry-After`, and there is no single documented maximum wait. More concretely, the "persistent failures terminate clearly" acceptance path can be delayed by up to `max_retry_after` (60 s default) on the last attempt for no benefit.
- **Recommendation:** Make `Retry-After` the authoritative wait for 429 (e.g. use it as the wait for that attempt and skip the additional exponential backoff), and do not sleep `Retry-After` when the attempt is the last one (or, equivalently, defer the sleep to tenacity so it only occurs before an actual retry). Document the actual maximum wait.

### Finding #2 — `max_retry_after` is not validated for positivity
- **Severity:** Minor
- **File/line:** `libs/adapters/difficult_retailer/client.py:101-119` (`_validate_backoff_params` validates `multiplier`/`min_wait`/`max_wait` only), `181` (`max_retry_after` resolution), `374-381` (`_cap_retry_after`)
- **Problem:** Unlike the other backoff parameters, `max_retry_after` has no positivity validation. `max_retry_after=0` is accepted and silently caps every `Retry-After` to `0`; `max_retry_after=-3` is accepted and produces `_cap_retry_after(5.0) == -3.0`, so `_sleep(-3.0)` returns immediately and a misleading `rate_limited_waiting` log is emitted with `retry_after_capped=-3.0`.
- **Impact:** Misconfiguration via `DIFFICULT_RETAILER_MAX_RETRY_AFTER` yields surprising, non-obvious behavior and log noise. No functional risk in normal operation.
- **Recommendation:** Validate `max_retry_after > 0` in `_validate_backoff_params` (or a dedicated validator), consistent with the other backoff parameters.

---

## 6. Non-Defect Observations

- **Deterministic, no-real-wait test design is sound.** The injectable `sleep_fn` (sync and async) and sub-10 ms tenacity waits satisfy "Tests must inject/mock clocks/sleep; no long real waits in CI." The `test_no_real_sleep_in_tests` test explicitly asserts elapsed time stays under 1 s.
- **The 5xx narrowing now correctly distinguishes transient from deterministic server errors.** 500/502/503/504 are retried; 501/505 are surfaced as non-retryable `SourceFetchError` (`UNKNOWN_ERROR`). This is a precise, well-tested classification.
- **`max_retry_after` cap is a genuine improvement over TASK-051.** Previously an unbounded `Retry-After` (e.g. 300 s) was slept in full; now capped at 60 s by default.
- **Partial-success scope limitation.** The adapter is single-page (no pagination), so the "preserve partial success across a bounded collection" requirement is only demonstrated as single-page partial parsing, not as a multi-page collection interrupted by a transient failure. Consistent with the adapter's stated single-page design; not a defect, but the requirement is only weakly evidenced.
- **Cross-adapter inconsistency (out of scope).** Sibling adapters `web_retailer/client.py` and `ebay/client.py` still use the non-jittered `wait_exponential`. TASK-052 correctly scoped its change to `difficult_retailer` only, but the platform now has divergent backoff behavior across adapters; worth a follow-up task if uniformity is desired.
- **`Retry-After` HTTP-date form is not handled.** `Retry-After` is parsed as a float only; the `Retry-After: <http-date>` form falls into the `ValueError` branch and is treated as absent. A reasonable simplification for this scope.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The two-commit change set satisfies the task's four acceptance criteria — bounded observable retries, clear termination on persistent failures, preserved partial work, and no duplicate logical data — and introduces no out-of-scope or architectural changes. The prior review's blocking findings (#1 default-jitter collapse, #2 dead `backoff_jitter`) are resolved, and the over-broad 5xx retry (#3) and metric-count assertions (#7) are also fixed.

Independently verified checks pass: 111 tests, `ruff check`, `ruff format --check`, and `mypy`. The default backoff is confirmed to produce real jitter from the first retry.

The two remaining findings are non-blocking: the stacked 429 wait (Retry-After + backoff) with a wasted `Retry-After` sleep on the final attempt (Finding #1, Moderate), and the missing positivity validation for `max_retry_after` (Finding #2, Minor). These are recommended follow-ups, not acceptance blockers.
