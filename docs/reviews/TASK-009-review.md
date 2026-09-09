I have completed my investigation. I've read the task spec (`ai/tasks/TASK-009-kafka-consumer.md`), the reviewer instructions (`ai/REVIEWER.md`), the current on-disk implementation (`libs/common/kafka_consumer.py`), tests, docs, `.env.example`, `pyproject.toml`, `FOLLOWUPS.md`, the event contracts, the config base, the producer (TASK-008), ADR-001, and the relevant SPECIFICATION.md (┬º8ΓÇô┬º10) and PROJECT.md (┬º5, ┬º9, ┬º11) sections.

Key reconciliation: the supplied diff shows the **fixed** implementation (matching the on-disk HEAD `463012b`), while the committed `docs/reviews/TASK-009-review.md` is a *stale* prior review against `b3a28c4` that flagged three blocking defects. Those three defects are now resolved in code, but the documentation was not updated to match, and the non-blocking findings remain unaddressed and undocumented in `FOLLOWUPS.md`.

Here is the complete review report.

---

# TASK-009 Review ΓÇö Reusable Kafka Consumer

## 1. Review Header

| Field | Value |
| --- | --- |
| Task ID | TASK-009 |
| Review date | 2026-09-09 |
| Reviewed HEAD | `463012bbb9f5f2c5338ae80e576db36cad427ca7` |
| Reviewed Git range | `1d6bce1320f76d8ec028a1a20f40e1429cc88c44..463012bbb9f5f2c5338ae80e576db36cad427ca7` |
| Scope | Reusable Kafka consumer for canonical product-observation events |
| Verdict | **CHANGES REQUIRED** |

Sources of authority consulted: `ai/PROJECT.md` (┬º5 Event Semantics, ┬º9 Reliability, ┬º11 Security), `ai/SPECIFICATION.md` (┬º8 Kafka Architecture, ┬º9 Delivery Semantics, ┬º10 Invalid Events and DLQ), `docs/adr/ADR-001-kafka-topic-configuration.md`, `ai/tasks/TASK-009-kafka-consumer.md`, and the referenced TASK-006/TASK-008 artifacts (`libs/event_contracts`, `libs/common/kafka_producer.py`, `libs/common/config.py`).

Note: this review was performed read-only. The reviewer was prohibited from executing shell commands (`git status`, `pytest`, `ruff`, `mypy`), so test execution and lint/type checks were not independently run; see ┬º4.

Note on the committed review file: `docs/reviews/TASK-009-review.md` present at HEAD is a **prior** review against `b3a28c417b5a30fa9b4c978fc531960a63f79360` and is superseded by this report. The three blocking findings it raised (H1/H2/H3) have since been fixed in code.

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
| --- | --- | --- |
| Consumer group configuration | Met | `KafkaConsumerSettings(AppSettings)` with `kafka_group_id`, `kafka_auto_offset_reset`, session/heartbeat/max-poll timeouts, `kafka_enable_auto_commit=False`; `consumer_config` builds the librdkafka dict. |
| Deserialization and validation | Met | `poll()` deserializes via `deserialize_event(value.decode("utf-8"))`; valid events returned as `ConsumerMessage`. Failures are now surfaced to the caller as `DeserializationError` (see prior-H2 resolution). |
| Explicit offset handling | Met | `commit_message` (offset+1) and `commit_offsets` provided; `close()` no longer commits (prior-H1 resolution). |
| Graceful shutdown | Met (code) / docs inaccurate | SIGINT/SIGTERM handler sets `_shutdown_requested`; `poll()` returns empty on shutdown; context manager calls `close()`; `close()` is idempotent and does **not** commit. `docs/kafka-consumer.md` still claims `close()` "flushes pending commits" (see M3). |
| Document when offsets are committed and what happens on processing failure | Met with inaccuracies | `docs/kafka-consumer.md` covers commit timing, failure matrix, crash-after-write, and `event_id` deduplication ΓÇö but its graceful-shutdown text and example code contradict the corrected API (see M3). |
| Tests: valid event / malformed event / restart / duplicate delivery | Present but shallow | All four categories exist in `tests/test_kafka_consumer.py`; malformed events are now asserted to surface as `DeserializationError`. Restart/redelivery/duplicate tests remain mock tautologies (see M1). |
| Acceptance: reliably consumes canonical events without claiming exactly-once | **Met** | The three prior blocking defects (H1/H2/H3) are resolved; at-least-once honesty is correct in code and docstring. Remaining defects are non-blocking (M1ΓÇôM3, Min1ΓÇôMin4). |

## 3. Git Diff Review

Files changed (4, all new in this range):

- `docs/kafka-consumer.md` ΓÇö consumer guide.
- `docs/reviews/TASK-009-review.md` ΓÇö prior review report (stale; superseded here).
- `libs/common/kafka_consumer.py` ΓÇö new consumer module (+375).
- `tests/test_kafka_consumer.py` ΓÇö new unit tests (+626).

Assessment:

- **Scope correctness:** All implementation files belong to TASK-009. The committed `docs/reviews/TASK-009-review.md` is a review artifact of this task, not out-of-scope code.
- **Unrelated changes:** None observed.
- **Architectural changes:** None. Adds a library module; does not alter service boundaries, event semantics, or ADR-001 partitioning/consumer groups.
- **Accidental changes:** None. No debug code, temporary files, generated artifacts, or secrets found.
- **Dependency change:** None. `confluent-kafka` was already introduced in TASK-008.
- **Documentation/config gaps (see Min4):** `.env.example` lists the producer's `APP_KAFKA_*` variables but none of the consumer's; `libs/common/README.md` documents the producer but not the consumer.

## 4. Test and Verification Review

### Tests examined

`tests/test_kafka_consumer.py` (626 lines) covers: settings defaults/config dict/missing group ID; valid consumption; poll timeout; malformed JSON; invalid schema; None value; offset commit after success; no-commit-on-failure; restart with committed offsets; uncommitted redelivery; duplicate delivery; downstream dedup; shutdown-does-not-commit; shutdown flag; double-close; operations-after-close; partition EOF; transport error; unknown-topic error; subscription; assignment.

### Test adequacy

Improved over the prior review in the malformed-event area: three new tests assert malformed/invalid/None messages are surfaced as `DeserializationError`, and `test_shutdown_does_not_commit_unprocessed_offsets` now correctly asserts `close()` performs no commit (directly covering the prior H1 fix). However, the required "restart" and "duplicate delivery" tests remain mock tautologies: `test_restart_uses_committed_offsets` and `test_uncommitted_messages_redelivered_on_restart` assert mock `poll`/`commit_offsets` results rather than Kafka offset semantics, and the `TestDuplicateDelivery` tests assert the same mock `event_json` twice. No test verifies the caller-driven skip path for a `DeserializationError` (i.e., committing the malformed offset via `commit_offsets`) across `close()`/restart. See M1.

### Independently verified (executed by reviewer)

None. The reviewer was prohibited from executing shell commands, so `pytest`, `ruff`, and `mypy` were **not** run.

### Implementation evidence reviewed (not rerun)

`libs/common/kafka_consumer.py`, `tests/test_kafka_consumer.py`, `docs/kafka-consumer.md`, `libs/common/config.py`, `libs/common/kafka_producer.py`, `libs/event_contracts/`, `.env.example`, `pyproject.toml`, and `docs/reviews/FOLLOWUPS.md` were inspected directly. No test-run report was supplied.

### Unverified

- Test execution (unit tests).
- `ruff check` / `ruff format --check`.
- `mypy` ΓÇö notably `KafkaConsumerSettings.__init__(self, **kwargs: str | int | bool)` with `# type: ignore[arg-type]` under `warn_unused_ignores = true` (Min3). The override may be unnecessary entirely (the producer does not override `__init__`), and the ignore may be unused and thus fail mypy.
- Branch name and working-tree cleanliness (no `git status`/`git log`).

## 5. Findings

### High (blocking)

None. The three previously-blocking defects are resolved:

- **Prior H1 (close() committed current position):** resolved ΓÇö `close()` now only calls `self._consumer.close()`; `enable.auto.commit=False` prevents any implicit commit.
- **Prior H2 (malformed messages silently discarded):** resolved ΓÇö `poll()` returns `(list[ConsumerMessage], list[DeserializationError])`, surfacing failed messages with topic/partition/offset/`raw_value` so the caller can commit-to-skip, route to DLQ, or leave uncommitted.
- **Prior H3 (environment overridden to "development"):** resolved ΓÇö `KafkaConsumerSettings.__init__` no longer injects `environment`; it passes kwargs through to `AppSettings`, which still requires `APP_ENVIRONMENT`.

### Moderate (non-blocking)

**M1 ΓÇö Required "restart"/"duplicate delivery" tests remain mock tautologies; the malformed-offset advance path is untested.**
File: `tests/test_kafka_consumer.py`.
`test_restart_uses_committed_offsets` asserts `commit_offsets` was called and `close.called`; `test_uncommitted_messages_redelivered_on_restart` re-asserts the same mocked `mock_msg` at offset 42 on a "second" consumer; both `TestDuplicateDelivery` tests feed the same mocked JSON at two offsets. None exercises real Kafka offset semantics, and no test verifies that a `DeserializationError`'s offset can be advanced via `commit_offsets` (the documented skip path) across `close()`/restart.
Impact: the required restart/duplicate coverage is largely illusory, so a regression in offset handling would not be caught by the unit suite.
Recommendation: add a test that, given a surfaced `DeserializationError`, the caller can `commit_offsets([TopicPartition(topic, partition, offset+1)])` and that this is honored; strengthen restart/duplicate tests to assert actual `commit` calls rather than re-asserting the mock message. Real-Kafka integration coverage is owned by TASK-012, so unit-level assertions should at least pin the commit/offset interaction.

**M2 ΓÇö Consumer settings lack the producer's validators and omit `allow.auto.create.topics=false`.**
File: `libs/common/kafka_consumer.py`, `KafkaConsumerSettings`.
`kafka_group_id` accepts empty/arbitrary strings (only runtime-checked in `KafkaConsumer.__init__`, i.e., after settings load), and `kafka_bootstrap_servers` is not shape-validated ΓÇö unlike `KafkaProducerSettings` (`valid_name`/`valid_brokers`). `consumer_config` also omits `allow.auto.create.topics: false`, which ADR-001 states is disabled and the producer sets explicitly.
Impact: invalid configuration surfaces later than the producer's; the omission is defensively inconsistent with ADR-001 even though librdkafka's consumer default is already `false`.
Recommendation: add `valid_name`-style validators for `kafka_group_id`/bootstrap servers and include `"allow.auto.create.topics": False` in `consumer_config`.

**M3 ΓÇö `docs/kafka-consumer.md` now contradicts the corrected code.**
File: `docs/kafka-consumer.md`.
After the H1/H2 fixes, the guide was not updated:
1. "Graceful Shutdown" step 3 still says "`close()` flushes pending commits before leaving group" ΓÇö false; `close()` no longer commits.
2. The shutdown example still ends with "# Automatically closes and commits pending offsets" ΓÇö false.
3. The "Test scenarios covered" list still says "2. Malformed JSON handling (logged and skipped)" and "3. Invalid schema handling (logged and skipped)" ΓÇö false; they are surfaced to the caller as `DeserializationError`.
4. Both example loops still use `messages = consumer.poll(timeout=1.0)` then `for msg in messages` ΓÇö `poll()` now returns a 2-tuple `(messages, errors)`, so the examples are broken as written.
5. "What Happens When Processing Fails" step 3 says "Optionally route to DLQ" with no DLQ path exposed by the consumer (DLQ routing is TASK-010).

Impact: the task's explicit requirement to "document when offsets are committed and what happens when processing fails" is undermined ΓÇö the guide misleads users about shutdown behavior and shows non-working example code.
Recommendation: update ┬ºGraceful Shutdown (remove the "flushes pending commits"/"commits pending offsets" claims), fix the example code to unpack the tuple and handle `errors`, and align the test-scenario list with the surfacing behavior.

### Minor (non-blocking)

**Min1 ΓÇö `except Exception` in `poll()` is too broad.** It catches programming errors (e.g., `AttributeError`) alongside the intended `pydantic.ValidationError`/`UnicodeDecodeError`, hiding bugs. `MessageDeserializationError` is raised then swallowed in the same `try`. File: `libs/common/kafka_consumer.py`, `poll()`.

**Min2 ΓÇö Signal handler registration is a library side effect.** `__init__` calls `signal.signal(SIGINT/SIGTERM, ΓÇª)`, overriding the host application's handlers and only working on the main thread. A reusable library class should not clobber the embedding application's shutdown handling. File: `libs/common/kafka_consumer.py`, `_register_signal_handlers()`.

**Min3 ΓÇö `__init__(self, **kwargs: str | int | bool)` with `# type: ignore[arg-type]` is type-unsound and likely unnecessary.** The producer does not override `__init__`; this override adds nothing but the odd annotation and an ignore that may be unused (and thus fail under `warn_unused_ignores = true`). Unverified (mypy not run). File: `libs/common/kafka_consumer.py`, `KafkaConsumerSettings.__init__`.

**Min4 ΓÇö Documentation/config gaps.** `.env.example` omits the consumer's `APP_KAFKA_GROUP_ID` / `APP_KAFKA_AUTO_OFFSET_RESET` / timeout variables; `libs/common/README.md` lists the producer but not the consumer; `docs/kafka-consumer.md` examples use `kafka:9092` while `docs/kafka-producer.md` states containers use `kafka:29092`.

## 6. Non-Defect Observations

- **Per-message synchronous commit and single-message-per-poll** trade throughput for a simple, observable boundary ΓÇö consistent with the producer's design and acceptable for TASK-009; batching/performance is deferred.
- **Metrics are deferred to TASK-011** and real-Kafka integration tests to TASK-012 (consistent with the producer's documented posture). The consumer emits structured logs only.
- **`auto.offset.reset="earliest"`** is appropriate for the local/replay orientation of this milestone (ADR-001); production consumers would typically want `latest` with explicit reasoning ΓÇö worth a later note, not a defect here.
- **The at-least-once vs exactly-once honesty** is well expressed in both the module docstring and `docs/kafka-consumer.md`, matching PROJECT ┬º5 and SPEC ┬º9.

## 7. Verdict

**CHANGES REQUIRED**

All three previously-blocking defects (close-commits, silent malformed discard, environment override) are resolved in code, and the acceptance criterion "reliably consumes canonical events without claiming exactly-once" is now satisfied at the implementation level. However, the task cannot be `APPROVED` because the non-blocking findings (M1ΓÇôM3, Min1ΓÇôMin4) are neither fixed nor recorded in `docs/reviews/FOLLOWUPS.md` (which is empty), and ΓÇö most notably ΓÇö `docs/kafka-consumer.md` now **contradicts** the corrected code on graceful shutdown and shows non-working example code. These must be fixed or explicitly deferred in `FOLLOWUPS.md` before acceptance.

---

WORKFLOW_REVIEW: {"head": "463012bbb9f5f2c5338ae80e576db36cad427ca7", "verdict": "CHANGES REQUIRED", "blocking_findings": 0}
