# TASK-035 Review Report

| Field | Value |
|---|---|
| **Task** | TASK-035 — Fake Store API Adapter |
| **Review date** | 2026-09-14 |
| **Reviewed change set** | `7a90965` (`b144326..7a90965`) — Fake Store adapter commit |
| **Branch** | `feature/TASK-035` (HEAD `b38f711`; see Git Diff Review) |
| **Scope** | `libs/adapters/fake_store/*`, `tests/test_adapters/test_fake_store_adapter.py`, `requirements*.txt` |
| **Verdict** | **CHANGES REQUIRED** |

---

## 1. Summary

The Fake Store adapter is a clean, type-safe implementation of `SourceAdapterProtocol`
that maps valid products into canonical `ProductObservationEvent` instances correctly.
Valid-record mapping, source-identity preservation, deterministic event IDs, and
canonical-field isolation are all sound, and the static checks are green.

However, the adapter does **not** satisfy the protocol's malformed-record contract:
the HTTP client silently discards records that fail source-model validation, so
`FetchResult.malformed` can never contain source-level malformed records. This is a
direct violation of TASK-034 protocol invariant #4 and of the TASK-035 requirement to
"handle … malformed … responses explicitly." The test suite masks this because it
mocks the client at the adapter layer, so the client's own error/parsing logic (where
the malformed handling and HTTP-error mapping live) is never exercised.

---

## 2. Requirements Coverage

| Requirement | Status | Evidence |
|---|---|---|
| Typed HTTP client/response models | ✅ Met | `models.py` (`FakeStoreProduct`, `FakeStoreRating`, `extra="forbid"`), `client.py` (`FakeStoreClient`) |
| Map source records into canonical event boundary | ✅ Met | `adapter.py` uses `SourceAdapterProtocol._build_event` |
| Preserve source-level external identity | ✅ Met | `external_id=str(product.id)`; verified by tests |
| Handle price/category/availability/timestamps per canonical rules | ⚠️ Partial | availability/category/timestamps correct; **price is non-nullable** (`models.py:26`) despite canonical `price: Decimal \| None` |
| Handle timeout, HTTP error, malformed, empty responses explicitly | ⚠️ Partial | timeout/HTTP/empty handled in `client.py`; **malformed records are silently dropped** (`client.py:93-95`) |
| Keep source-specific fields inside adapter boundary | ✅ Met | `test_no_source_specific_fields_leak` verifies no `rating`/`image`/`description` leak |
| CI tests use deterministic mocks/fixtures (no live service) | ✅ Met (mock level) | All tests use mocks; **but mocks target the adapter, not the client** (see §4) |

### Tests required by the task

| Test | Status | Notes |
|---|---|---|
| Representative product mapping | ✅ | `test_map_single_product` |
| Multiple records | ✅ | `test_fetch_multiple_products` |
| Nullable fields | ⚠️ Partial | image/rating null covered; **null price not covered** (model forbids it) |
| Malformed upstream record | ❌ Not genuinely tested | `test_malformed_record_separated` never uses `malformed_product_dict` and asserts `malformed == 0` |
| HTTP timeout/error | ⚠️ Partial | Tests assert the adapter re-raises a pre-built `SourceFetchError`; the client's httpx→`SourceFetchError` mapping is never exercised |
| Empty source response | ✅ | `test_empty_list_returns_empty_events` |
| Canonical event compatibility | ✅ | `TestCanonicalCompatibility` |

### Acceptance criterion

> Fake Store data can be converted into canonical observation events with no downstream source-specific code.

✅ Satisfied for **valid** records. The criterion is met for the happy path, but the
malformed-record path does not meet the underlying contract (see Finding 1).

---

## 3. Git Diff Review

- **Scope of the TASK-035 commit (`7a90965`):** Correct. It touches only
  `libs/adapters/fake_store/*`, the two requirement files, and
  `tests/test_adapters/test_fake_store_adapter.py`. No unrelated application code.
- **Dependencies:** `httpx>=0.27,<1` (runtime) and `pytest-asyncio>=0.24` (dev) are
  reasonable and correctly scoped. `pytest-asyncio` is actually used
  (`@pytest.mark.asyncio`), and `httpx` is imported by the client.
- **No secrets/debug artifacts:** None introduced. `fakestoreapi.com` is a public URL;
  no credentials are committed.
- **Branch isolation (process finding):** `feature/TASK-035` HEAD is `b38f711`, the
  **TASK-036 (Best Buy)** commit, stacked on top of `7a90965`. The branch therefore
  contains both TASK-035 and TASK-036 changes. The TASK-035 commit itself is cleanly
  isolated, but the branch is not. Per `ai/AGENTS.md` §16 and `ai/REVIEWER.md`, this is
  reported as a process/scope finding (see Finding 6).

---

## 4. Test and Verification Review

### Independently executed by the reviewer

| Command | Result |
|---|---|
| `python -m pytest tests/test_adapters/test_fake_store_adapter.py -v` | **18 passed** (Python 3.14, pytest 9.0.2, asyncio mode STRICT) |
| `python -m ruff check libs/adapters/fake_store tests/test_adapters/test_fake_store_adapter.py` | **All checks passed** |
| `python -m mypy libs/adapters/fake_store` | **Success: no issues in 4 source files** |

Verification status: **Independently verified** (static checks and unit tests above).

### Coverage gap

All 18 tests patch `libs.adapters.fake_store.adapter.FakeStoreClient` and replace
`fetch_products` with an `AsyncMock`. Consequently:

- The client's `httpx.TimeoutException` / `httpx.HTTPStatusError` / `httpx.RequestError`
  → `SourceFetchError` mapping is **never tested**.
- The invalid-JSON and non-list-response branches in `client.py` are **never tested**.
- The per-record `FakeStoreProduct.model_validate` failure path is **never tested**.

The "HTTP timeout/error" tests inject a pre-constructed `SourceFetchError` via
`side_effect`, which only proves the adapter re-raises an exception it was already
given — not that the client correctly translates `httpx` exceptions.

---

## 5. Findings

### F1 — High — Malformed source records are silently discarded

- **File:** `libs/adapters/fake_store/client.py:91-95`
- **Problem:** In `fetch_products`, each raw item is validated with
  `FakeStoreProduct.model_validate(item)`; on any failure the code executes
  `except Exception: pass` (comment says "Log but continue", but nothing is logged and
  the record is dropped). These records never reach `FetchResult.malformed`.
- **Impact:**
  1. Violates TASK-034 protocol invariant #4 — a fetch of *only* malformed records
     returns empty `events` **and** empty `malformed` with `total_records == 0`,
     indistinguishable from a genuinely empty source.
  2. Data loss: malformed records cannot be routed to a DLQ/invalid path.
  3. `total_records=len(products)` (`adapter.py:102`) undercounts, because `products`
     already excludes the dropped records — contradicting the protocol's
     "total records received before filtering" semantics.
- **Recommendation:** Have the client return (or separately surface) records that fail
  validation, and have the adapter populate `FetchResult.malformed` with them plus a
  diagnostic reason. Use the protocol's `MalformedRecordError` rather than a bare
  `except Exception`.

### F2 — High — `FakeStoreClient` error/parsing logic is untested

- **File:** `tests/test_adapters/test_fake_store_adapter.py` (all 18 tests)
- **Problem:** Every test patches the client at the adapter layer; no test drives
  `FakeStoreClient.fetch_products` directly. The task's required "HTTP timeout/error"
  and "malformed upstream record" tests therefore do not exercise the code that
  implements those behaviors. This gap is what allowed F1 to go unnoticed.
- **Impact:** The client's exception mapping, JSON/non-list handling, and per-record
  validation (the "explicit error handling" the task requires) are unverified.
- **Recommendation:** Add direct `FakeStoreClient` tests using `httpx.MockTransport`
  (or a mocked `AsyncClient`) covering: timeout → `SourceFetchError`, 4xx/5xx →
  `SourceFetchError`, invalid JSON → `SourceFetchError`, non-list → `SourceFetchError`,
  and a batch containing a malformed record.

### F3 — Moderate — `price` is non-nullable, contradicting the canonical contract

- **File:** `libs/adapters/fake_store/models.py:26`
- **Problem:** `price: float = Field(...)` is required, but the canonical
  `ProductObservationPayload.price` is `Decimal | None` ("null when the source does not
  provide a usable price"). A record with `price: null` fails source validation and is
  dropped (compounding F1). The adapter's guard
  `product.price if product.price is not None else None` (`adapter.py:86`) is dead code.
- **Impact:** The adapter cannot emit a null-price observation, which the canonical
  contract explicitly supports and the "nullable fields" test requirement implies.
- **Recommendation:** Model `price` as `Optional[float]`, and add a null-price test.

### F4 — Minor — Dead/misleading try-except in `FakeStoreAdapter.fetch`

- **File:** `libs/adapters/fake_store/adapter.py:70-74`
- **Problem:** `try: … except Exception: raise` is a no-op. The comment says
  "wrap unexpected exceptions" but nothing is wrapped.
- **Recommendation:** Remove the block, or actually wrap unexpected exceptions into
  `SourceFetchError`.

### F5 — Minor — Malformed entries carry no diagnostic reason

- **File:** `libs/adapters/fake_store/adapter.py:95`
- **Problem:** `malformed.append(product.model_dump())` stores only the raw dump. The
  `FetchResult.malformed` contract documents that each entry contains the original
  record **plus a diagnostic message**; the protocol-provided `MalformedRecordError`
  is unused.
- **Recommendation:** Include a `reason` alongside the raw record.

### F6 — Minor (process) — Branch contains out-of-scope TASK-036 commit

- **File:** n/a (git topology)
- **Problem:** `feature/TASK-035` HEAD is `b38f711` (`feat(adapter): Implement Best Buy
  API source adapter (TASK-036)`), so the branch includes TASK-036 changes. The
  TASK-035 commit `7a90965` itself is cleanly scoped, but the branch is not isolated to
  TASK-035.
- **Recommendation:** Confirm intended branch topology; TASK-035 review scope is
  `7a90965` only.

---

## 6. Non-Defect Observations

1. **`SourceFetchError` has no `retryable` field.** The TASK-034 protocol's
   `SourceFetchError` carries only `message` and `source`, so the adapter cannot
   distinguish retryable (timeout/5xx) from non-retryable (4xx) failures except through
   the message string. This is a protocol-level limitation, not a TASK-035 defect, but
   downstream retry logic should not expect a `retryable` attribute.
2. **Hardcoded product URL.** `adapter.py` constructs
   `https://fakestoreapi.com/products/{id}` even when a different `base_url` is
   supplied. Harmless in production, but the URL should ideally be derived from the
   configured base URL so injected/test clients stay consistent.
3. **`FakeStoreClient._get_client` lazy initialization** creates the `httpx.AsyncClient`
   on first use and relies on the caller to invoke `close()`. This is acceptable given
   the adapter's `close()`, but an unclosed client would leak if `close()` is never
   called.
4. The positive-path mapping is solid: deterministic event IDs, timezone-aware UTC
   timestamps, `currency="USD"`, and correct `Availability("in_stock")` defaulting for a
   source that provides no availability data.

---

## 7. Verdict

**CHANGES REQUIRED**

The valid-record mapping is correct and well-tested, and static checks are green, but
the implementation does not meet the malformed-record contract. Silently discarding
malformed records (F1) violates TASK-034 protocol invariant #4 and the TASK-035
requirement to handle malformed responses explicitly; it also loses data and
undercounts `total_records`. This is masked by a test suite that mocks at the wrong
layer (F2), leaving the client's error/parsing logic untested.

Before acceptance, address at minimum:

- **F1** — capture malformed records into `FetchResult.malformed` instead of dropping them.
- **F2** — add direct `FakeStoreClient` tests covering the timeout/HTTP/JSON/non-list/malformed paths.

Strongly recommended:

- **F3** — make `price` nullable to match the canonical contract.
- **F4/F5** — clean up the dead try-except and add a diagnostic reason to malformed entries.
