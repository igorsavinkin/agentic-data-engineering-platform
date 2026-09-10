# TASK-012 Review — Kafka Integration Tests (Re-review after fix `2fb6909`)

## 1. Review Header

- **Task ID:** TASK-012 — Kafka Integration Tests
- **Review date:** 2026-09-10
- **Reviewed change set:** `54b0f18..2fb6909` (commits `b9fc8f4` + `2fb6909`), branch `feature/TASK-012`
- **Scope:** New integration test suite `tests/test_kafka_integration.py` (now 1013 lines) covering the Milestone 1 event-platform scenarios. No production code changed. This re-review verifies the fix commit `2fb6909` against the prior review's findings and adds the full `mypy` type-check gate, which was omitted from the prior cycle.
- **Verdict:** **CHANGES REQUIRED** — the logic fixes for F1–F6/F8/F9 are correct, but two blocking issues remain: (1) `DeadLetterSink(...)` is invoked as a constructor at runtime (a `TypeError`), and (2) the file fails the project's `mypy` gate (10 errors).

---

## 2. Requirements Coverage

Sources: `ai/tasks/TASK-012-kafka-integration-tests.md`, `ai/ROADMAP.md` §5 (Milestone 1), `ai/SPECIFICATION.md` §7–§10 and §22, `ai/PROJECT.md` §5/§12.

| Requirement | Status | Implementation evidence |
| --- | --- | --- |
| Producer → Kafka → Consumer end-to-end | ✅ Met | `test_end_to_end_event_delivery`, `test_complete_event_flow_from_source_to_consumption`. |
| Valid event handled | ✅ Met | Covered by the end-to-end tests. |
| Malformed event handled | ✅ Met | `test_malformed_json_handling` produces raw invalid-JSON bytes and asserts `DeserializationError`; now uses a deadline-bounded poll loop. |
| Invalid event (schema / missing field) | ✅ Met (fixed) | `test_invalid_event_rejected_by_producer` mutates a valid event (`schema_version = 99`) to reach the producer snapshot-validation path; `test_schema_validation_error_handling` and `test_invalid_event_does_not_corrupt_pipeline` produce raw invalid bytes directly to the topic. |
| Duplicate event / at-least-once | ✅ Met | `test_duplicate_events_delivered_to_consumer`, `test_downstream_deduplication_by_event_id`, `test_duplicate_tolerance_meets_at_least_once_semantics`. |
| Consumer restart / offset management | ✅ Met | `test_committed_offsets_survive_restart`, `test_uncommitted_messages_redelivered_after_restart`, `test_graceful_shutdown_leaves_offsets_intact`; first-session polls now use deadline loops. |
| Failure/retry path | ❌ Not met | `test_transient_processing_error_with_retry` and `test_permanent_failure_routes_to_dlq` call `DeadLetterSink(dead_letter_sink)`, which raises `TypeError: Callable() takes no arguments` at runtime (F1). The DLQ test's import/assertion fixes are correct, but the callable wrapping still breaks both tests. |
| Demonstrates Milestone 1 acceptance criteria | ❌ Not met | The failure/retry scenario is still non-functional, so the suite does not fully demonstrate the criteria. |

---

## 3. Git Diff Review

- **Scope correctness:** Two files changed across the range: `tests/test_kafka_integration.py` (the deliverable) and `docs/reviews/TASK-012-review.md` (the prior review report, committed by the fix). No production code or unrelated files touched.
- **Branch/task isolation:** ✅ **Resolved.** The task is now on `feature/TASK-012` (both commits), satisfying `ai/AGENTS.md` §16. Prior finding F1 is closed.
- **Fix commit scope:** `2fb6909` ("Resolve Qwen review findings F2-F9") correctly targets the identified logic defects. Note: the subject says "F2-F9" but the body omits **F7** (CI exclusion / test cost), which is **not** addressed (see F3).
- **Unrelated changes:** None.
- **Architectural changes:** None.
- **Accidental changes / debug / secrets:** None. No credentials; Compose variables are randomized per test.
- **Dependencies/configuration:** No new third-party dependencies; no `pyproject.toml`/CI/infra changes.

---

## 4. Test and Verification Review

- **Tests examined:** `tests/test_kafka_integration.py` (17 `@pytest.mark.integration` tests), traced against `kafka_producer.py`, `kafka_consumer.py`, `kafka_errors.py`, `event_contracts/product_observation.py`, `manage_kafka_topics.py`, `docker-compose.yml`.
- **Independently verified (reviewer-executed):**
  - `ruff check tests/test_kafka_integration.py` → **passed**.
  - `mypy` (full project, as CI runs it) → **FAILED, 10 errors**, all in this file (see F2). This is the authoritative type-check gate and it currently fails.
  - `pytest --collect-only -q -m integration tests/test_kafka_integration.py` → **17 tests collected**.
  - `from libs.common.kafka_errors import DeadLetterSink; DeadLetterSink(lambda x: None)` → **`TypeError: Callable() takes no arguments`** (confirms F1).
  - `hasattr(confluent_kafka.Producer, "close")` → `True` (runtime `Producer.close()` exists; the corresponding mypy error is a stub gap, not a runtime failure).
- **Implementation evidence reviewed:** The fix commit message describes the intended fixes; the code matches those descriptions for F2–F6, F8, F9.
- **Unverified:** The 17 integration tests were **not** executed against a live Kafka broker (they require Docker and are excluded from CI via `pyproject.toml` `addopts = "-m 'not integration'"` and the plain `pytest` step in `.github/workflows/ci.yml`).

### Correction to the prior review cycle

The prior cycle ran `ruff` and `pytest --collect-only` but **not `mypy`**. Running the full type-check gate now surfaces 10 errors that were present in the original commit `b9fc8f4` and remain unfixed. The `DeadLetterSink(...)` runtime `TypeError` (F1) was also present in the original commit and was missed. These are newly reported here.

---

## 5. Findings

### F1 — `DeadLetterSink(...)` is called as a constructor and raises `TypeError` at runtime (High)

- **File/ref:** `tests/test_kafka_integration.py:657` (`test_transient_processing_error_with_retry`) and `:693` (`test_permanent_failure_routes_to_dlq`).
- **Problem:** `DeadLetterSink` is a type alias `Callable[[dict[str, object]], None]` in `libs/common/kafka_errors.py` — a `typing` special form, not a class or factory. `dead_letter=DeadLetterSink(dead_letter_sink)` invokes it as a constructor and raises `TypeError: Callable() takes no arguments` at runtime. Independently confirmed.
- **Impact:** Both "failure/retry" acceptance-scenario tests fail immediately with `TypeError`, so the Milestone 1 failure path is still not demonstrated. (The DLQ test's import and envelope assertions were fixed, but this wrapping remains.)
- **Recommendation:** Pass the sink directly, e.g. `dead_letter=dead_letter_sink`, matching the existing call sites in `tests/test_kafka_errors.py` (`c.process_next(handler, sink)` and `c.process_next(MagicMock(), dlq.publish)`), which pass the callable without wrapping.

### F2 — File fails the project's `mypy` gate (High)

- **File/ref:** `tests/test_kafka_integration.py` — `mypy` (full run) reports 10 errors:
  - `:262`, `:424`, `:992` — `Need type annotation` for `consumed_events`, `consumed_messages`, `received` (empty lists).
  - `:318`, `:371` — `"Producer" has no attribute "close"` (confluent_kafka type stubs do not declare `close`; runtime is fine, but CI `mypy` fails).
  - `:657`, `:693` — `"<typing special form>" not callable` (same root cause as F1).
  - `:927`, `:929`, `:934` — variable `producer` is rebound from `KafkaEventProducer` to confluent `Producer` (name shadowing in `test_invalid_event_does_not_corrupt_pipeline`).
- **Impact:** `.github/workflows/ci.yml` runs `mypy` (no args) and `pyproject.toml` includes `tests/`. This file fails that gate, so CI would fail and `ai/AGENTS.md` §7 / §14 (Definition of Done) is not satisfied.
- **Recommendation:** Annotate the empty lists (`list[ConsumerMessage]` / `list[ProductObservationEvent]`); avoid reusing the `producer` name for the confluent client (use e.g. `raw_producer`); and replace the `Producer.close()` calls (or suppress with a targeted `# type: ignore[attr-defined]`) given the stub gap. Fixing F1 resolves two of the ten errors.

### F3 — Integration suite still excluded from CI and expensive to run (Moderate, carried over as F7)

- **File/ref:** `pyproject.toml` (`addopts = "-m 'not integration'"`), `.github/workflows/ci.yml`; `real_broker` fixture at `tests/test_kafka_integration.py:96-157`.
- **Problem:** The fix commit subject claims to resolve "F2-F9", but F7 (this finding) is **not** addressed: the deliverable is never run in CI, and `real_broker` is function-scoped (a fresh Kafka Compose project per test for ~16 of 17 tests).
- **Impact:** The suite remains unverified in CI, and its cost discourages regular execution.
- **Recommendation:** Document where/how these tests run (e.g., a Docker-capable CI job), and consider a session-scoped broker with per-test topic/group isolation.

### Resolved findings (verified)

- **F1 (prior) — branch isolation:** ✅ Resolved — now on `feature/TASK-012`.
- **F2 (prior) — DLQ test imports/assertions:** ✅ Resolved — `ProcessingError` imported from `kafka_consumer`; assertions now check `event_type`, `payload.error_type`, and `payload.raw_value_base64` per the actual `diagnostic_envelope` contract.
- **F3 (prior) — invalid-event tests:** ✅ Resolved — producer rejection uses a mutated valid event; schema/invalid cases produce raw bytes directly.
- **F4 (prior) — Kafka restart test:** ✅ Resolved — now performs `docker compose stop/start kafka` and consumes a post-restart event.
- **F5 (prior) — ordering assertion:** ✅ Resolved — `assert [e.event_id for e in consumed_events] == [e.event_id for e in events]`.
- **F6 (prior) — single-poll flakiness:** ✅ Resolved — deadline-bounded poll loops adopted throughout.
- **F8 (prior) — dead fixture/code:** ✅ Resolved — `duplicate_event` and `invalid_event_payload` removed.
- **F9 (prior) — import placement:** ✅ Resolved — imports hoisted to module top; `serialize_event` (now unused) removed.

---

## 6. Non-Defect Observations

1. **Placeholder commit identity.** Commits are authored by `Workflow Test <workflow@example.invalid>`, consistent with the automated workflow; not treated as evidence of human review.
2. **Broker restart readiness probe is weak.** In `test_consumer_handles_kafka_restart`, the post-restart readiness check constructs a `Producer` and calls `poll(0)` without closing it; librdkafka `Producer` construction/`poll(0)` does not reliably establish broker connectivity. The subsequent `publish` has a 30 s delivery timeout and effectively acts as the real readiness gate, so the test is likely still robust, but the probe itself is cosmetic.
3. **DLQ scenario uses an in-memory sink.** Both failure tests route to a local list-based sink rather than the real `KafkaDeadLetterProducer`/`products.invalid.v1`; that is reasonable for testing `process_next`'s routing decision (the real-broker DLQ path is covered in `tests/test_kafka_errors.py`).
4. **Sequential-offset assumption.** `test_multiple_events_preserve_ordering_within_partition` asserts exact `offset[i+1] == offset[i]+1`, which holds for a single idempotent producer to one partition but is stronger than ordering strictly requires.

---

## 7. Verdict

**CHANGES REQUIRED**

Blocking findings:

- **F1** — `DeadLetterSink(dead_letter_sink)` raises `TypeError: Callable() takes no arguments` at runtime, breaking both failure/retry tests.
- **F2** — the file fails the repository's `mypy` gate (10 errors), which would fail CI and violates the Definition of Done.

The prior cycle's logic defects (F1–F6, F8, F9) are correctly resolved and verified. After F1 and F2 are addressed, the remaining item is the non-blocking F3 (CI execution/cost decision).
