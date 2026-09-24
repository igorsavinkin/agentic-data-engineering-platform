# TASK-105 Post-Merge Review — DLQ Test

## 1. Review Header

- **Task ID:** TASK-105 — DLQ Test
- **Review date:** 2026-09-24
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Review type:** Post-merge review of the final merged state on `main`
- **Reviewed change set / Git range:** `446d32ef5fc172b0bd52d7a4e0cabb9db64ea185..3a4bcd4b96adeb4761844f80e3cc9e6ccd12ab3d`
- **Reviewed HEAD:** `3a4bcd4b96adeb4761844f80e3cc9e6ccd12ab3d` (`fix(TASK-105): redesign DLQ tests around actual deserialization DLQ path`)
- **Branch:** `main` (code already merged)
- **Prior review:** `docs/reviews/TASK-105-review.md` (round 1, `CHANGES REQUIRED`, F1–F8)
- **Scope:** `tests/test_dlq.py` (final state, 518 lines) + round-1 review record
- **Verdict:** CHANGES REQUIRED

The reviewed range contains two commits: `671dcfb` (`feat(TASK-105): add dead-letter queue
integration tests`) and `3a4bcd4` (`fix(TASK-105): redesign DLQ tests around actual deserialization
DLQ path`). The fix commit correctly resolves round-1 findings F1–F6, but introduces one new
**blocking defect** in the mixed-batch test: its `dead_letter` sink is a local `lambda` that never
publishes to Kafka, so the test's own DLQ-topic assertion fails. The reviewer independently ran the
module against a live Docker Kafka broker: **1 failed, 4 passed**.

---

## 2. Requirements Coverage

Source of truth: `ai/tasks/TASK-105-dlq-test.md` (objective, Failure Engineering Rules, Engineering
Rules, Definition of Done), `ai/AGENTS.md` §8 (DLQ behavior), and the actual DLQ envelope contract in
`libs/common/kafka_errors.py` (`diagnostic_envelope`).

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Malformed events are routed to the DLQ | **Partially met / broken** | `TestConsumerLevelDlq.test_deserialization_failure_routes_to_dlq` (passes) and `TestDlqQueryable` (passes) correctly drive `KafkaConsumer.process_next(dead_letter=…)` and the DLQ record is produced with `error_type`/`raw_value_base64`. But the primary mixed-batch test (`TestDlqRoutingMixedBatch`) fails because its `dead_letter` sink is a local `lambda` that never publishes to `products.invalid.v1` (F1). |
| DLQ events are queryable with diagnostic context | **Met** | `TestDlqQueryable.test_dlq_events_contain_diagnostic_context` passes; asserts `event_type == "product.invalid"` and payload fields `error_type`, `raw_value_base64`, `topic`, `partition`, `offset`, `consumer_group` — all present in `diagnostic_envelope()`. |
| Main pipeline continues processing valid events unaffected | **Partially met** | `test_dlq_does_not_block_valid_event_processing` passes (valid event processed after a bad message, both arms asserted). The mixed-batch test that asserts valid events processed alongside a malformed message fails at its DLQ arm (F1), so the "unaffected" claim is not demonstrated end-to-end in that test. |
| Verify DLQ monitoring surfaces alerts | **Partially met** | Only `KafkaMetric.DEAD_LETTERED` / `INVALID` / `PROCESSED` counters are asserted (`TestDlqMetrics`, passes). No Prometheus alert rule or Grafana alert is exercised (none exists in-repo; TASK-018 deferred alert rules). See F3. |
| Failure → Detection → Metric/log → Recovery → No silent data loss | **Partially met** | Detection (deserialization failure) and metric arms are demonstrated and pass. The log arm is not asserted. "No silent data loss" is not demonstrated end-to-end for the mixed-batch case because the DLQ record is never actually persisted there (F1). |
| Reuse existing DLQ handling semantics; do not change processor behavior | **Met** | No production code changed in the range; tests import and reuse `KafkaConsumer`, `KafkaDeadLetterProducer`, `diagnostic_envelope`, `KafkaMetric`. |
| Tests are repeatable and deterministic | **Met (with defect caveat)** | Round-1 F6 (cross-partition ordering dependency) is fixed via dedicated `processed_ids` / `dlq_calls` lists. Test 1's failure is a deterministic correctness defect (DLQ never published), not flakiness. |
| Document the DLQ scenario and expected behavior | **Met** | Module docstring accurately documents the deserialization path (`KafkaConsumer.poll` → `DeserializationError` → `process_next` → `diagnostic_envelope`) and the five scenarios; round-1 F5 (validation/deserialization conflation) is corrected. |

---

## 3. Git Diff Review

The reviewed range contains two commits on `main`:

- `671dcfb` — `feat(TASK-105): add dead-letter queue integration tests`
- `3a4bcd4` — `fix(TASK-105): redesign DLQ tests around actual deserialization DLQ path`

Net diff (`446d32e..3a4bcd4`):

- `tests/test_dlq.py` — added, final state 518 insertions (round 1 added 606 lines; the fix commit rewrote it down to 518).
- `docs/reviews/TASK-105-review.md` — added (187 insertions); this is the round-1 review record, an authorized artifact under `docs/reviews/`.

- **Scope correctness:** All changes belong to TASK-105. No production, config, infrastructure, or migration code was modified.
- **Unrelated changes:** None.
- **Architectural changes:** None. Service boundaries (`KafkaConsumer.process_next` → `diagnostic_envelope` → `KafkaDeadLetterProducer`) are exercised, not altered.
- **Accidental changes:** None (no debugging code, temporary files, generated artifacts, or secrets).
- **Dependencies/configuration:** No new dependencies. The test reuses `confluent_kafka`, `pydantic`, `pytest`, and the existing `docker-compose.yml` stack.
- **Branch/task isolation:** Both commits are TASK-105 and are now merged to `main`; no changes from another TASK-* branch are included.

---

## 4. Test and Verification Review

### Tests examined

Five integration tests (module `pytestmark = pytest.mark.integration`):

1. `TestDlqRoutingMixedBatch::test_valid_events_processed_while_malformed_bytes_route_to_dlq` (line 228)
2. `TestDlqQueryable::test_dlq_events_contain_diagnostic_context` (line 305)
3. `TestDlqMetrics::test_consumer_metrics_increment_on_dlq_routing` (line 371)
4. `TestConsumerLevelDlq::test_deserialization_failure_routes_to_dlq` (line 426)
5. `TestConsumerLevelDlq::test_dlq_does_not_block_valid_event_processing` (line 485)

### Verification status — Independently verified (executed by the reviewer)

The reviewer ran the module against a live Docker Kafka broker (the `real_broker` fixture starts an
isolated Compose project and creates all topics). Result: **1 failed, 4 passed** in 480s.

| Command | Result |
|---------|--------|
| `python -m pytest tests/test_dlq.py --collect-only -q -m integration` | 5 tests collected; module imports cleanly |
| `python -m pytest tests/test_dlq.py -m integration -v --tb=short` | **1 failed, 4 passed** (480.18s) |
| `python -m ruff check tests/test_dlq.py` | All checks passed |
| `python -m ruff format --check tests/test_dlq.py` | 1 file already formatted |
| `python -m mypy tests/test_dlq.py` | Success: no issues found in 1 source file |

Observed failure (exact, from pytest):

- `test_valid_events_processed_while_malformed_bytes_route_to_dlq` — `tests/test_dlq.py:289: assert 0 == 1`

The captured log shows the malformed message was detected and the `dead_letter` sink was invoked
(`kafka_deserialization_failed` → `kafka_dead_letter_delivered`), yet no record appeared in
`products.invalid.v1`. This is because the sink is a local `lambda` that appends to a Python list
rather than `dlq_producer.publish` (see F1). The remaining four tests passed.

Note: `pyproject.toml` sets `addopts = "-m 'not integration'"`, so a plain `pytest` run deselects all
five tests. The reviewer explicitly ran with `-m integration` as required by the DoD.

---

## 5. Findings

### F1 — CRITICAL — Mixed-batch test's `dead_letter` sink never publishes to the DLQ topic

- **File/line:** `tests/test_dlq.py:269` (the `dead_letter=` argument; failure surfaces at `:289`)
- **Problem:** `test_valid_events_processed_while_malformed_bytes_route_to_dlq` passes `dead_letter=lambda record: dlq_calls.append(record)` to `process_next`. That sink only appends the envelope dict to an in-memory list; it never calls `dlq_producer.publish` (the `KafkaDeadLetterProducer` created at line 261 is unused). The test then consumes `products.invalid.v1` and asserts `len(dlq_output) == 1`, which fails with `0 == 1` because nothing was ever published.
- **Impact:** The mixed-batch test — the primary demonstration of "malformed events route to the DLQ while valid events are unaffected" — fails. The task's core objective is not verified in this test. This is a regression introduced by the fix commit (round 1's version routed the malformed event through `ProcessorPipeline` with `invalid_sink=invalid_producer.publish`).
- **Recommendation:** Use `dead_letter=dlq_producer.publish` (as the other three passing tests do), and keep the local `dlq_calls` list only if needed for an additional in-process assertion.

### F2 — MODERATE — "Does not block valid processing" test creates an unused DLQ producer and never persists a real DLQ record

- **File/line:** `tests/test_dlq.py:501` (`dlq_producer = KafkaDeadLetterProducer(...)`), `:509` (`dead_letter=lambda record: dlq_calls.append(record)`)
- **Problem:** `test_dlq_does_not_block_valid_event_processing` also uses a local `lambda` as the `dead_letter` sink while constructing (and closing) a `KafkaDeadLetterProducer` that is never used. Unlike F1, this test does not assert a Kafka DLQ record exists, so it passes — but it only proves the sink *callback* was invoked, not that a DLQ event was durably produced/queryable. The test/docstring speak of "a DLQ event", which is misleading.
- **Impact:** Weaker-than-claimed coverage and a misleading test name; a wasted producer connection. No functional failure, but it should be corrected for accuracy and symmetry with the other tests.
- **Recommendation:** Route through `dead_letter=dlq_producer.publish` (recording delivery separately if an in-process assertion is still desired), so the test genuinely exercises the DLQ persistence path.

### F3 — MINOR — "Alerts" still reduced to a metric-counter assertion

- **File/line:** `tests/test_dlq.py:371-421` (`TestDlqMetrics`)
- **Problem:** The objective says "Verify DLQ monitoring surfaces alerts." The test asserts only `KafkaMetric.DEAD_LETTERED`, `INVALID`, and `PROCESSED` counters. No Prometheus alert rule or Grafana alert is exercised; the in-repo "monitoring surface" is the `kafka_dead_letter_events_total` counter (no alert rule exists — TASK-018 explicitly deferred alert rules).
- **Impact:** The literal "alerts" wording remains unsatisfied; the metric arm is. This is unchanged from round-1 F7 and is non-blocking.
- **Recommendation:** Either document that "alerts" is satisfied by the DLQ counter/dashboard exposure, or add an explicit check that the DLQ metric is exported/queried (mirroring the TASK-104 review's treatment of the "log" arm).

### F4 — MINOR — Fixture scaffolding duplicated wholesale from `test_processor_integration.py`

- **File/line:** `tests/test_dlq.py:59-224` (fixtures and helpers)
- **Problem:** The fixture block (`clean_environment`, `real_broker`, `_make_producer_settings`, `_make_consumer_settings`, `_consume_json`, `broker_address`, and the five `*_settings` fixtures) is copied from `tests/test_processor_integration.py` with only project/client-id strings changed. There is no shared `tests/conftest.py` for Kafka integration fixtures. Unchanged from round-1 F8.
- **Impact:** Maintenance burden and drift risk across integration-test modules.
- **Recommendation:** Extract shared Kafka integration fixtures into a `tests/conftest.py` (out of TASK-105's test-only scope; propose as a follow-up).

### F5 — MINOR — Unused fixture parameter in the mixed-batch test signature

- **File/line:** `tests/test_dlq.py:233` (`validated_consumer_settings: KafkaConsumerSettings`)
- **Problem:** `test_valid_events_processed_while_malformed_bytes_route_to_dlq` declares `validated_consumer_settings` in its signature but never uses it (the fix commit removed the validated-topic consumption).
- **Impact:** Cosmetic; the fixture is still instantiated (and its group id generated) for no purpose.
- **Recommendation:** Drop the unused parameter.

---

## 6. Non-Defect Observations

- **Round-1 F1–F6 are correctly resolved.** The fix commit removes the `process_batch` / `validation_envelope` path entirely and drives the real deserialization DLQ path (`process_next(dead_letter=…)` → `diagnostic_envelope`). The wrong `reason` assertion is replaced with `error_type == "ValidationError"`; the re-polling deserialization-error design (F2) and the latent `DeserializationError`→`process_batch` `AttributeError` (F3) are gone; the `external_id` nesting error (F4) is gone; the validation/deserialization conflation (F5) is corrected in the docstring; and the ordering-dependent "does not block" flag logic (F6) is replaced with dedicated `processed_ids`/`dlq_calls` lists.
- The three consumer-level/path tests (`TestDlqQueryable`, `TestDlqMetrics`, `TestConsumerLevelDlq.test_deserialization_failure_routes_to_dlq`) are now correct and pass independently. Their envelope assertions match the actual `diagnostic_envelope()` contract (`event_type == "product.invalid"`; payload keys `topic`, `partition`, `offset`, `consumer_group`, `raw_value_base64`, `error_type`, `validation_errors`, `attempts`).
- The `diagnostic_envelope` / `deserialize_event` contracts themselves are consistent with prior tasks and are not at fault; the single failure is a test-side plumbing defect (F1).
- No secrets, no production-code changes, no new dependencies, and no weakening of existing suites. `ruff check`, `ruff format --check`, and `mypy` all pass on the final file — the remaining defect is a runtime behavior that static checks do not catch (the `dead_letter` callable's type is `Callable[[dict], None]`, which the local `lambda` satisfies).

---

## 7. Verdict

**CHANGES REQUIRED**

The fix commit resolved the round-1 defects and four of five integration tests now pass against a live
Kafka broker, but the final merged state still fails its own acceptance surface: the mixed-batch test
(`test_valid_events_processed_while_malformed_bytes_route_to_dlq`) fails at
`tests/test_dlq.py:289` (`assert 0 == 1`) because its `dead_letter` sink is a local `lambda` that never
publishes to `products.invalid.v1` (F1). That test is the primary end-to-end demonstration of the task
objective — malformed events routed to the DLQ while valid events are unaffected — so the objective is
not yet reliably verified. Fix F1 (and, for accuracy, F2); F3–F5 are non-blocking.
