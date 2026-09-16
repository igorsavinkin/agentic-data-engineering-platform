# TASK-046 Review — Retailer Source Selection and Adapter

## 1. Review Header

- **Task ID:** TASK-046 — Retailer Source Selection and Adapter
- **Review date:** 2026-09-16
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:** `0ee22b592ae0449b71436593782933af350ea15c...c49c2807de40afadb32469bcdc465fbdaa32930b`
- **Reviewed HEAD:** `c49c2807de40afadb32469bcdc465fbdaa32930b` (`feat(TASK-046): Add Wayfair retailer adapter skeleton`) on `feature/TASK-046`
- **Scope:** `libs/adapters/wayfair/` (new package) and `tests/test_adapters/test_wayfair_adapter.py` (new)
- **Verdict:** `CHANGES REQUIRED`

Sources of authority consulted: `ai/tasks/TASK-046-retailer-source-adapter.md`, `ai/REVIEWER.md`, `ai/AGENTS.md`, `ai/SPECIFICATION.md` (§4 Data Sources / §4.2 Source Adapter Architecture / §21 Security), `ai/ROADMAP.md` (Milestone 5B), and the existing adapter implementations (`libs/adapters/protocol.py`, `fake_store/`, `best_buy/`, `ebay/`), `libs/observability/source_metrics.py`, and `libs/common/config.py`.

No document conflicts were found that affect this task.

---

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
|---|---|---|
| Select a real, stable, well-known retailer scrapable via plain HTTP + HTML parsing | ⚠️ Partial | `wayfair` chosen (`adapter.py` `source_name == "wayfair"`). Choice works via HTTP, but selection/scrapability rationale is not documented (see F3). |
| Implement `libs/adapters/<retailer>/` with `adapter.py`, `client.py`, `models.py` | ✅ Met | All three files present plus `__init__.py`. |
| Adapter implements `SourceAdapterProtocol` with unique `source_name` | ✅ Met | `WayfairAdapter(SourceAdapterProtocol)`; `source_name -> "wayfair"`; `fetch()` returns `FetchResult`. |
| HTTP client fetches a single listing page and returns raw HTML body | ✅ Met | `WayfairClient.fetch_listing_page()` returns `response.text`. |
| Parsing/mapping out of scope — return empty `FetchResult` or `NotImplementedError` with clear TASK-047 path | ✅ Met | `fetch()` returns empty `FetchResult` (events=(), total_records=0); docstrings and inline comments point to TASK-047. |
| Externalize configuration (base URL, timeout, headers incl. User-Agent) via env vars or existing config conventions | ❌ Not met | Config is constructor-injectable only; no `os.environ`/`os.getenv`/pydantic-settings reads (see F1). |
| Handle HTTP errors (timeout, 4xx, 5xx, connection failure) via `SourceFetchError` | ✅ Met | `client.py` maps `HTTPStatusError` (403/429/other), `TimeoutException`, `ConnectError`, `RequestError` to `SourceFetchError(source="wayfair")`. |
| Do not leak HTML structure/source-specific details downstream | ✅ Met | Adapter returns empty events; no CSS selectors/HTML structures outside the package; `models.py` is a contained placeholder. |
| Typed Python, `httpx.AsyncClient`, deterministic mocked-HTTP tests | ✅ Met | Typed code; `httpx.AsyncClient` lazy via `_get_client()`; tests use `AsyncMock`/`MagicMock`. |
| Never commit/log credentials | ✅ Met | No credentials present. |

### Acceptance criteria

| Criterion | Status |
|---|---|
| Implements `SourceAdapterProtocol` | ✅ Met |
| Fetches HTML via HTTP with proper error handling | ✅ Met |
| Configurable through environment variables | ❌ Not met (constructor-only; see F1) |
| Deterministic mocked tests covering success and failure modes | ✅ Met (with a config-validation gap; see F2) |

---

## 3. Git Diff Review

- **Files changed:** 5 new files, +532 insertions, 0 deletions:
  - `libs/adapters/wayfair/__init__.py` (+6)
  - `libs/adapters/wayfair/adapter.py` (+95)
  - `libs/adapters/wayfair/client.py` (+112)
  - `libs/adapters/wayfair/models.py` (+25)
  - `tests/test_adapters/test_wayfair_adapter.py` (+294)
- **Scope correctness:** ✅ All changes belong to TASK-046. The diff is purely additive and confined to the new `wayfair` adapter package and its tests.
- **Unrelated changes:** ✅ None.
- **Architectural changes:** ✅ None. No modifications to `protocol.py`, the event contract, downstream consumers, services, or configuration modules. The new adapter sits entirely behind the existing `SourceAdapterProtocol` boundary, consistent with SPECIFICATION §4.2.
- **Accidental changes / debugging / dead code / generated artifacts / secrets:** ✅ None committed. The one intentional placeholder (`WayfairProduct` in `models.py`) is unused, which is expected for a TASK-047 skeleton (see F4).
- **Dependency/configuration changes:** ✅ No new dependency introduced; `httpx` is already used by existing adapters. No changes to `requirements*.txt` or `pyproject.toml`. Configuration is not wired into env vars, which is a scope-completeness gap rather than an out-of-scope change (see F1).

Branch/task isolation: ✅ correct — reviewed on `feature/TASK-046`, working tree clean, single task commit.

---

## 4. Test and Verification Review

### Tests examined

`tests/test_adapters/test_wayfair_adapter.py` (19 tests):

- Adapter construction and `source_name == "wayfair"` ✅
- HTTP client 200 → returns HTML body; custom path ✅
- HTTP client failure modes: 403, 404, 429, 500, timeout, connection error → `SourceFetchError` ✅
- Client `close()` and no-op close ✅
- Adapter returns empty `FetchResult` with `source == "wayfair"`, `has_events is False` ✅
- Empty/whitespace HTML → `SourceFetchError` ✅
- Adapter propagates client `SourceFetchError`; records success/failure metrics ✅
- Adapter `close()` delegates to client ✅

### Verification results

| Check | Result | Classification |
|---|---|---|
| `python -m pytest tests/test_adapters/test_wayfair_adapter.py -q` | 19 passed in 0.52s | **Independently verified** |
| `python -m pytest -q -m "not integration"` (full unit suite) | 918 passed, 135 deselected in 565.76s | **Independently verified** |
| `python -m ruff check libs/adapters/wayfair tests/test_adapters/test_wayfair_adapter.py` | All checks passed | **Independently verified** |
| `python -m ruff format --check libs/adapters/wayfair tests/test_adapters/test_wayfair_adapter.py` | 5 files already formatted | **Independently verified** |
| `python -m mypy libs/adapters/wayfair` | Success: no issues in 4 source files | **Independently verified** |
| Integration tests (`pytest -m integration`) | Not run | **Not required** — this task is an adapter skeleton with mocked HTTP; it touches no Kafka/persistence/MinIO/infrastructure boundary. |

### Test adequacy

Good coverage of the success path and the required HTTP failure modes. Two gaps:

- The task's explicit test requirement **"Configuration validation (missing/invalid base URL, timeout)"** has no corresponding tests, and the implementation contains no such validation (F2).
- No test drives the client through the adapter's real (non-mocked) configuration path for invalid `base_url`/`timeout` (consequence of F1/F2).

No evidence that existing tests were weakened to pass.

---

## 5. Findings

### F1 — Configuration is not externalized through environment variables (High)

- **Affected file:** `libs/adapters/wayfair/client.py:11-40`, `libs/adapters/wayfair/adapter.py:23-41`
- **Problem:** `WAYFAIR_BASE_URL`, `DEFAULT_TIMEOUT`, `DEFAULT_USER_AGENT`, and the default `search_path` are module constants; the client and adapter read no environment variables and use no `APP_`-prefixed pydantic-settings class. `base_url`, `timeout`, `user_agent`, and `search_path` are only injectable via constructor arguments. The sibling adapters that need config read it from the environment (`best_buy/client.py` uses `os.environ.get("BESTBUY_API_KEY")`; `ebay/client.py` uses `os.getenv("EBAY_APP_ID")`), and the repository's typed-config convention is `APP_`-prefixed env vars via `libs/common/config.py`.
- **Impact:** The acceptance criterion "is configurable through environment variables" is not satisfied. Under Docker/Kubernetes/Helm deployment (where configuration is injected via environment, per SPECIFICATION §21 and `libs/common/config.py`), the base URL, timeout, and User-Agent cannot be overridden through the environment. The task requirement "externalize configuration (base URL, timeout, request headers including User-Agent) through environment variables or existing config conventions" is likewise unmet.
- **Recommendation:** Read these values from environment variables (e.g., `WAYFAIR_BASE_URL`, `WAYFAIR_TIMEOUT`, `WAYFAIR_USER_AGENT`, and optionally `WAYFAIR_SEARCH_PATH`) with the constructor argument as an override, or introduce an `APP_`-prefixed settings class consistent with `libs/common/config.py`. Add tests that exercise the env-var path.

### F2 — Configuration validation (missing/invalid base URL, timeout) is absent (Moderate)

- **Affected file:** `libs/adapters/wayfair/client.py:29-35` (`__init__`), `tests/test_adapters/test_wayfair_adapter.py`
- **Problem:** The task's test list explicitly requires "Configuration validation (missing/invalid base URL, timeout)". The client performs no validation: `base_url.rstrip("/")` silently accepts an empty string or a non-URL value, and `timeout` accepts zero/negative values (which will only fail later, and unclearly, when `httpx.Timeout(...)` is constructed or a request is made). No validation tests were added.
- **Impact:** An explicitly required test (and the validation behavior it implies) is missing. Invalid configuration surfaces late and with a confusing error rather than a clear, log-safe `SourceFetchError`/`ConfigurationError`.
- **Recommendation:** Validate `base_url` (non-empty, parseable URL) and `timeout` (positive finite number) at construction, raising a clear error; add the corresponding unit tests.

### F3 — Retailer selection and plain-HTTP scrapability are not documented (Moderate)

- **Affected file:** repository documentation (no ADR/doc/comment records the decision); `libs/adapters/wayfair/client.py:76-79` (403 message acknowledges bot detection)
- **Problem:** The task requires selecting a "stable, well-known retailer" scrapable via plain HTTP and, if JavaScript rendering is needed, documenting the decision and escalating. Wayfair is a reasonable well-known choice, but there is no recorded analysis of whether a plain-HTTP fetch of a listing page actually returns name/price/availability HTML. Wayfair is widely known for aggressive bot protection (Akamai/PerimeterX) that frequently returns 403 or a JS challenge to non-browser clients — a risk the 403 handler message itself recognizes ("may have been blocked by bot detection").
- **Impact:** If the chosen site cannot be fetched without browser automation or bot-bypass engineering, TASK-047/048 (HTML parsing, pagination) will be blocked, and the milestone's "simplest reliable collection method" constraint (SPECIFICATION §4.3) is at risk. The decision is currently unverifiable from the repository.
- **Recommendation:** Add a short note/ADR (or code comment) documenting the selection rationale and an explicit scrapability check (e.g., confirm a plain HTTP GET of a real listing page returns name/price/availability in the HTML). If bot protection blocks plain HTTP, escalate per the task before TASK-047.

### F4 — `WayfairProduct` placeholder model is unused and not re-exported (Minor)

- **Affected file:** `libs/adapters/wayfair/models.py`, `libs/adapters/wayfair/__init__.py:6`
- **Problem:** `WayfairProduct` is defined but never imported or used anywhere (expected for a TASK-047 placeholder), and it is not re-exported from `__init__.py`, unlike `fake_store`, `best_buy`, and `ebay` which all re-export their models.
- **Impact:** Minor inconsistency with existing adapter package conventions; harmless today.
- **Recommendation:** Re-export `WayfairProduct` from `__init__.py` (and add to `__all__`) for consistency, or drop it until TASK-047 if the model shape is still undecided.

### F5 — Test asserts a private attribute (Minor)

- **Affected file:** `tests/test_adapters/test_wayfair_adapter.py:288-293` (`test_adapter_creates_client_with_config`)
- **Problem:** The test asserts `adapter._search_path`, coupling the test to a private implementation detail.
- **Impact:** Low — a refactor of the internal attribute name would break the test spuriously.
- **Recommendation:** Assert observable behavior instead (e.g., inject a spy client and assert the path passed to `fetch_listing_page`, or assert the constructed `WayfairClient`'s configured path).

---

## 6. Non-Defect Observations

- **N1 — Empty-HTML sanity check is a sensible addition.** `adapter.fetch()` raising `SourceFetchError` for empty/whitespace HTML goes slightly beyond the minimum ("return empty FetchResult") but is a reasonable guard and is well tested.
- **N2 — Default `search_path` may not be a real Wayfair listing URL.** `/search/products?keyword=electronics` is a configurable placeholder default. It should be validated against a real Wayfair URL during TASK-047, but this is acceptable for a skeleton.
- **N3 — `kwargs` construction is slightly awkward.** `WayfairAdapter.__init__` builds a `dict[str, Any]` solely to conditionally pass `user_agent`. A clearer default (e.g., always pass `user_agent` with a shared default) would be more idiomatic; no functional impact.
- **N4 — `collected_at` reused as `fetched_at`.** Since `events` is empty, this is harmless; the name is only slightly misleading.
- **N5 — Structure closely mirrors existing adapters.** Metrics usage (`FETCH_ATTEMPTS`, `record_fetch_success`/`record_fetch_failure`, `time_fetch()`), lazy `_get_client()`, `close()`, and the error-mapping shape all match `fake_store`/`best_buy`, which is good for maintainability.

---

## 7. Verdict

`CHANGES REQUIRED`

The adapter skeleton is well-structured, correctly implements `SourceAdapterProtocol`, fetches HTML with proper `SourceFetchError` handling, and passes 918 unit tests plus lint/format/type checks. However, one explicit acceptance criterion — **"configurable through environment variables"** — is unmet (F1, High), and the task's required configuration-validation tests/behavior are absent (F2, Moderate). The retailer selection should also be documented with a plain-HTTP scrapability check before the milestone proceeds (F3, Moderate).

Blocking findings: F1 (must fix before acceptance). F2 and F3 should be addressed in the same pass; F4 and F5 are non-blocking.
