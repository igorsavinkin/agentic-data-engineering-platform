# TASK-043 Review Report (Round 2)

## 1. Review Header

- **Task ID:** TASK-043 — Seller / Listing Normalization
- **Review date:** 2026-09-16
- **Reviewer:** Qwen Code (automated review, round 2 - timeout, manual verification)
- **Reviewed commit:** `bf9ef6add212e2e2cf4f2e905d51aa29c80581d1` (`fix(TASK-043): Address Qwen review findings (round 2)`)
- **Reviewed change set:** `bbd26f20449eee568215b57dc806a7afe52886b6...bf9ef6add212e2e2cf4f2e905d51aa29c80581d1` on `feature/TASK-043`
- **Scope:** Fix two MAJOR findings from round 1 review
- **Verdict:** `APPROVED`

---

## 2. Findings Resolution

### Finding 1 — Normalized price/currency is computed then discarded (RESOLVED)

**Original problem:** `normalize_price` returned exact `Decimal` and currency, but `normalize_listing` discarded both, storing only lossy `float(summary.price.value)` without currency.

**Fix applied in `libs/adapters/ebay/normalizer.py`:**
```python
# Persist normalized price/currency (exact Decimal + ISO currency)
if price is not None:
    metadata["price"] = str(price)  # Decimal as string for JSON serialization
    metadata["currency"] = currency
elif summary.price is not None:
    # Fallback: store raw info when normalization produced None (e.g. negative)
    metadata["price_original"] = float(summary.price.value)
    metadata["currency"] = currency
```

**Verification:** Test `test_full_listing_normalized` now asserts:
```python
assert listing.metadata["price"] == "999.99"  # Exact Decimal as string
assert listing.metadata["currency"] == "USD"
```

All 43 tests pass including `test_partial_listing_handles_partial_data` which verifies EUR currency preservation.

---

### Finding 2 — Seller identity is double-prefixed (RESOLVED)

**Original problem:** `build_seller_id("ebay", "username")` returned `"ebay:username"`, then `Seller.qualified_id` prepended source again producing `"ebay:ebay:username"`.

**Fix applied in `libs/adapters/ebay/normalizer.py`:**
```python
# Use raw username as seller_id; Seller.qualified_id will prepend source
# automatically, producing "ebay:<username>" (not "ebay:ebay:<username>")
seller_id = username
```

**Verification:** Test `test_full_seller_normalized` now asserts:
```python
assert result.seller_id == "top_seller"  # Raw username, not double-prefixed
assert result.qualified_id == "ebay:top_seller"  # Single prefix via qualified_id
```

All seller identity tests pass with correct single-prefix pattern.

---

### Finding 3 — Tests encode/mask both defects (RESOLVED)

Tests updated to assert corrected behavior:
- `test_full_seller_normalized`: Now checks `seller_id == "top_seller"` and `qualified_id == "ebay:top_seller"`
- `test_full_listing_normalized`: Now asserts `metadata["price"]` and `metadata["currency"]` presence
- `test_partial_listing_handles_partial_data`: Fixed expectation for `Decimal("50.0")` string representation

---

## 3. Quality Checks

| Check | Result |
|---|---|
| `ruff check .` | ✅ All checks passed |
| `ruff format --check .` | ✅ 229 files already formatted |
| `mypy libs/` | ✅ Success: no issues found in 45 source files |
| `pytest tests/test_adapters/test_ebay_normalizer.py` | ✅ 43 passed |

---

## 4. Verdict

**`APPROVED`**

Both MAJOR findings from round 1 have been correctly addressed:
1. Price/currency now persisted as exact Decimal string and ISO currency code
2. Seller identity uses raw username, producing correct single-prefix `qualified_id`

The normalization layer is clean, deterministic, fully typed, and all 43 unit tests pass. Ready to merge.
