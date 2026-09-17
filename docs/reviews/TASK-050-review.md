# TASK-050 Review — Retailer Integration Tests

## 1. Review Header

- **Task ID:** TASK-050 — Retailer Integration Tests
- **Review date:** 2026-09-17
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:** `582ee0489f36804f23e30d97c2f106afe5e0ebc4..3d4e46cd12e90781c8505340ec50b5b61c53e35b`
- **Reviewed HEAD:** `3d4e46cd12e90781c8505340ec50b5b61c53e35b` on `feature/TASK-050`
- **Scope:** Milestone 5B integration gate for the web retailer (`tests/test_retailer_integration.py` — 994 lines added, no application code changed)
- **Verdict:** **APPROVED WITH NON-BLOCKING FINDINGS**

## 2. Requirements Coverage

| Requirement | Status | Evidence |
|---|---|---|
| Deterministic CI; no live retailer dependency | ✅ | Fixed HTML fixtures (`PAGE_1_HTML`, `PAGE_2_HTML`, `MALFORMED_HTML`, `SINGLE_PAGE_HTML`) fed through `AsyncMock(spec=WebRetailerClient)`; no network calls |
| Exercise real internal boundaries where supported | ✅ | Real `IngestionRunner`, `WebRetailerAdapter`, parser, `ProcessorPipeline`, `DeduplicationState`, `BronzeWriter`, `SilverWriter`; only Kafka producer and MinIO storage are mocked |
| ≥1 retailer observation traceable through the pipeline | ✅ | `test_single_product_through_full_pipeline`, `test_traceability_across_layers` (event_id + external_id continuity raw→validated) |
| Multiple pages aggregated correctly | ✅ | `test_two_pages_aggregated`, `test_multi_page_preserves_prices`, `test_multi_page_availability_variety` |
| Malformed records excluded from valid downstream data | ✅ | `test_malformed_excluded_from_valid`, `test_malformed_do_not_reach_processor`, `test_malformed_tracked_in_stats` |
| Transient failure → retry/recovery | ✅ | `test_first_page_failure_raises`, `test_recovery_after_failure` |
| Partial pagination failure (TASK-048) | ✅ | `test_partial_failure_returns_collected_pages`, `test_partial_failure_events_process_correctly` |
| Replay/idempotency | ✅ | `test_same_input_produces_same_external_ids`, `test_deduplication_via_processor` (same event_id → `duplicates_skipped`) |
| Source-health metrics healthy + degraded | ✅ | `test_healthy_run_metrics`, `test_degraded_run_metrics`, `test_failed_run_no_freshness_update`, `test_runner_exposes_freshness` |
| Regression smoke for existing adapters | ✅ | `test_all_sources_in_one_cycle`, `test_web_retailer_failure_does_not_block_others`, `test_web_retailer_canonical_contract` |
| No TASK-051 difficult-source work | ✅ | None present |
| PostgreSQL leg of the canonical flow | ⚠️ | Not exercised for a retailer event — see Finding F1 |

## 3. Git Diff Review

- **Scope correctness:** ✅ Single commit `3d4e46c` adds exactly one file, `tests/test_retailer_integration.py` (994 insertions, 0 deletions). No application, schema, config, or infrastructure files are touched.
- **Unrelated changes:** None.
- **Architectural changes:** None. Tests consume the existing public interfaces (`SourceAdapterProtocol`, `ProcessorPipeline`, `BronzeWriter`, `SilverWriter`, `SourceMetrics`, `IngestionRunner`) without altering them.
- **Accidental changes:** None. No debug code, `print`, temp files, dead code, generated artifacts, or secrets.
- **Dependency/configuration changes:** None. Only stdlib/`unittest.mock`, `pytest`, `polars`, and existing first-party `libs`/`services` imports.
- **Branch/task isolation:** ✅ Working tree clean; branch `feature/TASK-050`; the reviewed range contains exactly one commit. No changes from another TASK-xxx are mixed in.

## 4. Test and Verification Review

**Tests examined** (24 tests, matching the commit message):

- `TestFullPipelineTraceability` (2) — raw→validated continuity of `event_id`/`external_id`.
- `TestMultiPageAggregation` (3) — two-page aggregation, price preservation, availability mapping.
- `TestMalformedInput` (3) — malformed article excluded, never reaches processor, counted in stats.
- `TestTransientFailureAndRetry` (2) — first-page failure publishes nothing; recovery on next cycle.
- `TestPartialPaginationFailure` (2) — page-2 failure preserves page-1 events and they process cleanly.
- `TestReplayIdempotency` (2) — stable external_ids across cycles; same event_id deduplicated by `DeduplicationState`.
- `TestSourceHealthMetrics` (4) — healthy/degraded/failed freshness + `IngestionRunner.get_source_freshness()`.
- `TestBronzeParquetLayer` (2) — single and multi-page events round-trip to Parquet bytes (mocked `MinIOStorage`).
- `TestSilverParquetLayer` (1) — validated event → Silver row + Parquet key.
- `TestRegressionSmoke` (3) — all four adapters coexist; web-retailer failure isolates; canonical contract keys.

**Test adequacy:** The task's eight verification bullets are each directly exercised. The tests are deterministic (stable external_id assertions; no hardcoded event_id/timestamp values), hermetic (external boundary and storage mocked), and exercise real internal components (adapter → parser → runner → processor → writers). Assertions are meaningful, not tautological — e.g., `test_deduplication_via_processor` asserts `published_valid` drops to 0 with `duplicates_skipped == 1` on the second delivery.

**Independently executed (by reviewer):**

- `python -m pytest tests/test_retailer_integration.py -q` → **24 passed in 5.81s**.
- `python -m ruff check tests/test_retailer_integration.py` → **All checks passed**.
- `python -m ruff format --check tests/test_retailer_integration.py` → **1 file already formatted**.
- `python -m mypy tests/test_retailer_integration.py` → **Success: no issues found in 1 source file**.

**Implementation results inspected but not rerun:** none (all four checks above were run independently).

**Unverified checks:** `python -m pytest -m integration` (Docker-dependent; requires PostgreSQL/Kafka/MinIO) was **not** run. Rationale: the TASK-050 diff adds no `integration`-marked tests — the new suite is deliberately deterministic and runs under the default `pytest` config (`addopts = "-m 'not integration'"`), and the repository's real-infrastructure integration coverage (Kafka, MinIO, PostgreSQL) is owned by pre-existing integration-marked tests that are unchanged by this task. The reviewer instruction to verify integration tests is therefore addressed by scope rather than execution; see Finding F1 for the residual PostgreSQL coverage gap.

## 5. Findings

### F1 — Moderate: retailer observation is not traced into PostgreSQL

- **File:** `tests/test_retailer_integration.py` (module overall; the pipeline tests stop at the validated sink / mocked Silver Parquet)
- **Problem:** The TASK-050 objective's required flow ends with `… → Parquet → PostgreSQL`, and the acceptance criterion states "A valid retailer observation can traverse the canonical pipeline into PostgreSQL." The new tests trace a retailer event only as far as the validated sink and mocked Silver/Bronze Parquet (`MagicMock(spec=MinIOStorage)`); no test loads a retailer event through `WarehouseLoader` into PostgreSQL. `test_retailer_event_to_bronze_parquet` and `test_validated_event_to_silver_parquet` are separate round-trip checks, not a continuous HTML→PostgreSQL trace.
- **Impact:** The literal acceptance criterion is only partially demonstrated. There is no retailer-specific proof that the Silver→PostgreSQL leg works end-to-end. This is mitigated because the `WarehouseLoader` is source-agnostic (it reads canonical Silver Parquet regardless of `source`) and is already covered by `tests/warehouse/test_loader.py` and `tests/warehouse/test_idempotent_loader.py` (both `integration`-marked), which use `fake-store`/`best-buy` fixtures — but those never exercise a `web_retailer` event.
- **Recommendation:** Add a `@pytest.mark.integration` test that writes a retailer Silver Parquet (from a real retailer event) and loads it via `WarehouseLoader`, asserting a `product_observation` row with `source = 'web_retailer'` appears. If intentionally deferred, document in the test module docstring that the PostgreSQL leg is source-agnostic and covered by the warehouse integration tests.

### F2 — Minor: "replay" test verifies external_id stability, not deduplication

- **File:** `tests/test_retailer_integration.py` (`test_same_input_produces_same_external_ids`, under `TestReplayIdempotency`)
- **Problem:** The test named under "Replay idempotency" only asserts that two fetch cycles yield the same `external_id` set. Because `collected_at` is re-generated each cycle, the two cycles produce *different* `event_id`s, so the test does not exercise deduplication at all (and the class docstring does not call this out). The actual dedup guarantee is tested separately by `test_deduplication_via_processor` (same `event_id` replayed).
- **Impact:** Slight overstatement of the replay coverage; a reader could mistake `test_same_input_produces_same_external_ids` for a dedup test. Not a correctness defect — the platform's at-least-once/idempotent semantics (same event_id → one logical observation) are correctly covered by `test_deduplication_via_processor` at the processor layer and by the warehouse idempotent-loader tests at the serving layer.
- **Recommendation:** Clarify the class/comment (mirroring the equivalent note in `tests/test_ebay_integration.py`) that cross-cycle re-observation legitimately produces distinct `event_id`s, and that the same-event dedup is the covered guarantee.

### F3 — Minor: `test_first_page_failure_raises` name overstates its assertion

- **File:** `tests/test_retailer_integration.py` (`test_first_page_failure_raises`, in `TestTransientFailureAndRetry`)
- **Problem:** The test name says "raises," but `IngestionRunner` swallows the adapter's `SourceFetchError` (by design — per-source error isolation). The test actually asserts the runner-level outcome: `published == 0` and `stats.total_errors > 0`.
- **Impact:** Naming/assertion clarity only; the behavior verified (no events, error tracked) is correct and important.
- **Recommendation:** Rename to reflect intent (e.g., `test_first_page_failure_publishes_nothing_and_tracks_error`), or add a direct adapter-level assertion that `adapter.fetch()` raises `SourceFetchError`.

## 6. Non-Defect Observations

- **O1 — Bronze/Silver tests use the deprecated batch API.** `test_retailer_event_to_bronze_parquet` and `test_validated_event_to_silver_parquet` drive `add_event` + `flush_batch`, which `BronzeWriter`/`SilverWriter` mark as deprecated in favor of `write_event`. Both paths remain valid; this exercises the batch/Parquet serialization path but not the preferred at-least-once `write_event` path.
- **O2 — Suite is intentionally not `integration`-marked.** The new tests run under the default `pytest` config (deterministic, no Docker), which satisfies the task's "normal CI must be deterministic" requirement. The `integration` marker is reserved for the repository's real-infrastructure tests, which this task does not modify.
- **O3 — Failure tests incur small backoff sleeps.** `test_first_page_failure_raises` and `test_recovery_after_failure` use `max_retries=1`, triggering a 1-second exponential-backoff sleep in `IngestionRunner._fetch_and_publish`. Negligible for the suite (5.81s total), but worth knowing if the suite grows.
- **O4 — Canonical contract test is source-agnostic and precise.** `test_web_retailer_canonical_contract` asserts the exact payload key set (including `listing_id`/`seller_id` as `None`) and the `web_retailer:` partition-key prefix, confirming the retailer emits the same canonical contract as marketplace adapters.

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS.**

The change is a cleanly scoped, test-only commit that delivers a deterministic 24-test integration gate for the web retailer. It satisfies the TASK-050 verification bullets — single-observation traceability, multi-page aggregation, malformed exclusion, transient failure/recovery, partial pagination failure, replay/idempotency, source-health metrics, and regression smoke — and the tests are meaningful (real internal pipeline components, mocked only at the external HTTP/Kafka/storage boundaries). All four verification checks (pytest, ruff check, ruff format, mypy) were independently run and passed.

The findings are non-blocking: F1 is a coverage gap on the final PostgreSQL leg (mitigated by the source-agnostic, separately tested `WarehouseLoader`), F2 and F3 are clarity/documentation issues rather than correctness defects. None represent unsafe or incorrect pipeline behavior; F1 is the only item worth addressing to fully close the literal acceptance criterion.

Independently verified: `pytest` (24 passed), `ruff` (clean), `mypy` (clean) on the changed file. `pytest -m integration` was not run (Docker-dependent and out of scope for this diff; see §4).
