I have completed a thorough read-only investigation. Here is the complete review report.

---

# TASK-009 Review ΓÇö Reusable Kafka Consumer

## 1. Review Header

| Field | Value |
| --- | --- |
| Task ID | TASK-009 |
| Review date | 2026-09-09 |
| Reviewed HEAD | `dc54cc4567750fc35a3eb325d46c4807a5357780` |
| Reviewed Git range | `1d6bce1320f76d8ec028a1a20f40e1429cc88c44..dc54cc4567750fc35a3eb325d46c4807a5357780` |
| Scope | Reusable Kafka consumer for canonical product-observation events |
| Verdict | **CHANGES REQUIRED** |

Sources of authority consulted: `ai/PROJECT.md` (┬º5 at-least-once + idempotent processing), `ai/SPECIFICATION.md` (┬º8 Kafka Architecture, ┬º9 At-least-once delivery + idempotent processing, ┬º10 Invalid Events and DLQ), `docs/adr/ADR-001-kafka-topic-configuration.md`, `ai/tasks/TASK-009-kafka-consumer.md`, `ai/AGENTS.md`, and the referenced TASK-006/TASK-008 artifacts (`libs/event_contracts`, `libs/common/kafka_producer.py`, `libs/common/config.py`).

This review was performed read-only: shell commands (`git status`, `git log`, `pytest`, `ruff`, `mypy`) were prohibited, so branch name, working-tree cleanliness, and test/lint/type execution could not be independently verified. The committed `docs/reviews/TASK-009-review.md` at HEAD is a prior review against `895efc9310e6f14bc4c8aa9cf1ec352ed820d256` (not the reviewed HEAD) and is superseded by this report.

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
| --- | --- | --- |
| Consumer group configuration | Met | `KafkaConsumerSettings(AppSettings)` exposes `kafka_group_id`, `kafka_auto_offset_reset`, session/heartbeat/max-poll timeouts, `kafka_enable_auto_commit=False`; `consumer_config` builds the librdkafka dict; `KafkaConsumer.__init__` rejects an empty group id. |
| Deserialization and validation | Met | `poll()` calls `deserialize_event(value.decode("utf-8"))`; valid events become `ConsumerMessage`; malformed/invalid/None values are surfaced to the caller as `DeserializationError` with topic/partition/offset/`raw_value` context. |
| Explicit offset handling | Met | `commit_message` commits `offset + 1`; `commit_offsets` commits explicit `TopicPartition`s; auto-commit disabled; commits are synchronous and only on success. |
| Graceful shutdown | Met | SIGINT/SIGTERM handler sets `_shutdown_requested`; `poll()` returns empty on shutdown; context manager calls `close()`; `close()` is idempotent and does **not** commit unprocessed offsets. |
| Document commit timing and failure behavior | Met | `docs/kafka-consumer.md` states offsets are committed only via `commit_message()` after success, that failures leave offsets uncommitted (redelivered), and that `close()` leaves the group without committing. |
| Tests: valid / malformed / restart / duplicate delivery | Met (restart/duplicate shallow) | All four categories exist in `tests/test_kafka_consumer.py`; malformed cases are asserted to surface as `DeserializationError`. Restart/duplicate tests are mock tautologies (see O1). |
| Acceptance: reliably consumes canonical events without claiming exactly-once | Met | At-least-once honesty is expressed in module/`close()` docstrings and `docs/kafka-consumer.md`; no exactly-once claim is made (PROJECT ┬º5, SPEC ┬º9). |

## 3. Git Diff Review

Files in the reviewed range:

- `docs/kafka-consumer.md` ΓÇö new consumer guide.
- `docs/reviews/FOLLOWUPS.md` ΓÇö modified (adds six deferred-finding rows).
- `docs/reviews/TASK-009-review.md` ΓÇö new review artifact (stale; superseded here).
- `libs/common/kafka_consumer.py` ΓÇö new consumer module.
- `tests/test_kafka_consumer.py` ΓÇö new unit tests.

Assessment:

- **Scope correctness:** All code/test/doc files belong to TASK-009. The review artifacts are legitimate outputs of this task's review cycle.
- **Unrelated changes:** None observed.
- **Architectural changes:** None. Adds a reusable library module; does not alter service boundaries, event semantics, or ADR-001 partitioning/consumer-group assignments.
- **Accidental changes:** None. No debug code, temporary files, generated artifacts, or secrets found.
- **Dependency change:** None. `confluent-kafka` was introduced in TASK-008.
- **Stale artifacts:** the committed review doc references commit `895efc93` and contains mojibake; `FOLLOWUPS.md` rows reference commit `463012b` (neither is the reviewed HEAD). Both are process notes, not code defects.

## 4. Test and Verification Review

### Tests examined

`tests/test_kafka_consumer.py` covers: settings defaults/config dict/missing group id; valid consumption; poll timeout; malformed JSON surfaced as `DeserializationError`; invalid schema surfaced; None value surfaced; offset commit after success; no-commit-on-failure; restart with committed offsets; redelivery of uncommitted messages; duplicate delivery; downstream dedup; no-commit-on-close; shutdown flag; double-close; operations-after-close; partition EOF; transport error; unknown-topic error; subscription; assignment.

### Test adequacy

The four required categories are present. The at-least-once offset interaction is pinned by `test_commit_after_successful_processing` (asserts commit of `offset + 1`), `test_no_commit_on_processing_failure`, and `test_shutdown_does_not_commit_unprocessed_offsets`, plus three tests that assert malformed/invalid/None values surface as `DeserializationError`. Weakness: the "restart"/"duplicate delivery" tests do not exercise real Kafka offset semantics (see O1); real-broker integration is owned by TASK-012.

### Independently verified (executed by reviewer)

None. `pytest`, `ruff`, and `mypy` were **not** run (shell execution prohibited).

### Implementation evidence reviewed (not rerun)

`libs/common/kafka_consumer.py`, `tests/test_kafka_consumer.py`, `docs/kafka-consumer.md`, `libs/common/config.py`, `libs/common/kafka_producer.py`, `libs/event_contracts/`, `docs/adr/ADR-001-kafka-topic-configuration.md`, `.env.example`, `libs/common/README.md`, `docker-compose.yml`, `pyproject.toml`, and `docs/reviews/FOLLOWUPS.md`. No test-run report was supplied for this HEAD.

### Unverified

- Test execution (unit tests).
- `ruff check` / `ruff format --check`.
- `mypy` ΓÇö notably `KafkaConsumerSettings.__init__` with `# type: ignore[arg-type]` under `warn_unused_ignores = true` (see M1).
- Branch name and working-tree cleanliness.

## 5. Findings

### High (blocking)

None. The three previously blocking defects are resolved in code and tests: `close()` no longer commits unprocessed offsets (verified in code and `test_shutdown_does_not_commit_unprocessed_offsets`); `poll()` surfaces malformed/invalid/None messages as `DeserializationError` instead of silently dropping them (verified in code and three tests); `KafkaConsumerSettings.__init__` no longer injects an `environment` override.

### Moderate (non-blocking)

**M1 ΓÇö `KafkaConsumerSettings.__init__` is a redundant, type-unsound passthrough.**
File: `libs/common/kafka_consumer.py`, `KafkaConsumerSettings.__init__`.
The override reduces to `super().__init__(**kwargs)` but keeps the narrowed `**kwargs: str | int | bool` signature and `# type: ignore[arg-type]`. This diverges from `KafkaProducerSettings` (which omits `__init__` entirely) and relies on a `type: ignore` that, under `pyproject.toml`'s `warn_unused_ignores = true`, is fragile. Impact: weakened static checking and convention divergence; possible future mypy/CI failure. Recommendation: delete the override and rely on the inherited `BaseSettings.__init__`.
Status: **Documented in `docs/reviews/FOLLOWUPS.md`** ("M1: KafkaConsumerSettings.__init__ passthrough with type ignore"). Γ£à

**M2 ΓÇö Consumer settings omit `allow.auto.create.topics=false` and the producer's validators.**
File: `libs/common/kafka_consumer.py`, `KafkaConsumerSettings`.
`consumer_config` does not set `allow.auto.create.topics: False` (the producer sets it; ADR-001 explicitly rejects auto-create and `docker-compose.yml` enforces it broker-side). `kafka_bootstrap_servers` has no `valid_brokers` validator and `kafka_group_id` has no `valid_name` validator (only a runtime empty-string check in `KafkaConsumer.__init__`). Impact: invalid configuration surfaces later than the producer's; client-side defense-in-depth against topic typos is missing. Recommendation: mirror `KafkaProducerSettings`'s `valid_name`/`valid_brokers` validators and add `"allow.auto.create.topics": False`.
Status: **Documented in `docs/reviews/FOLLOWUPS.md`** ("M2: Missing settings validation and allow.auto.create.topics=false"). Γ£à

### Minor (non-blocking)

**Min1 ΓÇö Broad `except Exception` in `poll()`; vestigial exception types/state.**
File: `libs/common/kafka_consumer.py`, `poll()`.
The broad `except Exception` catches programming errors alongside the intended `pydantic.ValidationError`/`UnicodeDecodeError`. `MessageDeserializationError` is raised inside the `try` and immediately swallowed (the caller only sees the `DeserializationError` dataclass); `ProcessingError` is defined but never raised in-module; `_subscribed_topics` is written but never read. Recommendation: narrow the caught types and either document the two exception classes as public API or remove them.
Status: **Documented in `docs/reviews/FOLLOWUPS.md`** ("Min1: Broad except Exception in poll()"). Γ£à

**Min2 ΓÇö Signal-handler registration is a library side effect.**
File: `libs/common/kafka_consumer.py`, `_register_signal_handlers`.
`__init__` registers SIGINT/SIGTERM handlers globally, overriding the host application's handlers, and only works on the main thread (non-main-thread construction logs a warning). A reusable library class should not clobber the embedding application's shutdown handling. Recommendation: accept an explicit shutdown flag/callback, or document this prominently.
Status: **Documented in `docs/reviews/FOLLOWUPS.md`** ("Min2: Signal handler registration as library side effect"). Γ£à

**Min3 ΓÇö Documentation/config gaps.**
- `.env.example` documents `APP_KAFKA_*` producer variables but none of the consumer's (`APP_KAFKA_GROUP_ID`, `APP_KAFKA_AUTO_OFFSET_RESET`, timeouts).
- `libs/common/README.md` documents `kafka_producer.py` but not `kafka_consumer.py`.
- `docs/kafka-consumer.md` examples use `kafka_bootstrap_servers="kafka:9092"`, but `docker-compose.yml` advertises container-to-container Kafka on `kafka:29092` (host is `localhost:9092`).
Status: **Documented in `docs/reviews/FOLLOWUPS.md`** ("Min3: Documentation/config gaps (.env.example, README, port discrepancy)"). Γ£à

**Min4 ΓÇö Stale comment in `test_commit_after_successful_processing`.**
File: `tests/test_kafka_consumer.py`, `test_commit_after_successful_processing`.
The comment "First call is from commit_message, second from close()" is stale: `close()` no longer commits. Comment-only; zero runtime impact.
Status: **Documented in `docs/reviews/FOLLOWUPS.md`** ("Min4: Stale comment in test_commit_after_successful_processing"). Γ£à

**Min5 ΓÇö Test module mutates global environment at import.**
File: `tests/test_kafka_consumer.py`, line 21.
`os.environ["APP_ENVIRONMENT"] = "development"` executes at module import, permanently mutating process-global state for the whole test session and diverging from `tests/test_kafka_producer.py`, which uses an autouse `monkeypatch` fixture that clears `APP_` variables and sets `APP_ENVIRONMENT` per test. Impact: weaker test isolation and a leak of `APP_ENVIRONMENT` into unrelated tests; inconsistent with the established convention. Recommendation: use a `monkeypatch`/`conftest.py` fixture.
Status: **NOT documented in `docs/reviews/FOLLOWUPS.md`.** Γ¥î

## 6. Non-Defect Observations

- **O1 ΓÇö "Restart"/"duplicate delivery" tests are mock tautologies.** `test_restart_uses_committed_offsets`, `test_uncommitted_messages_redelivered_on_restart`, and `TestDuplicateDelivery` assert the mock `poll()` results that were themselves configured, and do not exercise real Kafka offset resumption/redelivery. This is not recorded as a finding because the offset-commit interaction is still pinned by `test_commit_after_successful_processing`, `test_no_commit_on_processing_failure`, and `test_shutdown_does_not_commit_unprocessed_offsets`, and because real-broker integration is explicitly owned by TASK-012. It is flagged here for transparency.
- **O2 ΓÇö `auto.offset.reset="earliest"`** is appropriate for the local/replay orientation of this milestone (ADR-001); production consumers would often prefer `latest` with explicit reasoning.
- **O3 ΓÇö DLQ routing and metrics are correctly deferred.** SPEC ┬º10 requires invalid events be routed to `products.invalid.v1` and invalid-event metrics exposed; the consumer correctly leaves the DLQ decision to the caller (TASK-010) and metrics to TASK-011.
- **O4 ΓÇö Per-message synchronous commit / single-message-per-poll** trades throughput for a simple, observable boundary, consistent with the TASK-008 producer's posture.
- **O5 ΓÇö Stale review artifacts.** `FOLLOWUPS.md` rows reference commit `463012b` and the committed review doc references `895efc93`; neither is the reviewed HEAD. Both will be superseded by this report and by updated follow-up rows.

## 7. Verdict

**CHANGES REQUIRED**

There are no blocking (Critical/High) defects: the implementation correctly realizes at-least-once semantics ΓÇö `close()` does not commit unprocessed offsets, `poll()` surfaces deserialization failures with full context, and `KafkaConsumerSettings` no longer overrides `APP_ENVIRONMENT`. Six non-blocking findings (M1, M2, Min1ΓÇôMin4) are recorded in `docs/reviews/FOLLOWUPS.md`.

However, one non-blocking finding ΓÇö **Min5** (module-level `os.environ["APP_ENVIRONMENT"] = "development"` mutation in `tests/test_kafka_consumer.py`, inconsistent with the producer test's `monkeypatch` fixture) ΓÇö is neither fixed nor recorded in `FOLLOWUPS.md`. Per the acceptance rule ("APPROVED only when all blocking defects are resolved and nonblocking findings are fixed or documented in FOLLOWUPS.md"), the verdict is CHANGES REQUIRED: either fix Min5 or add it to `FOLLOWUPS.md`.

---

WORKFLOW_REVIEW: {"head": "dc54cc4567750fc35a3eb325d46c4807a5357780", "verdict": "CHANGES REQUIRED", "blocking_findings": 0}
