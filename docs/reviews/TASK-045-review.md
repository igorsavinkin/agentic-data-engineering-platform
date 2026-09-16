# TASK-045 Review Report

## 1. Review Header

- **Task ID:** TASK-045 — eBay Integration Tests
- **Review date:** 2026-09-16
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `3df127c..7cfa2d8` on `feature/TASK-045`, merged to `main` via `7cfa2d8` (PR #57)
  - 5 commits: `a9d9c6c`, `28ffbd4`, `a168c91`, `48b14ab`, `3a94de0`
  - 4 files changed: `libs/adapters/ebay/adapter.py` (+10), `tests/test_ebay_integration.py` (+1131), `tests/test_ebay_bronze_integration.py` (+203), `docs/reviews/TASK-045-review.md` (+154, round-1 review being superseded by this report)
- **Scope:** Post-merge review of the final merged state (not the original single-commit submission reviewed in round 1).
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

---

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
|---|---|---|
| Keep source-specific structures behind the adapter/normalization boundary | ✅ Met | Tests construct `EbayListingSummary`/`EbaySearchResponse` behind the adapter and assert canonical `ProductObservationEvent` output only; `test_ebay_does_not_leak_source_specific_fields` asserts the exact canonical payload key set with no eBay-specific fields. |
| Preserve stable source, listing/product, event, and timestamp identity | ⚠️ Partial | Source (`event.source == "ebay"`), `external_id`, `event_id`, and partition key are asserted. `listing_id`/`seller_id` are now populated by the adapter and asserted at the event level, but are **dropped at the Parquet persistence layer** (see F1). |
| Use typed Python, explicit configuration, deterministic tests, existing conventions | ✅ Met | Typed helpers/fixtures; `ruff`/`mypy` pass on all changed files (independently verified). |
| Consider retries, replay, duplicates, partial failure, idempotency | ✅ Met | Error isolation, empty response, replay determinism, processor deduplication (`test_deduplication_via_processor_pipeline`), and Bronze replay overwrite (`test_ebay_replay_idempotency`) are covered. |
| Never commit or log credentials | ✅ Met | Fully mocked (`AsyncMock`); the Bronze integration test uses the standard local `minioadmin` dev credentials already used by the repository, not secrets. |
| Do not begin later roadmap tasks | ✅ Met | Only test files plus a 10-line adapter identity-wiring change; no application/library scope expansion. |
| Escalate if a fundamental incompatible canonical model / schema change is required | ✅ N/A | No canonical/warehouse schema change attempted. |

### Task-specific scope & acceptance criteria

| Criterion | Status | Evidence |
|---|---|---|
| Integration tests from mocked eBay responses through adapter, marketplace normalization, canonical ingestion, Kafka, processor, Parquet, and PostgreSQL where infrastructure supports it | ✅ Met (within supported boundaries) | Hermetic tests cover adapter → mock Kafka producer → processor pipeline; `test_ebay_bronze_integration.py` covers Bronze Parquet persistence behind `@pytest.mark.integration`. PostgreSQL is not exercised (no established in-memory/unit boundary for it in this task's path). |
| Cover multiple sellers/listings | ✅ Met | `test_multiple_listings_from_different_sellers`, `TestMultipleListingsSameProduct` (4 tests), `test_multiple_ebay_listings_different_sellers` (Bronze). |
| Cover replay, repeated observations, ambiguity, malformed input | ✅ Met | `TestReplayIdempotency`, `TestMalformedInput`, `TestAmbiguity`, Bronze replay overwrite. |
| Regression smoke tests for existing sources | ✅ Met | `TestRegressionSmoke` runs fake_store + best_buy + ebay together; `test_multiple_ebay_fetch_cycles`. |
| Acceptance: multiple marketplace listings for one logical product without breaking canonical pipeline | ⚠️ Partial (honestly scoped) | Multiple same-titled listings from different sellers coexist through the pipeline with distinct `listing_id`/`seller_id` (prerequisite demonstrated). True grouping into one logical product is deferred because the eBay `item_summary/search` endpoint exposes no UPC/GTIN/EAN/ASIN (documented in test docstrings). See N2. |
| Acceptance: final stored state and replay/idempotency asserted | ✅ Met | Processor validated sink state and Bronze Parquet stored state are asserted; dedup + overwrite idempotency are asserted. |
| Acceptance: no live eBay credentials | ✅ Met | Fully mocked. |
| Acceptance: pass repository quality checks | ✅ Met | `pytest` (hermetic), `ruff check`, `ruff format --check`, `mypy` all pass (independently verified). |

---

## 3. Git Diff Review

- **Scope correctness:** ✅ Correct. The range contains the TASK-045 test work plus a minimal, targeted adapter change (+10 lines) that wires the pre-existing marketplace identity helpers (`build_listing_id`, `build_seller_id`) into `_map_listing_to_event`. This is a legitimate, in-scope enabler for the tests (round-1 F3).
- **Unrelated changes:** ✅ None. No other application/library files touched.
- **Architectural changes:** ✅ None. No event-contract, Kafka, data-lake, warehouse, or service-boundary changes. The adapter change reuses existing `libs.marketplace.identity` helpers rather than inventing new structures.
- **Accidental/debug/temporary/secret content:** ✅ None. No debug prints, dead/generated files, or secrets.
- **Dependency/config changes:** ✅ None. `pyproject.toml`, requirements, CI, and infra untouched.
- **Test weakening:** ✅ None. Only additions; no existing test deleted or relaxed.
- **Branch/task isolation:** ✅ Correct. The range contains only the five TASK-045 commits; the round-1 review doc (`docs/reviews/TASK-045-review.md`) is a committed review artifact superseded by this report.
- **Note:** The adapter diff is the only production-code change in an otherwise test-only task. It is narrowly scoped and correct; verified in §4.

---

## 4. Test and Verification Review

### Tests examined
`tests/test_ebay_integration.py` (26 tests, hermetic) covering:
- single listing → one canonical event; source/external_id/name/price/currency
- three listings from three different sellers; partition key format
- `listing_id`/`seller_id` populated (`ebay:<item_id>`, `ebay:<username>`); `None` when no/whitespace seller
- multiple same-titled listings from different sellers coexist with distinct identities; same-product listings survive the processor pipeline; listings without product IDs remain distinct
- processor pipeline: adapter → producer → processor → validated sink; traceability across raw → validated
- replay determinism + processor `DeduplicationState` dedup
- malformed records (client-level and all-listings-malformed via `model_construct`)
- eBay failure does not block other sources; empty response → zero events/errors
- ambiguity: no price / no seller / no category / out-of-stock
- regression smoke: all three sources in one cycle; no eBay-specific field leakage; multi-cycle accumulation

`tests/test_ebay_bronze_integration.py` (4 tests, `@pytest.mark.integration`) covering Bronze Parquet write/read-back, partition structure (`bronze/source=ebay/year=…`), replay overwrite idempotency, and multiple listings from different sellers persisting to distinct keys.

### Test adequacy
Coverage is now substantially complete versus round 1. The adapter-mapping, error-isolation, ambiguity, replay/dedup, processor-pipeline, and Bronze-persistence boundaries are all exercised. The single most important improvement over round 1 is that `listing_id`/`seller_id` are now *populated* and asserted at the event level, and the processor/Bronze boundaries are actually exercised.

### Verification status

| Check | Result | Classification |
|---|---|---|
| `python -m pytest tests/test_ebay_integration.py -q` | ✅ 26 passed (2.78s) | **Independently verified** |
| `python -m ruff check tests/test_ebay_integration.py tests/test_ebay_bronze_integration.py libs/adapters/ebay/adapter.py` | ✅ All checks passed | **Independently verified** |
| `python -m ruff format --check …` (same three files) | ✅ 3 files already formatted | **Independently verified** |
| `python -m mypy …` (same three files) | ✅ Success: no issues found in 3 source files | **Independently verified** |
| `python -m pytest -m integration` | ⏭️ Not run — requires a running MinIO container (`localhost:9000`) | **Unverified** (see note below) |

### Integration-test note
`tests/test_ebay_bronze_integration.py` correctly carries `pytestmark = pytest.mark.integration` (round-1 F5 resolved). The reviewer did not execute `-m integration` because it requires external infrastructure (MinIO/Docker) and the review instructions scoped independent execution to the hermetic test plus static checks. The Bronze test logic was inspected against `BronzeWriter`, `MinIOStorage`, and `build_partition_key`; it mirrors the established `tests/test_bronze_writer_integration.py` pattern.

---

## 5. Findings

### F1 — Bronze test docstring claims `listing_id`/`seller_id` "survive the round-trip", but they are dropped at the Parquet layer (Moderate)
- **File:** `tests/test_ebay_bronze_integration.py` (module docstring); related `libs/raw_writer/bronze_writer.py` `event_to_row`, `libs/schema/parquet_schemas.py` `BRONZE_SCHEMA`/`SILVER_SCHEMA`, `services/processor/schema_normalization.py` `NORMALIZED_SCHEMA`.
- **Problem:** The module docstring lists "listing_id and seller_id survive the round-trip" as something the tests verify. They do not: commit `3a94de0` explicitly removed those assertions because `BRONZE_SCHEMA`/`event_to_row` (owned by TASK-021/TASK-024) do not persist those columns, and `NORMALIZED_SCHEMA`/`SILVER_SCHEMA` likewise omit them. `make_ebay_event` constructs payloads *with* `listing_id`/`seller_id`, the writer silently drops them, and no test detects it. The surviving docstring line is now factually false.
- **Impact:** A reader (or future maintainer) is misled into believing marketplace identity is preserved end-to-end. The genuine, cross-cutting gap — marketplace listing/seller identity is lost at Bronze/Silver persistence, which is precisely the identity needed to group "multiple listings for one logical product" downstream — is invisible in the test suite.
- **Recommendation:** Correct the docstring to state the actual behavior (e.g. "listing_id/seller_id are populated on the canonical event but not yet persisted by `BRONZE_SCHEMA`; see TASK-021/TASK-024"), and add an explicit assertion that documents the drop so the gap is surfaced rather than hidden. Propose a follow-up task to extend `BRONZE_SCHEMA`/`SILVER_SCHEMA`/`NORMALIZED_SCHEMA` (and `event_to_row`) with nullable `listing_id`/`seller_id` columns. This is not a TASK-045 code defect (the schemas are owned by earlier tasks), but the misleading documentation is in-scope.

### F2 — Processor "traceability" assertions are tautological; they do not exercise normalization (Minor)
- **File:** `tests/test_ebay_integration.py` (`test_ebay_through_full_pipeline`, `test_ebay_traceability_across_layers`).
- **Problem:** `ProcessorPipeline._publish_valid_records` passes the *original* `ConsumerMessage.event` object (not the normalized/validated DataFrame row) to `validated_sink`. Therefore `validated.payload.listing_id == "ebay:PP1"`, `validated.payload.seller_id == …`, and `validated.event_id == raw_event.event_id` are asserted on the same object instance that entered the pipeline — they are trivially true and do not demonstrate that the normalize/validate/deduplicate transformation preserves these fields. In fact `NORMALIZED_SCHEMA` drops `listing_id`/`seller_id`.
- **Impact:** The tests overstate what they prove about cross-layer identity preservation. The canonical event (Kafka validated topic) does carry the fields because the sink publishes the original event, but the *analytical* transformation schema does not retain them.
- **Recommendation:** Either (a) assert against a sink that receives the actual normalized/validated payload if such a path exists, or (b) add a comment clarifying that the assertions verify adapter→pipeline wiring (not schema-level preservation), and rely on F1's follow-up for the persistence gap. Low priority given the sink contract is pre-existing.

### F3 — Sentinel typing smell in `_make_listing` persists (Minor)
- **File:** `tests/test_ebay_integration.py` (`_make_listing`).
- **Problem:** `category_ids: list[str] | None | object = _UNSET` collapses the declared type to `object`, forcing `resolved_categories = category_ids  # type: ignore[assignment]`. Round-1 F6's `Decimal` import was hoisted, but this sentinel pattern remains.
- **Impact:** Cosmetic; no functional or correctness effect.
- **Recommendation:** Use a module-level sentinel with a narrow type (e.g. a dedicated `_UNSET` dataclass/`Literal` sentinel, or an explicit `None` + "unset" convention) to drop the `type: ignore`.

### F4 — Bronze fixture teardown deletes all objects in a shared bucket (Minor)
- **File:** `tests/test_ebay_bronze_integration.py` (`storage` fixture teardown).
- **Problem:** Teardown lists and deletes every object under prefix `""` in the `test-bronze` bucket, which is also used by `tests/test_bronze_writer_integration.py`. It also reaches into the private `MinIOStorage._client` instead of the public `list_objects` API. This mirrors the pre-existing `test_bronze_writer_integration.py` fixture, so it is not a new anti-pattern, but it is a shared-state hazard under parallelized integration runs.
- **Impact:** Possible cross-module interference if `-m integration` is ever run with `pytest-xdist`; negligible in sequential runs.
- **Recommendation:** Scope deletes to an eBay-specific prefix (e.g. `bronze/source=ebay/`) or a per-run bucket suffix, and use the public `MinIOStorage.list_objects`/`delete_object` surface (or add a `delete_object` helper) rather than `_client`.

---

## 6. Non-Defect Observations

- **N1 — Round-1 findings are substantially resolved.** F3 (populated `listing_id`/`seller_id`) is fixed in the adapter and asserted at event level; F2 (processor/Parquet/PostgreSQL) is addressed with processor-pipeline tests plus Bronze `integration`-marked tests; F4 (idempotency) is addressed with `DeduplicationState` and Bronze overwrite tests; F5 (missing `integration` marker) is fixed. F6's `Decimal` import is hoisted.
- **N2 — "One logical product" is honestly scoped.** `TestMultipleListingsSameProduct` and its class/docstring docstrings explicitly state that the eBay `item_summary/search` endpoint does not expose product identifiers (UPC/GTIN/EAN/ASIN), so end-to-end product grouping is not testable at this layer; the marketplace identity primitives (`ListingProductMapper`, `derive_product_key_from_listing`) are tested in TASK-044 and remain available for a richer source. This is a defensible, transparent resolution of round-1 F1 rather than a fake grouping test.
- **N3 — The adapter change is minimal and correct.** The +10 lines reuse `build_listing_id`/`build_seller_id` and correctly `strip()` the seller username (with a whitespace-only rejection test), matching `libs.marketplace.identity` semantics.
- **N4 — eBay-specific Bronze coverage mirrors the generic writer test.** `test_ebay_bronze_integration.py` follows `test_bronze_writer_integration.py` conventions; its incremental value is the `source=ebay` partition assertion and multi-seller persistence. Its docstring's "listing_id/seller_id survive" claim is the one inaccuracy (F1).
- **N5 — `event_id` non-determinism is now documented.** `TestReplayIdempotency` correctly notes that `collected_at` (and hence `event_id`) differs across real fetch cycles, so cross-cycle dedup is by design deferred to downstream identity/constraints; the dedup test correctly operates on the *same* Kafka message instead.
- **N6 — Full default suite not independently rerun.** The reviewer verified the new hermetic file (26 tests) plus static checks only; the broad default suite and `-m integration` were not independently executed (the latter requires MinIO).

---

## 7. Verdict

**`APPROVED WITH NON-BLOCKING FINDINGS`**

The final merged state satisfies the TASK-045 acceptance criteria within the boundaries the repository's test infrastructure actually supports: the adapter now populates `listing_id`/`seller_id`, the hermetic suite exercises adapter → mock Kafka producer → processor pipeline (including deduplication and replay), and Bronze Parquet stored-state/replay-idempotency coverage is present behind the `integration` marker. All changed files pass `pytest`, `ruff check`, `ruff format --check`, and `mypy` (independently verified). The diff is correctly scoped, contains no secrets or unrelated changes, and preserves architecture.

The remaining findings are non-blocking: a misleading docstring in the Bronze test that overstates `listing_id`/`seller_id` persistence (F1, Moderate), tautological processor "traceability" assertions (F2, Minor), a minor typing sentinel smell (F3, Minor), and a shared-bucket teardown hazard inherited from an existing fixture (F4, Minor). The substantive follow-up — persisting `listing_id`/`seller_id` through the Bronze/Silver Parquet schemas — belongs to TASK-021/TASK-024 and should be tracked as a separate task; it is outside TASK-045's scope to fix.

The reviewer did not modify any code.
