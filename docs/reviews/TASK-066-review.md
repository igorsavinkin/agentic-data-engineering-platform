# TASK-066 Review — Price Analytics

## 1. Review Header

- **Task ID:** TASK-066 — Price Analytics
- **Review date:** 2026-09-19
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `736eafdcf18b1be86ed86b04bd33b7640a3cdf47...23c19562ae55d822db20aa9714ba7bb474614e2a`
- **Reviewed HEAD:** `23c19562ae55d822db20aa9714ba7bb474614e2a` on `feature/TASK-066`
- **Merge base / parent of HEAD:** `a7916e6fc43318aa1e02b3b8ad4f0678bb6d2bf7`
- **Commits in range:** `23c1956 feat(TASK-066): price analytics API endpoints` (single commit)
- **Scope:** `services/api/repositories/analytics.py`, `services/api/routes/v1/analytics.py`, `services/api/routes/v1/router.py`, `services/api/schemas.py`, `tests/api/routes/v1/test_analytics.py`
- **Verdict:** `CHANGES REQUIRED`

---

## 2. Requirements Coverage

Task objective: expose established warehouse analytical queries — latest price, changes, and bounded min/max/average/source-listing comparisons where supported; reuse the existing SQL/query layer; **never aggregate unlike currencies without established conversion**.

| Requirement | Status | Evidence |
|---|---|---|
| Read-only analytics endpoints behind a repository/query layer | ✅ Met | `AnalyticsRepository` (`services/api/repositories/analytics.py`); thin handlers in `services/api/routes/v1/analytics.py` |
| "Changes" query (chronological price deltas) | ✅ Met | `GET /analytics/price-changes` via `LAG(...)` window function |
| "Bounded min/max/average" query | ⚠️ Partial | `GET /analytics/price-statistics` computes min/max/avg per source, but aggregates across currencies (Finding 1) |
| Source/listing comparisons | ⚠️ Partial | `GET /analytics/price-movers` (`source_id` filter, per-`source_product_id` grouping), but computes range instead of chronological change (Finding 2) |
| **Never aggregate unlike currencies without conversion** | ❌ Violated | Both `price-statistics` and `price-movers` aggregate `min/max/avg` over price with no currency filter/grouping (Finding 1) |
| Bounded queries / pagination | ✅ Met (with caveat) | `page`/`page_size` bounded (`le=100`); `limit`/`days_back`/`min_observations` bounded; caveat: movers fetch all grouped rows before slicing (Finding 6) |
| Typed FastAPI/Pydantic | ✅ Met | New Pydantic schemas in `schemas.py`; frozen dataclasses in repository |
| Thin handlers, logic in reusable layer | ✅ Met | Route handlers only map dataclass → response schema |
| No secrets / internal stack traces | ✅ Met | Reuses existing structured error handlers |
| No unrelated changes | ✅ Met | Diff limited to analytics repository/routes/schemas + analytics tests + one router registration line |
| Documentation/OpenAPI updated where appropriate | ✅ Met | FastAPI auto-generates OpenAPI from typed routes/schemas |

Scope note: SPECIFICATION.md §16 lists only `GET /analytics/price-changes` and `GET /analytics/anomalies`. The two additional endpoints (`price-movers`, `price-statistics`) are not in that list, but they are justified by the TASK-066 objective ("changes" and "bounded min/max/average/source-listing comparisons"). `anomalies` is correctly left out of scope. "Latest price" requires no new endpoint because TASK-064 already exposes `latest_price` on product list/detail.

---

## 3. Git Diff Review

- **Branch / isolation:** On `feature/TASK-066`; working tree clean; single commit `23c1956` in the reviewed range. The provided three-dot range `736eafd...23c1956` resolves to the same single-commit change set (merge-base `a7916e6` is the direct parent of HEAD). No cross-task contamination. ✅
- **Files changed (5):**
  - `services/api/repositories/analytics.py` (new, 320 lines) — `AnalyticsRepository` + frozen dataclasses.
  - `services/api/routes/v1/analytics.py` (new, 132 lines) — three `GET` handlers + `_decimal_to_float`.
  - `services/api/routes/v1/router.py` (+2) — registers the analytics router.
  - `services/api/schemas.py` (+63) — six new Pydantic response models.
  - `tests/api/routes/v1/test_analytics.py` (new, 256 lines) — 18 tests.
- **Out-of-scope / unrelated changes:** None found.
- **Architectural changes:** None. The API remains read-only; the warehouse-loader-owns-writes boundary is preserved (the ORM models remain query-only).
- **Accidental / debug / secrets / generated artifacts:** None found.
- **New dependencies:** None. Only `sqlalchemy.case`, `func`, `select`, and stdlib imports, all already available.

---

## 4. Test and Verification Review

### Tests examined
`tests/api/routes/v1/test_analytics.py` — 18 tests across three classes:
- `TestPriceChanges` (8): empty, full list, pagination, `source_product_id` filter, delta computation, first-observation-has-no-change, invalid `page`, invalid `page_size`.
- `TestPriceMovers` (6): empty, returns movers, `limit`, `source_id` filter, invalid `days_back`, invalid `limit`.
- `TestPriceStatistics` (4): empty, per-source stats, statistics values, invalid `days_back`.

### Verification status

| Check | Result | Classification |
|---|---|---|
| `python -m pytest tests/api/routes/v1/test_analytics.py -v` | 18 passed | Independently verified |
| `python -m pytest tests/api -q` | 66 passed | Independently verified |
| `python -m ruff check services/api` | All checks passed | Independently verified |
| `python -m ruff format --check services/api` | 19 files already formatted | Independently verified |
| `python -m mypy` | Success: 163 source files | Independently verified (excludes `services/` — see Finding 5) |
| `python -m mypy services/api` | Fails with module-name collision (`api.models` vs `services.api.models`) | Independently verified (Finding 5) |
| `python -m pytest -m integration` | Not run (Docker PostgreSQL required) | Unverified |

### Test adequacy notes
- Tests use in-memory **SQLite** via `Base.metadata.create_all`, not PostgreSQL. Window-function (`LAG`) and `TIMESTAMP(timezone=True)`/`NUMERIC` behavior differ between SQLite and PostgreSQL; no integration-marked test exercises these endpoints against the real warehouse. Coverage gap, not a defect.
- **No test exercises the explicit "never aggregate unlike currencies" constraint** (all seeded prices are USD). The constraint is the one hard requirement in the task objective and is completely untested.
- **No test exercises a chronological price decrease** for `price-movers`, which would expose Finding 2 (the endpoint reports a decrease as an increase).
- No `from_date` test for `price-changes` (there is a `source_product_id` test but no date-filter test), so Finding 3 is unexercised.
- Seed data uses a fixed date (`_NOW = 2026-09-15`) while the repository computes its cutoff from `datetime.now(timezone.utc)`, making the `price-movers` and `price-statistics` tests wall-clock dependent (Finding 4).

---

## 5. Findings

### Finding 1 — High: aggregates across currencies, violating an explicit task constraint

- **File / line:** `services/api/repositories/analytics.py` — `list_price_statistics` (`func.avg/min/max` over `ProductObservation.price`, lines ~262–281) and `list_price_movers` (`func.min/func.max` over `ProductObservation.price`, lines ~169–183). Also `list_price_changes` for a currency flip between consecutive observations.
- **Problem:** The task objective states "never aggregate unlike currencies without established conversion." The statistics and movers queries aggregate `min/max/avg` (and the movers compute `lp - fp`) over price without any `currency` filter or grouping. A source or listing whose observations mix currencies (e.g. USD and EUR) produces a meaningless minimum/maximum/average and a bogus "price change" (`$10` vs `€12` treated as a `+2` delta). The `price-changes` endpoint likewise reports a delta across a currency change with no `prev_currency` field to signal it.
- **Impact:** Incorrect analytical results for multi-currency sources/listings, which the task explicitly forbids. The error is silent — the response gives no indication the aggregation is across unlike currencies.
- **Recommendation:** Restrict each aggregate/change to a single currency (group by `currency`, or filter to one currency and surface/require the currency), or exclude observations whose currency differs from the listing's established currency. Add a multi-currency test.

### Finding 2 — High: `price-movers` uses MIN/MAX as a "first/last" proxy, so price decreases are reported as increases

- **File / line:** `services/api/repositories/analytics.py` — `list_price_movers`, `func.min(...)` / `func.max(...)` (lines ~173–175) and `fp = row.min_price; lp = row.max_price; abs_change = lp - fp` (lines ~191–194). The dataclass/schema field names `first_price`, `last_price`, `price_change_absolute`, `price_change_percent` are populated from min/max.
- **Problem:** `min`/`max` describe the price *range*, not the chronological *change*. Because `max >= min`, `abs_change` is always `>= 0` and `price_change_percent` is always non-negative; a genuine price drop is reported as a rise. Concretely, in the seed data `sp2` ("Gadget B") chronologically drops `50.00 → 45.00` (−10%), but the endpoint reports `first_price=45.00`, `last_price=50.00`, `price_change_absolute=+5.00`, `price_change_percent=+11.11`. The docstring admits it is a "proxy", but the API contract (field names and schema) presents the range as if it were a directional change. This directly fails the "changes" / "largest price increase" analytical questions in SPECIFICATION.md §3/§17.
- **Impact:** The core "price movers" feature returns materially wrong, misleading numbers (direction inverted, magnitude inflated) to any consumer or the LangGraph agent.
- **Recommendation:** Compute chronological first/last price per `source_product_id` (e.g. `FIRST_VALUE`/`LAST_VALUE` ordered by `collected_at`, or a first-observation/last-observation subquery), derive `price_change = last - first` (which can be negative), and rank by absolute or signed change as intended. Add a test that asserts a price decrease yields a negative change.

### Finding 3 — Moderate: `from_date` breaks LAG "previous price" semantics

- **File / line:** `services/api/repositories/analytics.py` — `list_price_changes`, LAG window (lines ~85–88) and `from_date` filter applied in the same query (lines ~111–112).
- **Problem:** The `from_date` `WHERE` clause is applied to the same `SELECT` that computes `LAG(price) OVER (PARTITION BY source_product_id ORDER BY collected_at ASC)`. Window functions are evaluated after filtering, so the first observation at/after the cutoff has `prev_price = NULL` instead of the actual last price *before* the cutoff. The "change since from_date" for the earliest in-window observation is silently dropped rather than compared against its pre-window predecessor.
- **Impact:** Filtering by `from_date` misstates the first delta in each partition; consumers cannot correctly answer "what changed since date X".
- **Recommendation:** Compute `LAG` over the unfiltered history in a subquery, then apply `from_date` in an outer query (or accept and document the semantics). Add a `from_date` test that verifies the first in-window observation's `prev_price` equals the pre-cutoff price.

### Finding 4 — Moderate: `price-movers` and `price-statistics` tests are wall-clock dependent

- **File / line:** `tests/api/routes/v1/test_analytics.py` — seed data uses fixed `_NOW = datetime(2026, 9, 15, ...)`; `services/api/repositories/analytics.py` — `cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)` (lines 167 and 262).
- **Problem:** The repository computes its window from the machine clock, but the tests seed observations at fixed 2026 dates and query with `days_back=30`. The tests only pass while the machine clock is within ~30 days of the seed's latest `collected_at` (2026-09-10). Once `now() − 30 days` exceeds that date, all seeded observations are filtered out and `test_returns_movers`, `test_returns_source_stats`, and `test_statistics_values` fail with empty results.
- **Impact:** Non-deterministic, time-bomb tests that will start failing ~2026-10-10 for no code reason, eroding CI trust.
- **Recommendation:** Inject a clock/`now` reference (or accept an explicit cutoff parameter) into the repository and freeze time in tests, or seed data relative to `datetime.now(timezone.utc)`.

### Finding 5 — Moderate: `mypy` configuration does not type-check the reviewed code (pre-existing)

- **File / line:** `pyproject.toml` — `[tool.mypy] files = ["scripts", "tests", "libs"]`.
- **Problem:** `python -m mypy` reports "Success: 163 source files" while the production code in `services/` (including all of TASK-066) is excluded. Running `python -m mypy services/api` independently fails on a module-name collision (`api.models` vs `services.api.models`), so the `services/` tree is not cleanly type-checkable under the current config. This is the same gap reported as TASK-065 Finding 5; it is not introduced by this diff, but it directly weakens the "typed code / type checks pass" Definition of Done for a typed-API task.
- **Impact:** The typed-code guarantee for the analytics repository/routes is unsupported by CI.
- **Recommendation:** Extend the mypy config to cover `services/` (resolving the module-base collision) so the API service is genuinely type-checked.

### Finding 6 — Moderate: `price-movers` fetches all matching groups and ranks in Python

- **File / line:** `services/api/repositories/analytics.py` — `list_price_movers`, unbounded aggregate query then `movers.sort(...)` + `movers = movers[:limit]` (lines ~183–205).
- **Problem:** The database query returns **every** `source_product_id` in the window satisfying `HAVING count >= min_observations`, with no `LIMIT` at the DB layer; ranking and truncation happen in Python after the full result set is materialized. This contradicts the "bound queries" engineering rule and does not scale with the number of listings.
- **Impact:** Memory/latency growth proportional to the number of listings in the window, not to the requested `limit`.
- **Recommendation:** Push ranking/`LIMIT` into SQL where the target backend supports it (e.g. a windowed `ROW_NUMBER`), or keep the Python ranking but impose a DB-side bound (e.g. only fetch rows with a minimum `max−min` candidate) with documented trade-offs.

### Finding 7 — Minor: monetary values returned as binary `float`

- **File / line:** `services/api/routes/v1/analytics.py` (`_decimal_to_float`, `float(item.first_price)`, `float(item.price_change_absolute)`); `services/api/schemas.py` (`price`, `prev_price`, `min_price`, `max_price`, `avg_price`, `first_price`, `last_price`, and change fields typed `Optional[float]`/`float`).
- **Problem:** Prices are stored as `NUMERIC(12,2)` (exact) but converted to `float` at the boundary, losing exactness/scale (same issue as TASK-064 Finding 2, now carried into analytics).
- **Impact:** Precision/display artifacts for downstream JSON consumers; "avg_price" already a float loses scale.
- **Recommendation:** Return `Decimal` (Pydantic serializes as number/string) or a formatted string for money fields.

### Finding 8 — Minor: paginated analytics schema re-declares `PaginatedResponse` fields

- **File / line:** `services/api/schemas.py` — `PriceChangeListResponse` duplicates `items`, `total`, `page`, `page_size` already present in `PaginatedResponse`.
- **Problem:** Recurrence of TASK-064 Finding 3 / TASK-065 Finding 4; schema drift risk as more paginated endpoints (TASK-067/068) are added.
- **Recommendation:** Make `PaginatedResponse` generic over the item type and reuse it.

### Finding 9 — Minor: missing test coverage for the two High findings and `from_date`

- **File / line:** `tests/api/routes/v1/test_analytics.py`.
- **Problem:** No test for multi-currency aggregation (Finding 1), no test for a chronological price decrease in `price-movers` (Finding 2), and no `from_date` test for `price-changes` (Finding 3). The current suite would pass even if all three defects shipped.
- **Impact:** The highest-risk behaviors are untested.
- **Recommendation:** Add deterministic tests for currency mixing, a price decrease, and `from_date` boundary semantics.

### Finding 10 — Minor: unreachable `else ""` branch in `collected_at` conversion

- **File / line:** `services/api/repositories/analytics.py` — `collected_at=row.collected_at.isoformat() if row.collected_at else ""` (line ~145).
- **Problem:** `ProductObservation.collected_at` is `nullable=False`, so `row.collected_at` is always a `datetime`; the `else ""` branch is dead. It also produces an empty string (not `None`) if the invariant ever breaks, despite the schema typing `collected_at: str` as required.
- **Impact:** Minor dead code / inconsistent null representation; no current functional effect.
- **Recommendation:** Use `row.collected_at.isoformat()` directly (or return `None` if the field were ever made nullable).

---

## 6. Non-Defect Observations

- **"Latest price" is already satisfied by TASK-064** (`latest_price` on product list/detail), so TASK-066 correctly adds no redundant "latest price" endpoint.
- **The `price-changes` LAG query is otherwise well-formed** for the unfiltered case: partitioned by `source_product_id`, ordered by `collected_at ASC`, and the `total` count is computed over the pre-pagination subquery (accurate, not inflated by joins). The `!= None` comparisons correctly emit `IS NOT NULL` (the `# noqa: E711` is appropriate).
- **No N+1 queries:** `price-movers` issues exactly two queries (aggregate + metadata enrichment) regardless of row count; `price-changes` issues count + page; `price-statistics` one query.
- **Structured error/validation handling is reused** (422 for invalid `page`/`page_size`/`limit`/`days_back`/`min_observations`), and no secrets or stack traces are exposed.
- **Bounding is reasonable:** `page_size`/`limit` capped at 100, `days_back` capped at 365, `min_observations` between 2 and 100.
- **Consistent with existing style:** reuses TASK-064/065's `_decimal_to_float` helper and the repository-layer `.isoformat()` timestamp convention, so prior open findings (float money, stringly-typed timestamps, `PaginatedResponse` duplication) carry over rather than being newly introduced.
- **`min_observations` default `ge=2`** means newly-listed products with a single observation never appear in movers; a defensible choice, but worth documenting for consumers.

---

## 7. Verdict

**CHANGES REQUIRED**

The implementation is cleanly scoped, isolated to TASK-066, architecturally compliant (read-only repository layer, no writes), and passes all unit tests (`18` analytics tests, `66` API-suite tests), `ruff check`, and `ruff format --check` — all independently executed. The diff contains no unrelated changes, secrets, or new dependencies.

Two High findings block acceptance:

1. **Finding 1** — the implementation aggregates `min/max/avg` and price deltas across unlike currencies, directly violating the task's explicit constraint "never aggregate unlike currencies without established conversion."
2. **Finding 2** — `price-movers` uses MIN/MAX as a first/last proxy, so the endpoint reports price *decreases* as *increases* with inverted `first_price`/`last_price` values, producing materially wrong answers for the "largest price change" questions the feature is meant to serve.

Both are correctness defects in the core analytics deliverable and should be fixed before acceptance. Findings 3–6 are Moderate robustness/correctness/verification issues that should be addressed in the same or an immediate follow-up; Findings 7–10 are Minor. PostgreSQL integration verification for these endpoints was not evidenced and remains unverified (requires Docker).
