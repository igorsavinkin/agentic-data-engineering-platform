# TASK-104 Review — Duplicate/Replay Test

## 1. Review Header

- **Task ID:** TASK-104 — Duplicate/Replay Test
- **Review date:** 2026-09-24
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:** `8c7fd7b27c5f127e78481bcc5ab38ae232d47ff2..d6aac4631fdc74a243718d6bad28bcbd3426323c`
- **Reviewed HEAD:** `d6aac4631fdc74a243718d6bad28bcbd3426323c` (`feat(TASK-104): add duplicate/replay integration tests`)
- **Branch:** `feature/TASK-104`
- **Scope:** one new file, `tests/test_duplicate_replay.py` (763 insertions)
- **Verdict:** CHANGES REQUIRED

## 2. Requirements Coverage

Source of truth: `ai/tasks/TASK-104-duplicate-replay-test.md`, with `ai/PROJECT.md` §5 (at-least-once + idempotent processing) and `ai/ROADMAP.md` M12 ("Duplicate events must not create duplicate logical records").

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Demonstrate duplicate-event handling | Met | Scenario 1 (`test_duplicate_events_deduplicated_with_metrics`, line 424) publishes the same event object twice and asserts `published_valid == 1`, `duplicates_skipped == 1`, and `EVENTS_DUPLICATE == 1`. |
| Demonstrate Kafka replay (offset reset) | **Not met** | Scenario 2 (`test_replay_with_dedup_state_skips_seen_events`, line 490) claims to reset offsets but commits all offsets and reuses the same group — the replay branch is dead code (see F1). |
| Replayed events do not create duplicate logical records in PostgreSQL | Met | Scenario 3 (line 587) loads the same Parquet file twice through `WarehouseLoader` and asserts the second load creates `0` observations. Backed by `uq_product_observations_event_id` (migration `002`). |
| Replayed events do not create duplicate logical records in Parquet | **Not met** | No Parquet-level duplicate verification exists; Scenario 5 is misnamed (see F3). |
| Deduplication across service boundaries | Partially met | Processor-level dedup and warehouse idempotency are each tested, but never connected in a real cross-boundary flow (see F2). |
| Failure → Detection → Metric/log → Recovery → No silent data loss | Partially met | Metrics detection is asserted; log detection is not (see F5). |
| Repeatable/deterministic | Met | Fixed partition key (`_SAME_EXTERNAL_ID`), isolated Compose projects with random ports, fresh per-test DBs/consumer groups. |
| Reuse existing dedup/idempotent semantics | Met | Uses `DeduplicationState`, `ProcessorMetrics`, `ProcessorPipeline`, `WarehouseLoader` as-is; no production code changes. |

## 3. Git Diff Review

- **Scope correctness:** Single-file change; every change belongs to the task. No production, config, or infrastructure code was modified.
- **Unrelated changes:** None.
- **Architectural changes:** None.
- **Accidental changes:** None (no debugging code, temporary files, generated artifacts, or secrets).
- **Dependencies/configuration:** No new dependencies. The test reuses `confluent_kafka`, `polars`, `psycopg2`, `alembic`, and the existing `docker-compose.yml` stack.
- **Branch/task isolation:** Correct — work is on `feature/TASK-104`, commit is task-scoped.

## 4. Test and Verification Review

### Tests examined

Five integration tests (all under `pytestmark = pytest.mark.integration`):

1. `TestDuplicateDeliveryDetection::test_duplicate_events_deduplicated_with_metrics`
2. `TestKafkaReplayDeduplication::test_replay_with_dedup_state_skips_seen_events`
3. `TestCrossBatchDeduplication::test_warehouse_prevents_duplicates_after_processor_restart`
4. `TestEndToEndDuplicateReplay::test_end_to_end_duplicate_no_postgresql_duplicates`
5. `TestReplayNoParquetDuplicates::test_multiple_replays_emit_no_duplicates`

The file follows the established integration-test conventions of `test_kafka_failure.py` (TASK-101) and `test_processor_crash.py` (TASK-103): Docker-daemon skip, isolated Compose projects, random host ports, alembic migration against a fresh database, and a module-level `# mypy:` escape hatch.

### Verification status

- **Independently verified (reviewer executed):**
  - `python -m pytest tests/test_duplicate_replay.py --collect-only -m integration -q` → 5 tests collected; module imports cleanly.
  - `python -m ruff check tests/test_duplicate_replay.py` → All checks passed.
  - `python -m ruff format --check tests/test_duplicate_replay.py` → 1 file already formatted.
- **Unverified (not independently executed):**
  - `python -m pytest -m integration` was not run by the reviewer (requires a live Docker Kafka/PostgreSQL stack). The commit contains no test-run report or captured results, so there is **no implementation evidence** that the integration suite was actually executed and passed. Given the task scope touches Kafka and PostgreSQL, this evidence gap is material.

### Test adequacy

- Metrics-based duplicate detection is well exercised (Scenario 1).
- Warehouse idempotency is genuinely exercised (Scenario 3).
- The Kafka replay scenario is **not** actually exercised (F1), the "end-to-end" claim is overstated (F2), and the Parquet half of the objective is untested (F3). These are adequacy gaps, not merely missing polish.

## 5. Findings

### F1 — HIGH — Scenario 2 never performs a Kafka replay; core assertions are dead code
- **File/line:** `tests/test_duplicate_replay.py:490-569`
- **Problem:** The test commits the offset of every consumed message (`original_consumer.commit_message(msg)`), then constructs `replay_consumer` with the **same** `group_id` and `auto.offset.reset=earliest`. Because a committed offset exists, Kafka resumes from the committed offset (end of partition) and redelivers nothing, so `replay_messages` is always empty. The `if replay_messages:` block (lines 545-564) — which contains the actual replay-dedup assertions (`published_valid == 0`, `duplicates_skipped == len(replay_messages)`, `EVENTS_DUPLICATE == len(replay_messages)`) — is never executed. The only executed assertion is the trivial `assert dedup_state.size == 3` (line 569).
- **Impact:** The task's primary "Kafka replay" requirement is not demonstrated at all. The docstring ("reset consumer offsets … all events redelivered") does not match the code, and the test passes vacuously. This is exactly the "test that does not actually exercise the requirement" failure mode the review must flag.
- **Recommendation:** Actually reset the consumer group offset (e.g., `commit_offsets` a `TopicPartition(..., 0)` back to zero for the assigned partition) or use a fresh group with `auto.offset.reset=earliest` and no commits, then assert the replayed events are all detected as duplicates and `published_valid == 0`. Remove the dead `else` fallback.

### F2 — MODERATE — Scenario 4 "end-to-end" claim is overstated; PostgreSQL dedup uses unrelated synthetic data
- **File/line:** `tests/test_duplicate_replay.py:627-701` (especially 681-682)
- **Problem:** After processing duplicate Kafka events through `ProcessorPipeline`, the test builds a *separate* Parquet file with brand-new event IDs (`warehouse_event_ids = [f"evt-e2e-pg-{i}" ...]`, line 681) and loads that into PostgreSQL. The validated events from the Kafka→Processor leg never flow into the warehouse. "Deduplication across service boundaries" is therefore not actually demonstrated end-to-end.
- **Impact:** The warehouse idempotency check itself is valid, but the test's name and the commit message ("end-to-end … across full pipeline") overstate what is verified. A reader could conclude the Kafka events were deduplicated through to PostgreSQL when they were not.
- **Recommendation:** Either route the processor's validated output into the Parquet/loader leg (so the same event IDs appear in PostgreSQL), or retitle/descope the test to make clear it verifies two independent boundaries rather than a single end-to-end flow.

### F3 — MODERATE — Parquet duplicate prevention is not demonstrated
- **File/line:** `tests/test_duplicate_replay.py:705-764`
- **Problem:** The task requires verifying "replayed events do not create duplicate logical records in PostgreSQL **or Parquet**." `TestReplayNoParquetDuplicates::test_multiple_replays_emit_no_duplicates` never reads or writes a Parquet file and never asserts anything about Parquet records; it only re-processes the same in-memory `messages` through the pipeline three times and asserts processor counts. The Parquet half of the objective is untested anywhere in the file.
- **Impact:** Requirements-coverage gap. The "no duplicate Parquet records" property is claimed by naming and the commit message but is not backed by any test.
- **Recommendation:** Either add a Parquet-level replay assertion (e.g., write Silver Parquet, replay via Lake Writer / re-read and assert no duplicate `event_id` rows) or rename the scenario to accurately describe what it tests (processor-level replay) and record the Parquet gap as out of scope.

### F4 — MINOR — Dead helper and unused imports; validated topic never independently verified
- **File/line:** `tests/test_duplicate_replay.py:25, 53, 328-344`
- **Problem:** `_consume_validated_json` is defined but never called, and its supporting imports (`json`, `VALIDATED_TOPIC`) are otherwise unused. As a result, no test independently confirms the number of records actually published to `products.validated.v1`; every assertion relies solely on `ProcessorPipeline`'s self-reported `PipelineResult` counts.
- **Impact:** Reduced confidence and dead code. The pipeline counts are trustworthy only because the validated producer is synchronous and raises on failure, but the downstream effect is never observed.
- **Recommendation:** Call `_consume_validated_json` in Scenario 1 (and/or 4/5) to assert the validated topic holds exactly the expected unique events, or delete the dead helper and unused imports.

### F5 — MINOR — "Log" detection is configured but never asserted
- **File/line:** `tests/test_duplicate_replay.py:656`
- **Problem:** Scenario 4 enables `caplog.at_level(logging.DEBUG, logger="services.processor")` but never asserts any captured log record. The failure lifecycle requires `Detection -> Metric/log`; only the metric arm is verified.
- **Impact:** The "log" half of the detection requirement is not demonstrated.
- **Recommendation:** Assert a relevant processor log (e.g., duplicate/log-event emitted during dedup) inside the `caplog` context, or remove the unused `caplog` context.

## 6. Non-Defect Observations

- The fixture scaffolding is solid and consistent with TASK-101/103: Docker-daemon skip, isolated Compose projects via `COMPOSE_PROJECT_NAME`, random port binding to avoid collisions, and a per-test `CREATE DATABASE` + alembic migration for full PostgreSQL isolation.
- Scenario 3 is a clean, correct demonstration of warehouse idempotency through the `event_id` UNIQUE constraint (`ON CONFLICT (event_id) DO NOTHING` + conflict escalation in `_insert_observations`).
- Scenario 1 correctly exercises the full `Failure → Detection (EVENTS_DUPLICATE) → Recovery → No silent data loss` loop at the processor level, and Scenario 5 (despite its name) is a valid processor-level replay-of-a-batch demonstration.
- No secrets, no production-code changes, no new dependencies, and no test weakening of existing suites. `ruff check` and `ruff format --check` pass.

## 7. Verdict

**CHANGES REQUIRED**

Blocking rationale: F1 is a High finding — the "Kafka replay" scenario, a primary objective of the task, is never actually executed (its core assertions are unreachable), so the test passes vacuously. F2 and F3 additionally leave the "end-to-end across service boundaries" and "Parquet" halves of the objective unverified.

The implementation otherwise conforms to repository conventions and the duplicate-detection and PostgreSQL-idempotency aspects are genuinely covered. Resolving F1 (and, ideally, F2-F5) is required before acceptance.
