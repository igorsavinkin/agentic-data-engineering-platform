# TASK-104 Review — Duplicate/Replay Test

## 1. Review Header

- **Task ID:** TASK-104 — Duplicate/Replay Test
- **Review date:** 2026-09-24
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:** `8c7fd7b27c5f127e78481bcc5ab38ae232d47ff2..3a8674285f5869da2dcad92284c82a9086ddedb0`
- **Reviewed HEAD:** `3a8674285f5869da2dcad92284c82a9086ddedb0` (`fix(TASK-104): address Qwen review findings F1-F5`)
- **Branch:** `feature/TASK-104`
- **Scope:** one new file, `tests/test_duplicate_replay.py` (final state 721 lines), plus a prior review record `docs/reviews/TASK-104-review.md`
- **Verdict:** CHANGES REQUIRED

This is a re-review of the current HEAD after the implementer addressed a prior Qwen review
(recorded at `d6aac4631fdc74a243718d6bad28bcbd3426323c`, verdict CHANGES REQUIRED, findings F1–F5).
The prior review is superseded by this report.

---

## 2. Requirements Coverage

Source of truth: `ai/tasks/TASK-104-duplicate-replay-test.md`, with `ai/PROJECT.md` §5
(at-least-once + idempotent processing) and `ai/SPECIFICATION.md` §9 (a duplicate event must not
result in duplicate logical observations in the final analytical/serving layer).

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Demonstrate duplicate-event handling | Met | Scenario 1 (`test_duplicate_events_deduplicated_with_metrics`, line 386) publishes the same event twice and asserts `published_valid == 1`, `duplicates_skipped == 1`, `EVENTS_DUPLICATE == 1`, `EVENTS_PROCESSED == 2`, and `dedup_state.size == 1`. |
| Demonstrate Kafka replay (offset reset → redelivery) | Met | Scenario 2 (`test_replay_with_dedup_state_skips_seen_events`, line 452) now actually replays: the first consumer no longer commits offsets, so the second consumer in the same group redelivers all 3 messages and the dedup assertions are unconditionally executed (see §5, prior-F1 resolution). |
| Replayed events do not create duplicate logical records in PostgreSQL | Met | Scenario 3 (line 546) loads the same Parquet file twice through `WarehouseLoader`; the second load creates `0` observations. Backed by `uq_product_observations_event_id` (migration `002`) and `ON CONFLICT (event_id) DO NOTHING`. |
| Replayed events do not create duplicate logical records in Parquet | **Not met** | No Parquet-level assertion exists anywhere in the file. Scenario 5 was renamed to `TestMultipleProcessorReplays` (processor-level replay), and the Parquet half of the objective is neither tested nor recorded as out of scope (see R1). |
| Deduplication across service boundaries | Partially met | Processor dedup and warehouse idempotency are each verified, but as two *independent, disconnected* boundaries using disjoint synthetic event IDs — not a connected cross-boundary flow (see R2). |
| Failure → Detection → Metric/log → Recovery → No silent data loss | Partially met | The metric arm (`EVENTS_DUPLICATE`) is asserted; the log arm is not (see R3). |
| Repeatable/deterministic | Met | Fixed partition key (`_SAME_EXTERNAL_ID` → all events land in one partition), isolated Compose projects with random ports, fresh per-test DBs/consumer groups. |
| Reuse existing dedup/idempotent semantics | Met | Uses `DeduplicationState`, `ProcessorMetrics`, `ProcessorPipeline`, `WarehouseLoader` as-is; no production-code changes in the reviewed range. |

---

## 3. Git Diff Review

The reviewed range contains three commits:

- `d6aac46` — `feat(TASK-104): add duplicate/replay integration tests` (adds `tests/test_duplicate_replay.py`, 763 lines)
- `40102ad` — `docs: Record TASK-104 Qwen review (CHANGES REQUIRED)` (adds the prior review record)
- `3a86742` — `fix(TASK-104): address Qwen review findings F1-F5` (reworks `tests/test_duplicate_replay.py`, −88/+45)

Net diff (`8c7fd7b..3a86742`):

- `tests/test_duplicate_replay.py` — added
- `docs/reviews/TASK-104-review.md` — added (review record)

- **Scope correctness:** All changes belong to TASK-104. No production, config, infrastructure, or migration code was modified.
- **Unrelated changes:** None.
- **Architectural changes:** None. Service boundaries (processor, Lake Writer, Warehouse Loader) are exercised, not altered.
- **Accidental changes:** None (no debugging code, temporary files, generated artifacts, or secrets).
- **Dependencies/configuration:** No new dependencies. The test reuses `confluent_kafka`, `polars`, `psycopg2`, `alembic`, and the existing `docker-compose.yml` stack.
- **Branch/task isolation:** Correct — work is on `feature/TASK-104`; working tree clean at review time.

---

## 4. Test and Verification Review

### Tests examined

Five integration tests (all under `pytestmark = pytest.mark.integration`):

1. `TestDuplicateDeliveryDetection::test_duplicate_events_deduplicated_with_metrics`
2. `TestKafkaReplayDeduplication::test_replay_with_dedup_state_skips_seen_events`
3. `TestCrossBatchDeduplication::test_warehouse_prevents_duplicates_after_processor_restart`
4. `TestIndependentDedupBoundaries::test_processor_and_warehouse_each_prevent_duplicates`
5. `TestMultipleProcessorReplays::test_multiple_replays_emit_no_duplicates`

The file follows the established integration-test conventions of `test_kafka_failure.py` (TASK-101)
and `test_processor_crash.py` (TASK-103): Docker-daemon skip, isolated Compose projects via
`COMPOSE_PROJECT_NAME`, random host ports, alembic migration against a fresh per-test database, and
a module-level `# mypy:` escape hatch.

### Verification status

- **Independently verified (reviewer executed):**
  - `python -m pytest tests/test_duplicate_replay.py --collect-only -m integration -q` → 5 tests collected; module imports cleanly.
  - `python -m ruff check tests/test_duplicate_replay.py` → All checks passed.
  - `python -m ruff format --check tests/test_duplicate_replay.py` → 1 file already formatted.
- **Unverified (not independently executed):**
  - `python -m pytest -m integration` was **not** run by the reviewer (requires a live Docker Kafka/PostgreSQL stack). No test-run report or captured results exist in the repository, so there is **no implementation evidence** that the full integration suite was executed and passed. Given the task scope touches Kafka and PostgreSQL, this evidence gap is material and is carried forward from the prior review unchanged.

Note: `pyproject.toml` sets `addopts = "-m 'not integration'"`, so the default `pytest` run deselects all five tests. The DoD requires `python -m pytest -m integration` to be run separately; no evidence of that run is present.

---

## 5. Findings

### R1 — HIGH — Parquet duplicate prevention remains undemonstrated and undocumented
- **File/line:** `tests/test_duplicate_replay.py:662-721` (`TestMultipleProcessorReplays`)
- **Problem:** The task objective states the test "must verify that replayed events do not create duplicate logical records in PostgreSQL **or Parquet**." No test in the file reads or writes a Parquet file through the lake writer, and none asserts anything about Parquet record counts. Scenario 5 was renamed (prior F3) from "Replay does not create duplicate Parquet records" to "Multiple processor replay passes emit no duplicates" — an accurate rename, but the Parquet half of the objective is now simply absent rather than deferred. The prior F3 recommendation offered "rename … **and record the Parquet gap as out of scope**"; the out-of-scope record was not added.
- **Impact:** A named objective target is entirely unverified and its omission is undocumented, so a reader could not tell whether Parquet deduplication was deliberately descoped or accidentally missed. The task's Definition of Done ("objective … verified by focused tests") is not satisfied for the Parquet clause.
- **Recommendation:** Either (a) add a Parquet-level replay assertion — e.g. write the same validated event twice through `SilverWriter` and assert the deterministic `event_id`-derived object key is overwritten rather than duplicated, or read the Silver layer back and assert unique `event_id` rows — or (b) explicitly record in the test docstring/task that Parquet deduplication is provided by TASK-022's deterministic object keys and is out of scope for TASK-104's processor+warehouse focus. As written, the gap is silent.

The platform *does* provide the property: `SilverWriter._write_single` (`libs/lake_writer/silver_writer.py`) writes one Parquet object per event keyed by `build_partition_key(...)` which is derived from `event_id`, so a replay of the same `event_id` overwrites the same object key rather than producing a duplicate file. This makes option (a) a small, well-bounded addition.

### R2 — MODERATE — "Across service boundaries" is demonstrated as two disconnected boundaries, not a connected flow
- **File/line:** `tests/test_duplicate_replay.py:576-660` (especially `warehouse_event_ids` at line 638)
- **Problem:** `TestIndependentDedupBoundaries` processes duplicate Kafka events through the processor (asserting processor dedup + metrics), then builds a *separate* Parquet batch with brand-new `warehouse_event_ids = [f"evt-e2e-pg-{i}"]` and loads that into PostgreSQL. The Kafka→processor leg and the warehouse leg never share an event. The rename to "independent dedup boundaries" is honest, but the task's "deduplication works across service boundaries" is satisfied only in the "multiple independent boundaries" sense, not as a single event traced through the processor → warehouse path.
- **Impact:** Coverage nuance, not a correctness defect. The two boundaries are each genuinely exercised; only the connected-flow interpretation is absent.
- **Recommendation:** Acceptable as-is given the honest rename; optionally add one scenario that feeds the processor's *actual* validated events into the warehouse leg so the same `event_id` set crosses both boundaries. Otherwise, this finding can be closed as a documented scope decision.

### R3 — MINOR — "Log" half of the failure lifecycle is not asserted
- **File/line:** `tests/test_duplicate_replay.py` (no `caplog` usage remains)
- **Problem:** The failure-engineering rule requires `Detection -> Metric/log`. The metric arm is asserted (`EVENTS_DUPLICATE`), but no log is asserted. The prior F5 recommended asserting a log or removing the unused `caplog`; the `caplog` was removed. `ProcessorPipeline.process_batch` emits no duplicate-specific log (the `processor_batch_complete` log with a `duplicates` field lives in `services/processor/__main__.py`'s run loop, which the test bypasses), so a caplog assertion against the pipeline would currently find nothing without a production change.
- **Impact:** The "Metric/log" requirement is effectively satisfied by the metric arm; the log arm is undocumented rather than broken.
- **Recommendation:** Either accept "metric" as satisfying "Metric/log" and note it, or add a duplicate-detection log at the pipeline level (out of TASK-104's test-only scope). No action strictly required.

### R4 — MINOR — Scenario 3 name/docstring overstate a "processor restart" that is never simulated
- **File/line:** `tests/test_duplicate_replay.py:536-573`
- **Problem:** `TestCrossBatchDeduplication::test_warehouse_prevents_duplicates_after_processor_restart` and its class docstring describe a processor restart ("processor restarts, same events redelivered from Kafka"). The test body performs only a warehouse double-load of the same Parquet batch; no processor, Kafka consumer, or `DeduplicationState` reset is involved.
- **Impact:** Misleading naming only; the warehouse-idempotency assertion itself is correct and meaningful.
- **Recommendation:** Rename to reflect what is tested (e.g. `test_warehouse_prevents_duplicates_on_reload`) and align the docstring, or add an actual processor-restart simulation.

### Resolution of prior findings F1–F5

- **F1 (was HIGH) — resolved.** The `original_consumer.commit_message(msg)` loop was removed. `KafkaConsumer` configures `enable.auto.commit = False` and `enable.auto.offset.store = False` (verified in `libs/common/kafka_consumer.py`), so no offset is committed without an explicit call; the replay consumer uses the same `group_id` with `auto.offset.reset = "earliest"` and therefore genuinely redelivers all 3 messages. The dead `if replay_messages:`/`else` branch was replaced with an unconditional hard `assert len(replay_messages) == 3` and unconditional dedup assertions, so the test is no longer vacuous.
- **F2 (was MODERATE) — resolved.** Scenario 4 renamed to `TestIndependentDedupBoundaries` with a docstring that honestly describes two independent safeguards.
- **F3 (was MODERATE) — partially resolved.** Scenario 5 renamed accurately, but the Parquet gap was not recorded as out of scope; this is re-raised as R1.
- **F4 (was MINOR) — resolved.** Dead `_consume_validated_json` helper and unused `json`, `logging`, `VALIDATED_TOPIC`, `INVALID_TOPIC` imports removed.
- **F5 (was MINOR) — resolved.** Unused `caplog` context removed (the log-detection nuance is re-raised as R3).

---

## 6. Non-Defect Observations

- The fixture scaffolding is solid and consistent with TASK-101/103: Docker-daemon skip, isolated Compose projects via `COMPOSE_PROJECT_NAME`, random port binding, and a per-test `CREATE DATABASE` + alembic migration for full PostgreSQL isolation.
- Scenario 3 is a clean, correct demonstration of warehouse idempotency through the `event_id` UNIQUE constraint (`ON CONFLICT (event_id) DO NOTHING` plus explicit conflict escalation in `_insert_observations`).
- Scenario 1 correctly exercises the full `Failure → Detection (EVENTS_DUPLICATE) → Recovery → No silent data loss` loop at the processor level; Scenario 2 now genuinely exercises Kafka redelivery; Scenario 5 is a valid processor-level replay-of-a-batch demonstration.
- The validated-output producer (`KafkaValidatedOutputProducer.publish`) is synchronous and raises on delivery failure, so the pipeline's self-reported `published_valid`/`duplicates_skipped` counts are trustworthy even though no test independently re-reads `products.validated.v1`.
- No secrets, no production-code changes, no new dependencies, and no test weakening of existing suites. `ruff check` and `ruff format --check` pass; collect-only confirms the module imports cleanly.

---

## 7. Verdict

**CHANGES REQUIRED**

Blocking rationale: R1 — the task objective explicitly requires verifying that replayed events create
no duplicate logical records "in PostgreSQL **or Parquet**," and the Parquet half is entirely
untested and not documented as out of scope. Because the deliverable of a test task is precisely
its coverage, an unverified named objective target is a "must fix before acceptance" condition. The
fix is small: add a SilverWriter-level replay assertion, or record the gap as out of scope with
justification.

The previously blocking finding (F1, the vacuous Kafka-replay test) is now resolved and verified
correct, and the remaining issues (R2–R4) are Moderate/Minor. Resolving R1 is required before
acceptance.
