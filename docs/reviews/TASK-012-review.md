# TASK-012 Review — Kafka Integration Tests

## 1. Review Header

- **Task ID:** TASK-012 — Kafka Integration Tests
- **Review date:** 2026-09-10
- **Reviewed change set:** `54b0f18..b9fc8f4` (single commit `b9fc8f4` — `feat: Add Kafka integration tests for TASK-012`)
- **Scope:** New integration test suite `tests/test_kafka_integration.py` (917 lines) covering the Milestone 1 event-platform scenarios. No production code changed.
- **Verdict:** **CHANGES REQUIRED** — several tests in the deliverable are statically provable to fail (broken imports, wrong exception assertions, wrong DLQ-envelope assertions), and the change was committed directly to `main` rather than `feature/TASK-012`.

---

## 2. Requirements Coverage

Sources: `ai/tasks/TASK-012-kafka-integration-tests.md`, `ai/ROADMAP.md` §5 (Milestone 1), `ai/SPECIFICATION.md` §7–§10 and §22, `ai/PROJECT.md` §5/§12.

| Requirement | Status | Implementation evidence |
| --- | --- | --- |
| Producer → Kafka → Consumer end-to-end | ✅ Met | `test_end_to_end_event_delivery` and `test_complete_event_flow_from_source_to_consumption` publish via `KafkaEventProducer`, consume via `KafkaConsumer`, and assert `event_id`/`payload` integrity and committed offsets. |
| Valid event handled by consumer | ✅ Met | Covered by the end-to-end tests above. |
| Malformed event handled | ✅ Met | `test_malformed_json_handling` produces raw invalid-JSON bytes directly to `products.raw.v1` and asserts a `DeserializationError` with `raw_value`. Correct approach. |
| Invalid event (schema / missing field) | ❌ Not met | Three tests are broken: `test_invalid_event_rejected_by_producer`, `test_schema_validation_error_handling`, and `test_invalid_event_does_not_corrupt_pipeline` all call `deserialize_event(...)` on invalid input, which raises `pydantic.ValidationError` before the intended code path runs (see F3). |
| Duplicate event / at-least-once | ✅ Met | `test_duplicate_events_delivered_to_consumer`, `test_downstream_deduplication_by_event_id`, and `test_duplicate_tolerance_meets_at_least_once_semantics` assert both deliveries arrive and that `event_id` deduplication reduces to one logical event. |
| Consumer restart / offset management | ✅ Met (consumer-level) | `test_committed_offsets_survive_restart`, `test_uncommitted_messages_redelivered_after_restart`, `test_graceful_shutdown_leaves_offsets_intact` create a second consumer on the same group and assert committed/uncommitted behavior. |
| Failure/retry path | ⚠️ Partially met | `test_transient_processing_error_with_retry` (valid imports, correct logic) and `test_kafka_unavailable_handling` are sound. `test_permanent_failure_routes_to_dlq` is broken (ImportError + wrong assertions, F2). `test_consumer_handles_kafka_restart` does not actually test broker restart (F4). |
| Demonstrates Milestone 1 acceptance criteria | ❌ Not met | The acceptance criteria require correct handling of valid, malformed, duplicate, and restart cases. The invalid-event and permanent-DLQ tests are non-functional, so the suite does not demonstrate the criteria as written. |

---

## 3. Git Diff Review

- **Scope correctness:** Single new file `tests/test_kafka_integration.py`; all changes nominally belong to TASK-012. No production code or unrelated files touched.
- **Branch/task isolation:** ❌ **Violation.** The commit `b9fc8f4` is on `main` (working tree is `main`, "ahead of origin/main by 1 commit"), not `feature/TASK-012`. `ai/AGENTS.md` §16 ("Git Task Isolation") requires each `TASK-xxx` in its own `feature/TASK-xxx` branch. This is a process/scope finding even though the code is task-scoped (see F1).
- **Unrelated changes:** None.
- **Architectural changes:** None. The tests exercise existing `libs/common` and `libs/event_contracts` interfaces.
- **Accidental changes / debug / secrets:** None. No generated artifacts, no credentials. Docker Compose variables (`KAFKA_HOST_PORT`, `COMPOSE_PROJECT_NAME`, `PLATFORM_NETWORK_NAME`) are randomized per test.
- **Dependencies/configuration:** No new third-party dependencies. `confluent_kafka.Producer` is used directly in two tests (already a project dependency). `pyproject.toml`/CI/infra unchanged.

---

## 4. Test and Verification Review

- **Tests examined:** `tests/test_kafka_integration.py` (17 `@pytest.mark.integration` tests in 6 classes), traced against `libs/common/kafka_producer.py`, `libs/common/kafka_consumer.py`, `libs/common/kafka_errors.py`, `libs/event_contracts/product_observation.py`, `scripts/manage_kafka_topics.py`, and `docker-compose.yml`.
- **Test adequacy:** Below the required bar because the "invalid event" and "permanent failure/DLQ" scenarios — core Milestone 1 acceptance cases — are not correctly tested (F2, F3). The ordering test does not assert ordering (F5), and the "Kafka restart" test does not restart Kafka (F4).
- **Independently verified (reviewer-executed):**
  - `ruff check tests/test_kafka_integration.py` → **passed** (no lint errors).
  - `pytest --collect-only -q -m integration tests/test_kafka_integration.py` → **17 tests collected** (module imports cleanly; collection does not execute test bodies).
  - Reproduced the failure modes by direct invocation:
    - `deserialize_event({"event_id":"x","source":"s","produced_at":"..."})` (missing `payload`) raises `pydantic_core.ValidationError`, **not** `EventSerializationError`.
    - `from libs.common.kafka_errors import ProcessingError` raises `ImportError` (`ProcessingError` lives in `kafka_consumer.py`).
    - `diagnostic_envelope(...)` returns top-level keys `[event_id, event_type, payload, produced_at, schema_version, source]`; `error_type` is nested under `payload`, and `event_id` is a generated `uuid5` unrelated to the source event id.
- **Implementation evidence reviewed:** The commit message claims the tests "are properly marked ... and excluded from default test runs" and "use isolated Docker Compose projects". The marker/exclusion claim is accurate; the claim of functional coverage is not supported by the code.
- **Unverified:** The 17 integration tests were **not** executed against a live Kafka broker (they require Docker and are expensive; several are statically provable to fail, so execution was not justified). They are also **excluded from CI**: `pyproject.toml` sets `addopts = "-m 'not integration'"` and `.github/workflows/ci.yml` runs plain `pytest`, so nothing in CI would catch these defects (F7).

---

## 5. Findings

### F1 — Task committed to `main`, not `feature/TASK-012` (High, process/scope)

- **File/ref:** commit `b9fc8f4`; `git branch` = `main`.
- **Problem:** The TASK-012 change is committed directly on `main`, violating the `feature/TASK-xxx` branch-isolation rule in `ai/AGENTS.md` §16.
- **Impact:** Breaks the documented one-task-per-branch workflow and makes the task change indistinguishable from trunk history; other TASK changes could silently interleave.
- **Recommendation:** Re-do the commit on `feature/TASK-012` (or otherwise align with the team's branch policy) before accepting.

### F2 — `test_permanent_failure_routes_to_dlq` is broken (High)

- **File/ref:** `tests/test_kafka_integration.py:658-700` (local import line 660; assertions lines 696-697).
- **Problem:** Three independent defects:
  1. `from libs.common.kafka_errors import DeadLetterSink, ProcessingError` → `ProcessingError` is defined in `libs/common/kafka_consumer.py`, not `kafka_errors.py`. Verified `ImportError`.
  2. `assert envelope["event_id"] == valid_event.event_id` → `diagnostic_envelope()` generates a new `uuid5` envelope id; it does not preserve the source event id. Verified the envelope id is unrelated.
  3. `assert envelope["error_type"] == "ProcessingError"` → `error_type` is nested under `envelope["payload"]`, not top-level. Verified top-level keys are `[event_id, event_type, payload, produced_at, schema_version, source]`; the assertion raises `KeyError`.
- **Impact:** The test cannot pass as written (ImportError first; then assertion failures). The "permanent failure routes to DLQ" scenario is effectively untested.
- **Recommendation:** Import `ProcessingError` from `libs.common.kafka_consumer`; assert `envelope["payload"]["error_type"] == "ProcessingError"` and the envelope `event_id`/`source` per the actual `diagnostic_envelope` contract (or assert the base64 `raw_value` decodes to the original event).

### F3 — Invalid-event tests misuse `deserialize_event`, so they raise the wrong exception (High)

- **File/ref:**
  - `tests/test_kafka_integration.py:304-308` (`test_invalid_event_rejected_by_producer`)
  - `tests/test_kafka_integration.py:375` (`test_schema_validation_error_handling`)
  - `tests/test_kafka_integration.py:840-843` (`test_invalid_event_does_not_corrupt_pipeline`)
- **Problem:** Each test constructs invalid data and passes it through `deserialize_event(...)` first. `deserialize_event` validates with Pydantic and raises `pydantic.ValidationError` (for missing `payload`, and for `schema_version=999`), **before** `KafkaEventProducer.publish()` or the broker write is reached. The `pytest.raises(EventSerializationError)` wrapper never matches.
- **Impact:** These three tests error out (fail) rather than exercising producer rejection or consumer-side schema validation. This is the core "invalid event" acceptance scenario.
- **Recommendation:**
  - To test producer rejection, build a *valid* `ProductObservationEvent` and mutate it (e.g. `event.schema_version = 99`), matching the existing unit test `test_mutated_invalid_event_never_enqueues`.
  - To test consumer-side schema validation, produce raw JSON bytes with `schema_version: 999` directly to `products.raw.v1` (as `test_malformed_json_handling` does), without calling `deserialize_event` on the invalid payload.

### F4 — `test_consumer_handles_kafka_restart` does not restart Kafka (Moderate)

- **File/ref:** `tests/test_kafka_integration.py:726-754`.
- **Problem:** The test name and docstring claim "recover after brief Kafka broker interruption", but the body only publishes and consumes one event. `real_broker` is a parameter but is never used to stop/restart the broker.
- **Impact:** The task's "Failure/retry path" scenario (broker interruption/recovery) is not actually covered; the test is a mislabeled duplicate of the basic end-to-end case.
- **Recommendation:** Either implement an actual broker stop/start (e.g. `docker compose stop kafka` / `start kafka`) and assert recovery, or rename the test to reflect what it actually does.

### F5 — Ordering test never asserts ordering (Moderate)

- **File/ref:** `tests/test_kafka_integration.py:230-293` (`test_multiple_events_preserve_ordering_within_partition`).
- **Problem:** `consumed_events` is collected in consumption order but never compared against the published order. The test only asserts all 5 land in one partition and that the *receipt* offsets are sequential; it never verifies that consumed events arrive in the published sequence.
- **Impact:** The advertised "ordering within partition" behavior is not validated.
- **Recommendation:** Assert `[m.event.event_id for m in consumed] == [e.event_id for e in events]` (or the `name` sequence), in addition to the partition/offset checks.

### F6 — Single-`poll` pattern risks flakiness (Moderate)

- **File/ref:** `tests/test_kafka_integration.py` lines 335, 387, 513, 524, 546, 557, 581, 592, 743, 796, 857.
- **Problem:** Several tests call `consumer.poll(timeout=...)` exactly once and assert on the result, whereas the rest of the file (and the existing `test_kafka_producer.py`/`test_kafka_errors.py` integration tests) use a deadline-bounded retry loop. With a fresh consumer group, the first poll can return `None`/`_PARTITION_EOF` during initial rebalance/assignment.
- **Impact:** Intermittent failures that are not deterministic, especially under slower Docker startup.
- **Recommendation:** Use the deadline-bounded poll loop consistently for any test that must observe at least one record.

### F7 — Integration suite excluded from CI and expensive to run (Moderate)

- **File/ref:** `pyproject.toml` (`addopts = "-m 'not integration'"`), `.github/workflows/ci.yml` (plain `pytest`); `real_broker` fixture in `tests/test_kafka_integration.py:96-157`.
- **Problem:** The deliverable is never executed by CI. Additionally, `real_broker` is function-scoped and starts a fresh Kafka Compose project (`up --wait` + topic creation + `down --volumes`) for ~16 of 17 tests, so a full run is slow and resource-heavy and has no automated gate.
- **Impact:** Broken tests (F2/F3) go unnoticed, and the suite is unlikely to be run regularly.
- **Recommendation:** Decide and document how/where these tests run (e.g., a Docker-capable CI job). Consider a session-scoped broker with per-test topic/group isolation to reduce the per-test startup cost.

### F8 — Dead fixture and dead code (Minor)

- **File/ref:** `duplicate_event` fixture at `tests/test_kafka_integration.py:90` is never referenced; the `events` list at line 259 is appended but never read.
- **Impact:** Minor clutter; the unused fixture suggests an intended duplicate-event scenario that was never wired up.
- **Recommendation:** Remove the unused fixture/list, or use them in the appropriate tests.

### F9 — Inconsistent import placement (Minor)

- **File/ref:** local imports at `tests/test_kafka_integration.py:320,353,610,642,660,673` (e.g. `from confluent_kafka import Producer`, `from libs.common.kafka_errors import ...`).
- **Problem:** Imports are placed inside function bodies and some functions have two separate `from libs.common.kafka_errors import ...` statements, diverging from the project's top-of-module import convention.
- **Impact:** Readability/consistency only; no runtime effect.
- **Recommendation:** Hoist imports to module top per the surrounding test files.

---

## 6. Non-Defect Observations

1. **Placeholder commit identity.** The commit author is `Workflow Test <workflow@example.invalid>`, consistent with the automated workflow described in `docs/AUTOMATED_TASK_WORKFLOW.md`. Not a defect, but the reviewer should not treat the commit identity as evidence of human review.
2. **Broker fixture creates all five topics.** Unlike `test_kafka_producer.py` (which creates only `TOPICS[0]`), `real_broker` here iterates `manager.TOPICS`. This is correct and more complete, and mirrors the `products.invalid.v1` requirement for DLQ.
3. **DLQ scenario uses an in-memory sink.** `test_permanent_failure_routes_to_dlq` routes to a local list-based `DeadLetterSink`, not the real `KafkaDeadLetterProducer`/`products.invalid.v1` topic. That is reasonable for testing `process_next`'s routing decision; the real broker DLQ path is already covered by `test_real_dlq_failure_restart_and_offset` in `tests/test_kafka_errors.py`.
4. **Sequential-offset assumption.** `test_multiple_events_preserve_ordering_within_partition` assumes exact `offset[i+1] == offset[i]+1`, which holds for a single idempotent producer to one partition but is a stronger assertion than ordering requires.

---

## 7. Verdict

**CHANGES REQUIRED**

Blocking findings:

- **F2** — `test_permanent_failure_routes_to_dlq` cannot run (ImportError) and asserts against the wrong DLQ-envelope shape.
- **F3** — three invalid-event tests raise `pydantic.ValidationError` instead of the intended exception/path, so the "invalid event" acceptance scenario is not demonstrated.
- **F1** — the change is on `main`, not `feature/TASK-012`, violating the branch-isolation rule.

The task's deliverable is the test suite itself, so non-functional tests are equivalent to missing functionality. F4–F6 materially weaken coverage/robustness and should be addressed with the blocking fixes. F7–F9 are non-blocking but recommended.
