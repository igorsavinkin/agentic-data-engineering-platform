# TASK-049 Review — Source-Health Metrics

## 1. Review Header

- **Task ID:** TASK-049 — Source-Health Metrics
- **Review date:** 2026-09-17
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:** `9198c5bfecab0195724968688bbe7f299637387d..e57cd7c328de93f4a80b5ea4ac2a23a55536b678`
- **Reviewed HEAD:** `e57cd7c328de93f4a80b5ea4ac2a23a55536b678` on `feature/TASK-049`
- **Scope:** source-health metrics for the web retailer adapter (`libs/adapters/web_retailer/*`, `libs/observability/source_metrics.py`, and their tests)
- **Verdict:** **APPROVED WITH NON-BLOCKING FINDINGS**

## 2. Requirements Coverage

| Requirement | Status | Evidence |
|---|---|---|
| Reuse existing `SourceMetrics`; no second metrics framework | ✅ | New counters added to existing `SourceMetric` StrEnum and `SourceMetrics`; no new framework |
| Track fetch attempts / success / failure | ✅ | Pre-existing `FETCH_ATTEMPTS` / `FETCH_SUCCESS` / `FETCH_FAILURE`, still wired in `adapter.fetch()` |
| Track pages fetched | ✅ | New `SourceMetric.PAGES_FETCHED` + `record_pages_fetched()`; incremented per parsed page in `_fetch_paginated()` |
| Track records collected / events emitted | ✅ | Pre-existing `RECORDS_COLLECTED` / `RECORDS_EMITTED` via `record_fetch_success()` |
| Track malformed records | ✅ | New `MALFORMED_RECORDS` + `record_malformed(len(all_malformed))` |
| Track retry activity | ✅ | New `RETRY_ATTEMPTS` + `record_retry()`, wired via tenacity `before_sleep=self._on_retry` in `client.py` |
| Track fetch latency | ✅ | Pre-existing `time_fetch()` / `_LatencyTracker` already wrapping `_fetch_paginated()` |
| Track parse latency | ⚠️ | Not tracked; no parse-latency abstraction exists, so the task's "where existing abstractions support them" qualifier makes this acceptable (see Observation O1) |
| Expose last-successful/freshness timestamp | ✅ | Pre-existing `SourceFreshness`, updated via `record_fetch_success()`; exposed via `get_last_successful_fetch()` / `snapshot()["source_last_successful_fetch"]` |
| Distinguish zero-result vs network failure vs parser degradation vs partial pagination vs stale | ✅ | `ZERO_RECORD_FETCHES`, `FETCH_FAILURE` (+ no freshness update), `MALFORMED_RECORDS`, `PARTIAL_FAILURES`, freshness age respectively |
| Low-cardinality labels only | ✅ | `snapshot()` labels are fixed metric names + `source` only; no URL/product/external ID/event ID/exception/page-URL labels |
| Structured logs for degraded/partial runs, no secrets / page bodies | ✅ | `degraded_collection`, `parser_malformed_records`, `pagination_failed`, `pagination_empty_page` use `extra` with integer/enum fields only |
| Metrics/logging failures must not change ingestion semantics | ✅ | All new metric methods wrapped in `try/except Exception: pass`; logging via stdlib `logger`, which does not propagate handler errors |
| Integrate with TASK-048 retry/pagination (no duplication) | ✅ | Retry metric via existing tenacity hook; pagination partial-failure metric inside existing loop |
| No Grafana dashboards / alerts / Airflow DAGs | ✅ | None introduced |

## 3. Git Diff Review

- **Scope correctness:** ✅ All changes are confined to the web retailer adapter health metrics and its tests. The 5 files (`adapter.py`, `client.py`, `source_metrics.py`, two test files) are all in-scope.
- **Unrelated changes:** None.
- **Architectural changes:** None. New metrics extend the existing instance-local `SourceMetrics` (consistent with the TASK-011 `KafkaMetrics` / TASK-040 source-metrics conventions documented in `source_metrics.py`).
- **Accidental changes:** None (no debug code, temp files, dead code, generated artifacts, or secrets).
- **Dependency/configuration changes:** None. No new third-party dependencies; reuses existing `tenacity`, `httpx`, stdlib `logging`.
- **Branch/task isolation:** ✅ Working tree clean; branch `feature/TASK-049`; the reviewed range contains exactly one commit (`e57cd7c`). No changes from other TASK-xxx are mixed in.

## 4. Test and Verification Review

**Tests examined:**

- `tests/test_observability/test_source_metrics.py` — new `TestTask049HealthMetrics` (12 tests): new counters start at zero, increment behavior (default + explicit counts), exception isolation, freshness set/not-set on success/failure, degraded-run snapshot, no-high-cardinality check.
- `tests/test_adapters/test_web_retailer_adapter.py` — new `TestHealthMetrics` (10 tests): successful fetch pages, multi-page count, zero-result, network failure, parser malformed, partial pagination, record/event counts, freshness, no-high-cardinality snapshot, and retry metrics.

**Test adequacy:**

All task-required test categories are nominally covered (successful fetch, zero-result, network failure, parser degradation, retry, partial pagination, record/event counts, freshness, no high-cardinality labels). However, the retry-metric test is superficial (see Finding F1).

**Independently executed (by reviewer):**

- `python -m pytest tests/test_observability/test_source_metrics.py tests/test_adapters/test_web_retailer_adapter.py -q` → **91 passed**.
- `python -m ruff check libs/adapters/web_retailer/adapter.py libs/adapters/web_retailer/client.py libs/observability/source_metrics.py tests/test_adapters/test_web_retailer_adapter.py tests/test_observability/test_source_metrics.py` → **All checks passed**.
- `python -m mypy libs/observability/source_metrics.py libs/adapters/web_retailer/adapter.py libs/adapters/web_retailer/client.py` → **Success: no issues found in 3 source files**.

**Implementation results inspected but not rerun:** none (all three checks above were run independently).

**Unverified checks:** `python -m pytest -m integration` (Docker-dependent) was not run. TASK-049 does not touch Kafka/persistence/MinIO/infrastructure boundaries, so integration tests are out of scope for this change.

## 5. Findings

### F1 — Moderate: retry-metric integration is not actually tested

- **File:** `tests/test_adapters/test_web_retailer_adapter.py` (`test_retry_metrics_via_client`, lines ~866–881)
- **Problem:** The test named `test_retry_metrics_via_client` constructs `mock_client = AsyncMock(spec=WebRetailerClient)` but never calls `adapter.fetch()` or `mock_client.fetch_listing_page()`. It then calls `metrics.record_retry()` twice directly and asserts `RETRY_ATTEMPTS == 2`. This is a duplicate of `test_record_retry` in `test_source_metrics.py` and does not exercise the newly added `before_sleep=self._on_retry` → `_on_retry` → `record_retry()` wiring in `client.py`.
- **Impact:** The retry-metric requirement (a core TASK-049 item) has no integration coverage. A regression in the tenacity `before_sleep` wiring (e.g., a removed or misspelled callback) would pass the full suite undetected.
- **Recommendation:** Add a real client-level test: construct `WebRetailerClient(http_client=<mock that returns 500 then 200>, metrics=metrics, max_retries=3)` and assert `metrics.snapshot()[SourceMetric.RETRY_ATTEMPTS] == 1` after `fetch_listing_page()`. Remove or rename the misleading `test_retry_metrics_via_client`.

### F2 — Minor: adapter does not propagate metrics to an injected client

- **File:** `libs/adapters/web_retailer/adapter.py` (`__init__`, lines ~48–62)
- **Problem:** `self._metrics` is set on the adapter, but only the default-constructed client receives `metrics=self._metrics`. When a caller passes `client=`, the injected client's `_metrics` is left as-is (normally `None`), so its `_on_retry` callback silently records nothing.
- **Impact:** Retry metrics silently do not flow when a client is injected alongside a `metrics` object. The production path (adapter-constructed client) works correctly, but the DI/test path is a silent no-op — and it is the root cause of F1's weak test.
- **Recommendation:** Either wire the adapter's metrics into an injected client (`self._client._metrics = self._metrics`), or document the contract that an injected client must be given its own metrics. Prefer the former so the adapter owns the metrics wiring consistently.

### F3 — Minor: empty mid-pagination page is logged as degradation but not reflected in metrics

- **File:** `libs/adapters/web_retailer/adapter.py` (`_fetch_paginated`, lines ~125–133)
- **Problem:** When pagination stops because a later page returns an empty body, the code logs `pagination_empty_page` (a `WARNING`), but does not set `partial_failure = True`. Consequently neither `PARTIAL_FAILURES` nor the `degraded_collection` log fires for this case.
- **Impact:** A logged warning (implying degradation) is inconsistent with the new degraded/partial-failure metrics, so an empty-page truncation is not distinguishable via metrics. The empty-page → clean-stop semantics pre-date TASK-049 (the diff only reformats the log), so this is not a regression, but TASK-049 introduced the degraded/partial-failure signal without classifying this case.
- **Recommendation:** Decide whether an empty mid-pagination page should set `partial_failure` (or a distinct signal), and align the log with the metrics accordingly.

## 6. Non-Defect Observations

- **O1 — Parse latency is not tracked.** Fetch latency is captured via the pre-existing `time_fetch()` / `_LatencyTracker`. There is no parse-latency abstraction in `SourceMetrics`, and the task's "where existing abstractions support them" qualifier makes this acceptable. If parse latency is eventually wanted, add a dedicated timer around `parse_listing_page` rather than overloading the fetch timer.
- **O2 — Partial failure is recorded as both success and partial failure.** On a mid-cycle page failure, the code records `FETCH_SUCCESS` (and updates freshness) in addition to `PARTIAL_FAILURES`. This is consistent with TASK-048's "return partial results rather than losing everything" semantics and gives a distinct failure signal, but consumers should treat `PARTIAL_FAILURES > 0` as "successful but degraded." This resolves the prior TASK-048 review concern (F1) that a partial fetch had no failure signal in metrics.
- **O3 — `pages_fetched` counts parsed pages, not fetched pages.** The counter increments after a page is successfully parsed; an empty page (break) or a failing page is not counted. The name is a minor nuance, not a defect — the count is "pages that yielded a parse result."
- **O4 — Cycle-level vs per-page granularity.** TASK-049 adds cycle-level aggregates (`pages_fetched`, `malformed`, `partial_failures`, `retry_attempts`) but not per-page success/failure counters. This satisfies the TASK-049 spec, which asks for these aggregate signals; per-page counters remain out of scope.

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS.**

The implementation satisfies all TASK-049 requirements: it reuses the existing `SourceMetrics` framework, adds low-cardinality counters for pages/malformed/retries/partial failures, exposes freshness, adds structured degraded-run logging without secrets or page bodies, preserves ingestion semantics under metric/logging failure, and integrates with (rather than duplicates) the TASK-048 retry/pagination behavior. The diff is cleanly scoped to the task, with no unrelated or architectural changes and no new dependencies or secrets.

The findings are non-blocking: F1 is a test-coverage gap (the production retry-metric path works, but no test exercises it), F2 is a silent no-op only on the injected-client path, and F3 is a pre-existing classification now made visible by the new metrics. None represent unsafe behavior in the primary production path, but F1/F2 should be addressed to avoid false confidence in the retry-metric requirement.

Independently verified: unit tests (91 passed), `ruff` (clean), and `mypy` (clean) on the changed files.
