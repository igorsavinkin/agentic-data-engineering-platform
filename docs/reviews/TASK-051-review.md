# TASK-051 Review — Difficult-Source Adapter

## 1. Review Header

- **Task:** TASK-051 — Difficult-Source Adapter
- **Review date:** 2026-09-17
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `4dcf51114f61d6ae2711e8729c3e8da1dbb24b3d...bd2115c115b500977c382a813e3cebb4ec9da404`
  - Single commit: `bd2115c` — `feat(TASK-051): Add difficult-source adapter for premium retailer`
  - **Reviewed HEAD:** `bd2115c115b500977c382a813e3cebb4ec9da404` on `feature/TASK-051`
- **Scope:** `libs/adapters/difficult_retailer/` (new adapter package), `tests/test_adapters/test_difficult_retailer_adapter.py`, and `tests/fixtures/difficult_retailer/` (new test fixtures). 12 files, +1604 lines, all additive.
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

---

## 2. Requirements Coverage

Sources: `ai/tasks/TASK-051-difficult-source-adapter.md`, `ai/SPECIFICATION.md` §4, `ai/PROJECT.md` §7, `ai/ROADMAP.md` §12 (Milestone 5C).

| Requirement | Status | Implementation evidence |
|---|---|---|
| Select/document the difficult source | Partial | A fictional "premium retailer" (`source_name == "premium_retailer"`) was selected rather than Amazon or a named real retailer. Documented only in code docstrings (`difficult_retailer/__init__.py`, `adapter.py`); no governance/doc update records the selection rationale. See Finding #4. |
| Implement behind `SourceAdapterProtocol`; no source-specific structures leak downstream | Met | `DifficultRetailerAdapter(SourceAdapterProtocol)`; emits only `ProductObservationEvent`; HTML/CSS knowledge confined to `parser.py`. |
| Prefer least complex reliable collection mechanism | Met | Single-page HTTP GET + HTML parse; no browser automation. |
| Preserve stable source/external identity and canonical event compatibility | Met | `source_name` is a constant `"premium_retailer"`; `external_id` (product_id) preserved verbatim; events built via `SourceAdapterProtocol._build_event`. |
| Externalize headers, endpoints, timeouts, credentials/tokens, other config | Partial | `base_url`, `timeout`, `user_agent`, `catalog_path`, `max_retries` externalized via constructor + env vars (`DIFFICULT_RETAILER_*`). `Accept`/`Accept-Language` headers hardcoded. No credentials/tokens (fictional source). See Finding #6. |
| Treat blocking, rate limiting, unavailable, structural changes, partial parseability as explicit outcomes | Partial | All cases are detected and raise `SourceFetchError`, but the `ResponseKind` classification is collapsed into a message string rather than a structured field. See Findings #1, #2. |
| Never add stealth/evasion to defeat access controls | Met | No CAPTCHA solving or access-control circumvention; blocked/rate-limited responses are surfaced as outcomes and respected. |
| CI deterministic, fixtures/mocks, no live access | Met | All tests use local HTML fixtures + `AsyncMock`/`MagicMock`; no network. |
| Do not redesign downstream Kafka/processor/lake/warehouse schemas | Met | No files outside the adapter + test scope changed. |
| Keep detailed backoff/degradation/freshness for TASK-052–054 | Mostly met | No degradation-detection or freshness module added; but the client implements bounded retry + `Retry-After` handling, lightly overlapping TASK-052. Not blocking. |

**Tests required by the task** — all present: adapter protocol compliance, representative page mapping, unavailable/blocked, malformed/partial, timeout/network failure, canonical compatibility, stable source identity, deterministic mocked execution.

---

## 3. Git Diff Review

- **Scope correctness:** Correct. Every change belongs to TASK-051. The diff is purely additive (12 new files, 0 modified existing files), so no existing behavior was touched.
- **Unrelated changes:** None.
- **Architectural changes:** None. No Kafka/processor/lake/warehouse schema changes. The new adapter sits entirely behind `SourceAdapterProtocol`.
- **Accidental/debug/dead code:** No debugging artifacts or secrets. Minor dead code noted in `classifier.py` (Finding #5).
- **Dependencies/configuration:** No new dependencies — reuses `httpx`, `tenacity`, `selectolax`, `pydantic` already used by the sibling `web_retailer` adapter. Config externalized via env vars consistent with `WebRetailerClient`.
- **Branch/task isolation:** Reviewed commit `bd2115c` is the only commit in range and sits on `feature/TASK-051`; working tree clean. No cross-task contamination.

---

## 4. Test and Verification Review

### Tests examined

`tests/test_adapters/test_difficult_retailer_adapter.py` (63 tests) plus six HTML fixtures. Coverage spans the classifier, parser, adapter protocol compliance, success path, blocked/rate-limited/unavailable responses, structural change, partial parse, network failure, configuration, canonical compatibility, metrics, and deterministic execution.

### Test adequacy

Good breadth and appropriate use of deterministic fixtures/mocks. Gaps:

- Retry behavior is not actually exercised (Finding #3): `_make_adapter` hardcodes `max_retries=1`, so tests named `..._after_retries_...` perform a single attempt.
- No test for 500/502/504 handling or for the retry-attempt metric increment.
- Env-var override tests cover only `BASE_URL` and `CATALOG_PATH` (not `TIMEOUT`, `USER_AGENT`, `MAX_RETRIES`), whereas the sibling `test_web_retailer_adapter.py` covers all five.

### Verification status

| Check | Result | Status |
|---|---|---|
| `python -m pytest tests/test_adapters/test_difficult_retailer_adapter.py -q` | **63 passed** | Independently verified |
| `python -m ruff check libs/adapters/difficult_retailer tests/test_adapters/test_difficult_retailer_adapter.py` | All checks passed | Independently verified |
| `python -m ruff format --check libs/adapters/difficult_retailer tests/test_adapters/test_difficult_retailer_adapter.py` | 6 files already formatted | Independently verified |
| `python -m mypy libs/adapters/difficult_retailer` | Success (5 source files) | Independently verified |
| Integration tests (`pytest -m integration`) | Not run — TASK-051 is a pure adapter with mocked HTTP and introduces no Kafka/persistence/infrastructure code; the milestone integration gate is TASK-055. | Unverified (out of scope for this task) |

---

## 5. Findings

### Finding #1 — `ResponseKind` classification is discarded; not surfaced structurally
- **Severity:** Moderate
- **File/line:** `libs/adapters/difficult_retailer/client.py:172,194` and `libs/adapters/protocol.py` (`SourceFetchError`)
- **Problem:** `classify_response()` produces a structured `ResponseKind` (blocked / rate_limited / unavailable / …), but `fetch_listing_page` converts every classified failure into a generic `SourceFetchError` whose message merely embeds the kind as an English string (e.g. `"…response classified as blocked"`). The docstring claims the error carries `response_kind`, but `SourceFetchError` has no such attribute (only `message` and `source`).
- **Impact:** The "explicit outcomes" requirement is weakened: downstream source-aware retry/degradation strategies (TASK-052/053) would have to string-match error messages, which is fragile and undermines the purpose of the `ResponseKind` enum.
- **Recommendation:** Attach the classified kind to `SourceFetchError` (or a dedicated subclass/attribute) so callers can branch on `ResponseKind` rather than message text.

### Finding #2 — Docstring/behavior mismatch: 5xx (except 503) are not retried
- **Severity:** Moderate
- **File/line:** `libs/adapters/difficult_retailer/client.py:4,174,257`; `classifier.py:76`
- **Problem:** The module and method docstrings state "Retries transient failures (5xx, timeouts, connection errors)" (or "5xx except 503"), but `classify_response()` maps 500/502/504 to `UNKNOWN_ERROR`, which `_do_request` raises as the non-retryable `_ClassifiedError`. Only 503 (`UNAVAILABLE`) is retried. This diverges from the sibling `WebRetailerClient`, which retries all `>= 500`, and from SPECIFICATION §4.2 ("retries and exponential backoff").
- **Impact:** Genuine transient server errors (500/502/504) fail fast with no retry, contradicting the documented contract and established convention.
- **Recommendation:** Either classify 500/502/504 as retryable (matching the sibling adapter) or correct the docstrings to accurately describe the retry policy. Prefer retrying transient 5xx.

### Finding #3 — Retry path is untested; test names are misleading
- **Severity:** Moderate
- **File/line:** `tests/test_adapters/test_difficult_retailer_adapter.py:91,334,355`
- **Problem:** `_make_adapter` hardcodes `max_retries=1`, so `test_503_raises_after_retries` and `test_429_after_retries_raises` perform exactly one attempt — no retry occurs. There is no test with `max_retries > 1` plus a retryable error, and no assertion on the retry-attempt metric or on 500/502/504 behavior.
- **Impact:** The retry/backoff logic introduced in this task is effectively unverified by tests.
- **Recommendation:** Add a test that sets `max_retries > 1` with a retryable response and asserts the retry count (and `source_retry_attempts_total`); fix misleading test names.

### Finding #4 — Difficult-source selection not documented in governance docs
- **Severity:** Moderate
- **File/line:** none (no docs change in the commit); documented only in `libs/adapters/difficult_retailer/__init__.py`, `adapter.py`
- **Problem:** TASK-051 requires "Select/document the difficult source". The implementation selects a fictional "premium retailer" instead of the named default ("Amazon or equivalent", SPECIFICATION §4.1). The choice is justified nowhere beyond short code docstrings, and the rationale (why fictional vs. Amazon/a real retailer) is unrecorded.
- **Impact:** The selection decision — a durable, replaceable-source concern explicitly called out in SPECIFICATION §4.1 — is not traceable for future maintainers.
- **Recommendation:** Record the selection and rationale in `ai/SPECIFICATION.md` §4.1 (or a short note/ADR) so the difficult source identity is documented in governance, not only in code.

### Finding #5 — Dead/unused `ResponseKind.STRUCTURAL_CHANGE` and redundant 403 branch
- **Severity:** Minor
- **File/line:** `libs/adapters/difficult_retailer/classifier.py:27,61-65`
- **Problem:** `STRUCTURAL_CHANGE` is declared in the enum but never returned by `classify_response()` (structural change is detected separately in the parser). The 403 branch has an `if any(indicator...)` whose both paths `return ResponseKind.BLOCKED`, making the `if` dead.
- **Impact:** Misleading surface area; no functional impact.
- **Recommendation:** Remove the unused enum value (or have the classifier produce it) and simplify the 403 branch to a single `return ResponseKind.BLOCKED`.

### Finding #6 — Headers only partially externalized
- **Severity:** Minor
- **File/line:** `libs/adapters/difficult_retailer/client.py` (`_get_client`)
- **Problem:** TASK-051 requires "Externalize headers, endpoints, timeouts, credentials/tokens if any, and other configuration." Only `User-Agent` is externalized; `Accept` and `Accept-Language` remain hardcoded.
- **Impact:** Technically below the letter of the requirement; low practical risk since the fictional source has no credentials and the omitted headers are static defaults. Consistent with the sibling `WebRetailerClient`.
- **Recommendation:** Externalize the remaining headers via the same constructor/env-var pattern, or explicitly document why they are intentionally static.

### Finding #7 — Double wait on rate-limit (Retry-After + tenacity backoff)
- **Severity:** Minor
- **File/line:** `libs/adapters/difficult_retailer/client.py` (`_do_request`, 429 branch)
- **Problem:** On 429, `_do_request` sleeps `retry_after` then raises `_TransientHttpError`, which additionally triggers tenacity's `wait_exponential`. The `Retry-After` value is not actually used as the tenacity wait, producing two stacked waits.
- **Impact:** Unnecessarily long effective backoff on rate-limit; behavior is somewhat surprising and not reflected in tests (tests use `Retry-After: 0`).
- **Recommendation:** Defer this to TASK-052 (bounded rate-limit/backoff policy) and, in the interim, either use `Retry-After` as the tenacity wait or drop the explicit `asyncio.sleep`.

### Finding #8 — Partial parseability not reflected in metrics
- **Severity:** Minor
- **File/line:** `libs/adapters/difficult_retailer/adapter.py` (`_fetch_single`)
- **Problem:** Partial parseability (some valid, some malformed) increments `MALFORMED_RECORDS` and logs `degraded_collection`, but `record_partial_failure()` / `PARTIAL_FAILURES` is never invoked, despite partial parseability being a named difficult-source outcome.
- **Impact:** The degradation signal is incomplete in metrics, reducing observability for TASK-053.
- **Recommendation:** Decide and document whether partial parseability should increment `PARTIAL_FAILURES`; if so, call `record_partial_failure()`.

### Finding #9 — Generic malformed reason discards underlying error detail
- **Severity:** Minor
- **File/line:** `libs/adapters/difficult_retailer/adapter.py` (`_to_canonical_event` exception handler)
- **Problem:** When canonical construction fails, the malformed entry uses a fixed `"Failed canonical event construction"` reason and drops the actual exception.
- **Impact:** Reduced diagnosability of edge-case validation failures (e.g. a negative price triggering the Pydantic validator).
- **Recommendation:** Include the exception message in the malformed reason (bounded, to avoid cardinality issues).

---

## 6. Non-Defect Observations

- **Browser-like default User-Agent is not stealth/evasion.** The default `Mozilla/5.0 … Chrome/120` UA plus `Accept`/`Accept-Language` headers mimic a browser, but the adapter does not attempt to solve CAPTCHAs, rotate identities, or defeat rate limits — blocked and rate-limited responses are surfaced and respected. This satisfies the "no stealth/evasion" requirement.
- **Fictional source choice is defensible.** A fictional deterministic source avoids live-access, legal, and anti-bot constraints while still demonstrating the required difficult behaviors (bot detection, rate limit, unavailability, structural change, partial parse). It is consistent with SPECIFICATION §4.1's replacement allowance — the gap is only the missing documented rationale (Finding #4).
- **Canonical isolation is clean.** HTML/CSS selectors are confined to `parser.py`; `ParsedProduct` is a local intermediate model; only `ProductObservationEvent` crosses the adapter boundary.
- **Metric hygiene follows TASK-040/TASK-011 conventions.** Instance-local, bounded labels (`source_name` only), exception-safe wrappers; no secrets in logs or metrics.
- **`difficult_retailer/__init__.py` exports only the adapter** (not the client/classifier/parser), unlike `web_retailer/__init__.py` which also exports the client and model. This is cosmetic and does not affect correctness.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The implementation correctly delivers a difficult-source adapter behind `SourceAdapterProtocol`, preserves canonical event compatibility and stable source identity, treats the required difficult-source behaviors as explicit outcomes, and includes a comprehensive, deterministic, mocked test suite (63 tests passing). All repository checks independently verified pass: `ruff check`, `ruff format --check`, and `mypy`. No downstream schema/architecture changes, no secrets, no new dependencies.

The findings are Moderate-to-Minor and do not block acceptance: the most substantive are the loss of the structured `ResponseKind` on errors (Finding #1), the inaccurate 5xx-retry documentation/behavior (Finding #2), the untested retry path (Finding #3), and the undocumented source-selection rationale (Finding #4). These should be addressed before or during TASK-052/TASK-053, which will consume the failure/classification outcomes this adapter produces.
