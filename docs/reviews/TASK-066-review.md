# TASK-066 Review — Price Analytics

## 1. Review Header

- **Task ID:** TASK-066 — Price Analytics
- **Review date:** 2026-09-19
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set (three-dot diff):** `a8643dbccd64a1cc2532936fc46f366c23b03435...399a5cd3827489168a55b413de3e20f5b680db52`
- **Reviewed HEAD:** `399a5cd3827489168a55b413de3e20f5b680db52` on `feature/TASK-066`
- **Merge base of the three-dot range:** `5b823078a68bf24f0ab42b5d3ab98a7b81900833`
- **Commits in range (2-dot `a8643db..399a5cd` = 3 commits):**
  - `0c1f8d1` feat(TASK-066): price analytics API endpoints
  - `7c4cda0` fix(TASK-066): address review findings — currency grouping and chronological first/last price
  - `399a5cd` fix(TASK-066): enforce currency guards, fix from_date LAG, eliminate N+1
- **Scope:** `services/api/repositories/analytics.py`, `services/api/routes/v1/analytics.py`, `services/api/routes/v1/router.py`, `services/api/schemas.py`, `tests/api/routes/v1/test_analytics.py` (plus a reviewer artifact, see §3)
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

> **Note on the base commit.** The named base `a8643db` ("feat:new tasks commit and push script") is on a *divergent* branch — it added `scripts/commit_tasks.sh`, which is not part of TASK-066 and is not reachable from the feature branch. The feature branch actually diverges from `5b823078`. The three-dot diff (`a8643db...399a5cd`) correctly resolves against `5b823078` and shows only the six task-relevant files. A naive two-dot `git diff a8643db..399a5cd` would misleadingly report `scripts/commit_tasks.sh` as deleted; that is an artifact of the divergent base, not a TASK-066 change.

---

## 2. Requirements Coverage

Task objective: expose established warehouse analytical queries — latest price, changes, and bounded min/max/average/source-listing comparisons where supported; reuse the existing SQL/query layer; **never aggregate unlike currencies without established conversion**.

| Requirement | Status | Evidence |
|---|---|---|
| Read-only analytics behind a repository/query layer | ✅ Met | `AnalyticsRepository` (`services/api/repositories/analytics.py`); thin handlers in `services/api/routes/v1/analytics.py` |
| "Latest price" | ✅ Met (no new endpoint) | Already exposed by TASK-064 (`latest_price` on product list/detail) |
| "Changes" query (chronological deltas) | ✅ Met | `GET /analytics/price-changes` via `LAG(...) OVER (PARTITION BY source_product_id ORDER BY collected_at ASC)` |
| "Bounded min/max/average" | ✅ Met | `GET /analytics/price-statistics` computes per-source **and per-currency** min/max/avg |
| Source/listing comparisons | ✅ Met | `GET /analytics/price-movers` ranks source-products by chronological first→last change percentage |
| **Never aggregate unlike currencies without conversion** | ✅ Met | All three endpoints now guard currency: statistics groups by `(source, currency)`; movers skips source-products whose first/last observation currencies differ; price-changes nulls deltas when `prev_currency != currency` |
| Reuse existing SQL/query layer | ⚠️ Partial | Reuses the API ORM repository pattern but **not** the existing `warehouse/analytics/queries.py` analytical SQL layer from TASK-032 — see Finding F1 |
| Bounded queries / pagination | ⚠️ Partial | `page_size`/`limit` ≤ 100, `days_back` ≤ 365, `min_observations` 2–100; but movers fetches all candidates and full per-candidate histories, ranking in Python — see Finding F2 |
| Typed FastAPI/Pydantic | ✅ Met | New Pydantic response models in `schemas.py`; frozen dataclasses in the repository |
| Thin handlers, logic in reusable layer | ✅ Met | Route handlers map dataclass → response schema |
| No secrets / internal stack traces | ✅ Met | Reuses structured validation (422); no secret handling |
| No unrelated changes | ✅ Met | See §3 (the only non-implementation file is a reviewer artifact) |
| Tests deterministic | ✅ Met | 21 tests; wall-clock dependency resolved via `datetime.now(timezone.utc)` seed |

Scope note: SPECIFICATION.md §16 lists `GET /analytics/price-changes` and `GET /analytics/anomalies`. The two extra endpoints (`price-movers`, `price-statistics`) are justified by the TASK-066 objective ("changes" and "bounded min/max/average/source-listing comparisons"); `anomalies` is correctly left out of scope (TASK-032 notes anomaly semantics are not yet deterministic enough).

---

## 3. Git Diff Review

- **Branch / isolation:** On `feature/TASK-066`; three commits in the reviewed range. Working tree has an unstaged edit to `docs/reviews/TASK-066-review.md` (this review supersedes it). No cross-task contamination.
- **Files changed (6, three-dot diff):**
  - `services/api/repositories/analytics.py` (new) — `AnalyticsRepository` + frozen dataclasses.
  - `services/api/routes/v1/analytics.py` (new) — three `GET` handlers + `_decimal_to_float`.
  - `services/api/routes/v1/router.py` (+2) — registers the analytics router.
  - `services/api/schemas.py` (+66) — six new Pydantic response models.
  - `tests/api/routes/v1/test_analytics.py` (new) — 21 tests.
  - `docs/reviews/TASK-066-review.md` (new) — **process observation**, see below.
- **Out-of-scope / unrelated changes:** The only non-implementation file is `docs/reviews/TASK-066-review.md`, a prior reviewer's report committed inside `7c4cda0` (an implementation "fix" commit). Committing a review artifact inside a TASK-066 implementation commit blurs the independent-reviewer/implementer separation mandated by REVIEWER.md. Additionally, the version committed at HEAD references pre-rebase commit hashes (`23c1956`, `a7916e6`) that are no longer reachable from this branch, so it is stale. This is a process note, not a functional defect.
- **Architectural changes:** None. The API remains read-only; the warehouse-loader-owns-writes boundary is preserved (ORM models remain query-only).
- **Accidental / debug / secrets / generated artifacts:** None found.
- **New dependencies:** None — only `sqlalchemy.case`, `func`, `select`, and stdlib imports, all already present.
- **`scripts/commit_tasks.sh`:** Not part of this task. Its apparent "deletion" in a two-dot `git diff a8643db..399a5cd` is an artifact of the divergent base `a8643db` (which added it on a separate branch); the three-dot diff and the feature-branch history contain no such change.

---

## 4. Test and Verification Review

### Tests examined
`tests/api/routes/v1/test_analytics.py` — 21 tests across three classes:
- `TestPriceChanges` (10): empty, full list, pagination, `source_product_id` filter, delta computation, first-observation-no-change, invalid `page`, invalid `page_size`, `from_date` preserves LAG from full history (new), currency change produces null delta (new).
- `TestPriceMovers` (7): empty, returns movers, price-drop-reported-correctly, `limit`, `source_id` filter, invalid `days_back`, invalid `limit`.
- `TestPriceStatistics` (4): empty, per-source stats, statistics values, invalid `days_back`.

### Verification status

| Check | Result | Classification |
|---|---|---|
| `python -m pytest tests/api/routes/v1/test_analytics.py -q` | 21 passed | **Independently verified** |
| `python -m pytest tests/api -q` | 69 passed | **Independently verified** |
| `python -m ruff check services/api` | All checks passed | **Independently verified** |
| `python -m ruff format --check services/api` | 19 files already formatted | **Independently verified** |
| `python -m mypy` | Success: no issues in 163 source files | **Independently verified** (excludes `services/` — Finding F3) |
| `python -m mypy services/api` | Fails: module-name collision (`api.models` vs `services.api.models`) | **Independently verified** (Finding F3) |
| `python -m pytest -m integration` | Not run (Docker PostgreSQL required) | **Unverified** |

### Test adequacy notes
- Tests use in-memory **SQLite** via `tests/api/conftest.py` (`Base.metadata.create_all`), not PostgreSQL. `LAG`, `NUMERIC(12,2)`, and `TIMESTAMP(timezone=True)` behave differently between SQLite and PostgreSQL; there is no integration-marked test exercising these endpoints against the real warehouse. Coverage gap, not a defect.
- The two new tests added in `399a5cd` (`test_from_date_preserves_lag_from_full_history`, `test_currency_change_produces_null_delta`) correctly pin down the two previously-flagged High-risk behaviors (from_date LAG semantics and cross-currency deltas). This is exactly the right coverage for the fixes.
- `test_price_drop_reported_correctly` pins the chronological first/last fix (negative change reported correctly).
- No PostgreSQL integration test for the analytics endpoints (the `warehouse/analytics` SQL from TASK-032 is integration-tested separately; the API's re-implemented SQL is not — see Finding F1).

---

## 5. Findings

### F1 — Moderate: analytical SQL duplicated instead of reusing `warehouse/analytics/queries.py`

- **File / line:** `services/api/repositories/analytics.py` (whole module) vs existing `warehouse/analytics/queries.py`.
- **Problem:** TASK-066 states "Expose established warehouse analytical queries … **Reuse existing SQL/query layer**". The repository already contains `warehouse/analytics/queries.py` (TASK-032), which implements the same three analytical operations — `price_change_analysis` (LAG deltas), `products_ranked_by_price_increase` (first/last ranking), and `source_statistics_summary` (min/max/avg) — and is documented as the analytical-query layer in `docs/architecture-communication/reading-notes.md`. The API re-implements all three in SQLAlchemy ORM without importing or referencing that layer (`grep` confirms no `warehouse.analytics` usage anywhere under `services/`).
- **Impact:** Duplicated analytical logic across two layers with semantic drift risk. The drift is already visible: the warehouse `price_change_analysis` filters out first-observation rows (`WHERE prev_price IS NOT NULL`), while the API's `price-changes` includes them with a null delta; the warehouse `products_ranked_by_price_increase` has no currency guard, while the API adds one (the API is actually *more* correct on currency). The "reuse" instruction is not satisfied.
- **Recommendation:** Reconcile the two layers. Either (a) have the API execute the warehouse analytical queries (adapting the PostgreSQL-specific SQL — `AT TIME ZONE`, `FILTER`, `::numeric`, `INTERVAL` — to a form compatible with the API's execution path and the hermetic SQLite test suite), or (b) document and justify the deliberate two-layer split and keep the two implementations in sync, ideally via a short ADR. This is a judgment call worth surfacing to the human owner.

### F2 — Moderate: `price-movers` still unbounded in DB fetch and ranks in Python

- **File / line:** `services/api/repositories/analytics.py` — `agg_q` (207–221) has no DB-side `LIMIT`; `first_q`/`last_q` (230–258) fetch full per-candidate observation histories with no window/`LIMIT 1`; ranking and truncation happen in Python (`movers.sort(...)` / `movers = movers[:limit]`, 287–288).
- **Problem:** The prior N+1 defect is fixed (now a constant 4 queries), but the queries still materialize every candidate `source_product_id` and, for each, every in-window observation row. The Python layer only keeps the first/last row per candidate after the DB has transferred the entire ordered history.
- **Impact:** Data transferred and memory scale with total observations/candidates in the window, not the requested `limit`. Contradicts the "bound queries" engineering rule in spirit for large listings.
- **Recommendation:** Use a windowed query to fetch only the boundary rows — e.g. `ROW_NUMBER() OVER (PARTITION BY source_product_id ORDER BY collected_at ASC, id ASC)` with `rn = 1` (and `DESC` for last) — and push ranking/`LIMIT` into SQL where supported.

### F3 — Moderate: `mypy` configuration does not type-check the reviewed code (pre-existing)

- **File / line:** `pyproject.toml` — `[tool.mypy] files = ["scripts", "tests", "libs"]`.
- **Problem:** `python -m mypy` reports "Success … 163 source files" while `services/` (all of TASK-066) is excluded. `python -m mypy services/api` fails independently on a module-name collision (`api.models` vs `services.api.models`), so the `services/` tree is not cleanly type-checkable under the current config. Same gap as TASK-065; not introduced by this diff but weakens the "typed code / type checks pass" Definition of Done.
- **Impact:** The typed-code guarantee for the analytics repository/routes is unsupported by CI.
- **Recommendation:** Extend the mypy config to cover `services/` (resolving the module-base collision, e.g. via `explicit_package_bases` or `MYPYPATH`), so the API service is genuinely type-checked.

### F4 — Minor: monetary values returned as binary `float`

- **File / line:** `services/api/routes/v1/analytics.py` (`_decimal_to_float` at 132; `float(item.first_price)`/`float(item.last_price)` at 96–99); `services/api/schemas.py` (price fields typed `float`/`Optional[float]`).
- **Problem:** Prices are stored as `NUMERIC(12,2)` (exact) but converted to `float` at the boundary, losing exactness/scale (same issue as TASK-064, now carried into analytics).
- **Impact:** Precision/display artifacts for downstream JSON consumers.
- **Recommendation:** Return `Decimal` (Pydantic serializes as number/string) or a formatted string for money fields.

### F5 — Minor: paginated analytics schema re-declares `PaginatedResponse` fields

- **File / line:** `services/api/schemas.py` — `PriceChangeListResponse` duplicates `items`, `total`, `page`, `page_size` already declared on `PaginatedResponse`.
- **Problem:** Recurrence of TASK-064/065 findings; schema-drift risk as TASK-067/068 add more paginated endpoints.
- **Recommendation:** Make `PaginatedResponse` generic over the item type and reuse it.

### F6 — Minor: non-deterministic ordering tiebreak on `collected_at`

- **File / line:** `services/api/repositories/analytics.py` — LAG windows (99–105) and movers first/last queries (239, 255) order by `collected_at` only; the paginated price-changes final query (166) orders by `collected_at.desc()` only.
- **Problem:** No `id` (or other deterministic) tiebreaker. The existing `list_observations` in `product.py` uses `collected_at.desc(), id.desc()`; the analytics queries do not. When two observations share a `collected_at` (possible with coarse timestamps or dedup), first/last selection and page boundaries become non-deterministic (a row can be duplicated or skipped across pages).
- **Impact:** Minor correctness/stability risk; currently masked by unique timestamps in the test seed.
- **Recommendation:** Add `ProductObservation.id` as a secondary sort key to every `order_by` that drives window partitioning or pagination.

---

## 6. Non-Defect Observations

- **The prior review's blocking finding is resolved.** The explicit "never aggregate unlike currencies" constraint is now enforced in all three endpoints, each with a dedicated test. This was the single hard requirement and it now holds.
- **The two original High findings are fixed correctly:** `price-statistics` groups by `(source, currency)`; `price-movers` derives first/last prices chronologically (not via MIN/MAX) with a negative-change test.
- **`from_date` LAG semantics are now correct:** LAG is computed over full history in an inner subquery and `from_date` is applied as an outer filter, so the first in-window observation retains its true predecessor delta.
- **"Latest price" needs no new endpoint** — TASK-064 already exposes it on product list/detail.
- **Structured error/validation handling is reused** (422 for invalid `page`/`page_size`/`limit`/`days_back`/`min_observations`); no secrets or stack traces exposed.
- **Bounding is reasonable at the API boundary:** `page_size`/`limit` ≤ 100, `days_back` ≤ 365, `min_observations` 2–100.
- **`price-statistics` uses a `LEFT JOIN` with the cutoff in the `ON` clause**, so sources with zero in-window observations appear with null stats and `currency=None`. This is defensible (surfaces "sources stopped producing data"); worth a doc note.
- **`_decimal_to_float` is duplicated** across `products.py` and `analytics.py`; a shared helper would reduce drift (Minor, style, subsumed under F4).

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The implementation is cleanly scoped, isolated to TASK-066, architecturally compliant (read-only repository layer, no writes, no new dependencies), and passes all unit tests (`21` analytics tests, `69` API-suite tests), `ruff check`, and `ruff format --check` — all independently executed. The previously blocking High finding (cross-currency aggregation) is now fully resolved across all three endpoints with regression tests; the `from_date` LAG and N+1 defects are also fixed.

Remaining findings are non-blocking:

- **F1 (Moderate)** — the analytical SQL is re-implemented rather than reused from the existing `warehouse/analytics/queries.py` layer, creating duplication/drift and not fully satisfying the "reuse existing SQL/query layer" instruction. This is the one point worth a human decision (reuse vs. documented two-layer split).
- **F2 (Moderate)** — `price-movers` still materializes all candidates and full histories in the DB→Python transfer (constant 4 queries, but unbounded row volume).
- **F3 (Moderate)** — pre-existing mypy config does not type-check `services/`.
- **F4–F6 (Minor)** — `float` money serialization, `PaginatedResponse` duplication, and missing `id` ordering tiebreakers.

PostgreSQL integration verification for these endpoints was not evidenced and remains unverified (requires Docker); the unit suite covers the SQL semantics only under SQLite.
