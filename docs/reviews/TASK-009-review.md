I have completed my investigation. I read the task spec, reviewer instructions, project constitution, specification, ADR-001, the implementation (`libs/common/kafka_consumer.py`), event contracts, config base, the producer (TASK-008) for convention comparison, the tests, the consumer doc, `.env.example`, `libs/common/README.md`, `pyproject.toml`, ROADMAP sequencing, and the existing `FOLLOWUPS.md`. Here is the review report.

---

# TASK-009 Review ΓÇö Kafka Consumer

## 1. Review Header

| Field | Value |
| --- | --- |
| Task ID | TASK-009 |
| Review date | 2026-09-09 |
| Reviewed commit | `463012bbb9f5f2c5338ae80e576db36cad427ca7` |
| Reviewed Git range | `1d6bce1320f76d8ec028a1a20f40e1429cc88c44..463012bbb9f5f2c5338ae80e576db36cad427ca7` |
| Scope | Reusable Kafka consumer for canonical product-observation events |
| Verdict | **CHANGES REQUIRED** |

Sources of authority consulted: `ai/PROJECT.md` (┬º5 Event Semantics, ┬º9 Reliability, ┬º11 Security), `ai/SPECIFICATION.md` (┬º7 Event Contract, ┬º8 Kafka Architecture, ┬º9 Delivery Semantics, ┬º10 Invalid Events and DLQ, ┬º21 Security), `docs/adr/ADR-001-kafka-topic-configuration.md`, `ai/tasks/TASK-009-kafka-consumer.md`, `ai/ROADMAP.md` (TASK-009ΓåÆ010ΓåÆ011ΓåÆ012 sequencing), and the referenced TASK-006/TASK-008 artifacts (`libs/event_contracts`, `libs/common/kafka_producer.py`, `libs/common/config.py`).

This review supersedes the stale `docs/reviews/TASK-009-review.md` that is committed in the branch (it references commit `b3a28cΓÇª`, not the reviewed HEAD). The review was performed read-only; shell commands (`git status`, `pytest`, `ruff`, `mypy`) were prohibited, so branch/working-tree state and test execution could not be independently verified ΓÇö see ┬º4.

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
| --- | --- | --- |
| Consumer group configuration | Met | `KafkaConsumerSettings(AppSettings)` exposes `kafka_group_id`, `kafka_auto_offset_reset`, session/heartbeat/max-poll timeouts, `kafka_enable_auto_commit=False`; `consumer_config` builds the librdkafka dict. `KafkaConsumer.__init__` rejects an empty group id. |
| Deserialization and validation | Met | `poll()` deserializes via `deserialize_event(value.decode("utf-8"))` and returns `ConsumerMessage` for valid events. |
| Explicit offset handling | Met | `commit_message` (offset+1) and `commit_offsets` commit explicit offsets only. |
| Graceful shutdown | Met | SIGINT/SIGTERM handler sets `_shutdown_requested`; `poll()` returns empty when shutdown requested; context manager calls `close()`; `close()` is idempotent and **no longer commits** (H1 resolved). |
| Document when offsets are committed and what happens on processing failure | **Not met ΓÇö documentation contradicts implementation** | `docs/kafka-consumer.md` still states `close()` "flushes pending commits before leaving group" and that the context manager "commits pending offsets", which is the opposite of the corrected behavior; its example code uses the removed single-return `poll()` API. See Finding H1. |
| Tests: valid event / malformed event / restart / duplicate delivery | Present | All four categories have tests in `tests/test_kafka_consumer.py`, including new tests for the deserialization-error surface and the no-commit-on-close behavior. |
| Acceptance criterion: reliably consumes canonical events without claiming exactly-once | Met (code) | The at-least-once/honesty claim is correct in code; the reliability defects H2/H3 from the prior review are resolved. |

## 3. Git Diff Review

Files changed (all new, in `docs/`, `libs/common/`, `tests/`):

- `docs/kafka-consumer.md` ΓÇö consumer guide.
- `docs/reviews/TASK-009-review.md` ΓÇö a prior review artifact (stale: references `b3a28cΓÇª`, verdict CHANGES REQUIRED with 3 blocking findings).
- `libs/common/kafka_consumer.py` ΓÇö new consumer module.
- `tests/test_kafka_consumer.py` ΓÇö new unit tests.

Assessment:

- **Scope correctness:** All code/test/doc files belong to TASK-009. No out-of-scope service changes.
- **Unrelated changes:** None observed in code.
- **Architectural changes:** None. Adds a reusable library module; does not alter service boundaries, event semantics, or ADR-001 partitioning/consumer groups.
- **Accidental changes:** None. No debug code, temporary files, generated artifacts, or secrets found.
- **Dependency change:** None. `confluent-kafka` was already introduced in TASK-008.
- **Stale artifact note:** the committed `docs/reviews/TASK-009-review.md` is an outdated review (references a non-HEAD commit and contains mojibake/`???` artifacts in the rendered diff). It should be replaced by this report.
- **Documentation/config gaps (see Min3):** `.env.example` still omits the consumer's `APP_KAFKA_GROUP_ID` / `APP_KAFKA_AUTO_OFFSET_RESET` / timeout variables (the producer section was added in TASK-008), and `libs/common/README.md` documents the producer but not the consumer.

Evidence caveat: the supplied diff renders `docs/kafka-consumer.md` test-scenario bullets as unresolved `???` placeholders, whereas the on-disk file resolves them (`Γ£à`). Without `git status`/`git show` the reviewer could not determine whether this reflects diff rendering or working-tree state. The on-disk file was treated as authoritative. Branch name and working-tree cleanliness were **not independently verified**.

## 4. Test and Verification Review

### Tests examined

`tests/test_kafka_consumer.py` covers: valid consumption, poll timeout, malformed JSON surfaced as `DeserializationError`, invalid schema surfaced, None value surfaced, offset commit after success, no-commit-on-failure, restart with committed offsets, redelivery of uncommitted messages, duplicate delivery, downstream dedup, **no-commit-on-close**, shutdown flag, double-close, operations-after-close, partition EOF, transport error, unknown-topic error, and subscription/assignment.

### Test adequacy

Materially improved over the prior review: the H1 interaction is now pinned by `test_shutdown_does_not_commit_unprocessed_offsets`, and the H2 interaction by the three "returned as error" tests. Remaining weakness: the restart/redelivery/duplicate tests (`test_restart_uses_committed_offsets`, `test_uncommitted_messages_redelivered_on_restart`, `TestDuplicateDelivery`) still assert mock `poll()` results rather than real Kafka offset semantics ΓÇö they would pass regardless of commit behavior. Real-broker integration coverage is correctly deferred to TASK-012, so this is non-blocking.

### Independently verified (executed by reviewer)

None. The reviewer was prohibited from executing shell commands, so `pytest`, `ruff`, and `mypy` were **not** run.

### Implementation evidence reviewed (not rerun)

`libs/common/kafka_consumer.py`, `tests/test_kafka_consumer.py`, and `docs/kafka-consumer.md` inspected directly. No test-run report was supplied for this HEAD.

### Unverified

- Test execution (unit tests).
- `ruff check` / `ruff format --check`.
- `mypy` ΓÇö notably `KafkaConsumerSettings.__init__(self, **kwargs: str | int | bool)` with `# type: ignore[arg-type]` under `warn_unused_ignores = true` (see Finding M1); a possibly-unused ignore would fail mypy.
- Branch name and working-tree state.

## 5. Findings

### High (blocking)

**H1 ΓÇö `docs/kafka-consumer.md` still describes the removed commit-on-close behavior and uses the removed single-return `poll()` API, contradicting the corrected at-least-once semantics.**
File: `docs/kafka-consumer.md` ΓÇö "Graceful Shutdown" section and examples.
The "Graceful Shutdown" list states `3. close() flushes pending commits before leaving group`, and the shutdown example ends with `# Automatically closes and commits pending offsets`. The implementation's `close()` now only calls `self._consumer.close()` and its docstring explicitly says it "Leaves the consumer group cleanly without committing unprocessed offsets." The doc therefore states the *opposite* of the code ΓÇö the exact data-loss behavior that was just removed. In addition, the examples assign `messages = consumer.poll(timeout=1.0)` and then iterate `for msg in messages:`, but `poll()` now returns a `(messages, errors)` tuple, so the example code would not run (it would iterate over the two lists). The "Test scenarios covered" bullets still say malformed/invalid events are "logged and skipped" rather than surfaced as `DeserializationError`.
Impact: the task's explicit "Document when offsets are committed" requirement is satisfied with a factually incorrect statement about the core reliability guarantee; a reader following the guide would believe uncommitted messages are acknowledged on shutdown.
Recommendation: update the guide to state that `close()` does **not** commit; correct the example code to unpack `messages, errors = consumer.poll(...)` and demonstrate `DeserializationError` handling; adjust the "logged and skipped" wording.

### Moderate (non-blocking)

**M1 ΓÇö `KafkaConsumerSettings.__init__` is now a pointless, type-unsound passthrough.**
File: `libs/common/kafka_consumer.py`, `KafkaConsumerSettings.__init__`.
After removing the `environment="development"` injection, the override reduces to `super().__init__(**kwargs)` but keeps the narrowed `**kwargs: str | int | bool` signature and `# type: ignore[arg-type]`. This (a) drops `BaseSettings.__init__` capabilities such as `_env_file`/`_secrets_dir`, (b) is type-unsound, and (c) under `warn_unused_ignores = true` risks a mypy failure if the ignore is not actually triggered. `KafkaProducerSettings` omits `__init__` entirely.
Impact: possible mypy/CI failure; unnecessary divergence from the producer convention.
Recommendation: delete the `__init__` override entirely; rely on inherited `BaseSettings.__init__`.

**M2 ΓÇö Consumer settings lack the producer's validation and omit `allow.auto.create.topics=false`.**
File: `libs/common/kafka_consumer.py`.
`kafka_bootstrap_servers` has no `valid_brokers` validator and `kafka_group_id` has no `valid_name` validator (only a runtime empty-string check). `consumer_config` omits `allow.auto.create.topics: false`, so a typo'd topic could be auto-created ΓÇö ADR-001 states auto-create is disabled.
Impact: invalid configuration surfaces later than it should; a typo'd subscription can implicitly create a topic.
Recommendation: add `valid_name`/`valid_brokers` validators (mirror `KafkaProducerSettings`) and include `"allow.auto.create.topics": False` in `consumer_config`.

### Minor (non-blocking)

**Min1 ΓÇö `except Exception` in `poll()` is too broad.** It catches programming errors alongside the intended `pydantic.ValidationError`/`UnicodeDecodeError`. `MessageDeserializationError` is raised and immediately swallowed by the same `try` (effectively dead), and `ProcessingError` is defined but only referenced in the docstring. Consider narrowing the caught types and, if `MessageDeserializationError`/`ProcessingError` are intended public API, document them rather than leaving them vestigial.

**Min2 ΓÇö Signal handler registration is a surprising library side effect.** `__init__` calls `signal.signal(SIGINT/SIGTERM, ΓÇª)`, overriding host-application handlers and only working on the main thread. A reusable library class should not clobber the embedding application's graceful-shutdown handling.

**Min3 ΓÇö Documentation/config gaps.** `.env.example` omits the consumer's `APP_KAFKA_GROUP_ID` / `APP_KAFKA_AUTO_OFFSET_RESET` / timeout variables; `libs/common/README.md` lists the producer but not the consumer; `docs/kafka-consumer.md` examples use `kafka:9092` while the producer doc specifies containers use `kafka:29092`; `test_commit_after_successful_processing` carries a stale comment ("second from close()") though `close()` no longer commits.

## 6. Non-Defect Observations

- **Per-message synchronous commit and single-message-per-poll** trade throughput for a simple, observable boundary ΓÇö consistent with the producer's design and acceptable for TASK-009; batching is deferred.
- **Metrics are deferred to TASK-011** and real-Kafka integration tests to TASK-012; the consumer emits structured logs only, consistent with the producer's TASK-008 posture.
- **`auto.offset.reset="earliest"`** is appropriate for the local/replay orientation of this milestone (ADR-001); production consumers would typically prefer `latest` ΓÇö worth a later note, not a defect here.
- The **at-least-once vs exactly-once honesty** is now correctly expressed in both the code docstring and `close()`'s docstring, matching PROJECT ┬º5 and SPEC ┬º9.
- Surfacing `DeserializationError` in `poll()` correctly leaves the DLQ routing decision to the caller and overlaps cleanly with TASK-010, which owns the invalid-topic/DLQ path.

## 7. Verdict

**CHANGES REQUIRED**

The three code-level blocking defects from the prior review are resolved: `close()` no longer commits the current position, `poll()` surfaces deserialization failures with full context, and `KafkaConsumerSettings` no longer overrides `APP_ENVIRONMENT`.

One blocking defect remains, plus unfixed non-blocking findings:

1. `docs/kafka-consumer.md` still asserts `close()` flushes/commits pending offsets and uses the removed single-return `poll()` API, contradicting the corrected at-least-once semantics ΓÇö H1 (blocking).
2. `KafkaConsumerSettings.__init__` is a type-unsound passthrough with a possible `warn_unused_ignores` mypy failure ΓÇö M1.
3. Missing settings validation and `allow.auto.create.topics=false` ΓÇö M2.
4. Minor findings Min1ΓÇôMin3.

Non-blocking findings are neither fixed nor documented in `docs/reviews/FOLLOWUPS.md` (currently empty). The verdict is therefore CHANGES REQUIRED: fix H1 and either fix or record M1/M2/Min1ΓÇôMin3 in `FOLLOWUPS.md`.

---

WORKFLOW_REVIEW: {"head": "463012bbb9f5f2c5338ae80e576db36cad427ca7", "verdict": "CHANGES REQUIRED", "blocking_findings": 1}
