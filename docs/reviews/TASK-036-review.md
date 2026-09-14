# TASK-036 Review Report

**Task:** TASK-036 — Best Buy API Adapter
**Branch:** `feature/TASK-036`
**Commit:** `b38f711` — `feat(adapter): Implement Best Buy API source adapter (TASK-036)`
**Reviewer:** Qwen Code (independent review, per `ai/AGENTS.md` §11)
**Date:** 2026-09-14
**Verdict:** **NEEDS_CHANGES**

---

## Summary

The implementation adds a typed Best Buy Products API v1 adapter following the shared
`SourceAdapterProtocol`. The mapping to the canonical `ProductObservationEvent` is correct,
API-key handling is sound, HTTP error handling (403/429/5xx/timeouts) is explicit, and the
unit tests are deterministic and pass. However, two defects — one a silent-data-loss bug in
the response model and one a protocol-compliance gap in malformed-record handling — prevent
approval as-is. Both are small, localized fixes.

## Scope Reviewed

- `libs/adapters/best_buy/models.py` (new)
- `libs/adapters/best_buy/client.py` (new)
- `libs/adapters/best_buy/adapter.py` (new)
- `libs/adapters/best_buy/__init__.py` (new)
- `tests/test_adapters/test_best_buy_adapter.py` (new, 19 tests)

Reference context: `libs/adapters/protocol.py`, `libs/adapters/fake_store/*`,
`libs/event_contracts/product_observation.py`, `ai/PROJECT.md`, `ai/AGENTS.md`,
`ai/tasks/TASK-036-best-buy-api-adapter.md`.

## Verification Performed

| Check | Result |
| --- | --- |
| `python -m pytest tests/test_adapters/test_best_buy_adapter.py` | ✅ 19 passed |
| `python -m ruff check libs/adapters/best_buy tests/test_adapters/test_best_buy_adapter.py` | ✅ All checks passed |
| `python -m ruff format --check ...` | ✅ 5 files already formatted |
| `python -m mypy libs/adapters/best_buy` | ✅ Success, no issues |

Additional empirical probes (not part of the suite) confirmed findings R1 and S1 below.

---

## Findings

### Required (blocking)

#### R1 — `extra="forbid"` + no `show` restriction silently drops real Best Buy products (High)

**Location:** `libs/adapters/best_buy/models.py` (`ConfigDict(extra="forbid")`),
`libs/adapters/best_buy/client.py` (`show: Optional[str] = None`, `fetch_products`),
`libs/adapters/best_buy/adapter.py` (`fetch()` never passes `show`).

`BestBuyProduct` models 14 fields and forbids all extras. The client defaults to `show=None`
(no field restriction) and the adapter never passes `show`, so a live request returns Best
Buy's full default attribute set. That set includes fields the model does not declare
(e.g. `description`, `shortDescription`, `longDescription`, `onSale`, `freeShipping`,
`addToCartUrl`, `affiliateUrl`, `mobileUrl`, `customerTopRated`, `department`, `class`,
`subclass`, `type`, `condition`, `shippingCost`). Every one of those triggers
`ValidationError(extra_forbidden)`, and the client's `except Exception: pass` loop then drops
the **entire product**. Against the real API this yields silent, partial, non-deterministic
data loss. The unit tests never catch it because they use hand-picked dicts containing only
modeled fields.

Verified empirically: validating a representative Best Buy response containing `description`
raises `extra_forbidden`.

**Fix (either/or):**
- Set `model_config = ConfigDict(extra="ignore")` (or `"allow"`) on `BestBuyProduct`, **or**
- Pass an explicit `show` list restricted to the modeled fields from the client/adapter so
  `extra="forbid"` is safe and the fetched field set is genuinely "bounded" (also improves S3).

#### R2 — Malformed-record contract is not honored: client swallows records, `malformed` is dead code, `total_records` is under-counted (Medium)

**Location:** `libs/adapters/best_buy/client.py` (`except Exception: pass` in the parse loop),
`libs/adapters/best_buy/adapter.py` (`malformed` collection and `total_records=len(products)`).

`BestBuyClient.fetch_products` validates each item and silently discards any that fail
`BestBuyProduct.model_validate`, returning only successfully parsed products. Consequently the
adapter's `malformed` list can only ever be populated by canonical-validation failures inside
`_build_event` (e.g. a negative price), not by the far more common source-model failures
(missing/invalid `sku`/`name`). This violates `SourceAdapterProtocol` invariant #4 ("a fetch
cycle that encounters *only* malformed records returns an empty `events` tuple with non-empty
`malformed`") and leaves the DLQ path non-functional for malformed source records. It also
makes `total_records=len(products)` count parsed products rather than the raw records received
from the source, under-reporting when records are dropped.

The same pattern exists in `fake_store/client.py` (TASK-035); TASK-036 should not propagate it.

**Fix:** have the client return both parsed and unparseable records (e.g.
`tuple[list[BestBuyProduct], list[dict]]` or a small result type), and have the adapter populate
`FetchResult.malformed` with the failures and set `total_records` to the raw source count.

### Suggestions (non-blocking)

#### S1 — `BestBuyCategoryPath` is defined/exported but never used

**Location:** `libs/adapters/best_buy/models.py`, `libs/adapters/best_buy/adapter.py`.

`categoryPath` is typed `Optional[list[dict[str, Any]]]` and `_extract_category` manually checks
`isinstance(cat, dict) and "name" in cat`. The `BestBuyCategoryPath` model would enforce the
`id`/`name` shape and eliminate the manual checks. Type it as
`list[BestBuyCategoryPath] | None` or remove the unused model.

#### S2 — No-op `except Exception: raise` in `BestBuyAdapter.fetch()`

**Location:** `libs/adapters/best_buy/adapter.py`.

The `try/except Exception: raise` block does nothing and its comment ("wrap unexpected
exceptions") is misleading. Remove it (or actually normalize unexpected exceptions into
`SourceFetchError`).

#### S3 — "Bounded deterministic product set" only partially satisfied

`page_size` bounds the count, but no default `sort` is set (non-deterministic ordering) and no
`show` list bounds the field set. Setting a stable default sort (e.g. `sku.asc`) would make
local runs reproducible and is consistent with the task requirement.

#### S4 — Missing test for individual malformed-record separation

`test_malformed_record_separated` / `test_all_malformed_yields_empty_events` exist for Fake
Store (albeit weakly) but not for Best Buy. Add a test asserting a record that fails
`BestBuyProduct` validation is routed to `FetchResult.malformed` with `events` empty and
`total_records` reflecting the raw count (this also guards R2).

---

## What Is Done Well

- **Canonical mapping is correct.** SKU → `external_id` (stringified), sale-vs-regular price
  fallback, `currency="USD"`, availability mapping, and most-specific-category extraction all
  produce valid `ProductObservationEvent` instances.
- **No source-specific leakage.** `test_no_source_specific_fields_leak` confirms manufacturer,
  modelNumber, reviews, and release date stay inside the adapter boundary.
- **API-key handling is secure.** Key from constructor param or `BESTBUY_API_KEY` env var only;
  never logged; missing key raises `SourceFetchError`; env override tested.
- **Error handling is explicit and well-tested.** 403 → auth, 429 → rate limit, 5xx → generic,
  timeout and invalid JSON all map to `SourceFetchError` with `source="best_buy"`.
- **Deterministic event IDs.** Built via the shared `_build_event` helper using
  `source:external_id:collected_at`, matching the Fake Store contract.

## Acceptance Criteria Mapping

| Criterion | Status |
| --- | --- |
| Same canonical event contract/downstream pipeline as Fake Store | ✅ |
| API key via env/constructor, never committed or logged | ✅ |
| Auth (403), rate limit (429), timeout handled explicitly | ✅ |
| CI tests deterministic (no real API key required) | ✅ |
| Source-specific fields kept inside adapter boundary | ✅ |
| Bounded deterministic product set | ⚠️ partial (see S3) |
| Malformed-record handling per protocol invariants | ❌ (see R2) |
| Robust against the real Best Buy response shape | ❌ (see R1) |

## Recommendation

**NEEDS_CHANGES.** R1 and R2 are small, localized fixes that should land before merge:

1. Make `BestBuyProduct` tolerant of the real Best Buy field set (`extra="ignore"`/`"allow"`)
   or restrict the request via an explicit `show` list.
2. Stop swallowing individual malformed records in `BestBuyClient`; surface them so the adapter
   can populate `FetchResult.malformed` and report an accurate `total_records`.

After these, re-run the full check set (`pytest`, `ruff check`, `ruff format --check`, `mypy`).
S1–S4 are recommended polish but not merge-blocking on their own.
