# TASK-104 Review — Duplicate/Replay Test

## 1. Review Header

- **Task ID:** TASK-104 — Duplicate/Replay Test
- **Review date:** 2026-09-24
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:** `8c7fd7b27c5f127e78481bcc5ab38ae232d47ff2..e18ca649442147a5dd3e9c85e9799d05d78a9f9e`
- **Reviewed HEAD:** `e18ca649442147a5dd3e9c85e9799d05d78a9f9e` (`fix(TASK-104): exercise SilverWriter for Parquet replay idempotency test`)
- **Branch:** `feature/TASK-104`
- **Scope:** one new test file, `tests/test_duplicate_replay.py` (802 lines), plus the review record `docs/reviews/TASK-104-review.md`
- **Verdict:** APPROVED WITH NON-BLOCKING FINDINGS

This is the third review pass. The implementer addressed round-1 findings F1–F5 (`3a86742`), added a
Parquet-level test in `e16c8b3` (found vacuous — round-2 finding R1, CHANGES REQUIRED), and now in
`e18ca64` replaced that vacuous test with a real `SilverWriter` + mock-`MinIOStorage` test. This
report re-evaluates the full change set at the new HEAD.

---

## 2. Requirements Coverage

Source of truth: `ai/tasks/TASK-104-duplicate-replay-test.md`, `ai/PROJECT.md` §5 (at-least-once +
idempotent processing), and `ai/SPECIFICATION.md` §9 (a duplicate event must not result in duplicate
logical observations in the final analytical/serving layer).

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Demonstrate duplicate-event handling | Met | Scenario 1 (`test_duplicate_events_deduplicated_with_metrics`, line 394) publishes the same event twice and asserts `published_valid == 1`, `duplicates_skipped == 1`, `EVENTS_DUPLICATE == 1`, `EVENTS_PROCESSED == 2`, `dedup_state.size == 1`. |
| Demonstrate Kafka replay (offset reset → redelivery) | Met | Scenario 2 (`test_replay_with_dedup_state_skips_seen_events`, line 460) performs a genuine replay: the first consumer commits no offsets, the second consumer in the same group redelivers all 3 messages (`len(replay_messages) == 3`), and dedup assertions are unconditional (`duplicates_skipped == 3`). |
| Replayed events do not create duplicate logical records in PostgreSQL | Met | Scenario 3 (`test_warehouse_prevents_duplicates_after_processor_restart`, line 554) double-loads the same Parquet batch; the second load creates `0` observations (`observations_created == 0`), backed by `UNIQUE(event_id)` and `ON CONFLICT (event_id) DO NOTHING`. Independently verified against a live PostgreSQL container. |
| Replayed events do not create duplicate logical records in Parquet | **Met (was R1)** | `test_silver_writer_replay_overwrites_no_duplicates` (line 761) now instantiates `SilverWriter` against a mock `MinIOStorage`, writes 5 events twice, and asserts 5 storage objects (not 10), each keyed by `event_id`. Verified independently (see §4). |
| Deduplication across service boundaries | Partially met | Processor dedup and warehouse idempotency are each verified, but as two independent, disconnected boundaries using disjoint synthetic event IDs — not a single event traced through processor → warehouse. See N1. |
| Failure → Detection → Metric/log → Recovery → No silent data loss | Partially met | The metric arm (`EVENTS_DUPLICATE`) is asserted; the log arm is not. See N3. |
| Repeatable/deterministic | Met | Fixed partition key (`_SAME_EXTERNAL_ID` → single partition), isolated Compose projects with random ports, fresh per-test DBs/consumer groups, fixed timestamps/event IDs. |
| Reuse existing dedup/idempotent semantics | Met | Uses `DeduplicationState`, `ProcessorMetrics`, `ProcessorPipeline`, `WarehouseLoader`, and `SilverWriter` as-is. No production-code changes in the reviewed range. |

---

## 3. Git Diff Review

The reviewed range contains six commits:

- `d6aac46` — `feat(TASK-104): add duplicate/replay integration tests`
- `40102ad` — `docs: Record TASK-104 Qwen review (CHANGES REQUIRED)`
- `3a86742` — `fix(TASK-104): address Qwen review findings F1-F5`
- `b946cdd` — `docs: Update TASK-104 Qwen review (round 2, CHANGES REQUIRED)`
- `e16c8b3` — `feat(TASK-104): add Parquet-level replay duplicate verification`
- `e18ca64` — `fix(TASK-104): exercise SilverWriter for Parquet replay idempotency test`

Net diff (`8c7fd7b..e18ca64`):

- `tests/test_duplicate_replay.py` — added (802 lines)
- `docs/reviews/TASK-104-review.md` — added (review record)

- **Scope correctness:** All changes belong to TASK-104. No production, config, infrastructure, or migration code was modified.
- **Unrelated changes:** None.
- **Architectural changes:** None. Service boundaries (processor, Lake Writer, Warehouse Loader) are referenced, not altered.
- **Accidental changes:** None (no debugging code, temporary files, generated artifacts, or secrets).
- **Dependencies/configuration:** No new dependencies. The test reuses `confluent_kafka`, `polars`, `psycopg2`, `alembic`, `pydantic`, and the existing `docker-compose.yml` stack. `io` and `decimal.Decimal` imports were added for the Silver test.
- **Branch/task isolation:** Correct — work is on `feature/TASK-104`; no changes from another TASK-* branch are included.

---

## 4. Test and Verification Review

### Tests examined

Six integration tests (module `pytestmark = pytest.mark.integration`, line 67):

1. `TestDuplicateDeliveryDetection::test_duplicate_events_deduplicated_with_metrics` (line 394)
2. `TestKafkaReplayDeduplication::test_replay_with_dedup_state_skips_seen_events` (line 460)
3. `TestCrossBatchDeduplication::test_warehouse_prevents_duplicates_after_processor_restart` (line 554)
4. `TestIndependentDedupBoundaries::test_processor_and_warehouse_each_prevent_duplicates` (line 596)
5. `TestMultipleProcessorReplays::test_multiple_replays_emit_no_duplicates` (line 679)
6. `TestSilverParquetReplayIdempotency::test_silver_writer_replay_overwrites_no_duplicates` (line 761)

### Verification status — Independently verified (executed by the reviewer)

The reviewer ran the full suite against a live Docker Kafka/PostgreSQL stack. All six tests passed:

| Command | Result |
|---------|--------|
| `python -m pytest tests/test_duplicate_replay.py --collect-only -q -m integration` | 6 tests collected (2.67s), module imports cleanly |
| `python -m ruff check tests/test_duplicate_replay.py` | All checks passed |
| `python -m ruff format --check tests/test_duplicate_replay.py` | 1 file already formatted |
| `python -m pytest tests/test_duplicate_replay.py::TestSilverParquetReplayIdempotency -m integration -v` | **1 passed** (3.00s, in-memory) |
| `python -m pytest tests/test_duplicate_replay.py::TestCrossBatchDeduplication -m integration -v` | **1 passed** (22.52s, live PostgreSQL) |
| `python -m pytest "tests/test_duplicate_replay.py::TestDuplicateDeliveryDetection" "tests/test_duplicate_replay.py::TestKafkaReplayDeduplication" -m integration -v` | **2 passed** (250.61s, live Kafka) |
| `python -m pytest "tests/test_duplicate_replay.py::TestMultipleProcessorReplays" "tests/test_duplicate_replay.py::TestIndependentDedupBoundaries" -m integration -v` | **2 passed** (256.44s, live Kafka + PostgreSQL) |

Note: `pyproject.toml` sets `addopts = "-m 'not integration'"`, so the default `pytest` run deselects
all six. The reviewer explicitly ran with `-m integration` as required by the DoD, and confirmed the
Kafka- and PostgreSQL-backed scenarios exercise real infrastructure rather than being deselected.

---

## 5. Findings

No blocking findings. The single round-2 blocker (R1 — vacuous Parquet test) is resolved; the
remaining items are Moderate/Minor and non-blocking.

### N1 — MODERATE — "Across service boundaries" is demonstrated as two disconnected boundaries, not a connected flow

- **File/line:** `tests/test_duplicate_replay.py:596-669` (especially `warehouse_event_ids` at line ~644)
- **Problem:** `TestIndependentDedupBoundaries` processes duplicate Kafka events through the processor
  (asserting processor dedup + metrics), then builds a *separate* Parquet batch with brand-new
  `warehouse_event_ids = [f"evt-e2e-pg-{i}"]` and loads that into PostgreSQL. The Kafka→processor leg and
  the warehouse leg never share an event. "Across service boundaries" is satisfied in the
  "multiple independent boundaries" sense, not as a single event traced through processor → warehouse.
- **Impact:** Coverage nuance, not a correctness defect. Each boundary is genuinely exercised; only the
  connected-flow interpretation is absent. The class docstring now honestly labels these "independent
  safeguards", which is an accurate description of what the test proves.
- **Recommendation:** Acceptable as-is; optionally add one scenario that feeds the processor's *actual*
  validated events into the warehouse leg. Otherwise close as a documented scope decision.

### N2 — MINOR — Scenario 3 name/docstring overstate a "processor restart" that is never simulated

- **File/line:** `tests/test_duplicate_replay.py:544-572`
- **Problem:** `TestCrossBatchDeduplication::test_warehouse_prevents_duplicates_after_processor_restart`
  and its class docstring describe a processor restart ("processor restarts, same events redelivered
  from Kafka"). The test body performs only a warehouse double-load of the same Parquet batch; no
  processor, Kafka consumer, or `DeduplicationState` reset is involved.
- **Impact:** Misleading naming only; the warehouse-idempotency assertion itself is correct.
- **Recommendation:** Rename to `test_warehouse_prevents_duplicates_on_reload` and align the docstring.

### N3 — MINOR — "Log" half of the failure lifecycle is not asserted

- **File/line:** `tests/test_duplicate_replay.py` (no `caplog` usage)
- **Problem:** The failure-engineering rule requires `Detection -> Metric/log`. The metric arm is
  asserted (`EVENTS_DUPLICATE`), but no duplicate-detection log is asserted. `ProcessorPipeline.process_batch`
  emits no duplicate-specific log (the `duplicates` field is only logged in `services/processor/__main__.py`'s
  run loop, which the test bypasses).
- **Impact:** The "Metric/log" requirement is effectively satisfied by the metric arm; the log arm is
  undocumented rather than broken.
- **Recommendation:** Either accept "metric" as satisfying "Metric/log" (and note it), or add a
  duplicate-detection log at the pipeline level (out of TASK-104's test-only scope).

### N4 — MINOR — Silver test still inherits the integration marker despite being in-memory

- **File/line:** `tests/test_duplicate_replay.py:731-801` (module `pytestmark` at line 67)
- **Problem:** The new Silver test correctly moved to its own class (`TestSilverParquetReplayIdempotency`)
  but still inherits the module-level `pytest.mark.integration`, even though it uses only a
  `MagicMock(spec=MinIOStorage)` and in-memory Polars — no Kafka, MinIO/S3, or PostgreSQL. It runs without
  Docker (verified: 3.00s in-memory).
- **Impact:** Structural/readability only; the test is still correctly selected by `-m integration` and
  the module remains internally consistent.
- **Recommendation:** Optional — could carry `@pytest.mark.integration` justification or be excluded from
  the marker, but keeping it under the integration umbrella for a task whose deliverable is integration
  coverage is defensible.

---

## 6. Non-Defect Observations

- The round-2 blocker R1 is genuinely resolved: the replacement test instantiates the real
  `SilverWriter` and drives `write_event → _write_single → build_partition_key → storage.put_object`,
  then reads the written Parquet bytes back and asserts 5 distinct `event_id`-keyed objects after replay.
  The deterministic key (leaf = `<event_id>.parquet`) is the platform mechanism that makes replay an
  overwrite, and the test now exercises exactly that path rather than reimplementing dedup in Polars.
- The fixture scaffolding is solid: Docker-daemon skip, isolated Compose projects via
  `COMPOSE_PROJECT_NAME`, random port binding, and a per-test `CREATE DATABASE` + Alembic migration for
  full PostgreSQL isolation.
- Scenario 3 is a clean, correct demonstration of warehouse idempotency via the `event_id` `UNIQUE`
  constraint (`ON CONFLICT (event_id) DO NOTHING` plus explicit conflict escalation in
  `_insert_observations`).
- Scenario 1 correctly exercises the full `Failure → Detection (EVENTS_DUPLICATE) → Recovery → No silent
  data loss` loop at the processor level; Scenario 2 genuinely exercises Kafka redelivery; Scenario 5 is a
  valid processor-level replay-of-a-batch demonstration.
- The validated-output producer (`KafkaValidatedOutputProducer.publish`) is synchronous and raises on
  delivery failure, so the pipeline's self-reported `published_valid`/`duplicates_skipped` counts are
  trustworthy even though the tests do not independently re-read `products.validated.v1`.
- `storage.check_health.return_value` is set in the Silver test but `check_health` is never called by
  `write_event`/`_write_single`; harmless defensive setup, not a defect.
- No secrets, no production-code changes, no new dependencies, and no weakening of existing suites.
  `ruff check` and `ruff format --check` pass; collect-only confirms the module imports cleanly.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The round-2 blocker (R1 — the Parquet test did not exercise the Silver write path) is resolved by
`e18ca64`, which now instantiates the real `SilverWriter` against a mock `MinIOStorage` and verifies
that replaying 5 events overwrites the same 5 `event_id`-keyed objects rather than creating 10. The
reviewer independently ran the entire suite against live Kafka and PostgreSQL: all six tests pass, and
`ruff check` / `ruff format --check` are clean.

Remaining findings N1–N4 are Moderate/Minor and non-blocking: N1 reflects an honest, documented
interpretation of "across service boundaries" (independent safeguards rather than a connected flow);
N2/N3/N4 are naming and marker-convention nits. None of them invalidate the task's objective — the
replay/duplicate behavior is now genuinely verified at the processor, Parquet, and PostgreSQL
boundaries, with the metric arm of the failure lifecycle asserted.
