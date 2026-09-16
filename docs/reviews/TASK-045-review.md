# TASK-045 Review Report

## 1. Review Header

- **Task ID:** TASK-045 — eBay Integration Tests
- **Review date:** 2026-09-16
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed commit:** `a9d9c6c1b86192733d51ee2a16d06ffd65158719` (`feat(TASK-045): Add eBay integration tests covering full ingestion pipeline`)
- **Reviewed change set:** `3df127c09033366e0344106edeffba5043a2d232...a9d9c6c1b86192733d51ee2a16d06ffd65158719` on `feature/TASK-045` (1 commit, 1 file)
- **Scope:** Full TASK-045 implementation — a single new test file `tests/test_ebay_integration.py` (+692 insertions)
- **Verdict:** `CHANGES REQUIRED`

---

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
|---|---|---|
| Keep source-specific structures behind the adapter/normalization boundary | ✅ Met | Tests construct `EbayListingSummary`/`EbaySearchResponse` behind the adapter and assert canonical `ProductObservationEvent` output only. |
| Preserve stable source, listing/product, event, and timestamp identity | ⚠️ Partial | Source identity (`event.source == "ebay"`) and `external_id` are asserted; **listing/seller identity is not** — see F3. |
| Use typed Python, explicit configuration, deterministic tests, existing conventions | ✅ Met | Typed helpers/fixtures; `ruff`/`mypy` pass on the file (independently verified). |
| Consider retries, replay, duplicates, partial failure, idempotency | ⚠️ Partial | Error isolation, empty response, and two-cycle determinism are covered; **idempotency/deduplication is not** — see F4. |
| Never commit or log credentials | ✅ Met | No credentials, secrets, or logging introduced; tests use mocks/`MagicMock`. |
| Do not begin later roadmap tasks | ✅ Met | Only a test file added; no application/library changes. |
| Escalate if a fundamental incompatible canonical model / schema change is required | ✅ N/A | No canonical/warehouse change attempted. |

### Task-specific scope & acceptance criteria

| Criterion | Status | Evidence |
|---|---|---|
| Integration tests from mocked eBay responses through adapter, marketplace normalization, canonical ingestion, Kafka, processor, Parquet, and PostgreSQL | ❌ Not met | Tests stop at the **mock Kafka producer** (`MockProducer`). Marketplace normalization, processor, Parquet, and PostgreSQL boundaries are not exercised (F2, F3). |
| Cover multiple sellers/listings | ✅ Met | `test_multiple_listings_from_different_sellers`, `test_all_three_sources_in_one_cycle`. |
| Cover replay, repeated observations, ambiguity, malformed input | ✅ Met (except idempotency) | Replay determinism (`TestReplayIdempotency`), malformed (`TestMalformedInput`), ambiguity (`TestAmbiguity`). |
| Regression smoke tests for existing sources | ✅ Met | `TestRegressionSmoke` runs fake_store + best_buy + ebay together and checks no source-specific field leakage. |
| Acceptance: demonstrate **multiple marketplace listings for one logical product** | ❌ Not met | No test maps two listings to one logical product (F1). |
| Acceptance: **final stored state** asserted | ❌ Not met | No processor/Parquet/PostgreSQL output is asserted (F2). |
| Acceptance: replay/idempotency asserted | ⚠️ Partial | Replay determinism asserted; idempotency is not (F4). |
| Acceptance: tests need no live eBay credentials | ✅ Met | Fully mocked (`AsyncMock` client). |
| Acceptance: pass repository quality checks | ✅ Met | `pytest`, `ruff`, `mypy` all pass on the new file (independently verified). |

---

## 3. Git Diff Review

- **Scope correctness:** ✅ Correct. The range contains a single new file, `tests/test_ebay_integration.py` (+692, 0 deletions). No application/library code touched.
- **Unrelated changes:** ✅ None.
- **Architectural changes:** ✅ None. No service boundaries, event contracts, Kafka semantics, data-lake, or warehouse schema changes.
- **Accidental/debug/temporary/secret content:** ✅ None. No debug prints, dead/generated files, or secrets.
- **Dependency/config changes:** ✅ None. `pyproject.toml`, requirements, CI, and infrastructure untouched. All imports resolve to existing modules.
- **Test weakening:** ✅ None. Only additions; no existing test deleted or relaxed.
- **Branch/task isolation:** ✅ Correct. Reviewed HEAD `a9d9c6c` is on `feature/TASK-045`; the range contains only the single TASK-045 commit and no TASK-044/other-task changes.

---

## 4. Test and Verification Review

### Tests examined
`tests/test_ebay_integration.py` (16 tests) covering:
- single listing → one canonical event; source/external_id/name/price/currency assertions
- three listings from three different sellers
- partition key format (`ebay:<external_id>`)
- two-cycle replay determinism (same external IDs, same prices/currency)
- client-level malformed records tracked in `runner.stats`
- all-listings-malformed → zero events (`model_construct` to trigger mapping failure)
- eBay failure does not block fake_store (error isolation)
- empty eBay response → zero events, zero errors
- ambiguity: no price, no seller, no category, out-of-stock
- regression smoke: fake_store + best_buy + ebay in one cycle
- no eBay-specific fields leak into the canonical payload
- multiple fetch cycles accumulate events

### Test adequacy
The adapter-mapping and failure-isolation coverage is solid and correctly exercises the `EbayAdapter` → `IngestionRunner` wiring. However, the tests are **not actually integration tests** in the sense the task requires: every test stops at `mock_producer.published` (the raw topic). The processor, Parquet, and PostgreSQL boundaries named in the task's own Task-Specific Scope are absent, and the central Milestone 5A scenario ("multiple marketplace listings for one logical product") is not represented at all.

### Verification status

| Check | Result | Classification |
|---|---|---|
| `python -m pytest tests/test_ebay_integration.py -q` | ✅ 16 passed (2.24s) | **Independently verified** |
| `python -m ruff check tests/test_ebay_integration.py` | ✅ All checks passed | **Independently verified** |
| `python -m ruff format --check tests/test_ebay_integration.py` | ✅ 1 file already formatted | **Independently verified** |
| `python -m mypy tests/test_ebay_integration.py` | ✅ Success: no issues found in 1 source file | **Independently verified** |
| `python -m pytest -q` (full default suite) | ⏱️ Timed out after 7 minutes (no result) | **Unverified** — only the new file was fully verified |
| `python -m pytest -m integration` | Not run — the new file contains **no `integration`-marked tests** | **Absent** — see F5 |

### Integration-test deselection note
Per REVIEWER.md, the default pytest configuration excludes `integration`-marked tests (`addopts = "-m 'not integration'"`). The task scope explicitly names processor, Parquet, and PostgreSQL boundaries. **No test in the new file carries `@pytest.mark.integration`**, so there are no integration tests to run or inspect — the "integration" in the filename is misleading relative to the task's own scope (F5).

---

## 5. Findings

### F1 — The core Milestone 5A acceptance ("multiple marketplace listings for one logical product") is not tested (High)
- **File:** `tests/test_ebay_integration.py` (class `TestEbayIngestion`)
- **Problem:** The closest test, `test_multiple_listings_from_different_sellers`, creates three **different** products (`Product A/B/C`) from three **different** sellers and asserts only that three events are published. There is no test that maps two or more listings to a **single logical product** — via a shared `listing_id`/`seller_id`/product key/GTIN — and asserts they resolve to one logical identity. This is the exact scenario Milestone 5A exists to demonstrate, and TASK-045's acceptance criterion names it first.
- **Impact:** The entire point of the marketplace source milestone is unverified. Without this test, there is no evidence the platform "represents multiple marketplace listings for one logical product without breaking the canonical pipeline."
- **Recommendation:** Add a test with at least two listings sharing one logical product identity (e.g. same GTIN/UPC, or a `ListingProductMapper` assigning both `qualified_id`s to one `product_key`) and assert the canonical events preserve `listing_id`/`seller_id` and group correctly.

### F2 — Acceptance criterion "final stored state ... asserted" is unmet; processor/Parquet/PostgreSQL boundaries are absent (High)
- **File:** `tests/test_ebay_integration.py` (entire file)
- **Problem:** Every test asserts only `mock_producer.published` (raw-topic events). None exercise the processor, Parquet, or PostgreSQL layers. The processor boundary is supportable **in-memory without Docker** — `tests/test_pipeline_e2e.py` already demonstrates `ProcessorPipeline` + `DeduplicationState` with tracking sinks — and Parquet/PostgreSQL are supportable behind the `integration` marker (existing `tests/test_silver_writer_integration.py`, `tests/test_datalake_integration.py`, `tests/warehouse/*`).
- **Impact:** The acceptance criterion "final stored state … asserted" is not satisfied. The task's own Task-Specific Scope ("through … processor, Parquet, and PostgreSQL where the established test infrastructure supports those boundaries") is only one-third exercised.
- **Recommendation:** Extend at least the happy path through `ProcessorPipeline` (raw → validated), asserting deduplication and the validated payload; add `@pytest.mark.integration` tests that assert Silver/Bronze Parquet and/or PostgreSQL stored state for eBay listings, mirroring existing integration patterns.

### F3 — Marketplace normalization/identity mapping is not exercised; eBay events carry `listing_id=None` / `seller_id=None` (High)
- **File:** `tests/test_ebay_integration.py` (`test_ebay_does_not_leak_source_specific_fields`); related `libs/adapters/ebay/adapter.py` `_map_listing_to_event`
- **Problem:** The task scope explicitly names "marketplace normalization", and the prior TASK-044 review (N2) flagged that "TASK-045 is the natural place to wire and exercise [the marketplace helpers] end to end." The new tests never import `libs/adapters/ebay/normalizer.py` or `libs/marketplace/*`. Worse, `test_ebay_does_not_leak_source_specific_fields` asserts the canonical payload keys include `listing_id` and `seller_id` but **never asserts they are populated** — codifying the adapter's current behavior, which emits both as `None` (`_build_event` defaults). eBay is a marketplace source; TASK-041 required "preserve listing/item and seller identifiers needed downstream."
- **Impact:** The marketplace identity capability built in TASK-042/043/044 is disconnected from the ingestion path, and the integration test suite silently endorses that disconnection. The "multiple listings for one logical product" requirement cannot be met while listing/seller identity is dropped.
- **Recommendation:** Add tests asserting `payload.listing_id == "ebay:<item_id>"` and `payload.seller_id == "ebay:<username>"` for a listing that has a seller. If the adapter does not populate these, the test will fail and correctly surface the adapter gap (which is itself the missing wiring from TASK-041 → TASK-042/044).

### F4 — "Replay idempotency" tests assert determinism, not idempotency (Moderate)
- **File:** `tests/test_ebay_integration.py` (class `TestReplayIdempotency`)
- **Problem:** `test_same_input_produces_same_external_ids` and `test_same_input_produces_same_prices` verify that two fetch cycles produce the same `external_id` set and the same price/currency. This is **re-emission determinism**, not idempotency. There is no assertion of deduplication by `event_id`, no `UNIQUE(event_id)` enforcement, and no final-state check. Notably, `event_id` is itself **non-deterministic across replays** because the adapter sets `collected_at = datetime.now(timezone.utc)` per cycle (and `_build_event` derives `event_id` from `collected_at`), so the tests deliberately avoid comparing `event_id`.
- **Impact:** The acceptance criterion "replay/idempotency are asserted" is only partially satisfied. Downstream deduplication (the actual idempotency guarantee) is untested.
- **Recommendation:** Route replayed events through `ProcessorPipeline` with a shared `DeduplicationState` (or assert the warehouse `UNIQUE(event_id)` constraint) to demonstrate that a duplicate observation does not produce a duplicate logical record. Document the `event_id`/`collected_at` non-determinism explicitly.

### F5 — File is named "integration" but contains no `@pytest.mark.integration` tests (Moderate)
- **File:** `tests/test_ebay_integration.py`; `pyproject.toml` (`addopts = "-m 'not integration'"`)
- **Problem:** All 16 tests are marked `@pytest.mark.asyncio` and run in the default hermetic suite; none is marked `integration`. Per REVIEWER.md, the reviewer must verify integration tests were executed rather than deselected — here there are no integration tests to execute. The filename promises integration coverage that the task's scope (Kafka/processor/Parquet/PostgreSQL) requires but the file does not deliver.
- **Impact:** Misleading naming; the repository's integration-test convention is not followed, and the genuine infrastructure-boundary coverage the task calls for is absent.
- **Recommendation:** Either mark the Parquet/PostgreSQL/Kafka-boundary tests `@pytest.mark.integration` (and run `python -m pytest -m integration`), or rename the file to reflect that it is currently a hermetic adapter/runner wiring test.

### F6 — Minor typing/style smells in the test helpers (Minor)
- **File:** `tests/test_ebay_integration.py` (`_make_listing`, `test_same_input_produces_same_prices`)
- **Problem:** `category_ids: list[str] | None | object = _UNSET` collapses the type to `object` (forcing `# type: ignore[assignment]`); a dedicated sentinel type or an explicit `None` default with a separate "unset" convention would be clearer. Also `from decimal import Decimal` is imported inside `test_same_input_produces_same_prices` rather than at module top, inconsistent with the file's other top-level imports.
- **Impact:** Cosmetic; no functional or correctness effect.
- **Recommendation:** Use a module-level sentinel object typed appropriately, and hoist the `decimal` import to the top of the file.

---

## 6. Non-Defect Observations

- **N1 — Adapter mapping coverage is otherwise good.** The tests correctly exercise malformed input (`model_construct` to force mapping failure), empty responses, missing price/seller/category, out-of-stock, error isolation, and cross-source coexistence. These portions are correct and pass.
- **N2 — The underlying adapter gap predates TASK-045.** The eBay adapter emitting `listing_id=None`/`seller_id=None` originates from TASK-041 (which did not populate the fields added in TASK-042/044). TASK-045 was the expected point to surface this (per TASK-044 review N2), but the tests instead enshrine the absence rather than exposing it.
- **N3 — Redundant monkeypatch in `test_ebay_failure_does_not_block_other_sources`.** It patches `libs.adapters.fake_store.adapter.FakeStoreClient` and then constructs `FakeStoreAdapter(client=mock_fs_client)` directly, so the patch is unused. Harmless but misleading.
- **N4 — Full default suite not fully verified.** The reviewer's `python -m pytest -q` run timed out after 7 minutes; only the new file was verified end-to-end. No regression is expected (the change is purely additive), but the full-suite result is not independently confirmed.
- **N5 — `test_all_listings_malformed_produces_no_events` uses `model_construct` bypass.** This is the correct technique to inject a validation-breaking record, but it relies on `name=None` being the failure trigger; a comment already documents the intent.

---

## 7. Verdict

**`CHANGES REQUIRED`**

The diff is correctly scoped (a single additive test file, no application/library changes, no secrets, clean ruff/mypy/pytest on that file), and the adapter-mapping/error-isolation coverage that is present is correct. However, the tests do not satisfy two of the four explicit acceptance criteria:

1. **"Multiple marketplace listings for one logical product"** is not demonstrated at all (F1) — this is the entire point of Milestone 5A.
2. **"Final stored state … asserted"** is not met — no processor, Parquet, or PostgreSQL boundary is exercised (F2).

In addition, the marketplace normalization/identity-mapping layer is neither exercised nor wired into the assertions, and the eBay canonical events' `listing_id`/`seller_id` remain `None` unexamined (F3). The "replay/idempotency" tests assert only determinism, not idempotency (F4), and the file contains no `@pytest.mark.integration` tests despite the filename and scope (F5).

Blocking findings: **F1, F2, F3**. These must be addressed before acceptance: add a same-product multi-listing test, extend the happy path through the processor (and Parquet/PostgreSQL behind the `integration` marker) to assert final stored state, and assert populated `listing_id`/`seller_id` (or fix the adapter so they are populated).

The reviewer did not modify any code.
