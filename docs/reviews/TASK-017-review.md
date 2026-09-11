# TASK-017 Review — Invalid Event / DLQ Handling

**Task ID:** TASK-017
**Review date:** 2026-09-11
**Reviewed change set:** `fd75588..e0dde91` (commit `e0dde917686636560a9e1463399eecf9d23ec9d5`)
**Scope:** Processor outcome routing to canonical Kafka topics and a validated-output producer.
**Verdict:** APPROVED WITH NON-BLOCKING FINDINGS

## 1. Review Header

- **Branch:** `feature/TASK-017` (correct, matches the task).
- **Commit:** `e0dde91` "Implement TASK-017: Invalid Event / DLQ Handling".
- **Files changed (4, all additive):**
  - `libs/common/kafka_validated_producer.py` (152 lines, new)
  - `services/processor/pipeline.py` (279 lines, new)
  - `tests/test_pipeline.py` (507 lines, new)
  - `tests/test_validated_producer.py` (229 lines, new)
- **Authorities consulted:** `ai/PROJECT.md`, `ai/SPECIFICATION.md` §6/§8/§9/§10, `docs/adr/ADR-001-kafka-topic-configuration.md`, `ai/tasks/TASK-017-*.md`, and the TASK-008/009/010/015/016 implementation modules the new code depends on.

## 2. Requirements Coverage

| # | Requirement | Status | Evidence |
|---|-------------|--------|----------|
| 1 | Valid records → `products.validated.v1` | PASS | `ProcessorPipeline._publish_valid_records` calls `validated_sink`; `KafkaValidatedOutputProducer.publish` targets `VALIDATED_TOPIC`. Tests `TestValidRecordsRouting`. |
| 2 | Invalid records → `products.invalid.v1` | PASS | `_publish_invalid_records` and `_publish_conflict_records` call `invalid_sink` (the DLQ sink). Tests `TestInvalidRecordsRouting`, `test_dedup_conflict_to_invalid`. |
| 3 | Invalid representation preserves identity/source/reason/context without leaking secrets | PARTIAL | `validation_envelope`/`conflict_envelope` carry `event_id`, `source`, `reason`, `validation_errors`, and curated `context`. **Gap:** conflict envelopes lose per-record context (see Finding 2). |
| 4 | Malformed input retains diagnosable context | PASS | `test_validation_failure_has_context`; context omits raw bytes/credentials (only `external_id`, `name`, `url`, `category`, `source`, `schema_version`). |
| 5 | Offset/ack compatible with at-least-once | PASS | Pipeline raises `PublishError` on output failure and never commits; docstring documents that the caller must not commit. `KafkaConsumer.process_next` re-raises and closes without committing. |
| 6 | Do not mark input complete if output publication failed | PASS | Output failures raise `PublishError`; no commit is performed by the pipeline. Tests `TestOutputPublishFailure`. |
| 7 | Retry/replay consequences documented | PASS | Pipeline module docstring has "Retry / replay" and "Offset semantics" sections. |
| 8 | Invalid records never silently disappear | PASS (with note) | Every row maps to exactly one output category; the `msg is None` guard logs but drops — currently unreachable (see Observations). |
| 9 | Kafka remains transport, not analytical storage | PASS | Pipeline only routes; no persistence introduced. |

### Required Tests Coverage

| Required test | Status | Test |
|---------------|--------|------|
| valid → validated only | PASS | `TestValidRecordsRouting` |
| invalid → invalid only | PASS | `TestInvalidRecordsRouting` |
| multiple reasons preserved | PASS | `TestMultipleValidationReasons` |
| output publish failure | PASS | `TestOutputPublishFailure` |
| malformed input diagnostics | PASS | `TestMalformedInputDiagnostics` |
| retry/replay behavior | PASS | `TestRetryReplayBehavior` |

## 3. Git Diff Review

- **Scope correctness:** All four files belong to TASK-017 (routing + producer + tests). No files outside scope.
- **Unrelated changes:** None. The diff is purely additive and does not modify TASK-008/009/010/015/016 code.
- **Architectural changes:** None. The pipeline composes existing `events_to_polars` → `normalize` → `validate` → `deduplicate` without altering their interfaces. No service boundary or ownership change.
- **Accidental changes:** None. No debugging code, temporary files, generated artifacts, or secrets.
- **Dependencies/configuration:** No new dependencies (`confluent_kafka`, `polars`, `pydantic` already in use). No config/infra change.
- **Branch/task isolation:** Correct branch and a single focused commit; no other TASK changes included.

## 4. Test and Verification Review

### Tests examined
- `tests/test_pipeline.py` — routing, envelopes, failure, replay, dedup conflict, mixed outcomes, empty batch (507 lines).
- `tests/test_validated_producer.py` — topic constant, publish success/failure, close/drain (229 lines).

### Test adequacy
- Coverage is broad and directly exercises all six required test scenarios plus edge cases.
- **Gap:** `test_dedup_conflict_to_invalid` asserts only `event_id` and `reason`, so it does not catch the per-record context loss (Finding 2) or the `total` over-count (Finding 1). No test asserts `PipelineResult.total` in the presence of conflicts.

### Independently executed by the reviewer
- `python -m pytest tests/test_pipeline.py tests/test_validated_producer.py -q` → **24 passed**.
- `python -m pytest -q` → **379 passed, 29 deselected** (integration tests).
- `python -m ruff check <4 new files>` → **All checks passed**.
- `python -m ruff format --check <4 new files>` → **4 files already formatted**.
- `python -m mypy` → **Success: no issues found in 34 source files**.

### Implementation evidence reviewed
- The commit message reports 24 new tests; consistent with the independently executed result.

### Verification classification
- **Independently verified** — pytest, ruff, and mypy were executed by the reviewer.

## 5. Findings

### F1 — Moderate: `PipelineResult.total` double-counts conflicts
- **File/line:** `services/processor/pipeline.py` — `PipelineResult.total` property and `_publish_conflict_records`.
- **Problem:** `_publish_conflict_records` increments *both* `result.published_invalid` and `result.conflicts` for each conflict record. `total` sums all four counters, so a conflict-only batch of N records yields `total == 2N`, violating the documented invariant "the sum of all counts equals the input batch size".
- **Impact:** Incorrect summary accounting for any batch containing dedup conflicts. Not caught by tests because `test_dedup_conflict_to_invalid` does not assert `total`, and `test_mixed_batch` has no conflicts.
- **Recommendation:** Define `total = published_valid + published_invalid + duplicates_skipped` (since `published_invalid` already includes conflicts), or document `conflicts` as a diagnostic sub-count of `published_invalid` and exclude it from `total`. Add a test asserting `total` with conflicts present.

### F2 — Moderate: Deduplication conflict envelopes lose per-record context
- **File/line:** `services/processor/pipeline.py` — `process_batch` (event_index construction) and `_publish_conflict_records`.
- **Problem:** `event_index` is keyed by `event_id`. When two messages share an `event_id` with different payloads (the dedup conflict case), the dict keeps only the last message, so both conflict rows resolve to the same `ConsumerMessage` and both envelopes emit the same `_event_context` (e.g., the last event's `external_id`). One conflicting record's actual identity is lost.
- **Impact:** Weakens requirement 3 ("enough original context for diagnosis") specifically for conflicts, which are a first-class routed outcome. `test_dedup_conflict_to_invalid` uses `event1` (external_id `prod-1`) and `event2` (external_id `prod-2`) but only asserts `event_id`/`reason`, so the wrong-context bug is not caught.
- **Recommendation:** Preserve per-row context by mapping rows to messages without collapsing same-`event_id` entries (e.g., index by position or carry the event alongside the DataFrame row), or include both payloads in the conflict envelope.

### F3 — Moderate: Divergent `products.invalid.v1` envelope schemas
- **File/line:** `services/processor/pipeline.py` (`validation_envelope`, `conflict_envelope`) vs `libs/common/kafka_errors.py` (`diagnostic_envelope`).
- **Problem:** TASK-010's `diagnostic_envelope` and TASK-017's `validation_envelope`/`conflict_envelope` write to the same topic with incompatible shapes: `validation_errors` is a list in one and a semicolon-joined string in the other; `source` is the consumer group in one and the event source in the other; `event_id` is a deterministic uuid5 in one and the original event id in the other.
- **Impact:** Downstream consumers of `products.invalid.v1` must handle two schemas. The topic is a diagnostic sink (not analytical), so this is Moderate rather than High, but the ambiguity should be resolved or explicitly documented.
- **Recommendation:** Establish and document a single canonical invalid-topic envelope, or clearly scope each producer's shape. Reconcile in TASK-019 (integration) if the two paths are expected to coexist.

## 6. Non-Defect Observations

1. **Pipeline invalid-routing is unreachable through the normal consumer path.** `KafkaConsumer.poll()` Pydantic-validates every message via `deserialize_event`, so records that would fail DataFrame-level `validate()` (negative price, bad currency, invalid availability, unsupported schema version, null required fields) are already rejected at deserialization and routed via TASK-010's `diagnostic_envelope`. The TASK-017 invalid/conflict path is exercised only by unit tests using `model_construct`. This is layering (transport validation vs processor validation), but it should be reconciled so the platform does not have two divergent DLQ producers for the same input.

2. **Valid records are published as the original event, not the normalized record.** The pipeline publishes `msg.event` to `products.validated.v1`, discarding the `normalize()` output (e.g., UTC timestamp conversion, whitespace stripping). In practice the difference is small because Pydantic already canonicalizes most fields, but the Silver-layer contract ("validated/normalized observations") may expect normalized values. Worth confirming in TASK-019/019+.

3. **`KafkaValidatedOutputProducer` minor divergences from `KafkaEventProducer`:**
   - Redefines `DeliveryReceipt` instead of importing it from `libs.common.kafka_producer`.
   - Increments `KafkaMetric.PROCESSED` (a consumer/processing counter) on producer success, and `PRODUCER_ERRORS` on failure; there is no producer-side "validated events" metric.
   - Reuses `KafkaProducerSettings` whose default `kafka_client_id` is `"ingestion"` (and carries an irrelevant `kafka_raw_topic`). Processor-specific client id must be supplied at wiring time.
   - Does not re-validate the wire snapshot via `deserialize_event` before publishing, unlike the ingestion producer; acceptable given prior validation.

4. **`services/processor/pipeline.py` is outside mypy coverage.** `pyproject.toml` sets `mypy.files = ["scripts", "tests", "libs"]`, which excludes `services/`. The new pipeline module is therefore not type-checked (the new `libs` producer file is). Pre-existing config decision, but worth noting.

5. **`msg is None` guards in the three `_publish_*` helpers are effectively unreachable.** Every DataFrame row's `event_id` originates from the batch, so `event_index.get(event_id)` always succeeds. The guards are defensive; if ever reached, they would log-and-drop a record, which would contradict requirement 8.

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The implementation satisfies the task's core routing, offset, and diagnostic requirements, is well-scoped, adds no dependencies, and passes all tests, lint, format, and type checks (independently verified). Three Moderate findings should be addressed — the `total` accounting bug (F1), the conflict-context loss (F2), and the divergent invalid-topic envelope schemas (F3) — but none corrupt routing correctness or block acceptance of the current task; they are best resolved alongside TASK-019 (integration) where the two DLQ paths and the Silver contract are reconciled.
