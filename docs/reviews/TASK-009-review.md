I have completed my investigation. I read the task spec, reviewer instructions, `ai/AGENTS.md`, project constitution, specification (┬º7ΓÇô┬º10, ┬º22), ADR-001, ROADMAP (TASK-009 sequencing), the implementation (`libs/common/kafka_consumer.py`), the event contract, the config base, the producer (TASK-008) for convention comparison, the tests, the consumer doc, `.env.example`, `libs/common/README.md`, `pyproject.toml`, `FOLLOWUPS.md`, and the committed (stale) prior review. Here is the review report.

---

# TASK-009 Review ΓÇö Reusable Kafka Consumer

## 1. Review Header

| Field | Value |
| --- | --- |
| Task ID | TASK-009 |
| Review date | 2026-09-09 |
| Reviewed HEAD | `895efc9310e6f14bc4c8aa9cf1ec352ed820d256` |
| Reviewed Git range | `1d6bce1320f76d8ec028a1a20f40e1429cc88c44..895efc9310e6f14bc4c8aa9cf1ec352ed820d256` |
| Scope | Reusable Kafka consumer for canonical product-observation events |
| Verdict | **CHANGES REQUIRED** |

Sources of authority consulted: `ai/PROJECT.md` (┬º5 Event Semantics, ┬º9 Reliability, ┬º11 Security), `ai/SPECIFICATION.md` (┬º7 Event Contract, ┬º8 Kafka Architecture, ┬º9 Delivery Semantics, ┬º10 Invalid Events and DLQ, ┬º22 Testing), `docs/adr/ADR-001-kafka-topic-configuration.md`, `ai/tasks/TASK-009-kafka-consumer.md`, `ai/ROADMAP.md` (TASK-009ΓåÆ010ΓåÆ011ΓåÆ012 sequencing), and the referenced TASK-006/TASK-008 artifacts (`libs/event_contracts`, `libs/common/kafka_producer.py`, `libs/common/config.py`).

**Reconciliation note:** the supplied diff and the committed `docs/reviews/TASK-009-review.md` both reference intermediate commits (`463012bΓÇª`, `b3a28c4ΓÇª`). The on-disk files at the reviewed HEAD were inspected directly and treated as authoritative. Importantly, `docs/kafka-consumer.md` on disk is now **corrected** to match the implementation ΓÇö the documentation-contradiction finding raised in the intermediate reviews is resolved. The committed `docs/reviews/TASK-009-review.md` is a stale prior review (verdict against `463012bΓÇª`) and is superseded by this report.

The review was performed read-only; shell commands (`git status`, `pytest`, `ruff`, `mypy`) were prohibited, so test execution and lint/type checks were not independently run ΓÇö see ┬º4.

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
| --- | --- | --- |
| Consumer group configuration | Met | `KafkaConsumerSettings(AppSettings)` exposes `kafka_group_id`, `kafka_auto_offset_reset`, session/heartbeat/max-poll timeouts, `kafka_enable_auto_commit=False`; `consumer_config` builds the librdkafka dict; `KafkaConsumer.__init__` rejects an empty group id. |
| Deserialization and validation | Met | `poll()` deserializes via `deserialize_event(value.decode("utf-8"))`; valid events returned as `ConsumerMessage`; failures surfaced to the caller as `DeserializationError` with topic/partition/offset/`raw_value`. |
| Explicit offset handling | Met | `commit_message` commits `offset + 1` (next offset to read); `commit_offsets` for advanced/explicit use; `close()` no longer commits, preserving at-least-once. |
| Graceful shutdown | Met | SIGINT/SIGTERM handler sets `_shutdown_requested`; `poll()` returns `([], [])` when shutdown requested; context manager calls `close()`; `close()` is idempotent and does **not** commit. |
| Document when offsets are committed and what happens on processing failure | Met | `docs/kafka-consumer.md` documents commit timing, failure matrix, crash-after-write-before-commit, and `event_id` deduplication; its graceful-shutdown text and examples now match the corrected code. |
| Tests: valid event / malformed event / restart / duplicate delivery | Present (see M1) | All four categories exist in `tests/test_kafka_consumer.py`; malformed events are asserted to surface as `DeserializationError`. Restart/duplicate tests remain mock tautologies. |
| Acceptance criterion: reliably consumes canonical events without claiming exactly-once | **Met** | At-least-once honesty is correct in code, docstrings, and docs; no exactly-once claim is made; downstream deduplication by `event_id` is documented. |

## 3. Git Diff Review

Files changed (all new, in `docs/`, `libs/common/`, `tests/`):

- `docs/kafka-consumer.md` ΓÇö consumer guide.
- `docs/reviews/TASK-009-review.md` ΓÇö a prior review artifact (stale: references `463012bΓÇª`/`b3a28c4ΓÇª`, not the reviewed HEAD); superseded by this report.
- `libs/common/kafka_consumer.py` ΓÇö new consumer module.
- `tests/test_kafka_consumer.py` ΓÇö new unit tests.

Assessment:

- **Scope correctness:** All code/test/doc files belong to TASK-009. No out-of-scope service changes.
- **Unrelated changes:** None observed.
- **Architectural changes:** None. Adds a reusable library module; does not alter service boundaries, event semantics, or ADR-001 partitioning/consumer-group policy.
- **Accidental changes:** None. No debug code, temporary files, generated artifacts, or secrets found.
- **Dependency change:** None. `confluent-kafka` was already introduced in TASK-008.
- **Stale artifact:** the committed `docs/reviews/TASK-009-review.md` is an outdated review against a non-HEAD commit; it should be replaced by this report (which the calling script does).
- **Documentation/config gaps (see Min3):** `.env.example` still omits the consumer's `APP_KAFKA_GROUP_ID` / `APP_KAFKA_AUTO_OFFSET_RESET` / timeout variables (the producer section was added in TASK-008), and `libs/common/README.md` documents the producer but not the consumer.

## 4. Test and Verification Review

### Tests examined

`tests/test_kafka_consumer.py` covers: settings defaults/config dict/missing group id; valid consumption; poll timeout; malformed JSON surfaced as `DeserializationError`; invalid schema surfaced; None value surfaced; offset commit after success; no-commit-on-failure; restart with committed offsets; redelivery of uncommitted messages; duplicate delivery; downstream dedup; **no-commit-on-close**; shutdown flag; double-close; operations-after-close; partition EOF; transport error; unknown-topic error; subscription; assignment.

### Test adequacy

Improved over the prior reviews: three new tests assert the `DeserializationError` surfacing surface, and `test_shutdown_does_not_commit_unprocessed_offsets` now directly pins the no-commit-on-close behavior (the previous blocking interaction). Remaining weakness (M1): the restart/redelivery/duplicate tests (`test_restart_uses_committed_offsets`, `test_uncommitted_messages_redelivered_on_restart`, `TestDuplicateDelivery`) still assert mock `poll()`/`commit_offsets()` results rather than real Kafka offset semantics, so they would pass regardless of actual commit behavior. No test verifies the documented skip path for a `DeserializationError` (advancing its offset via `commit_offsets`) across `close()`/restart. Real-broker integration coverage is correctly deferred to TASK-012, so this is non-blocking.

### Independently verified (executed by reviewer)

None. The reviewer was prohibited from executing shell commands, so `pytest`, `ruff`, and `mypy` were **not** run.

### Implementation evidence reviewed (not rerun)

`libs/common/kafka_consumer.py`, `tests/test_kafka_consumer.py`, `docs/kafka-consumer.md`, `libs/common/config.py`, `libs/common/kafka_producer.py`, `libs/event_contracts/`, `.env.example`, `pyproject.toml`, and `docs/reviews/FOLLOWUPS.md` inspected directly. No test-run report was supplied for this HEAD.

### Unverified

- Test execution (unit tests).
- `ruff check` / `ruff format --check`.
- `mypy` ΓÇö notably `KafkaConsumerSettings.__init__(self, **kwargs: str | int | bool)` with `# type: ignore[arg-type]` under `warn_unused_ignores = true` (see M3).
- Branch name and working-tree state (no `git status`/`git log` permitted).

## 5. Findings

### High (blocking)

None. The previously-blocking defects are resolved in the reviewed HEAD:

- **Prior H1 (docs/code contradicted on shutdown, and examples used the removed single-return `poll()` API):** resolved ΓÇö `docs/kafka-consumer.md` now states `close()` "leaves the consumer group **without committing** unprocessed offsets", its examples unpack `messages, errors = consumer.poll(...)`, and its test-scenario list describes events as "returned as `DeserializationError`".
- **Prior H2/H3 (silent malformed-message discard; environment override to `development`):** resolved in code ΓÇö `poll()` surfaces failures, and `KafkaConsumerSettings.__init__` no longer injects `environment`.

### Moderate (non-blocking)

**M1 ΓÇö Required "restart"/"duplicate delivery" tests remain mock tautologies; the malformed-offset skip path is untested.**
File: `tests/test_kafka_consumer.py`.
`test_restart_uses_committed_offsets` asserts `commit_offsets` was called and `close.called`; `test_uncommitted_messages_redelivered_on_restart` re-asserts the same mocked `mock_msg` at offset 42 on a "second" consumer; both `TestDuplicateDelivery` tests feed the same mocked JSON at two offsets. None exercises real Kafka offset semantics, and no test verifies that a surfaced `DeserializationError`'s offset can be advanced via `commit_offsets` (the documented skip path) across `close()`/restart.
Impact: the required restart/duplicate coverage is largely illusory, so an offset-handling regression would not be caught by the unit suite.
Recommendation: add a test that, given a `DeserializationError`, the caller can `commit_offsets([TopicPartition(topic, partition, offset + 1)])` and that it is honored; strengthen restart/duplicate tests to assert actual `commit` calls rather than re-asserting the mock message. Real-Kafka integration remains TASK-012.

**M2 ΓÇö Consumer settings lack the producer's validators and omit `allow.auto.create.topics=false`.**
File: `libs/common/kafka_consumer.py`, `KafkaConsumerSettings`.
`kafka_group_id` accepts empty/arbitrary strings (only runtime-checked in `KafkaConsumer.__init__`, i.e., after settings load), and `kafka_bootstrap_servers` is not shape-validated ΓÇö unlike `KafkaProducerSettings` (`valid_name` / `valid_brokers`). `consumer_config` also omits `allow.auto.create.topics: false`, which ADR-001 states is disabled and the producer sets explicitly.
Impact: invalid configuration surfaces later than the producer's; the omission is defensively inconsistent with ADR-001 (librdkafka's consumer default is already `false`, but the explicit producer parity and ADR-001 intent are worth mirroring).
Recommendation: add `valid_name`/`valid_brokers` validators (mirror `KafkaProducerSettings`) and include `"allow.auto.create.topics": False` in `consumer_config`.

**M3 ΓÇö `KafkaConsumerSettings.__init__` is an unnecessary, type-unsound passthrough with a likely-unused `# type: ignore[arg-type]`.**
File: `libs/common/kafka_consumer.py`, `KafkaConsumerSettings.__init__`.
The override reduces to `super().__init__(**kwargs)` but keeps the narrowed `**kwargs: str | int | bool` signature and `# type: ignore[arg-type]`. Since `**kwargs: dict[str, str | int | bool]` expands compatibly into `BaseSettings.__init__(**values: Any)`, the `arg-type` ignore is very likely **unused**, and `pyproject.toml` sets `warn_unused_ignores = true` ΓÇö which would make `mypy` fail with "Unused 'type: ignore' comment". It also (a) drops `BaseSettings.__init__` capabilities such as `_env_file`/`_secrets_dir`, and (b) diverges from `KafkaProducerSettings`, which omits `__init__` entirely.
Impact: potential mypy/CI failure (unverified ΓÇö mypy not run); unnecessary divergence from the producer convention.
Recommendation: delete the `__init__` override entirely and rely on the inherited `BaseSettings.__init__`.

### Minor (non-blocking)

**Min1 ΓÇö `except Exception` in `poll()` is too broad; two exception classes are vestigial.**
File: `libs/common/kafka_consumer.py`, `poll()`.
The broad `except Exception` catches programming errors alongside the intended `pydantic.ValidationError`/`UnicodeDecodeError`. `MessageDeserializationError` is raised for a None value but is immediately swallowed by that same `try` (effectively dead), and `ProcessingError` is defined but only referenced in docstrings.
Recommendation: narrow the caught types (e.g., `pydantic.ValidationError`, `UnicodeDecodeError`, `MessageDeserializationError`); if `MessageDeserializationError`/`ProcessingError` are intended public API, document them or remove them.

**Min2 ΓÇö Signal handler registration is a surprising library side effect.**
File: `libs/common/kafka_consumer.py`, `_register_signal_handlers()`.
`__init__` calls `signal.signal(SIGINT/SIGTERM, ΓÇª)`, overriding the host application's handlers and only working on the main thread. A reusable library class should not clobber the embedding application's graceful-shutdown handling.
Recommendation: expose an opt-in shutdown flag setter or accept an external shutdown signal rather than registering handlers unconditionally.

**Min3 ΓÇö Documentation/config gaps.**
`.env.example` omits the consumer's `APP_KAFKA_GROUP_ID` / `APP_KAFKA_AUTO_OFFSET_RESET` / session/heartbeat/max-poll timeout variables; `libs/common/README.md` lists the producer but not the consumer; `docs/kafka-consumer.md` examples use `kafka:9092` where `docs/kafka-producer.md` states containers on the Compose network use `kafka:29092`; `test_commit_after_successful_processing` carries a stale comment ("second from close()") though `close()` no longer commits.

## 6. Non-Defect Observations

- **Per-message synchronous commit and single-message-per-poll** trade throughput for a simple, observable boundary ΓÇö consistent with the producer's design and acceptable for TASK-009; batching/performance is deferred.
- **Metrics are deferred to TASK-011** and real-Kafka integration tests to TASK-012 (consistent with the producer's documented posture). The consumer emits structured logs only.
- **`auto.offset.reset="earliest"`** is appropriate for the local/replay orientation of this milestone (ADR-001); production consumers would typically prefer `latest` ΓÇö worth a later note, not a defect here.
- **The at-least-once vs exactly-once honesty** is now correctly expressed in the module docstring, `close()`'s docstring, and `docs/kafka-consumer.md`, matching PROJECT ┬º5 and SPEC ┬º9.
- Surfacing `DeserializationError` in `poll()` correctly leaves the DLQ-routing decision to the caller and overlaps cleanly with TASK-010, which owns the invalid-topic/DLQ path.

## 7. Verdict

**CHANGES REQUIRED**

All confirmed blocking defects are resolved in the reviewed HEAD: the documentation now matches the implementation on shutdown/commit behavior and the tuple-returning `poll()` API, and the at-least-once acceptance criterion is correctly met. However, the task cannot be `APPROVED` because the non-blocking findings (M1, M2, M3, Min1ΓÇôMin3) are neither fixed nor recorded in `docs/reviews/FOLLOWUPS.md` (which is empty). Per the acceptance rule, these must be fixed or explicitly deferred in `FOLLOWUPS.md` before approval.

The highest-value items to close are M3 (likely mypy failure under `warn_unused_ignores = true`) and M2 (ADR-001 parity on auto-create and settings validation).

---

WORKFLOW_REVIEW: {"head": "895efc9310e6f14bc4c8aa9cf1ec352ed820d256", "verdict": "CHANGES REQUIRED", "blocking_findings": 0}
