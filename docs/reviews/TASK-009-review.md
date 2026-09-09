I have completed my investigation. I've read the task spec, reviewer instructions, project constitution, specification, ADR-001, the implementation (`libs/common/kafka_consumer.py`), the event contracts, the config base, the producer (TASK-008) for convention comparison, the tests, the docs, `.env.example`, and `libs/common/README.md`. Here is the review report.

---

# TASK-009 Review ΓÇö Kafka Consumer

## 1. Review Header

| Field | Value |
| --- | --- |
| Task ID | TASK-009 |
| Review date | 2026-09-09 |
| Reviewed commit | `b3a28c417b5a30fa9b4c978fc531960a63f79360` |
| Reviewed Git range | `1d6bce1320f76d8ec028a1a20f40e1429cc88c44..b3a28c417b5a30fa9b4c978fc531960a63f79360` |
| Scope | Reusable Kafka consumer for canonical product-observation events |
| Verdict | **CHANGES REQUIRED** |

Sources of authority consulted: `ai/PROJECT.md` (┬º5 Event Semantics, ┬º9 Reliability, ┬º11 Security), `ai/SPECIFICATION.md` (┬º7 Event Contract, ┬º8 Kafka Architecture, ┬º9 Delivery Semantics, ┬º10 Invalid Events and DLQ), `docs/adr/ADR-001-kafka-topic-configuration.md`, `ai/tasks/TASK-009-kafka-consumer.md`, and the referenced TASK-006/TASK-008 artifacts (`libs/event_contracts`, `libs/common/kafka_producer.py`, `libs/common/config.py`).

Note: the review was performed with read-only file access. The reviewer was explicitly prohibited from executing shell commands (including `git status`, `pytest`, `ruff`, `mypy`), so branch/working-tree state and test execution could not be independently verified; see ┬º4.

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
| --- | --- | --- |
| Consumer group configuration | Met | `KafkaConsumerSettings(AppSettings)` with `kafka_group_id`, `kafka_auto_offset_reset`, session/heartbeat/max-poll timeouts, `enable.auto.commit=False`; `consumer_config` property builds the librdkafka dict. |
| Deserialization and validation | Met with defects | `poll()` deserializes via `deserialize_event(value.decode("utf-8"))`; valid events are returned as `ConsumerMessage`. Malformed/invalid messages are logged and dropped, but their offset is neither committed nor surfaced to the caller ΓÇö see Finding H2. |
| Explicit offset handling | Met with defects | `commit_message` (offset+1) and `commit_offsets` are provided; `close()` additionally performs a no-args `commit()` that acknowledges fetched-but-uncommitted messages ΓÇö see Finding H1. |
| Graceful shutdown | Met with defects | SIGINT/SIGTERM handler sets `_shutdown_requested`; `poll()` returns empty when shutdown is requested; context manager calls `close()`; `close()` is idempotent. But `close()` commits the current position (H1). |
| Document when offsets are committed and what happens on processing failure | Met with inaccuracies | `docs/kafka-consumer.md` covers commit timing, failure matrix, and redelivery. It inaccurately states `close()` "flushes pending commits" (see H1) and describes DLQ routing as "optional" (SPEC ┬º10 makes it required; the consumer exposes no DLQ path). |
| Tests: valid event / malformed event / restart / duplicate delivery | Present but shallow | All four categories have tests in `tests/test_kafka_consumer.py`; the restart/redelivery/duplicate tests are mock tautologies and the malformed-offset interaction is untested ΓÇö see Finding M1. |
| Acceptance criterion: reliably consumes canonical events without claiming exactly-once | **Not met** | The at-least-once/honesty claim is correct, but the reliability defects H1 and H2 mean a malformed message can wedge the partition on restart, and a processing-failed message can be silently lost on graceful shutdown. |

## 3. Git Diff Review

Files changed (3, all new):

- `docs/kafka-consumer.md` ΓÇö consumer guide.
- `libs/common/kafka_consumer.py` ΓÇö new consumer module (+348).
- `tests/test_kafka_consumer.py` ΓÇö new unit tests (+595).

Assessment:

- **Scope correctness:** All three files belong to TASK-009. No out-of-scope files modified.
- **Unrelated changes:** None observed.
- **Architectural changes:** None. Adds a library module; does not alter service boundaries, event semantics, or ADR-001 partitioning/consumer groups.
- **Accidental changes:** None. No debug code, temporary files, generated artifacts, or secrets found.
- **Dependency change:** None. `confluent-kafka` was already introduced in TASK-008.
- **Documentation/config gaps (see Min4):** `.env.example` was not extended with the consumer's new `APP_KAFKA_GROUP_ID` / `APP_KAFKA_AUTO_OFFSET_RESET` / timeout variables (the producer section was added in TASK-008), and `libs/common/README.md` documents the producer but not the consumer.

Evidence caveat: the supplied diff shows `docs/kafka-consumer.md` containing unresolved `???` placeholders in its test-scenario list, whereas the on-disk file has them resolved (`Γ£à`/`ΓÇö`). The reviewer was unable to run `git status`/`git show` to determine whether this reflects a stale diff or uncommitted working-tree changes. The on-disk file was treated as the authoritative implementation. Branch name and working-tree cleanliness were **not independently verified**.

## 4. Test and Verification Review

### Tests examined

`tests/test_kafka_consumer.py` (595 lines) covers: valid consumption, poll timeout, malformed JSON, invalid schema, None value, offset commit after success, no-commit-on-failure, restart with committed offsets, redelivery of uncommitted messages, duplicate delivery, downstream dedup, shutdown commit, shutdown flag, double-close, operations-after-close, partition EOF, transport error, unknown-topic error, and subscription/assignment.

### Test adequacy

Weak in the areas the task cares most about (see Finding M1): the "restart", "redelivery", and "duplicate delivery" tests assert mock poll results rather than Kafka offset semantics, and no test exercises the malformed-message offset interaction across `close()`/restart ΓÇö the exact path where H1/H2 live.

### Independently verified (executed by reviewer)

None. The reviewer was prohibited from executing shell commands, so `pytest`, `ruff`, and `mypy` were **not** run.

### Implementation evidence reviewed (not rerun)

`libs/common/kafka_consumer.py`, `tests/test_kafka_consumer.py`, and `docs/kafka-consumer.md` were inspected directly. No test-run report was supplied, and the docs reference the test command without asserting a result.

### Unverified

- Test execution (unit tests).
- `ruff check` / `ruff format --check`.
- `mypy` (notably the `**kwargs: str | int | bool` signature and `# type: ignore[arg-type]` with `warn_unused_ignores = true` in `pyproject.toml` ΓÇö see Min3).
- Branch name and working-tree state.

## 5. Findings

### High (blocking)

**H1 ΓÇö `close()` commits the consumer's current position, causing silent data loss.**
File: `libs/common/kafka_consumer.py`, `close()` (lines ~289ΓÇô297).
`close()` calls `self._consumer.commit(asynchronous=False)` with no message/offsets. This commits librdkafka's current position, which has already advanced past any message returned by `poll()` ΓÇö including messages the caller fetched but did not successfully process, and malformed messages silently dropped by `poll()`. A message whose processing failed (which the at-least-once contract says must be redelivered) is silently acknowledged on graceful shutdown. This directly contradicts the module docstring ("pending offsets are flushed") and `docs/kafka-consumer.md` ("close() flushes pending commits before leaving group"). It also contradicts `test_shutdown_commits_pending_offsets`, which enshrines the incorrect behavior.
Impact: data loss at the exact failure boundary this platform exists to protect.
Recommendation: remove the no-args `commit()` from `close()`; rely on the caller's explicit `commit_message` calls and simply `close()` the underlying consumer (which does not auto-commit when `enable.auto.commit=False`). If a final flush is desired, track which offsets were explicitly committed and flush only those.

**H2 ΓÇö Malformed/invalid messages are silently discarded with no way to advance their offset.**
File: `libs/common/kafka_consumer.py`, `poll()` (lines ~178ΓÇô210).
Deserialization failures are caught, logged, and the message is omitted from the return value; its offset is neither committed nor surfaced to the caller. Consequences: on crash/restart the malformed message redelivers indefinitely (a poison pill that wedges the partition's committed offset, since the caller can never acknowledge it); on graceful shutdown `close()` commits past it (silent loss). `MessageDeserializationError` is raised and immediately swallowed by the same `except Exception`, so it never surfaces. This violates SPEC ┬º10 ("Invalid events must not silently disappear ΓÇª routed to the invalid/DLQ path ΓÇª preserve enough information to diagnose") and the task's own "explicit offset handling" scope.
Impact: a single malformed message can wedge a partition on restart, or be silently dropped on graceful shutdown ΓÇö neither is "reliably consumes canonical events".
Recommendation: surface failed messages to the caller (e.g., a `ConsumerMessage`-or-error result, or a callback) so the caller can decide to commit/skip or route to DLQ; alternatively, commit the offset after logging with explicit "skip" semantics. This overlaps TASK-010 (which owns "invalid events must not disappear"), but the reusable interface must be corrected in TASK-009 so a caller *can* handle the failure.

**H3 ΓÇö `KafkaConsumerSettings.__init__` silently overrides `APP_ENVIRONMENT`.**
File: `libs/common/kafka_consumer.py`, `KafkaConsumerSettings.__init__` (lines ~43ΓÇô47).
The `__init__` injects `environment="development"` whenever it is absent from kwargs. Because pydantic-settings init kwargs outrank environment variables, this (a) makes the deliberately-required `AppSettings.environment` field optional for this subclass and (b) overrides a real `APP_ENVIRONMENT=production` with `development`. This breaks the platform's "separate development and production configuration" principle (PROJECT ┬º11 / SPEC ┬º21), which is why `config.py` declares `environment: Environment` with no default. It is inconsistent with `KafkaProducerSettings`, which does not override `__init__` and therefore requires `APP_ENVIRONMENT`.
Impact: a production misconfiguration can silently run as "development" with no startup failure.
Recommendation: remove the `__init__` override and supply `environment` in tests (or set `APP_ENVIRONMENT` in the test environment), matching the producer's behavior.

### Moderate (non-blocking)

**M1 ΓÇö Required test scenarios are mock tautologies and the critical malformed-offset interaction is untested.**
File: `tests/test_kafka_consumer.py`.
`test_restart_uses_committed_offsets`, `test_uncommitted_messages_redelivered_on_restart`, and both `TestDuplicateDelivery` tests assert mock poll results rather than real Kafka offset semantics; they would pass regardless of the consumer's commit behavior. `test_no_commit_on_processing_failure` asserts `commit` was not called *inside* the `with` block, before `close()` runs its (buggy) commit, so it never observes the actual close behavior. No test verifies what happens to a malformed message's offset across `close()`/restart.
Impact: the required "restart" and "duplicate delivery" coverage is illusory, and H1/H2 are not caught.
Recommendation: add a test asserting a malformed message's offset is either committed (skip) or surfaced to the caller, and a test asserting `close()` does not commit an offset that was never explicitly committed.

**M2 ΓÇö Consumer settings lack the validation present in the producer, and omit `allow.auto.create.topics=false`.**
File: `libs/common/kafka_consumer.py`.
`kafka_group_id` accepts empty/arbitrary strings (only runtime-checked in `KafkaConsumer.__init__`), and `kafka_bootstrap_servers` is not shape-validated ΓÇö unlike `KafkaProducerSettings`, which uses `valid_name`/`valid_brokers`. The consumer config dict also omits `allow.auto.create.topics: false`, so a typo'd topic could be auto-created (ADR-001 states auto-create is disabled).
Impact: invalid configuration surfaces later than it should; a typo'd subscription can implicitly create a topic.
Recommendation: add `valid_name`-style validators to consumer settings and include `allow.auto.create.topics: False` in `consumer_config`.

### Minor (non-blocking)

**Min1 ΓÇö `except Exception` in `poll()` is too broad.** It catches programming errors (e.g., `AttributeError`) alongside the intended `pydantic.ValidationError`/`UnicodeDecodeError`, hiding bugs. `MessageDeserializationError` is effectively dead (raised then swallowed in the same `try`).

**Min2 ΓÇö Signal handler registration is a surprising library side effect.** `__init__` calls `signal.signal(SIGINT/SIGTERM, ΓÇª)`, overriding the host application's handlers and only working on the main thread. A reusable library class should not clobber the embedding application's graceful-shutdown handling.

**Min3 ΓÇö `__init__(self, **kwargs: str | int | bool)` with `# type: ignore[arg-type]` is type-unsound.** The signature does not match `BaseSettings.__init__`, and under `warn_unused_ignores = true` the suppression may itself fail mypy. Unverified (mypy not run).

**Min4 ΓÇö Documentation/config gaps.** `.env.example` omits the consumer's `APP_KAFKA_GROUP_ID` / `APP_KAFKA_AUTO_OFFSET_RESET` / timeout variables; `libs/common/README.md` lists the producer but not the consumer; `docs/kafka-consumer.md` examples use `kafka:9092` while `docs/kafka-producer.md` specifies containers use `kafka:29092`; the failure matrix's "close() flushes pending commits" statement is inaccurate (see H1).

## 6. Non-Defect Observations

- **Per-message synchronous commit and single-message-per-poll** trade throughput for a simple, observable boundary ΓÇö consistent with the producer's design and acceptable for TASK-009; batching/performance is deferred.
- **Metrics are explicitly deferred to TASK-011**, and real-Kafka integration tests to TASK-012. The consumer emits structured logs only, consistent with the producer's TASK-008 posture.
- **`auto.offset.reset="earliest"`** is appropriate for the local/replay orientation of this milestone (ADR-001); production consumers would typically want `latest` with explicit reasoning ΓÇö worth a later note, not a defect here.
- The at-least-once vs exactly-once honesty is well expressed in both the code docstring and `docs/kafka-consumer.md`, matching PROJECT ┬º5 and SPEC ┬º9.

## 7. Verdict

**CHANGES REQUIRED**

Three blocking defects must be resolved before acceptance:

1. `close()` commits the current position (data loss on graceful shutdown) ΓÇö H1.
2. Malformed/invalid messages are silently discarded with no offset advancement or caller visibility (poison pill / silent drop) ΓÇö H2.
3. `KafkaConsumerSettings` silently overrides `APP_ENVIRONMENT` with `development` ΓÇö H3.

The non-blocking findings (M1, M2, Min1ΓÇôMin4) must be fixed or explicitly documented in `docs/reviews/FOLLOWUPS.md` before the task can be APPROVED.

---

WORKFLOW_REVIEW: {"head": "b3a28c417b5a30fa9b4c978fc531960a63f79360", "verdict": "CHANGES REQUIRED", "blocking_findings": 3}
