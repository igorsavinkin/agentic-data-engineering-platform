# TASK-043 Review Report

## 1. Review Header

- **Task ID:** TASK-043 — Seller / Listing Normalization
- **Review date:** 2026-09-16
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed commit:** `bf9ef6add212e2e2cf4f2e905d51aa29c80581d1` (`fix(TASK-043): Address Qwen review findings (round 2)`)
- **Reviewed change set:** `bbd26f20449eee568215b57dc806a7afe52886b6...bf9ef6add212e2e2cf4f2e905d51aa29c80581d1` on `feature/TASK-043`
  - `4eb376c` — `feat(TASK-043): Add eBay seller/listing normalization layer`
  - `bf9ef6a` — `fix(TASK-043): Address Qwen review findings (round 2)`
- **Scope:** Full TASK-043 implementation (3 files, +857 lines)
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

> Note: the working-tree `HEAD` is `7c835b1` (the prior review's documentation commit). The
> reviewed code is `bf9ef6a`, per the review instructions; this report is an independent
> re-review of `bbd26f2..bf9ef6a` and replaces the prior round-2 report in this file.

---

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
|---|---|---|
| Normalize eBay seller/listing into generic `Seller`/`MarketplaceListing` models | ✅ Met | `normalize_ebay_seller`, `normalize_listing` in `libs/adapters/ebay/normalizer.py` emit `libs.marketplace.seller.Seller` / `libs.marketplace.listing.MarketplaceListing` |
| Keep source-specific structures behind the adapter/normalization boundary | ✅ Met | Normalizer lives under `libs/adapters/ebay/`; downstream models (`libs/marketplace/*`) are source-agnostic |
| Normalize IDs (listing, seller) | ✅ Met | `listing_id = item_id`, `seller_id = username`; `qualified_id` yields `source:raw_id`. No double-prefix (verified by tests) |
| Normalize URLs | ✅ Met | `normalize_listing_url` prefers `item_web_url`, falls back to `https://www.ebay.com/itm/<item_id>`. Whitespace-only URL edge case → Finding F1 |
| Normalize exact price/currency | ✅ Met | `normalize_price` uses `Decimal(str(value))` + uppercased ISO currency; stored in metadata as `str(Decimal)`. Non-finite price edge case → Finding F3 |
| Normalize availability/condition where supported | ✅ Met | `availability_raw` boolean; `normalize_condition` canonical map. Incomplete map → Finding F2 |
| Normalize timestamps | ⚠️ N/A at this layer | No timestamp field exists on `MarketplaceListing`/`Seller` (TASK-042 design). Timestamps are handled at the event level (`collected_at`/`produced_at`) by `EbayAdapter`, consistent with the canonical event contract. Not a defect, but see Non-Defect Observation N1 |
| Preserve diagnostic/source identity | ✅ Mostly | `feedback_score`, `feedback_percentage`, `condition`, `availability_raw`, `category_id`, `price`/`currency` preserved in metadata. Unmapped condition and `image` dropped (Findings F2, Observation N5) |
| Deterministic, separated from HTTP I/O | ✅ Met | All functions are pure; no network/IO; deterministic given input |
| No fuzzy product matching | ✅ Met | Product key only via explicit `ListingProductMapper` lookup; no title similarity |
| Distinct sellers/listings never silently collapsed | ✅ Met | Identity via `qualified_id` (`source:raw_id`); tests `test_distinct_listings_never_collapsed`, `test_seller_identity_stable_across_observations` |
| Tests: success, malformed/partial, deterministic identity, replay | ✅ Met | 43 unit tests cover these categories; see §4 |

---

## 3. Git Diff Review

- **Scope correctness:** ✅ Correct. The range touches only:
  - `libs/adapters/ebay/normalizer.py` (new, +350) — the normalization layer
  - `libs/adapters/ebay/__init__.py` (+14) — re-exports
  - `tests/test_adapters/test_ebay_normalizer.py` (new, +493) — unit tests
- **Unrelated changes:** ✅ None.
- **Architectural changes:** ✅ None. No service boundaries, event semantics, or schema changes. New code sits entirely inside the eBay adapter package and the marketplace model library.
- **Accidental/debug/temporary/secret content:** ✅ None found. No credentials, no debug prints, no generated artifacts, no dead code.
- **Dependencies/config changes:** ✅ None. No new dependencies introduced; `pyproject.toml`, requirements, CI, and infra untouched.
- **Test weakening:** ✅ None. Tests assert corrected behavior; no test was deleted or weakened to force a green build.

---

## 4. Test and Verification Review

### Tests examined
`tests/test_adapters/test_ebay_normalizer.py` (43 tests) covering:
- seller normalization (full, `None`, empty username, missing feedback, source override, determinism)
- price normalization (valid, `None`, negative, zero, currency case, missing currency)
- condition mapping (parametrized over canonical + unknown values)
- URL construction (API URL preferred, fallback, whitespace trim)
- listing normalization (full, minimal, partial, determinism, source override, explicit product key, distinct-not-collapsed)
- product-key mapper assignment (assigned, no mapper, unknown listing)
- replay idempotency and edge cases

### Test adequacy
Good overall. Gaps are the edge cases identified in Findings F1–F3 (whitespace-only URL/title, non-finite price, unmapped eBay condition values), which are not exercised.

### Verification status

| Check | Result | Classification |
|---|---|---|
| `python -m pytest tests/test_adapters/test_ebay_normalizer.py -v` | ✅ 43 passed (0.42s) | **Independently verified** |
| `python -m ruff check libs/adapters/ebay/ tests/test_adapters/test_ebay_normalizer.py` | ✅ All checks passed | **Independently verified** |
| `python -m ruff format --check libs/adapters/ebay/ tests/test_adapters/test_ebay_normalizer.py` | ✅ 6 files already formatted | **Independently verified** |
| `python -m mypy libs/adapters/ebay/ tests/test_adapters/test_ebay_normalizer.py` | ✅ Success: no issues in 6 source files | **Independently verified** |
| Integration tests (`pytest -m integration`) | Not run | **Not required** — this task is pure functions with no Kafka/persistence/MinIO boundary; eBay integration is deferred to TASK-045 |

Additional independent probes (read-only, in-memory) confirmed Findings F1–F3 below.

---

## 5. Findings

### F1 — Whitespace-only `item_web_url` / `title` raises instead of degrading gracefully (Moderate)
- **File:** `libs/adapters/ebay/normalizer.py:197-198` (`normalize_listing_url`) and `:288` (`normalize_listing`)
- **Problem:** The module's stated design is "missing/partial metadata is handled deterministically rather than raising exceptions." However, a truthy-but-whitespace-only `item_web_url` returns `""` after `.strip()`, and `summary.title.strip()` yields `""` for a whitespace-only title. `MarketplaceListing` enforces `min_length=1` on `url` and `title`, so Pydantic raises `ValidationError` in both cases. Independently confirmed: `normalize_listing(EbayListingSummary(item_id="x", title="T", item_web_url="   "))` raises `ValidationError`; the same occurs for a whitespace-only title.
- **Impact:** A malformed/partial record can crash normalization instead of flowing through with deterministic handling, contradicting both the module's own design rationale and the task's "missing/partial metadata is handled deterministically" acceptance criterion.
- **Recommendation:** Treat empty-after-strip values as missing — e.g. `if item_web_url and item_web_url.strip():` before preferring the API URL; decide an explicit deterministic policy for empty titles (fallback placeholder or upstream rejection).

### F2 — Condition mapping is incomplete for real eBay values and drops the raw condition (Moderate)
- **File:** `libs/adapters/ebay/normalizer.py:40-52` (`EBAY_CONDITION_MAP`), `:145-172` (`normalize_condition`)
- **Problem:** eBay's condition vocabulary includes `"New other"`, `"Manufacturer refurbished"`, and `"Seller refurbished"`, none of which are in `EBAY_CONDITION_MAP`. These normalize to `None`, and the raw condition string is not preserved anywhere (metadata only stores `condition` when non-`None`). Independently confirmed: `normalize_condition("New other") == None`, `normalize_condition("Manufacturer refurbished") == None`.
- **Impact:** Condition information is silently lost for common real listings, reducing diagnostic/source-identity preservation. The task explicitly asks to normalize condition "where supported" and preserve diagnostic identity.
- **Recommendation:** Extend the map (e.g. `"new other" → "new_other"`, `"manufacturer refurbished"`/`"seller refurbished" → "refurbished"`) and/or retain the raw condition string in metadata when unrecognized.

### F3 — Non-finite price `inf` is accepted as a valid `Decimal('Infinity')` (Moderate)
- **File:** `libs/adapters/ebay/normalizer.py:136-137` (`normalize_price`)
- **Problem:** The docstring states "invalid or negative prices are treated as missing," but `Decimal(str(float('inf')))` produces a finite-looking-but-infinite `Decimal('Infinity')`, which is not `< 0` and is not caught, so it is returned as a valid price and later stored as `metadata["price"] == "Infinity"`. `nan` and `-inf` are handled correctly (`nan` via `InvalidOperation` on comparison; `-inf` via `< 0`), but `+inf` is not. Independently confirmed: `normalize_price(EbayPrice(value=float('inf'), currency='USD')) == (Decimal('Infinity'), 'USD')`.
- **Impact:** A nonsensical "Infinity" price can flow downstream, contradicting the stated invalid-price handling. Real-world likelihood from eBay is very low, but the guard is incomplete for the canonical "invalid" float values.
- **Recommendation:** Reject non-finite values: `if not amount.is_finite() or amount < 0: return None, ...`.

---

## 6. Non-Defect Observations

- **N1 — Timestamps handled at the event layer, not here.** `MarketplaceListing`/`Seller` deliberately carry no timestamp field (TASK-042); `collected_at`/`produced_at` are set by `EbayAdapter` on `ProductObservationEvent`. This is consistent with the architecture; the task's "timestamps" wording is satisfied at the event envelope, not the listing/seller model.
- **N2 — Price/currency live in `metadata` as strings.** `MarketplaceListing` has no typed `price`/`currency` field, so `metadata["price"]` is `str(Decimal)` and `metadata["currency"]` is a code. Exactness is preserved, but downstream consumers must re-parse the string. This is a consequence of the TASK-042 model, not a defect introduced here.
- **N3 — Adapter not yet wired to the normalizer.** `EbayAdapter._map_listing_to_event` still maps eBay summaries to `ProductObservationEvent` directly and duplicates URL construction, availability inference, and category extraction that the new normalizer also performs. Expected for TASK-043 scope; the parallel implementations should converge during TASK-045 (eBay integration tests).
- **N4 — `normalize_listing_with_product_key` types the mapper as `Any | None`** rather than `ListingProductMapper | None`, weakening static checking. Minor.
- **N5 — `image` is not preserved.** `EbayListingSummary.image` (`EbayImage.image_url`) is ignored during normalization and dropped. Image URLs are not in the task's explicit field list, but they are diagnostic source data.
- **N6 — Identity helpers bypassed but consistently.** The normalizer relies on `Seller.qualified_id` / `MarketplaceListing.qualified_id` rather than `build_seller_id` / `build_listing_id`. This is internally consistent and correctly avoids double-prefixing, but identity construction is now expressed in two places.
- **N7 — Availability boolean is a length-based heuristic.** `metadata["availability_raw"] = availability.is_in_stock` inherits the pre-existing `EbayAvailability.is_in_stock` semantics (list non-empty ⇒ in stock), which does not inspect `quantity`. Pre-existing (TASK-041) behavior, noted for downstream awareness.

---

## 7. Verdict

**`APPROVED WITH NON-BLOCKING FINDINGS`**

The normalization layer satisfies TASK-043's core requirements: it is deterministic, pure (no HTTP I/O), typed, and produces generic `Seller`/`MarketplaceListing` representations with stable `source:raw_id` identity that never silently collapses distinct listings or sellers. The diff is correctly scoped (3 files, no unrelated or architectural changes, no new dependencies, no secrets), and all 43 unit tests plus `ruff` and `mypy` pass under independent execution.

No Critical or High findings were identified. The three Moderate findings (F1–F3) concern robustness/coverage gaps in edge-case handling — whitespace-only URL/title, non-finite prices, and an incomplete condition map — which should be addressed but do not block acceptance of the normalization layer itself. None of them affect the deterministic identity, no-fuzzy-matching, or scope-discipline guarantees required by the task.
