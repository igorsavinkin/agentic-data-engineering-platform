# Post-Merge OCR Review — TASK-054 & TASK-055

**Review date:** 2026-09-17
**Reviewer:** Qoder (inline OCR methodology, no external LLM)
**PRs reviewed:** #66 (TASK-054), #67 (TASK-055)

---

## TASK-054 — Freshness Failure Scenarios (PR #66)

**Files reviewed:** 4 (3 production, 1 test)
**Issues found:** 1 high priority / 3 medium priority

### High Priority

- **`libs/observability/health_assessment.py:158`** — `update_freshness_age()` is never called in production code. The `STALE` degradation state and `get_freshness_state()` are fully implemented and tested but unreachable through the adapter or runner. `DifficultRetailerAdapter.fetch()` and `IngestionRunner` never feed freshness data into the health tracker.
  > Recommendation: In `DifficultRetailerAdapter.fetch()`, after recording success/failure, call `self._health_tracker.update_freshness_age(self._metrics.get_freshness_age_seconds())`. TASK-055 tests work around this by calling `update_freshness_age` manually via `adapter._health_tracker`.

### Medium Priority

- **`libs/observability/health_assessment.py:126`** — `SourceHealthTracker` docstring claims "Thread-safe for concurrent outcome recording" but neither `_outcomes`, `_consecutive_empty`, nor the new `_freshness_age_seconds` are protected by a lock. `SourceMetrics` uses `threading.Lock` correctly; the tracker does not.
  > Recommendation: Either add a `threading.Lock` or soften the docstring to state the single-threaded assumption. The new `_freshness_age_seconds` write is atomic in CPython but the pattern is fragile.

- **`tests/test_observability/test_freshness_failures.py:26-40`** — `_make_clock()` defines an inner `clock_fn()` that is never returned or used. All tests pass `clock=lambda: clock_list[0]` directly, making the inner function dead code and the docstring misleading.
  > Recommendation: Return the callable alongside the list (e.g., as a tuple or a small `Clock` dataclass), or delete the dead function and update the docstring.

- **`libs/observability/health_assessment.py:220`** — No-history assessment returns `HEALTHY` with reason "no fetch history", while `FreshnessState.NEVER_COLLECTED` exists for the same semantic. A caller of `get_source_health()` sees `healthy` for a source that has never been collected, creating a diagnostic mismatch.
  > Recommendation: Document that "never collected" is a freshness-level classification (not health-level), or add a `freshness_state` signal to the no-history assessment.

---

## TASK-055 — Difficult-Source Integration Tests (PR #67)

**Files reviewed:** 1 (test-only)
**Issues found:** 0 high priority / 3 medium priority

### Medium Priority

- **`tests/test_difficult_source_integration.py:665,700,768`** — Three test methods manually call `adapter._health_tracker.update_freshness_age(...)` to work around the production wiring gap from TASK-054 Finding #1. This couples tests to a private attribute (`_health_tracker`) and masks the fact that production code doesn't feed freshness. If the adapter is refactored, these tests silently stop testing the intended scenario.
  > Recommendation: Once `update_freshness_age` is wired into the adapter (TASK-054 Finding #1), remove the manual calls. Until then, add a comment like `# TODO: remove when adapter wires freshness into health tracker` so the workaround is visible.

- **`tests/test_difficult_source_integration.py:66-80`** — `MockProducer` duplicates the pattern from `test_retailer_integration.py`. Both files define `MockProducer`, `TrackingSinks`, `_wrap_as_consumer_message`, and `_mock_httpx_response` with near-identical implementations.
  > Recommendation: Extract shared test helpers into `tests/conftest.py` or a `tests/helpers/` module to avoid divergence. Not blocking, but the duplication will grow as more integration test files are added.

- **`tests/test_difficult_source_integration.py:860-910`** — `test_all_sources_in_one_cycle` tests 3 sources (premium_retailer, fake_store, best_buy) but omits eBay. The `_make_ebay_search_response` helper at line 189 is defined but never used in this test or any other.
  > Recommendation: Either include eBay in the regression smoke (it's part of the source roster) or delete the unused `_make_ebay_search_response` helper. Dead helpers in test files accumulate silently.

### Non-Defect Observations

- All 10 required scenarios covered (healthy, rate-limited+recovered, persistent rate limiting, unavailable, structural change, partially parseable, stale freshness, recovery, replay/dedup, regression smoke).
- Mock-based pattern is correct — no Docker dependency; uses `MagicMock(spec=...)` for MinIO/httpx, `AsyncMock` for clients. Tests run in ~14s.
- Fixture reuse is clean — HTML fixtures from `tests/fixtures/difficult_retailer/` are loaded once at module level and shared across scenarios.
- No production code changes — correct scope for a test-only deliverable.
- ruff/mypy clean — all lint and type checks pass.

---

## Summary

| PR | Files | High | Medium | Verdict |
|----|-------|------|--------|---------|
| #66 (TASK-054) | 4 | 1 | 3 | Approved with findings |
| #67 (TASK-055) | 1 | 0 | 3 | Approved with findings |

**Cross-cutting issue:** The `update_freshness_age` production wiring gap — TASK-054 introduced the API, TASK-055 tests it manually, but neither wired it into the adapter. This should be a follow-up task to make STALE detection operational end-to-end without test workarounds.
