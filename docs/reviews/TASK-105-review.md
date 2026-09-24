# TASK-105 Review — DLQ Test

## 1. Review Header

- **Task ID:** TASK-105 — DLQ Test
- **Review date:** 2026-09-24
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:** `446d32ef5fc172b0bd52d7a4e0cabb9db64ea185...671dcfb2831ec061a24ca2186fe2125973aa8545`
- **Reviewed HEAD:** `671dcfb2831ec061a24ca2186fe2125973aa8545` (`feat(TASK-105): add dead-letter queue integration tests`)
- **Branch:** `feature/TASK-105`
- **Scope:** one new test file, `tests/test_dlq.py` (606 insertions)
- **Verdict:** CHANGES REQUIRED

The change set is a single new integration-test module, `tests/test_dlq.py` (five test methods), plus
this review record. The reviewer independently ran the module against a live Docker Kafka broker:
**4 of 5 tests fail**. Two failures are reproducible field-name / envelope-shape mismatches against the
actual DLQ envelopes produced by `libs/common/kafka_errors.py` and `services/processor/pipeline.py`; the
other two are a broken deserialization-error collection design. Additionally, three tests contain a
latent `AttributeError` that is currently masked by the earlier failures.

---

## 2. Requirements Coverage

Source of truth: `ai/tasks/TASK-105-dlq-test.md` (objective, Failure Engineering Rules, Engineering
Rules, Definition of Done), `ai/AGENTS.md` §8 (DLQ behavior), and the actual DLQ envelope contracts in
`libs/common/kafka_errors.py` (`diagnostic_envelope`) and `services/processor/pipeline.py`
(`validation_envelope`).

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Demonstrate malformed events are routed to the DLQ | **Partially met / broken** | `TestConsumerLevelDlq.test_deserialization_failure_routes_to_dlq` correctly drives `KafkaConsumer.process_next(dead_letter=…)` and the DLQ record is produced (log `kafka_dead_letter_delivered`; `assert len(dlq_output) == 1` passes) — but the test then fails on a non-existent field (`KeyError: 'reason'`, line 552). The three "processor-level" tests never successfully route a malformed event at all (see F2/F3). |
| DLQ events are queryable with diagnostic context | **Not met** | `TestDlqQueryable` fails at error collection (line 408) before reaching the query assertions; and even if reached, `assert "external_id" in dlq_record["payload"]` (line 436) is wrong — `external_id` lives under `payload.context`, not `payload` (see F4). |
| Main pipeline continues processing valid events unaffected | **Partially met** | `test_invalid_events_route_to_dlq_valid_events_unaffected` verifies 2 valid events reach `products.validated.v1` and `published_valid == 2`, but fails at the DLQ arm (line 300). `test_dlq_does_not_block_valid_event_processing` (the only passing test) verifies valid processing but never actually asserts the DLQ happened (see F6). |
| Verify DLQ monitoring surfaces alerts | **Partially met** | Only the counter `KafkaMetric.DEAD_LETTERED` (and `INVALID`) is asserted. No Prometheus alert rule / Grafana alert is exercised (none exists in-repo; TASK-018 deferred alert rules). See F7. |
| Failure → Detection → Metric/log → Recovery → No silent data loss | **Partially met** | Detection and metric arms are attempted (metric assertions pass for the consumer-level test before its field-name failure). The log arm is not asserted. The "No silent data loss" arm is not demonstrated end-to-end because the processor-level tests never route the malformed event. |
| Reuse existing DLQ handling semantics; do not change processor behavior | **Met** | No production code changed in the reviewed range; the test imports and reuses `ProcessorPipeline`, `KafkaConsumer`, `KafkaDeadLetterProducer`, `ProcessorMetrics`, `KafkaMetric`. |
| Tests are repeatable and deterministic | **Not met** | `test_dlq_does_not_block_valid_event_processing` depends on cross-partition message ordering (see F6); the three processor-level tests are non-deterministic in whether a deserialization error is still available at the error-collection phase (see F2). |
| Document the DLQ scenario and expected behavior | **Partially met** | Module docstring documents the five scenarios and the failure lifecycle, but the "validation_failure" scenarios mis-describe the actual mechanism (they produce `schema_version=999`, which fails *deserialization*, not *validation* — see F5). |

---

## 3. Git Diff Review

The reviewed range contains a single commit:

- `671dcfb` — `feat(TASK-105): add dead-letter queue integration tests`

Net diff (`446d32e..671dcfb`):

- `tests/test_dlq.py` — added (606 insertions)

- **Scope correctness:** All changes belong to TASK-105. No production, config, infrastructure, or migration code was modified.
- **Unrelated changes:** None.
- **Architectural changes:** None. Service boundaries are referenced, not altered.
- **Accidental changes:** None (no debugging code, temporary files, generated artifacts, or secrets).
- **Dependencies/configuration:** No new dependencies. The test reuses `confluent_kafka`, `pydantic`, `polars`, `pytest`, and the existing `docker-compose.yml` stack.
- **Branch/task isolation:** Correct — work is on `feature/TASK-105`; no changes from another TASK-* branch are included.

---

## 4. Test and Verification Review

### Tests examined

Five integration tests (module `pytestmark = pytest.mark.integration`, line 44):

1. `TestDlqRoutingMixedBatch::test_invalid_events_route_to_dlq_valid_events_unaffected` (line 250)
2. `TestDlqQueryable::test_dlq_events_contain_diagnostic_context` (line 376)
3. `TestDlqMetrics::test_processor_metrics_increment_on_dlq_routing` (line 447)
4. `TestConsumerLevelDlq::test_deserialization_failure_routes_to_dlq` (line 497)
5. `TestConsumerLevelDlq::test_dlq_does_not_block_valid_event_processing` (line 555)

### Verification status — Independently verified (executed by the reviewer)

The reviewer ran the module against a live Docker Kafka broker (the `real_broker` fixture starts an
isolated Compose project and creates all topics). Result: **4 failed, 1 passed** in 465s.

| Command | Result |
|---------|--------|
| `python -m pytest tests/test_dlq.py --collect-only -q -m integration` | 5 tests collected; module imports cleanly |
| `python -m pytest tests/test_dlq.py -m integration -v --tb=short` | **4 failed, 1 passed** (465.20s) |
| `python -m ruff check tests/test_dlq.py` | All checks passed |
| `python -m ruff format --check tests/test_dlq.py` | 1 file already formatted |
| `python -m mypy tests/test_dlq.py` | Success: no issues found in 1 source file |

Observed failure points (exact, from pytest):

- `test_invalid_events_route_to_dlq_valid_events_unaffected` — `tests/test_dlq.py:300: assert 0 == 1`
- `test_dlq_events_contain_diagnostic_context` — `tests/test_dlq.py:408: assert 0 == 1`
- `test_processor_metrics_increment_on_dlq_routing` — `tests/test_dlq.py:470: assert 0 == 3`
- `test_deserialization_failure_routes_to_dlq` — `tests/test_dlq.py:552: KeyError: 'reason'`

The reviewer additionally confirmed, with a standalone Python check, the envelope shapes that the
assertions contradict:

- `diagnostic_envelope(...)["payload"]` keys = `attempts, consumer_group, error_type, offset, partition, raw_value_base64, topic, validation_errors` → **no `reason` key**; `error_type` is present.
- `validation_envelope(...)["payload"]` keys = `context, reason, validation_errors` → `external_id` is under `payload.context`, **not** a top-level `payload` key.
- `DeserializationError` fields = `topic, partition, offset, error, raw_value` → **no `.event` attribute**.

Note: `pyproject.toml` sets `addopts = "-m 'not integration'"`, so a plain `pytest` run deselects all
five tests. The reviewer explicitly ran with `-m integration` as required by the DoD.

---

## 5. Findings

### F1 — CRITICAL — Consumer-level DLQ assertion reads a non-existent field `reason`

- **File/line:** `tests/test_dlq.py:552`
- **Problem:** `test_deserialization_failure_routes_to_dlq` asserts `dlq_record["payload"]["reason"] == "deserialization_failure"`. `KafkaConsumer.process_next` routes deserialization failures via `diagnostic_envelope()` (`libs/common/kafka_errors.py`), whose payload contains `error_type`, `topic`, `partition`, `offset`, `consumer_group`, `raw_value_base64`, `validation_errors`, `attempts` — there is no `reason` key. Observed: `KeyError: 'reason'`.
- **Impact:** Test fails. (The DLQ routing itself is correct — the record is produced and `error_type`/`raw_value_base64` are present — only the assertion is wrong.)
- **Recommendation:** Assert `dlq_record["payload"]["error_type"] == "ValidationError"` (the actual type raised by `deserialize_event` for malformed JSON) and keep the `raw_value_base64` presence check, instead of `reason`.

### F2 — CRITICAL — Deserialization errors are not re-collectable by re-polling

- **File/line:** `tests/test_dlq.py:300`, `:408`, `:470`
- **Problem:** Three tests poll the same `KafkaConsumer` for deserialization errors *after* an earlier polling phase. `KafkaConsumer.poll` surfaces each `DeserializationError` exactly once, at the moment the message is first fetched; it does not re-fetch an already-fetched-but-uncommitted offset. In the mixed-batch and queryable tests, `_consume_raw_messages` / the initial poll loop already fetched (and discarded) the invalid message's error, so the later `while not errors: … poll()` loop collects nothing (`assert 0 == 1`). The metrics test's error-collection loop likewise returns zero (`assert 0 == 3`); its raw `Producer` delivery is also never confirmed (`flush` return and delivery callbacks are ignored), so a silent delivery failure yields zero errors with no diagnostic.
- **Impact:** Three of five tests fail; the approach cannot reliably demonstrate DLQ routing for the processor path.
- **Recommendation:** Collect `messages` and `errors` in a single poll pass (accumulate both from one loop), or route deserialization errors via `process_next(dead_letter=…)` as `TestConsumerLevelDlq` already does. Verify the raw `Producer` actually delivered (check `flush` return / delivery callback).

### F3 — HIGH — `DeserializationError` objects passed to `ProcessorPipeline.process_batch`

- **File/line:** `tests/test_dlq.py:308`, `:415`, `:479`
- **Problem:** `pipeline.process_batch(errors)` is called with `errors` being a `list[DeserializationError]`. `ProcessorPipeline.process_batch` → `_run_pipeline` accesses `msg.event.event_id`, but `DeserializationError` has no `.event` attribute (fields are `topic, partition, offset, error, raw_value`). This is a latent `AttributeError` currently masked by the earlier `assert len(errors) == N` failures (F2). It is not caught by mypy because the module disables `attr-defined` and `errors` is typed as bare `list`.
- **Impact:** Even after F2 is fixed, these three tests would crash. It reveals a conflation of two distinct DLQ paths (see F5).
- **Recommendation:** Do not pass `DeserializationError` to `process_batch`. Route deserialization failures through `process_next(dead_letter=…)`, or build the diagnostic envelope explicitly (as `tests/test_processor_integration.py::TestInvalidEventRouting` does), and reserve `process_batch` for valid `ConsumerMessage` batches.

### F4 — HIGH — `validation_envelope` context asserted at the wrong nesting level

- **File/line:** `tests/test_dlq.py:436`
- **Problem:** `test_dlq_events_contain_diagnostic_context` asserts `"external_id" in dlq_record["payload"]`. `validation_envelope()` builds `payload = {reason, validation_errors, context}` where `context` is `_event_context(event)` containing `external_id`, `name`, `url`, `category`, `source`, `schema_version`. So `external_id` lives at `payload.context.external_id`, not `payload.external_id`.
- **Impact:** Latent `AssertionError` (currently masked by F2). The "diagnostic context" claim is asserted against the wrong shape.
- **Recommendation:** Assert `dlq_record["payload"]["context"]["external_id"]` (and other context fields) instead of a top-level `external_id`.

### F5 — MODERATE — Tests conflate validation failures with deserialization failures

- **File/line:** `tests/test_dlq.py:117-135` (`_make_invalid_raw_event`), `:335`, `:434`
- **Problem:** `_make_invalid_raw_event` sets `schema_version: 999`, which causes `ProductObservationEvent.model_validate_json` to raise at the *deserialization* layer (`KafkaConsumer.poll` → `diagnostic_envelope`). The "processor-level" tests then route this through `process_batch` and assert `reason == "validation_failure"` — a field that only `validation_envelope` (the *validation* path, for events that deserialize but fail business rules) produces. The tests never actually exercise `validation_envelope`.
- **Impact:** The task's "malformed events route to DLQ" objective is only genuinely exercised for the deserialization path (in the consumer-level test). The pipeline validation path is never demonstrated.
- **Recommendation:** To exercise `validation_envelope`, produce an event with `schema_version: 1` that fails a business validation rule (e.g. negative `price`, invalid `availability`, null required field), and route it through `process_batch`. Keep deserialization-failure coverage in the consumer-level test.

### F6 — MODERATE — "Does not block valid processing" test is order-dependent and never asserts the DLQ

- **File/line:** `tests/test_dlq.py:555-606` (flag logic at `:584-591`)
- **Problem:** `test_dlq_does_not_block_valid_event_processing` sets `dlq_processed = True` only when `result` is truthy *and* `processed_valid_ids` is empty. If the valid event is processed before the malformed message (non-deterministic across the 3 partitions of `products.raw.v1`), `processed_valid_ids` is already non-empty, `dlq_processed` is never set, and the loop spins until the 20s deadline. The final assertions only check `processed_valid_ids`, so the DLQ occurrence is never actually asserted. (This test happened to pass in the reviewer run.)
- **Impact:** Non-deterministic timing and a false sense of coverage: the test can pass while never proving the DLQ event was handled.
- **Recommendation:** Record DLQ delivery with a dedicated flag inside the `dead_letter` sink (e.g. append to a list), and assert both `len(processed_valid_ids) >= 1` and that the DLQ sink was invoked, unconditionally.

### F7 — MINOR — "Alerts" reduced to a metric-counter assertion

- **File/line:** `tests/test_dlq.py:537-539`
- **Problem:** The objective says "Verify DLQ monitoring surfaces alerts." The test asserts only `KafkaMetric.DEAD_LETTERED` (and `INVALID`) counters increment. No Prometheus alert rule or Grafana alert is exercised; the in-repo "monitoring surface" is the `kafka_dead_letter_events_total` counter and Grafana dashboards (no alert rule exists — TASK-018 explicitly deferred alert rules).
- **Impact:** The literal "alerts" wording is not satisfied; the metric arm is.
- **Recommendation:** Either document that "alerts" is satisfied by the DLQ counter/dashboard exposure, or add an explicit check that the DLQ metric is exported/queried (mirroring the TASK-104 review's treatment of the "log" arm).

### F8 — MINOR — Fixture scaffolding duplicated wholesale from `test_processor_integration.py`

- **File/line:** `tests/test_dlq.py:46-241` (fixtures and helpers)
- **Problem:** The entire fixture block (`clean_environment`, `real_broker`, `_make_producer_settings`, `_make_consumer_settings`, `broker_address`, and the four `*_settings` fixtures) is copied from `tests/test_processor_integration.py` with only project/client-id strings changed. There is no shared `tests/conftest.py` for Kafka integration fixtures.
- **Impact:** Maintenance burden and drift risk across integration-test modules.
- **Recommendation:** Extract shared Kafka integration fixtures into a `tests/conftest.py` (out of TASK-105's test-only scope; propose as a follow-up).

---

## 6. Non-Defect Observations

- The consumer-level DLQ path (`KafkaConsumer.process_next` → `diagnostic_envelope` → `KafkaDeadLetterProducer.publish`) is exercised correctly by `test_deserialization_failure_routes_to_dlq`; the DLQ record is actually produced (`kafka_dead_letter_delivered` log; `assert len(dlq_output) == 1` passes). Only the `reason` field-name assertion is wrong.
- The metric assertions in that same test (`DEAD_LETTERED >= 1`, `INVALID >= 1`) are correct and precede the failing field assertion, so the consumer-level metric arm is sound.
- The `diagnostic_envelope` and `validation_envelope` contracts themselves are consistent with prior tasks (TASK-010/017/019) and are not at fault; the test's assertions simply do not match them.
- The module docstring accurately lays out the intended five scenarios and the `Failure → Detection → Metric/log → Recovery → No silent data loss` lifecycle; the intent is clear even though the implementation diverges from it.
- No secrets, no production-code changes, no new dependencies, and no weakening of existing suites. `ruff check`, `ruff format --check`, and `mypy` all pass on the new file — the defects are runtime/design defects that static checks do not catch.

---

## 7. Verdict

**CHANGES REQUIRED**

The module fails **4 of 5** integration tests when run against a live Kafka broker, and the failures
are not environmental: two are reproducible envelope-shape mismatches (F1 `KeyError: 'reason'`; F4
`external_id` nested under `context`), and the others stem from a broken deserialization-error
collection design (F2) plus a latent `AttributeError` from passing `DeserializationError` objects to
`ProcessorPipeline.process_batch` (F3). The task's objective — demonstrating that malformed events are
routed to the DLQ, that DLQ events are queryable with diagnostic context, and that the main pipeline is
unaffected — is therefore not reliably verified. Fix F1–F4 (and the design flaws in F5–F6) before
acceptance; F7–F8 are non-blocking.
