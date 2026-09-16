# TASK-046 Review — Retailer Source Selection and Adapter

## 1. Review Header

- **Task ID:** TASK-046 — Retailer Source Selection and Adapter
- **Review date:** 2026-09-17
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:** `0ee22b592ae0449b71436593782933af350ea15c...7dc71116b8c814aba7f792240dd10603e18de8a8` (merge-base of the provided review anchor `09f8502…7dc7111` to the reviewed HEAD)
- **Reviewed HEAD:** `7dc71116b8c814aba7f792240dd10603e18de8a8` (`fix(TASK-046): Switch to web_retailer, add env var config and validation`) on `feature/TASK-046`
- **Commits in range:** `c49c280` (`feat(TASK-046): Add Wayfair retailer adapter skeleton`), `7dc7111` (`fix(TASK-046): Switch to web_retailer, add env var config and validation`)
- **Scope:** `libs/adapters/web_retailer/` (new package: `__init__.py`, `adapter.py`, `client.py`, `models.py`), `tests/test_adapters/test_web_retailer_adapter.py` (new), and a committed `docs/reviews/TASK-046-review.md` (see N1).
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

Sources of authority consulted: `ai/tasks/TASK-046-retailer-source-adapter.md`, `ai/REVIEWER.md`, `ai/AGENTS.md`, `ai/PROJECT.md` (via AGENTS authority order), `ai/SPECIFICATION.md` (source-adapter boundary and delivery semantics), the existing adapter implementations (`libs/adapters/protocol.py`, `fake_store/`, `best_buy/`, `ebay/`), `libs/observability/source_metrics.py`, `libs/common/config.py`, `libs/event_contracts/product_observation.py`, and `services/ingestion/__main__.py`.

No document conflicts were found that affect this task.

---

## 2. Requirements Coverage

The final HEAD is the `web_retailer` implementation (targeting `books.toscrape.com`). Commit `c49c280` introduced a `wayfair` package that commit `7dc7111` fully replaced (renamed/removed); no `wayfair` files remain in the working tree.

| Requirement | Status | Implementation evidence |
|---|---|---|
| Select a real, stable, well-known retailer scrapable via plain HTTP + HTML parsing | ⚠️ Partial | `books.toscrape.com` chosen. Stable, plain HTTP, no JS/bot protection, and has name/price/availability in HTML — but it is a scraping tutorial/demo site, not a *real* retailer (see F1). |
| Implement `libs/adapters/<retailer>/` with `adapter.py`, `client.py`, `models.py` | ✅ Met | `web_retailer/` package contains all three plus `__init__.py` re-exporting all three classes. |
| Adapter implements `SourceAdapterProtocol` with a unique `source_name` | ✅ Met | `WebRetailerAdapter(SourceAdapterProtocol)`; `source_name == "web_retailer"` (unique vs. `fake_store`/`best_buy`/`ebay`/`mock_source`). |
| HTTP client fetches a single listing page and returns the raw HTML body | ✅ Met | `WebRetailerClient.fetch_listing_page()` returns `response.text`. |
| Parsing/mapping out of scope — empty `FetchResult` or `NotImplementedError`, with a clear TASK-047 path | ✅ Met | `fetch()` returns empty `FetchResult` (`events=()`, `malformed=()`, `total_records=0`); module/class docstrings point explicitly to TASK-047. |
| Externalize configuration (base URL, timeout, headers incl. User-Agent) via env vars or existing config conventions | ✅ Met | `WEB_RETAILER_BASE_URL`, `WEB_RETAILER_TIMEOUT`, `WEB_RETAILER_USER_AGENT`, `WEB_RETAILER_CATALOG_PATH`; resolution order constructor > env var > default (`_resolve_config`). This addresses the prior review's F1. |
| Handle HTTP errors (timeout, 4xx, 5xx, connection failure) via `SourceFetchError` | ✅ Met | `client.py` maps `HTTPStatusError` (403/429/generic), `TimeoutException`, `ConnectError`, `RequestError` → `SourceFetchError(source="web_retailer")`; exception order is specific-before-general. |
| Do not leak HTML structure / source-specific details downstream | ✅ Met | Adapter emits no events; no CSS selectors/HTML structures leave the package; `models.py` is a contained placeholder. |
| Typed Python, `httpx.AsyncClient`, deterministic mocked-HTTP tests | ✅ Met | Typed code; lazy `_get_client()`; tests use `AsyncMock`/`MagicMock`, no live network. |
| Never commit or log credentials | ✅ Met | No credentials present anywhere in the diff. |

### Acceptance criteria

| Criterion | Status |
|---|---|
| Implements `SourceAdapterProtocol` | ✅ Met |
| Fetches HTML via HTTP with proper error handling | ✅ Met |
| Configurable through environment variables | ✅ Met |
| Deterministic mocked tests covering success and failure modes | ✅ Met |

### Definition of Done

| Item | Status |
|---|---|
| Relevant tests pass | ✅ Independently verified (31 targeted tests) |
| Lint / format / type checks pass | ✅ Independently verified (ruff, ruff format, mypy) |
| Acceptance criteria verified | ✅ Met (with F1/F2 caveats) |
| Diff inspected | ✅ This review |
| Documentation updated where required | ⚠️ No doc lists a source catalog needing update; see F1 for the selection rationale gap |
| No secrets introduced | ✅ Confirmed |

---

## 3. Git Diff Review

The clean task change set (three-dot `09f8502…7dc7111`, i.e. merge-base `0ee22b5` → HEAD) is purely additive — 6 files, **820 insertions, 0 deletions**:

- `docs/reviews/TASK-046-review.md` (+155)
- `libs/adapters/web_retailer/__init__.py` (+12)
- `libs/adapters/web_retailer/adapter.py` (+99)
- `libs/adapters/web_retailer/client.py` (+167)
- `libs/adapters/web_retailer/models.py` (+25)
- `tests/test_adapters/test_web_retailer_adapter.py` (+362)

- **Scope correctness:** ✅ All changes belong to TASK-046. The diff is confined to the new `web_retailer` adapter package, its tests, and the review doc.
- **Unrelated changes:** ✅ None. The two-dot `09f8502..7dc7111` view also lists `M docs/reviews/TASK-045-review.md`, but that is an artifact of comparing against the non-ancestor commit `09f8502` (the TASK-045 review-doc commit); the correct merge-base-to-HEAD diff does not touch any TASK-045 file.
- **Architectural changes:** ✅ None. `protocol.py`, the event contract, downstream consumers, `services/ingestion`, and config modules are untouched. The adapter sits entirely behind the existing `SourceAdapterProtocol` boundary.
- **Accidental changes / debugging / dead code / generated artifacts / secrets:** ✅ None. The `web_retailer` package cleanly replaced the earlier `wayfair` package (verified: no `libs/adapters/wayfair/**` or `tests/**/test_wayfair*` files remain). No secrets, debug prints, or generated artifacts.
- **Dependency/configuration changes:** ✅ No new dependency; `httpx` is already used by existing adapters. No changes to `requirements*.txt` or `pyproject.toml`. Config uses new `WEB_RETAILER_*` env vars consistent with the adapter-local env-var pattern (`BESTBUY_API_KEY`, `EBAY_APP_ID`), not the `APP_` pydantic-settings convention reserved for services.

Branch/task isolation: ✅ correct — `feature/TASK-046`, working tree clean, exactly the two TASK-046 commits in the range.

---

## 4. Test and Verification Review

### Tests examined

`tests/test_adapters/test_web_retailer_adapter.py` (31 tests):

- Adapter construction and `source_name == "web_retailer"` ✅
- HTTP client 200 → returns HTML body; custom path forwarding ✅
- HTTP client failure modes: 403, 404, 429, 500, timeout, connection error → `SourceFetchError` ✅
- Client `close()` and no-op close ✅
- Default config, constructor overrides, each env var, constructor-over-env precedence ✅
- Invalid base URL (empty / no scheme / no host) → `SourceFetchError` ✅
- Invalid numeric timeout (0, negative) → `SourceFetchError` ✅
- Adapter returns empty `FetchResult` with `source == "web_retailer"`, `has_events is False`, `has_malformed is False` ✅
- Empty/whitespace HTML → `SourceFetchError` ✅
- Adapter propagates client `SourceFetchError`; success/failure metrics recorded ✅
- Adapter `close()` delegates; adapter forwards `catalog_path` to client ✅

### Verification results

| Check | Result | Classification |
|---|---|---|
| `python -m pytest tests/test_adapters/test_web_retailer_adapter.py -q` | 31 passed in 0.48s | **Independently verified** |
| `python -m ruff check libs/adapters/web_retailer tests/test_adapters/test_web_retailer_adapter.py` | All checks passed | **Independently verified** |
| `python -m ruff format --check libs/adapters/web_retailer tests/test_adapters/test_web_retailer_adapter.py` | 5 files already formatted | **Independently verified** |
| `python -m mypy libs/adapters/web_retailer` | Success: no issues found in 4 source files | **Independently verified** |
| Full unit suite (`python -m pytest -q -m "not integration"`) | Not run | Not required for an additive, isolated package; targeted checks above are sufficient |
| Integration tests (`python -m pytest -m integration`) | Not run | Not required — the adapter is an HTTP-only skeleton with mocked HTTP; it touches no Kafka/persistence/MinIO/infrastructure boundary |

### Test adequacy

Strong coverage of the success path and all required HTTP failure modes, plus the env-var and validation paths. Two gaps (see F2):

- No test exercises a **non-numeric `WEB_RETAILER_TIMEOUT`** env value (e.g. `"abc"`), which currently raises an unhandled `ValueError` rather than `SourceFetchError`.
- No test exercises `WEB_RETAILER_TIMEOUT=inf` (accepted today).

No evidence that existing tests were weakened to pass. The empty-HTML sanity guard (slightly beyond the task minimum) is well tested.

---

## 5. Findings

### F1 — Retailer selection does not satisfy the "real retailer" requirement (Moderate)

- **Affected file:** `libs/adapters/web_retailer/__init__.py:1-6`, `client.py:7` (`DEFAULT_BASE_URL = "http://books.toscrape.com"`), `adapter.py:12-14`
- **Problem:** The task Objective states *"Select a real retailer website as the Milestone 5B web-retailer source"*, and the first Requirement repeats *"Prefer a stable, well-known retailer"*. `books.toscrape.com` is a web-scraping tutorial/demo bookstore (created for scraping practice), not a real retailer. It does satisfy every *other* selection criterion — plain HTTP + HTML, no JavaScript/bot protection, name/price/availability in the HTML — and it cleanly resolves the prior review's F3 (Wayfair bot protection). But it is a literal deviation from "real retailer".
- **Impact:** The adapter skeleton is technically correct regardless of target, and TASK-047 (HTML parsing) can proceed against this site. However, the milestone objective of exercising a genuine web retailer is not achieved, and the deviation is not documented or escalated.
- **Recommendation:** Record the selection rationale (e.g. a short note/ADR or an inline comment in `__init__.py`) explicitly acknowledging that `books.toscrape.com` is a stable scraping sandbox chosen to keep TASK-047/048 deterministic, and flag for a human decision whether the milestone's "real retailer" objective is hard. If a genuinely real retailer is required, escalate before TASK-047 rather than discovering bot protection late.

### F2 — Timeout configuration validation is incomplete (Moderate)

- **Affected file:** `libs/adapters/web_retailer/client.py:80` (`resolved_timeout = float(_resolve_config(...))`) and `client.py:47-55` (`_validate_timeout`)
- **Problem:** The `float()` conversion happens *before* validation and outside any try/except. A non-numeric `WEB_RETAILER_TIMEOUT` env value (e.g. `"abc"` or `""`) raises an unhandled `ValueError` (`could not convert string to float: 'abc'`) instead of the required `SourceFetchError`. Additionally, `_validate_timeout` rejects only `<= 0` and NaN, so `inf` passes validation and is accepted as an effectively unlimited timeout. Confirmed by direct execution:
  - `WEB_RETAILER_TIMEOUT=abc` → `ValueError: could not convert string to float: 'abc'`
  - `WEB_RETAILER_TIMEOUT=inf` → client constructs with `_timeout == inf`
- **Impact:** The task explicitly requires "Configuration validation (missing/invalid base URL, timeout)". Numeric invalid values (0, negative, NaN) and all invalid base URLs are handled correctly, but the non-numeric env-var path — the exact path externalization is meant to support — fails with a confusing raw traceback, and `inf` is silently accepted.
- **Recommendation:** Convert the timeout inside the same validation path as the other values, catching `ValueError` and raising `SourceFetchError`; reject non-finite values (`math.isfinite`) in `_validate_timeout`. Add tests for `WEB_RETAILER_TIMEOUT=abc`, `WEB_RETAILER_TIMEOUT=""`, and `WEB_RETAILER_TIMEOUT=inf`.

### F3 — `_validate_base_url` does not trim whitespace (Minor)

- **Affected file:** `libs/adapters/web_retailer/client.py:33-45` (`_validate_base_url`)
- **Problem:** The empty check uses `url.strip()`, but the subsequent `urlparse(url)` runs on the untrimmed value. A base URL with leading/trailing whitespace (e.g. an env var with an accidental trailing space) yields `scheme == ""` and surfaces the "must use http or https scheme" message rather than a clear "non-empty/trim" message.
- **Impact:** Edge case; a slightly confusing error message only.
- **Recommendation:** Trim the URL before `urlparse`, or normalize the resolved value once in `__init__` (e.g. `resolved_base_url.strip()`), consistent with the empty-string check.

---

## 6. Non-Defect Observations

- **N1 — A stale review artifact is committed in the change set.** `docs/reviews/TASK-046-review.md` was added in commit `7dc7111` and reviews the *intermediate* `wayfair` implementation (`c49c280`, verdict `CHANGES REQUIRED`), not the final `web_retailer` HEAD. This report supersedes it. Committing an out-of-date review into the implementation branch is a process-hygiene issue, not a code defect; note that the TASK-045 review was instead recorded as a separate post-merge commit (`09f8502`).
- **N2 — Adapter is not wired into `services/ingestion/__main__.py`.** This is consistent with `ebay` (also not wired) and acceptable for a parsing-less skeleton that emits empty `FetchResult`s; wiring should land when TASK-047 produces events.
- **N3 — `WebRetailerProduct` placeholder is unused** but is now correctly re-exported from `__init__.py` (resolving the prior review's F4). Its shape (`product_id` required, `availability="unknown"`, `currency="GBP"`) will need reconciliation with the real parsed fields in TASK-047.
- **N4 — `fetched_at` reuses `collected_at`.** Harmless while `events` is empty; the naming is only slightly misleading.
- **N5 — Structure closely mirrors existing adapters.** Lazy `_get_client()`, `close()`, the error-mapping shape, and metrics usage (`FETCH_ATTEMPTS`, `record_fetch_success`/`record_fetch_failure`, `time_fetch()`) all match `fake_store`/`best_buy`/`ebay`, which is good for maintainability.
- **N6 — `WEB_RETAILER_*` env vars are not added to `.env.example`.** Consistent with the existing adapters (`BESTBUY_API_KEY`, `EBAY_APP_ID` are likewise absent from `.env.example`), so not flagged as a defect.

---

## 7. Verdict

`APPROVED WITH NON-BLOCKING FINDINGS`

The `web_retailer` adapter skeleton is correct and well-scoped: it implements `SourceAdapterProtocol` with a unique `source_name`, fetches HTML with proper `SourceFetchError` handling, externalizes base URL/timeout/User-Agent/catalog path through environment variables, and returns an empty `FetchResult` with a clear TASK-047 hand-off. All four independent verification checks (31 targeted tests, ruff, ruff format, mypy) passed. The prior review's blockers were resolved: env-var configuration is now present (F1 of that review), configuration validation is present for base URL and numeric timeout (F2 of that review, with the residual gap in F2 above), and the bot-protected Wayfair target was replaced.

Non-blocking findings:

- **F1 (Moderate)** — the chosen target `books.toscrape.com` is a scraping sandbox, not a *real* retailer; the deviation from the task Objective should be documented and surfaced for a human decision.
- **F2 (Moderate)** — timeout validation does not cover non-numeric env-var strings (`ValueError` leaks) or `inf`.
- **F3 (Minor)** — base-URL validation does not trim whitespace.

These do not block acceptance of the skeleton, and TASK-047 can proceed; F1 should be settled before the milestone advances much further.
