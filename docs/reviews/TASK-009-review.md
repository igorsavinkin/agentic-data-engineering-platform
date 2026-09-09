I have completed the read-only investigation. I read `ai/REVIEWER.md`, `ai/tasks/TASK-009-kafka-consumer.md`, `ai/AGENTS.md`, `ai/PROJECT.md`, `ai/SPECIFICATION.md` (event contract ┬º7, Kafka ┬º8, delivery semantics ┬º9, invalid events ┬º10, testing ┬º22), `ai/ROADMAP.md` (Milestone 1 sequencing), `docs/adr/ADR-001-kafka-topic-configuration.md`, the implementation (`libs/common/kafka_consumer.py`), the event contract (`libs/event_contracts/`), the config base (`libs/common/config.py`), the TASK-008 producer for convention comparison (`libs/common/kafka_producer.py`), the tests, the consumer doc, `.env.example`, `pyproject.toml`, `libs/common/README.md`, `docs/kafka-producer.md`, and the current `docs/reviews/FOLLOWUPS.md`.

No files were modified and no shell commands were executed (prohibited by both the task instructions and plan mode), so `pytest`, `ruff`, and `mypy` were not independently run.

Here is the review report.

---

# TASK-009 Review ΓÇö Reusable Kafka Consumer

## 1. Review Header

| Field | Value |
| --- | --- |
| Task ID | TASK-009 |
| Review date | 2026-09-09 |
| Reviewed HEAD | `d35c04cab5309f514323d9e481ade22bbc60e9a6` |
| Reviewed Git range | `1d6bce1320f76d8ec028a1a20f40e1429cc88c44..d35c04cab5309f514323d9e481ade22bbc60e9a6` |
| Scope | Reusable Kafka consumer for canonical product-observation events |
| Verdict | **CHANGES REQUIRED** |

Sources of authority consulted: `ai/PROJECT.md` (┬º5 Event Semantics, ┬º9 Reliability, ┬º11 Security, ┬º12 Testing), `ai/SPECIFICATION.md` (┬º7 Event Contract, ┬º8 Kafka Architecture, ┬º9 Delivery Semantics, ┬º10 Invalid Events and DLQ, ┬º22 Testing), `docs/adr/ADR-001-kafka-topic-configuration.md`, `ai/tasks/TASK-009-kafka-consumer.md`, `ai/ROADMAP.md` (Milestone 1 sequencing TASK-009 ΓåÆ TASK-010 ΓåÆ TASK-011 ΓåÆ TASK-012), and the referenced TASK-006/TASK-008 artifacts (`libs/event_contracts`, `libs/common/kafka_producer.py`, `libs/common/config.py`).

**Reconciliation note:** the supplied diff includes a committed `docs/reviews/TASK-009-review.md` that is a prior review against intermediate commits (`895efcΓÇª`, `463012bΓÇª`, `b3a28c4ΓÇª`). The on-disk files at the reviewed HEAD were inspected directly and treated as authoritative. The current on-disk `docs/kafka-consumer.md` is corrected to match the implementation (the earlier documentation/contradiction is resolved). The committed review file is a stale artifact and is superseded by this report (see finding Min5).

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
| --- | --- | --- |
| Consumer group configuration | Met | `KafkaConsumerSettings(AppSettings)` exposes `kafka_group_id`, `kafka_auto_offset_reset`, session/heartbeat/max-poll timeouts, `kafka_enable_auto_commit=False`; `consumer_config` builds the librdkafka dict; `KafkaConsumer.__init__` rejects an empty group id. |
| Deserialization and validation | Met | `poll()` deserializes via `deserialize_event(value.decode("utf-8"))`; valid events returned as `ConsumerMessage`; failures surfaced to the caller as `DeserializationError` with topic/partition/offset/`raw_value`. |
| Explicit offset handling | Met | `commit_message` commits `offset + 1` (next offset to read); `commit_offsets` for advanced/explicit use; `close()` does not commit, preserving at-least-once. |
| Graceful shutdown | Met | SIGINT/SIGTERM handler sets `_shutdown_requested`; `poll()` returns `([], [])` when shutdown requested; context manager calls `close()`; `close()` is idempotent and does not commit. |
| Document when offsets are committed and what happens on processing failure | Met | `docs/kafka-consumer.md` documents commit timing, the failure-behavior matrix, crash-after-write-before-commit, and `event_id` deduplication; module docstring and `close()` docstring agree. |
| Tests: valid event / malformed event / restart / duplicate delivery | Present (see M3) | All four categories exist in `tests/test_kafka_consumer.py`; malformed events asserted to surface as `DeserializationError`. Restart/duplicate tests remain mock tautologies. |
| Acceptance: reliably consumes canonical events without claiming exactly-once | **Met** | At-least-once honesty is correct in code, docstrings, and docs; no exactly-once claim; downstream dedup by `event_id` documented. |

## 3. Git Diff Review

Files changed (all in `docs/`, `libs/common/`, `tests/`):

- `docs/kafka-consumer.md` ΓÇö consumer guide (new).
- `docs/reviews/FOLLOWUPS.md` ΓÇö six deferred-finding entries added.
- `docs/reviews/TASK-009-review.md` ΓÇö prior review artifact (new; stale ΓÇö references `895efcΓÇª`/`463012bΓÇª`/`b3a28c4ΓÇª`, not the reviewed HEAD).
- `libs/common/kafka_consumer.py` ΓÇö new consumer module.
- `tests/test_kafka_consumer.py` ΓÇö new unit tests.

Assessment:

- **Scope correctness:** All code/test/doc files belong to TASK-009. No out-of-scope service changes.
- **Unrelated changes:** None observed.
- **Architectural changes:** None. Adds a reusable library module; does not alter service boundaries, event semantics, or ADR-001 partitioning/consumer-group policy.
- **Accidental changes:** The committed `docs/reviews/TASK-009-review.md` is a stale prior review against a non-HEAD commit (see Min5). No debug code, temporary files, generated artifacts, or secrets otherwise found.
- **Dependency change:** None. `confluent-kafka` was already introduced in TASK-008; no `requirements*.txt`/`pyproject.toml` change.
- **Documentation/config gaps (see Min3):** `.env.example` still omits the consumer's `APP_KAFKA_GROUP_ID` / `APP_KAFKA_AUTO_OFFSET_RESET` / timeout variables, and `libs/common/README.md` documents the producer but not the consumer.

## 4. Test and Verification Review

### Tests examined

`tests/test_kafka_consumer.py` covers: settings defaults/config dict/missing group id; valid consumption; poll timeout; malformed JSON surfaced as `DeserializationError`; invalid schema surfaced; None value surfaced; offset commit after success; no-commit-on-failure; restart with committed offsets; redelivery of uncommitted messages; duplicate delivery; downstream dedup; no-commit-on-close; shutdown flag; double-close; operations-after-close; partition EOF; transport error; unknown-topic error; subscription; assignment.

### Test adequacy

The malformed-message surfacing (`DeserializationError`) and no-commit-on-close behavior are now directly pinned by tests. The `offset + 1` commit logic is verified by `test_commit_after_successful_processing` (asserts next offset 43). Remaining weakness (M3): the restart/redelivery/duplicate tests still assert mock `poll()`/`commit_offsets()` results rather than real Kafka offset resume semantics, and no test verifies the documented skip path for a surfaced `DeserializationError` (advancing its offset via `commit_offsets`) across `close()`/restart. Real-broker integration coverage is deferred to TASK-012 per the roadmap, so this is non-blocking ΓÇö but it is not recorded in FOLLOWUPS.

### Independently verified (executed by reviewer)

None. Shell execution was prohibited, so `pytest`, `ruff`, and `mypy` were **not** run.

### Implementation evidence reviewed (not rerun)

`libs/common/kafka_consumer.py`, `tests/test_kafka_consumer.py`, `docs/kafka-consumer.md`, `libs/common/config.py`, `libs/common/kafka_producer.py`, `libs/event_contracts/`, `.env.example`, `libs/common/README.md`, `pyproject.toml`, and `docs/reviews/FOLLOWUPS.md` were inspected directly. No test-run report was supplied for this HEAD.

### Unverified

- Test execution (unit tests).
- `ruff check` / `ruff format --check`.
- `mypy` ΓÇö notably `KafkaConsumerSettings.__init__(**kwargs: str | int | bool)` with `# type: ignore[arg-type]` under `warn_unused_ignores = true` (see M1).
- Branch name and working-tree state (no `git status`/`git log` permitted).

## 5. Findings

### High (blocking)

None.

### Moderate (non-blocking)

**M1 ΓÇö `KafkaConsumerSettings.__init__` is a redundant, type-unsound passthrough with `# type: ignore[arg-type]`.**
File: `libs/common/kafka_consumer.py`, `KafkaConsumerSettings.__init__`.
Problem: the override reduces to `super().__init__(**kwargs)` but keeps the narrowed `**kwargs: str | int | bool` signature and `# type: ignore[arg-type]`. It diverges from `KafkaProducerSettings`, which omits `__init__` entirely. The narrowed signature hides the inherited `Environment`/`LogLevel` literal types; the `arg-type` ignore suppresses genuine errors from the pydantic plugin's typed `super().__init__` (so it is likely *used*, not "unused" ΓÇö but this is unverified without running mypy).
Impact: type-unsound settings construction; unnecessary divergence from the producer convention; drops `BaseSettings` special kwargs (`_env_file`, `_secrets_dir`).
Recommendation: delete the override and rely on the inherited `BaseSettings.__init__`.
Status: documented in FOLLOWUPS (M1). Γ£ô

**M2 ΓÇö Consumer settings lack the producer's validators and omit `allow.auto.create.topics=false`.**
File: `libs/common/kafka_consumer.py`, `KafkaConsumerSettings` / `consumer_config`.
Problem: `kafka_group_id` accepts arbitrary/empty strings (only runtime-checked in `KafkaConsumer.__init__`), and `kafka_bootstrap_servers` is not shape-validated ΓÇö unlike `KafkaProducerSettings` (`valid_name`/`valid_brokers`). `consumer_config` also omits `allow.auto.create.topics: false`, which ADR-001 states is disabled and the producer sets explicitly.
Impact: invalid configuration surfaces later than the producer's; defensively inconsistent with ADR-001 (librdkafka's consumer default is already `false`, but producer parity and ADR-001 intent are worth mirroring).
Recommendation: add `valid_name`/`valid_brokers` validators and include `"allow.auto.create.topics": False`.
Status: documented in FOLLOWUPS (M2). Γ£ô

**M3 ΓÇö Required "restart"/"duplicate delivery" tests remain mock tautologies; the malformed-offset skip path is untested.**
File: `tests/test_kafka_consumer.py`.
Problem: `test_restart_uses_committed_offsets` only asserts `close.called` after `reset_mock()`; `test_uncommitted_messages_redelivered_on_restart` re-asserts the same mocked message at offset 42 on a second mock consumer; `TestDuplicateDelivery` feeds the same JSON at two offsets. None exercises real offset resume/commit semantics, and no test verifies that a surfaced `DeserializationError`'s offset can be advanced via `commit_offsets` (the documented skip path) across `close()`/restart.
Impact: the required restart/duplicate coverage is largely illusory, so an offset-handling regression would not be caught by the unit suite (the `offset+1` arithmetic itself is covered by `test_commit_after_successful_processing`).
Recommendation: strengthen the restart test to assert actual commit/resume behavior where unit-testable, add a skip-path test, and/or record the real-broker remainder as deferred to TASK-012 in FOLLOWUPS.
Status: **not fixed and not documented in FOLLOWUPS.md.** Γ£ù

### Minor (non-blocking)

**Min1 ΓÇö Broad `except Exception` in `poll()`; two exception classes are vestigial.**
File: `libs/common/kafka_consumer.py`, `poll()`.
The broad `except Exception` catches programming errors alongside the intended `pydantic.ValidationError`/`UnicodeDecodeError`. `MessageDeserializationError` is raised for a None value but immediately swallowed by the same `try` (effectively dead), and `ProcessingError` is defined but only referenced in docstrings.
Status: documented in FOLLOWUPS (Min1). Γ£ô

**Min2 ΓÇö Signal handler registration is a surprising library side effect.**
File: `libs/common/kafka_consumer.py`, `_register_signal_handlers()`.
`__init__` unconditionally registers SIGINT/SIGTERM handlers, overriding host handlers and only working on the main thread.
Status: documented in FOLLOWUPS (Min2). Γ£ô

**Min3 ΓÇö Documentation/config gaps.**
`.env.example` omits the consumer's `APP_KAFKA_GROUP_ID`/`APP_KAFKA_AUTO_OFFSET_RESET`/timeout variables; `libs/common/README.md` lists the producer but not the consumer; `docs/kafka-consumer.md` examples use `kafka:9092` where `docs/kafka-producer.md` states containers on the Compose network use `kafka:29092`; `test_commit_after_successful_processing` carries a stale comment ("second from close()") though `close()` no longer commits.
Status: documented in FOLLOWUPS (Min3, Min4). Γ£ô

**Min5 ΓÇö Stale review artifact committed.**
File: `docs/reviews/TASK-009-review.md`.
The TASK-009 diff commits a prior review whose header/verdict reference commits (`895efcΓÇª`, `463012bΓÇª`, `b3a28c4ΓÇª`) that are not the reviewed HEAD. It will be replaced by this report, but committing a review artifact against a non-HEAD commit is a process/hygiene issue.
Status: not documented in FOLLOWUPS.md. Γ£ù (self-resolving via this report)

**Min6 ΓÇö "How replay is performed" is not explicitly documented.**
File: `docs/kafka-consumer.md`.
SPEC ┬º9 lists "how replay is performed" among the delivery-semantics items to document. The consumer exposes the mechanism (`commit_offsets` + `auto.offset.reset="earliest"`) but the guide does not contain a replay procedure. Replay demonstration is sequenced to TASK-039 and integration to TASK-012, so this is a low-severity gap rather than a TASK-009 defect.
Status: not documented in FOLLOWUPS.md. Γ£ù

## 6. Non-Defect Observations

- **Per-message synchronous commit and single-message-per-poll** trade throughput for a simple, observable boundary ΓÇö consistent with the producer's design and acceptable for TASK-009.
- **Metrics are deferred to TASK-011** and real-Kafka integration tests to TASK-012 (consistent with the producer's documented posture). The consumer emits structured logs only.
- **`auto.offset.reset="earliest"`** is appropriate for the local/replay orientation of this milestone (ADR-001); production consumers would typically prefer `latest` ΓÇö worth a later note, not a defect here.
- **At-least-once honesty** is correctly expressed in the module docstring, `close()`'s docstring, and `docs/kafka-consumer.md`, matching PROJECT ┬º5 and SPEC ┬º9.
- **Surfacing `DeserializationError` in `poll()`** correctly leaves the DLQ-routing decision to the caller and overlaps cleanly with TASK-010 (invalid-topic/DLQ path). `except Exception` currently includes `UnicodeDecodeError`/`pydantic.ValidationError` (intended) plus the effectively-dead `MessageDeserializationError`.

## 7. Verdict

**CHANGES REQUIRED**

All blocking defects are resolved at the reviewed HEAD: the documentation matches the implementation on shutdown/commit behavior and the tuple-returning `poll()` API, and the at-least-once acceptance criterion is correctly met. The previously blocking issues (silent malformed-message discard; environment override; docs/code contradiction) are gone.

However, the task cannot be `APPROVED` under the acceptance rule because at least one valid non-blocking finding ΓÇö **M3 (mock-tautology restart/duplicate tests and untested skip path)** ΓÇö is neither fixed nor recorded in `docs/reviews/FOLLOWUPS.md`. The current FOLLOWUPS.md documents six findings (M1, M2, Min1ΓÇôMin4) but omits M3, and also omits the committed stale-review artifact (Min5). The highest-value close is to either strengthen the restart/duplicate tests or explicitly defer the real-broker remainder to TASK-012 in FOLLOWUPS.md.

Verification status: `pytest`, `ruff`, and `mypy` were not independently run (shell execution prohibited); their status is **Unverified**.

---

WORKFLOW_REVIEW: {"head": "d35c04cab5309f514323d9e481ade22bbc60e9a6", "verdict": "CHANGES REQUIRED", "blocking_findings": 0}
