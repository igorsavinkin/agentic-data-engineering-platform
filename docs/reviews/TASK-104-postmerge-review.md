# TASK-104 Post-Merge Review — Duplicate/Replay Test

## 1. Review Header

- **Task ID:** TASK-104 — Duplicate/Replay Test
- **Review date:** 2026-09-24
- **Reviewer:** Qwen Code (independent post-merge review, no code modified)
- **Reviewed change set / Git range:** `8c7fd7b27c5f127e78481bcc5ab38ae232d47ff2..446d32ef5fc172b0bd52d7a4e0cabb9db64ea185`
- **Reviewed commit:** `446d32e` — `feat(TASK-104): add duplicate/replay integration tests (#123)` (squash-merge of PR #123 onto `main`)
- **Branch:** `main` (code already merged; post-merge review)
- **Scope:** one new test file `tests/test_duplicate_replay.py` (802 lines) plus a review record `docs/reviews/TASK-104-review.md` (194 lines). No production code changes.
- **Verdict:** APPROVED WITH NON-BLOCKING FINDINGS

### Important note on the requested Git range

The review instruction asked to inspect `10ee4a13c5757a297e2c34ec3299d14328b44a11..8c7fd7b27c5f127e78481bcc5ab38ae232d47ff2`. That range resolves to a **single commit**, `8c7fd7b` (`docs: add PostgreSQL to FastAPI E2E test report`), which adds only `docs/e2e/E2E-POSTGRESQL-TO-API-2026-09-24.md` and is **unrelated to TASK-104**.

The actual TASK-104 implementation on `main` is commit `446d32e` (parent `8c7fd7b`), whose diff is exactly the two TASK-104 files. The correct post-merge review range is therefore `8c7fd7b..446d32e`. This review proceeds on that range; the discrepancy is recorded for transparency and does not affect the verdict.

---

## 2. Requirements Coverage

Source of truth: `ai/tasks/TASK-104-duplicate-replay-test.md`, `ai/PROJECT.md` §5 (at-least-once + idempotent processing), `ai/SPECIFICATION.md` §9 (a duplicate event must not result in duplicate logical observations in the final analytical/serving layer), and `docs/adr/ADR-001-kafka-topic-configuration.md`.

| Requirement | Status | Implementation evidence |
|---|---|---|
| Demonstrate duplicate-event handling | Met | `TestDuplicateDeliveryDetection` (line ~394) publishes the same `ProductObservationEvent` twice and asserts `published_valid == 1`, `duplicates_skipped == 1`, `total == 2`, `EVENTS_DUPLICATE == 1`, `EVENTS_VALID == 1`, `EVENTS_PROCESSED == 2`, `dedup_state.size == 1`. |
| Demonstrate Kafka replay (offset reset → redelivery) | Met | `TestKafkaReplayDeduplication` (line ~460) performs a genuine replay: the first consumer in a fresh group consumes 3 messages without committing offsets (`enable.auto.commit=False`, verified in `libs/common/kafka_consumer.py`), and a second consumer in the same group redelivers all 3 (`len(replay_messages) == 3`, `auto.offset.reset=earliest`). Dedup assertions are unconditional (`duplicates_skipped == 3`, `published_valid == 0`). |
| Replayed events do not create duplicate logical records in PostgreSQL | Met | `TestCrossBatchDeduplication` (line ~554) double-loads the same Parquet batch; the second load reports `observations_created == 0`, backed by `UNIQUE(event_id)` and `ON CONFLICT (event_id) DO NOTHING` in `warehouse/loader/batch_loader.py:_insert_observations`. Independently re-verified against a live PostgreSQL container (§4). |
| Replayed events do not create duplicate logical records in Parquet | Met | `TestSilverParquetReplayIdempotency` (line ~761) instantiates the real `SilverWriter` against a mock `MinIOStorage`, writes 5 events twice, and asserts 5 storage objects (not 10), each keyed by `event_id` (leaf `<event_id>.parquet` via `build_partition_key`). Independently re-verified (§4). |
| Deduplication across service boundaries | Partially met | Processor dedup (`DeduplicationState`) and warehouse idempotency (`UNIQUE(event_id)`) are each verified, but as two disconnected boundaries using disjoint synthetic `event_id` sets — not a single event traced processor → warehouse. See Finding N1. |
| Failure → Detection → Metric/log → Recovery → No silent data loss | Partially met | The metric arm (`EVENTS_DUPLICATE`) is asserted; the log arm is not. See Finding N3. |
| Repeatable/deterministic | Met | Fixed partition key (`_SAME_EXTERNAL_ID`), isolated Compose projects (`COMPOSE_PROJECT_NAME` + random ports), fresh per-test databases/consumer groups, fixed timestamps and deterministic synthetic `event_id`s. |
| Reuse existing dedup/idempotent semantics | Met | Uses `DeduplicationState`, `ProcessorMetrics`, `ProcessorPipeline`, `WarehouseLoader`, and `SilverWriter` as-is. No production code was changed in the reviewed range. |

---

## 3. Git Diff Review

Net diff of `8c7fd7b..446d32e`:

- `tests/test_duplicate_replay.py` — added (802 lines)
- `docs/reviews/TASK-104-review.md` — added (194 lines, review record)

- **Scope correctness:** All changes belong to TASK-104. No production, configuration, infrastructure, or migration code was modified.
- **Unrelated changes:** None. (Note: the *requested* range `10ee4a1..8c7fd7b` would instead have surfaced `8c7fd7b`, an unrelated docs commit.)
- **Architectural changes:** None. Service boundaries (Processor, Lake Writer, Warehouse Loader) are referenced, not altered.
- **Accidental changes:** None — no debugging code, temporary files, generated artifacts, or dead code.
- **Dependencies/configuration:** No new dependencies. The test reuses `polars`, `psycopg2`, `confluent_kafka`, `alembic`, `pydantic`, and the existing `docker-compose.yml` stack. `io` and `decimal.Decimal` imports were added for the Silver test only.
- **Secrets:** None. The only credential present is `platform:platform-local`, the documented local-dev default (`docker-compose.yml` `POSTGRES_PASSWORD:-platform-local`, also in `.env.example`).
- **Branch/task isolation:** Correct. `446d32e` is a clean squash-merge of `feature/TASK-104` (PR #123) containing only TASK-104 changes; the intermediate feature-branch commits are not part of `main` history.

---

## 4. Test and Verification Review

### Tests examined

Six integration tests (module `pytestmark = pytest.mark.integration`, line 67):

1. `TestDuplicateDeliveryDetection::test_duplicate_events_deduplicated_with_metrics` (line ~394)
2. `TestKafkaReplayDeduplication::test_replay_with_dedup_state_skips_seen_events` (line ~460)
3. `TestCrossBatchDeduplication::test_warehouse_prevents_duplicates_after_processor_restart` (line ~554)
4. `TestIndependentDedupBoundaries::test_processor_and_warehouse_each_prevent_duplicates` (line ~596)
5. `TestMultipleProcessorReplays::test_multiple_replays_emit_no_duplicates` (line ~679)
6. `TestSilverParquetReplayIdempotency::test_silver_writer_replay_overwrites_no_duplicates` (line ~761)

### Verification status

#### Independently verified (executed by this reviewer)

| Command | Result |
|---|---|
| `python -m pytest tests/test_duplicate_replay.py --collect-only -q -m integration` | 6 tests collected (3.97s), module imports cleanly |
| `python -m ruff check tests/test_duplicate_replay.py` | All checks passed |
| `python -m ruff format --check tests/test_duplicate_replay.py` | 1 file already formatted |
| `python -m pytest "tests/test_duplicate_replay.py::TestSilverParquetReplayIdempotency" -m integration -v` | **1 passed** (1.71s, in-memory, no Docker) |
| `python -m pytest "tests/test_duplicate_replay.py::TestCrossBatchDeduplication" -m integration -v` | **1 passed** (23.74s, live PostgreSQL) |

#### Implementation evidence reviewed (not independently rerun)

The three Kafka-backed scenarios (`TestDuplicateDeliveryDetection`, `TestKafkaReplayDeduplication`, `TestMultipleProcessorReplays`) and the Kafka leg of `TestIndependentDedupBoundaries` were not independently rerun in this post-merge pass (they require a live Kafka broker and take ~4–5 minutes each). Their pass is attested by the committed `docs/reviews/TASK-104-review.md`, which records independent execution against live Kafka/PostgreSQL on the feature branch.

This reviewer independently confirmed the code-path mechanics that make those tests correct rather than vacuous:

- `KafkaConsumerSettings` defaults `auto.offset.reset = "earliest"` and `enable.auto.commit = False` (`libs/common/kafka_consumer.py:52,56`), so the replay consumer in the same group genuinely redelivers uncommitted messages.
- `DeduplicationState.check_and_update` and `deduplicate()` implement cross-batch and within-batch dedup on `event_id` (`services/processor/deduplication.py`).
- `ProcessorPipeline.process_batch` accounts `published_valid`, `duplicates_skipped`, `conflicts`, and `total` such that every input row appears in exactly one category, and increments `EVENTS_PROCESSED`/`EVENTS_VALID`/`EVENTS_DUPLICATE` accordingly (`services/processor/pipeline.py`).
- `WarehouseLoader._insert_observations` enforces `ON CONFLICT (event_id) DO NOTHING` and reports actual insert counts (`warehouse/loader/batch_loader.py`).
- `SilverWriter._write_single` keys each object by `build_partition_key(event, LakeLayer.SILVER)`, whose leaf is `<event_id>.parquet` (`libs/partitioning/partition_key.py`).

#### Note on default pytest configuration

`pyproject.toml` sets `addopts = "-m 'not integration'"`, so a plain `pytest` run deselects all six tests. The tests are correctly opt-in via `-m integration`, and this reviewer explicitly ran the in-memory and PostgreSQL scenarios with `-m integration` rather than relying on the deselection default.

---

## 5. Findings

No blocking findings. Four non-blocking findings (N1–N4), all carried forward from the pre-merge review and re-confirmed against the merged `main` state.

### N1 — MODERATE — "Across service boundaries" is demonstrated as two disconnected boundaries, not a connected flow

- **File/line:** `tests/test_duplicate_replay.py:596-669` (especially `warehouse_event_ids` at ~line 644)
- **Problem:** `TestIndependentDedupBoundaries` processes duplicate Kafka events through the processor (asserting processor dedup + metrics), then builds a *separate* Parquet batch with brand-new `warehouse_event_ids = [f"evt-e2e-pg-{i}"]` and loads that into PostgreSQL. The Kafka→processor leg and the warehouse leg never share an event, so "across service boundaries" is satisfied as "independent safeguards" rather than a single event traced processor → warehouse.
- **Impact:** Coverage nuance, not a correctness defect. Each boundary is genuinely exercised; only the connected-flow interpretation is absent. The class docstring honestly labels these "independent safeguards".
- **Recommendation:** Acceptable as-is; optionally add one scenario feeding the processor's *actual* validated events into the warehouse leg. Otherwise close as a documented scope decision.

### N2 — MINOR — Scenario 3 name/docstring overstate a "processor restart" that is never simulated

- **File/line:** `tests/test_duplicate_replay.py:544-572`
- **Problem:** `TestCrossBatchDeduplication::test_warehouse_prevents_duplicates_after_processor_restart` and its class docstring describe a processor restart; the body only performs a warehouse double-load of the same Parquet batch. No processor, Kafka consumer, or `DeduplicationState` reset is involved.
- **Impact:** Misleading naming only; the warehouse-idempotency assertion is correct.
- **Recommendation:** Rename to `test_warehouse_prevents_duplicates_on_reload` and align the docstring.

### N3 — MINOR — "Log" half of the failure lifecycle is not asserted

- **File/line:** `tests/test_duplicate_replay.py` (no `caplog` usage)
- **Problem:** The failure-engineering rule requires `Detection -> Metric/log`. The metric arm (`EVENTS_DUPLICATE`) is asserted, but no duplicate-detection log is asserted. `ProcessorPipeline.process_batch` does not emit a duplicate-specific log at the pipeline level.
- **Impact:** The requirement is effectively satisfied by the metric arm; the log arm is undocumented rather than broken.
- **Recommendation:** Either accept "metric" as satisfying "Metric/log" (and note it), or add a duplicate-detection log at the pipeline level (out of TASK-104's test-only scope).

### N4 — MINOR — Silver test inherits the integration marker despite being in-memory

- **File/line:** `tests/test_duplicate_replay.py:731-801` (module `pytestmark` at line 67)
- **Problem:** `TestSilverParquetReplayIdempotency` still inherits `pytest.mark.integration`, even though it uses only a `MagicMock(spec=MinIOStorage)` and in-memory Polars — no Kafka, MinIO/S3, or PostgreSQL. It runs without Docker (verified: 1.71s in-memory).
- **Impact:** Structural/readability only. The test is still correctly selected by `-m integration`.
- **Recommendation:** Optional — keep under the integration umbrella for a task whose deliverable is integration coverage, or exclude it from the marker. Defensible as-is.

---

## 6. Non-Defect Observations

- The Parquet replay test exercises the real platform mechanism: `SilverWriter.write_event → _write_single → build_partition_key → storage.put_object`, where the deterministic key leaf `<event_id>.parquet` makes replay an overwrite. It does not reimplement dedup in Polars, so it validates the production idempotency guarantee rather than a parallel reimplementation.
- Fixture scaffolding is solid: Docker-daemon skip guards, isolated Compose projects via `COMPOSE_PROJECT_NAME` + `PLATFORM_NETWORK_NAME`, random port binding, and a per-test `CREATE DATABASE` + Alembic `upgrade head` for full PostgreSQL isolation.
- Scenario 1 exercises the full `Failure → Detection (EVENTS_DUPLICATE) → Recovery → No silent data loss` loop at the processor level; Scenario 2 genuinely exercises Kafka redelivery; Scenario 5 is a valid processor-level replay-of-a-batch demonstration.
- `KafkaValidatedOutputProducer.publish` is synchronous and raises on delivery failure, so the pipeline's self-reported `published_valid`/`duplicates_skipped` counts are trustworthy even though the tests do not independently re-read `products.validated.v1`.
- `storage.check_health.return_value` is set in the Silver test but `check_health` is never called by `write_event`/`_write_single`; harmless defensive setup, not a defect.
- The test file disables four mypy error codes via `# mypy: disable-error-code=...`; acceptable for a test module and does not weaken the mypy gate on `libs`/`scripts`.
- No secrets, no production-code changes, no new dependencies, and no weakening of existing suites.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The TASK-104 objective is genuinely satisfied at the merged state on `main`: duplicate delivery is detected with metrics, Kafka replay is exercised with real offset redelivery, and both the PostgreSQL warehouse (`UNIQUE(event_id)` + `ON CONFLICT DO NOTHING`) and Silver Parquet (`<event_id>.parquet` overwrite) boundaries are verified to prevent duplicate logical records. The change set is correctly scoped (test-only), introduces no new dependencies or secrets, and preserves the service architecture.

This reviewer independently re-confirmed the module imports cleanly (6 tests collected), `ruff check`/`ruff format --check` pass, the in-memory Silver replay test passes, and the PostgreSQL warehouse idempotency test passes against a live container. The Kafka-backed scenarios are attested by the committed pre-merge review and supported by this reviewer's code-path verification of the consumer/dedup/metrics mechanics.

The four remaining findings are non-blocking (one Moderate coverage-nuance, three Minor naming/convention nits) and are documented above; none invalidates the task's objective or blocks the already-completed merge.
