# TASK-047 Review — HTML/Dynamic-Content Parsing

## 1. Review Header

- **Task ID:** TASK-047 — HTML/Dynamic-Content Parsing
- **Review date:** 2026-09-17
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:** `bd0ce01be4f6e8c67b0f5f647f3f2c9401bf0c48...dbc991202d4fe7515278ae83b19e92b55d6fe5c6` (three-dot). `bd0ce01` is a non-ancestor `chore:` commit; the merge-base is `17f31df7395bd0b7992082581835782b0d67ad6b` (the TASK-046 HEAD), so the effective task diff is exactly one commit.
- **Reviewed HEAD:** `dbc991202d4fe7515278ae83b19e92b55d6fe5c6` (`feat(TASK-047): Add HTML parsing for web retailer adapter`) on `feature/TASK-047`
- **Commits in range:** `dbc9912` only
- **Scope:** `libs/adapters/web_retailer/parser.py` (new), `libs/adapters/web_retailer/adapter.py` (modified), `requirements.txt` (modified), 5 HTML fixtures under `tests/fixtures/web_retailer/` (new), `tests/test_adapters/test_web_retailer_parser.py` (new), `tests/test_adapters/test_web_retailer_adapter.py` (modified).
- **Verdict:** `CHANGES REQUIRED`

Sources of authority consulted: `ai/tasks/TASK-047-html-content-parsing.md`, `ai/REVIEWER.md`, `ai/AGENTS.md`, `ai/SPECIFICATION.md` (source-adapter boundary and canonical contract), `ai/PROJECT.md`, the prior `ai/tasks/TASK-046-retailer-source-adapter.md`, the existing adapters (`libs/adapters/protocol.py`, `fake_store/`, `best_buy/`, `ebay/`), `libs/event_contracts/product_observation.py`, and `libs/observability/source_metrics.py`.

No document conflicts were found that affect this task. One task-text-vs-codebase-convention discrepancy (the `MalformedRecordError` mention) is recorded in N2.

---

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
|---|---|---|
| Parse HTML with a Python HTML parsing library; add dependency if needed | ✅ Met | `selectolax` used in `parser.py`; `selectolax>=0.3,<1` added to `requirements.txt`. Simplest reliable option for static HTML. |
| Extract name | ✅ Met | `_parse_article` reads the `h3 a` `title` attribute. |
| Extract price (as `Decimal`) | ✅ Met (with F4 caveat) | `_parse_price` returns `Decimal`; currency symbols/thousands separators handled. |
| Extract currency | ✅ Met | `_parse_price` maps £/€/$ symbols; defaults to `GBP`. |
| Extract availability | ✅ Met (with F5 caveat) | `_parse_availability` maps class/text → `in_stock`/`out_of_stock`/`preorder`/`unknown`. |
| Extract category | ✅ Met | `_extract_category` reads the breadcrumb, defaults to `"Books"`. |
| Extract product URL | ❌ Not met for the real source | `_resolve_url` mishandles `../`-relative links and resolves against the site root, producing wrong `url` values (see F1). |
| Extract stable external identifier | ✅ Met | `_extract_product_id` derives the slug from the URL path (e.g. `a-light-in-the-attic_1000`), stable across fetches. |
| Map to `ProductObservationEvent` via `_build_event()` | ✅ Met | `_to_canonical_event` calls `SourceAdapterProtocol._build_event(...)`. |
| Missing/malformed → `malformed`, not `events` (via `MalformedRecordError`) | ⚠️ Partial | Unparseable price → `price=None` (valid per canonical rules); missing availability → `unknown`; but products with missing name/URL are silently dropped at the parser, never reaching `malformed` (see F2). `MalformedRecordError` is not used (see N2). |
| Structural HTML changes → empty events + logging, no crash | ✅ Met | `parse_listing_page` catches per-article `Exception` and logs a warning; returns partial/empty list. |
| Keep HTML-specific logic inside the adapter package | ✅ Met | All selectors/regex live in `parser.py`; `libs/event_contracts/`, `libs/common/`, and downstream consumers untouched. |
| Preserve `source_name` from TASK-046 | ✅ Met | `source_name` remains `"web_retailer"`. |
| Currency defaults to retailer's local currency if absent | ✅ Met | `_parse_price` defaults to `"GBP"`; the target is a UK site. |
| Availability mapped to canonical enum | ✅ Met | `_parse_availability` returns only the four canonical values. |

### Tests coverage (task-specified)

| Required test | Status |
|---|---|
| Representative extraction (all fields) | ✅ `test_all_fields_populated` |
| Multiple products on one page | ✅ `test_extracts_multiple_products` (3 products) |
| Missing price → malformed or null price | ✅ `test_missing_price_element` / `test_unparseable_price_text` (→ `None`) |
| Missing availability → `unknown` | ✅ `test_missing_availability_element` |
| Malformed HTML / unexpected structure → no crash | ✅ `test_malformed_structure_does_not_crash` / `test_malformed_structure_partial_results` |
| Empty page → empty FetchResult | ✅ `test_empty_listing_returns_zero_events` |
| Canonical compatibility (source, stable external_id, deterministic event_id) | ✅ `test_event_source_matches_adapter`, `test_external_id_is_stable`, `test_event_id_is_deterministic` |
| Price edge cases — currency symbols | ✅ £/$/€ covered |
| Price edge cases — thousands separators | ❌ Not tested (see F6) |
| Price edge cases — free/zero price | ✅ `test_unparseable_price_text` ("free" → `None`), `test_zero_price_is_valid` (`£0.00`) |
| Deterministic fixtures, no live HTTP | ✅ All tests use `tests/fixtures/web_retailer/` or inline HTML strings |

### Acceptance criteria

| Criterion | Status |
|---|---|
| Adapter parses HTML listing pages into canonical events | ✅ Met (for fixture-shaped HTML) |
| Malformed/incomplete HTML → malformed records rather than crashes | ⚠️ Partial — incomplete records are dropped, not routed to `malformed` (F2) |
| All HTML-specific logic contained within the adapter package | ✅ Met |
| Tests use fixed HTML fixtures | ✅ Met |

### Definition of Done

| Item | Status |
|---|---|
| Relevant tests pass | ✅ Independently verified (57 targeted tests) |
| Lint / format / type checks pass | ✅ Independently verified (ruff check, ruff format --check, mypy) |
| Acceptance criteria verified | ⚠️ Partial (F1, F2) |
| Diff inspected | ✅ This review |
| Documentation updated where required | ✅ N/A — no doc change needed for a parsing-only change |
| No secrets introduced | ✅ Confirmed |

---

## 3. Git Diff Review

The clean task change set (three-dot `bd0ce01…dbc9912`, merge-base `17f31df`) is exactly one commit — 10 files, **772 insertions, 26 deletions**:

- `libs/adapters/web_retailer/adapter.py` (+72/−~14)
- `libs/adapters/web_retailer/parser.py` (+215, new)
- `requirements.txt` (+3)
- `tests/fixtures/web_retailer/empty_listing.html` (+14, new)
- `tests/fixtures/web_retailer/listing_page.html` (+73, new)
- `tests/fixtures/web_retailer/malformed_structure.html` (+27, new)
- `tests/fixtures/web_retailer/missing_availability.html` (+26, new)
- `tests/fixtures/web_retailer/missing_price.html` (+33, new)
- `tests/test_adapters/test_web_retailer_adapter.py` (+30/−~)
- `tests/test_adapters/test_web_retailer_parser.py` (+305, new)

- **Scope correctness:** ✅ All changes belong to TASK-047. The diff is confined to the `web_retailer` adapter package, its fixtures/tests, and the dependency declaration.
- **Unrelated changes:** ✅ None. The merge-base-to-HEAD diff touches no other task's files.
- **Architectural changes:** ✅ None. `protocol.py`, the event contract, downstream consumers, and other adapters are untouched. HTML parsing stays behind the `SourceAdapterProtocol` boundary.
- **Accidental changes / debugging / dead code / generated artifacts / secrets:** ⚠️ No secrets, debug prints, or generated artifacts; but `_PRICE_RE` and `parse_prices` are dead code (F3). No other stray files.
- **Dependency/configuration changes:** ✅ One new runtime dependency (`selectolax`) added to `requirements.txt` with a TASK-047 comment; no `pyproject.toml` duplication (the repo standardizes runtime deps in `requirements.txt`). No env/config changes.

Branch/task isolation: ✅ correct — `feature/TASK-047`, exactly one TASK-047 commit (`dbc9912`) on top of the TASK-046 HEAD (`17f31df`).

> **Review-time note:** during this review the working tree accumulated uncommitted changes — a modified `libs/adapters/web_retailer/parser.py` and an untracked `docs/reviews/TASK-047-review.md` — that are **not** part of the reviewed change set. This review is based strictly on the committed HEAD `dbc9912`; those uncommitted changes were not evaluated and were left untouched.

---

## 4. Test and Verification Review

### Tests examined

`tests/test_adapters/test_web_retailer_parser.py` + `tests/test_adapters/test_web_retailer_adapter.py` (57 tests total):

- Parser: representative extraction, multiple products, all-fields, out-of-stock, category-from-breadcrumb, URL resolution, empty HTML/listing, malformed structure, missing price/availability, currency symbols, integer price.
- Adapter: canonical events, source match, stable external_id, empty HTML → `SourceFetchError`, empty listing → zero events, null-price event, partial results on malformed structure, deterministic event_id, availability mapping, metrics on success/failure, close delegation, `catalog_path` forwarding.

### Verification results

| Check | Result | Classification |
|---|---|---|
| `python -m pytest tests/test_adapters/test_web_retailer_parser.py tests/test_adapters/test_web_retailer_adapter.py -q` | 57 passed in 0.69s | **Independently verified** |
| `python -m ruff check libs/adapters/web_retailer tests/test_adapters/test_web_retailer_parser.py tests/test_adapters/test_web_retailer_adapter.py` | All checks passed | **Independently verified** |
| `python -m mypy libs/adapters/web_retailer` | Success: no issues found in 5 source files | **Independently verified** |
| `python -m ruff format --check` on the committed `parser.py` / `adapter.py` (via `git show … \| python -m ruff format --check -`) | No differences | **Independently verified** |
| Integration tests (`python -m pytest -m integration`) | Not run | Not required — pure HTML parsing with fixture-based tests; no Kafka/persistence/MinIO/infrastructure boundary is touched |

### Test adequacy

Strong coverage of the success path and the required graceful-handling cases (missing price → null, missing availability → unknown, malformed structure → partial, empty → empty). Key gaps:

- **Fixtures are not representative of the live source** (see F1): `listing_page.html` uses bare relative hrefs (`a-light-in-the-attic_1000/index.html`), but the real books.toscrape.com default catalog page (`/catalogue/category/books_1/index.html`) emits `../../a-light-in-the-attic_1000/index.html` (confirmed by fetching the page). The `_resolve_url` defect is therefore invisible to the tests.
- **No test asserts the resolved `url` is actually correct** (only that it starts with `BASE_URL` and contains the slug), so an incorrect `../`-laden URL passes.
- **Thousands-separator price case is untested** despite being explicitly required (F6).

No evidence that existing tests were weakened to pass.

---

## 5. Findings

### F1 — `url` field is incorrectly resolved for the real source's `../`-relative links (High)

- **Affected file:** `libs/adapters/web_retailer/parser.py:124` (`_resolve_url`), `parser.py:134-135` (the `lstrip(".")`/`lstrip("/")` handling), `libs/adapters/web_retailer/adapter.py:73` (`base_url = self._client._base_url`)
- **Problem:** The adapter resolves relative product URLs against the **site root** (`http://books.toscrape.com`), not the actual page URL, and `_resolve_url` implements `../` handling as `lstrip(".")`/`lstrip("/")` rather than RFC 3986 relative-URL resolution. The live default catalog path (`/catalogue/category/books_1/index.html`) emits product links of the form `../../a-light-in-the-attic_1000/index.html` (independently confirmed by fetching the page). Independent execution shows the current code produces `http://books.toscrape.com/../a-light-in-the-attic_1000/index.html`, whereas `urllib.parse.urljoin` produces the correct `http://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html`.
- **Impact:** `url` is a required canonical field and is silently emitted wrong for the production default page — it contains a `../` path segment and points to a non-existent path. Pydantic only enforces `min_length=1`, so the invalid URL passes validation and flows downstream. `external_id` remains correct, but the URL corruption is silent (no crash, no warning). The tests miss this because the fixtures use bare relative hrefs instead of the real `../../` form.
- **Recommendation:** Resolve relative URLs against the actual fetched page URL (base URL + catalog path) using `urllib.parse.urljoin` (or equivalent proper resolution). Update `listing_page.html` to use the real `../../` link format and add an assertion that the resolved `url` equals the canonical `/catalogue/<slug>/index.html` form.

### F2 — Unparseable / missing-required-field products are silently dropped, never routed to `malformed` (Moderate)

- **Affected file:** `libs/adapters/web_retailer/parser.py:48` (`parse_listing_page`), `parser.py:82` (`_parse_article` returns `None` for missing `h3 a` / empty title), `libs/adapters/web_retailer/adapter.py:78-105`
- **Problem:** Products whose `<h3><a>` is missing or whose title is empty (i.e. missing `name`/`url`) are dropped at the parser and never appear in `FetchResult.malformed`. Independently verified against `malformed_structure.html`: it contains 3 `article.product_pod` elements, but the adapter reports `events=1, malformed=0, total_records=1`. This fails the requirement "records with … missing required fields go into `malformed` … not into `events`", and violates `SourceAdapterProtocol` invariant #4 (a batch of *only* malformed records should return non-empty `malformed`). The parser also does not surface malformed records back to the adapter, unlike `fake_store`/`best_buy`/`ebay` clients, which return `(products, malformed)`.
- **Impact:** Malformed/unparseable products vanish silently — no DLQ routing, no diagnostic beyond a `logger.warning`, and `total_records` undercounts the actual number of product articles received.
- **Recommendation:** Have `parse_listing_page` return `(products, malformed)` (or otherwise surface skipped articles with a raw HTML snippet and a reason), and have the adapter merge them into `FetchResult.malformed` and set `total_records` to the actual article count, consistent with the other adapters.

### F3 — Dead code: unused `_PRICE_RE` and unused `parse_prices` (Minor)

- **Affected file:** `libs/adapters/web_retailer/parser.py:26` (`_PRICE_RE`), `parser.py:213` (`parse_prices`)
- **Problem:** `_PRICE_RE` is compiled but never referenced anywhere. `parse_prices` is documented "exposed for testing" but no test imports or uses it (confirmed by grep). Both are dead code.
- **Impact:** Maintenance noise only; no functional impact.
- **Recommendation:** Remove `_PRICE_RE`; either add a test that exercises `parse_prices` or remove it.

### F4 — `price` is routed through `float`, losing the parser's `Decimal` guarantee (Minor)

- **Affected file:** `libs/adapters/web_retailer/adapter.py:130` (`price=float(product.price) if product.price is not None else None`)
- **Problem:** The parser correctly produces `Decimal` prices (per the task's "price (as Decimal)" requirement), but the adapter converts to `float`, after which `_build_event` reconstructs `Decimal(str(price))`. This unnecessary float round-trip is semantically inconsistent with the Decimal-first contract and can lose precision for some values, though it round-trips exactly for typical 2-decimal prices.
- **Impact:** Latent precision risk for money values; no observed failure for the fixture prices.
- **Recommendation:** Pass the `Decimal` through directly (broaden `_build_event`'s `price` type to `Decimal | float | None`, or construct the payload with the `Decimal` value), avoiding the float conversion.

### F5 — Fragile `availoffset` availability heuristic (Minor)

- **Affected file:** `libs/adapters/web_retailer/parser.py:200` (`_parse_availability`, the `if "availoffset" in classes: return "out_of_stock"` branch)
- **Problem:** `availoffset` is a CSS *layout* class, not a semantic stock indicator. The live site uses `class="instock availability"` for in-stock; the fixture invents `availoffset availability` for out-of-stock. Because the class check runs before the text check, an in-stock item that also carried `availoffset` (for layout) would be misclassified as `out_of_stock` before the reliable `"out of stock"` text check is reached. The text-based checks (`"in stock"` / `"out of stock"` / `"preorder"`) are the robust signal.
- **Impact:** Low — real out-of-stock items would still map correctly via text; only a layout-class collision could misclassify. The heuristic is overfit to the fixture.
- **Recommendation:** Prefer the text signal; drop or de-prioritize the `availoffset` class heuristic, and make the fixture reflect the real markup.

### F6 — Missing required thousands-separator price test (Minor)

- **Affected file:** `tests/test_adapters/test_web_retailer_parser.py` (`TestPriceParsing`)
- **Problem:** The task's Tests section explicitly requires "thousands separators" as a price edge case. Currency symbols and free/zero price are covered, but no test exercises a thousands-separated price. The code handles `£1,234.56 → Decimal("1234.56")` via `_THOUSANDS_RE`, but this path is unverified — and the European `1.234,56` form actually returns `None`, an untested and arguably surprising behavior.
- **Impact:** A required test edge case is missing; the thousands-separator path is unverified.
- **Recommendation:** Add a test for `£1,234.56 → Decimal("1234.56")`, and decide/document the intended behavior for `1.234,56`.

### F7 — Adapter reaches into the client's private `_base_url` (Minor)

- **Affected file:** `libs/adapters/web_retailer/adapter.py:73` (`base_url = self._client._base_url`)
- **Problem:** The adapter accesses the client's private `_base_url` attribute rather than a public accessor, coupling the adapter to the client's internals. The client stores the stripped value but exposes no getter.
- **Impact:** Fragile coupling; a client refactor would silently break URL resolution.
- **Recommendation:** Expose a public property/accessor on `WebRetailerClient` (and, per F1, expose the resolved page URL needed for proper relative-URL resolution).

---

## 6. Non-Defect Observations

- **N1 — Adapter-level `except Exception → malformed` is effectively unreachable in practice.** With a non-empty `base_url` (always the case for the real client), the only way `_to_canonical_event` can fail is an empty `url`, which requires a valid `name` but an empty `href` — a case no fixture covers and which the parser would normally drop first (see F2). The malformed path is real code but effectively dead given the parser's behavior.
- **N2 — The task says `MalformedRecordError`, but the codebase convention is a manual dict.** `MalformedRecordError` exists in `libs/adapters/protocol.py` but is never raised or caught anywhere in the repository (all of `fake_store`/`best_buy`/`ebay` use `{"raw_record": …, "reason": …}` dicts). TASK-047 follows the established convention rather than the literal task text. This is a task-spec drift worth reconciling across the suite, not a defect in this change.
- **N3 — `WebRetailerProduct` (from TASK-046) is now superseded.** The parser uses the new `ParsedProduct` dataclass; `libs/adapters/web_retailer/models.py` (`WebRetailerProduct`) remains exported in `__init__.py` but is unused, and its `price: float | None` shape conflicts with the parser's `Decimal` choice. Consider removing it or aligning it in a follow-up.
- **N4 — `fetched_at` reuses `collected_at`.** Same as the other adapters and harmless; the naming is only slightly misleading.
- **N5 — Structure mirrors the existing adapters well.** The `SourceAdapterProtocol._build_event` mapping, `FetchResult` assembly, `record_fetch_success`/`record_fetch_failure`, and `time_fetch` metrics usage match `fake_store`/`best_buy`/`ebay`, which is good for maintainability.
- **N6 — `selectolax` is a reasonable choice.** It is lightweight, fast, and well-suited to static HTML; consistent with the task's "simplest reliable option" guidance.

---

## 7. Verdict

`CHANGES REQUIRED`

The HTML parsing implementation is well-scoped and mostly correct: it confines all HTML knowledge to `parser.py`, maps records into the canonical `ProductObservationEvent` via `_build_event`, handles missing price/availability gracefully, and ships deterministic fixture-based tests. All independently-run checks pass (57 targeted tests, ruff check, ruff format --check, mypy).

One finding blocks acceptance:

- **F1 (High)** — the required `url` field is silently produced incorrectly for the real production page. `_resolve_url` mishandles `../`-relative links and resolves against the site root, yielding `http://books.toscrape.com/../a-light-in-the-attic_1000/index.html` instead of the correct `http://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html`. The fixtures use non-representative bare hrefs, so the defect is invisible to the current test suite.

The remaining findings are non-blocking but should be addressed before or shortly after merge:

- **F2 (Moderate)** — missing-required-field products are silently dropped rather than routed to `malformed`/DLQ, and `total_records` undercounts.
- **F3–F7 (Minor)** — dead code, a `float` round-trip on price, a fragile `availoffset` availability heuristic, a missing thousands-separator test, and a private-attribute access.

F1 should be fixed (proper URL resolution + representative fixtures + an assertion on the resolved URL) before this task is accepted.
