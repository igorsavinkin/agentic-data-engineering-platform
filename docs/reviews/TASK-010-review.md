I've completed a read-only investigation of TASK-010 against its spec, the reviewer guide, and the full implementation/test surface. I verified the deserialization error taxonomy (`deserialize_event` → Pydantic `model_validate_json`), the DLQ commit-after-acknowledgement ordering, the retry policy, the diagnostic-envelope secret hygiene, and the motivation for the pre-push hook fix (via `tests/test_task_workflow.py`, which runs real `git` subprocesses). Here is the complete report.

---

# TASK-010 Review — Kafka Consumer Error Handling

## 1. Review Header

| Field | Value |
| --- | --- |
| Task ID | TASK-010 |
| Review date | 2026-09-09 |
| Reviewed HEAD | `40fec2a34a6fdc6c152e09b510415cd223c7e8a7` |
| Reviewed Git range | `b3ece11b3651ab0aa06cf03717452e3ca7613c15..40fec2a34a6fdc6c152e09b510415cd223c7e8a7` |
| Scope | Initial failure path for invalid/unprocessable Kafka messages: acknowledged DLQ routing, explicit bounded retry, lossless diagnostic envelope, documented offset/commit semantics, plus a pre-push hook isolation fix |
| Verdict | **APPROVED** |

Sources of authority consulted: `ai/PROJECT.md` (§5 at-least-once + idempotent processing; §9 reliability; §10 observability; §11 security), `ai/SPECIFICATION.md` (§8 Kafka Architecture, §9 Delivery Semantics, §10 Invalid Events and DLQ, §20 Observability), `docs/adr/ADR-001-kafka-topic-configuration.md`, `ai/tasks/TASK-010-kafka-error-handling.md`, `ai/REVIEWER.md`, `ai/AGENTS.md`, `ai/ROADMAP.md` (Milestone 1/2 sequencing), and the TASK-008/TASK-009 artifacts (`libs/common/kafka_producer.py`, `libs/common/config.py`, `libs/event_contracts/`, `scripts/manage_kafka_topics.py`).

This review was performed **read-only**: shell commands (`git status`, `pytest`, `ruff`, `mypy`) were prohibited, so branch cleanliness and test/lint/type execution were not independently verified.

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
| --- | --- | --- |
| Invalid events must not disappear | Met | `poll()` surfaces `DeserializationError` for invalid JSON (Pydantic `model_validate_json` → `ValidationError`), invalid UTF-8 (`UnicodeDecodeError`), null value (`MessageDeserializationError`), and invalid/unsupported schema (`ValidationError`). `process_next()` routes every deserialization failure to an acknowledged DLQ and commits `offset + 1` only after the sink returns. Any unresolved DLQ/commit/handler failure closes the consumer before propagating, so a later commit cannot skip the record. |
| Transient failures have explicit retry behavior | Met | `RetryPolicy` (1–10 attempts, 0–5 s linear backoff, validated in `__post_init__`). `process_next()` retries only `TransientProcessingError` with delays `backoff_seconds * attempts` (default 0.25 s then 0.5 s), then routes to DLQ on exhaustion. `ProcessingError` (permanent) routes to DLQ immediately. |
| Diagnostic context must be preserved | Met | `diagnostic_envelope()` preserves deterministic `event_id` (UUID5 over group/topic/partition/offset), `event_type`, `schema_version`, `source`, `produced_at`, and a payload with topic/partition/offset/consumer_group/attempts/`error_type`/validation `type`+`loc`/exact input bytes as base64. Logs omit payloads and arbitrary exception messages (`test_logs_do_not_expose_input`). |
| Offset behavior must be documented | Met | `docs/kafka-consumer.md` failure/offset policy table and replay guidance; module docstrings; `commit_offsets()` per-partition error check; `enable.auto.commit` typed `Literal[False]`, `enable.auto.offset.store=False`, `allow.auto.create.topics=False`, close-never-commits. |
| Tests: invalid payload; unsupported schema; transient failure; restart after failure | Met | `tests/test_kafka_errors.py` covers all four. Restart-after-failure is exercised non-tautologically by `test_real_dlq_failure_restart_and_offset` (opt-in `-m integration`), which asserts the broker's committed offset and the delivered DLQ envelope bytes. |
| Acceptance: deterministic, documented, observable | Met | Deterministic DLQ `event_id` + documented replay/duplication trade-offs; structured events `kafka_processing_retry`, `kafka_dead_letter_delivered`, `kafka_processing_stopped`, `kafka_deserialization_failed`, `kafka_transport_error`. |

## 3. Git Diff Review

Files in the reviewed range:

- `.githooks/pre-push` — unsets hook-local Git env vars before running tests.
- `docs/kafka-consumer.md` — rewritten from a TASK-009 guide into a TASK-010 failure-policy and DLQ-contract guide.
- `docs/reviews/FOLLOWUPS.md` — updates five TASK-009 rows (M1, M2, Min1, Min4, Min5) to reflect resolution in TASK-010.
- `docs/reviews/TASK-010-review.md` — prior review against non-HEAD `4a611a1`; replaced by this report.
- `libs/common/kafka_consumer.py` — adds `raw_value`, narrows `poll()` exception types, adds `process_next()`, hardens `commit_offsets()`, removes the `__init__` passthrough, disables auto-offset-store/auto-topic-create, types auto-commit as `Literal[False]`.
- `libs/common/kafka_errors.py` — new module: `TransientProcessingError`, `RetryPolicy`, `KafkaDeadLetterProducer`, `DeadLetterSink`, `diagnostic_envelope`.
- `tests/test_kafka_consumer.py` — replaces import-time env mutation with an autouse scoped fixture; fixes a stale comment.
- `tests/test_kafka_errors.py` — new failure-path test module (unit + one real-broker integration test).

Assessment:

- **Scope correctness:** All product changes belong to TASK-010. The pre-push hook change is a one-line workflow fix directly necessitated by the repo's own test suite running under the hook (see O6).
- **Unrelated changes:** None. `FOLLOWUPS.md` updates and the review-artifact replacement are legitimate review-cycle bookkeeping.
- **Architectural changes:** None. No service boundary, event-contract, ADR-001 partitioning, or consumer-group change. The DLQ producer reuses `KafkaProducerSettings`/`PublishError` from TASK-008 rather than introducing a parallel pattern.
- **Accidental changes:** None. No debug code, temporary files, generated artifacts, or secrets.
- **Dependency/configuration change:** No new dependency. Consumer config gains `enable.auto.offset.store=False` and `allow.auto.create.topics=False` (defense-in-depth consistent with ADR-001).
- **Backward compatibility:** `ConsumerMessage.raw_value` and `DeserializationError.raw_value` are defaulted fields, so existing TASK-009 constructors remain valid.

## 4. Test and Verification Review

### Tests examined

`tests/test_kafka_errors.py`: invalid payload (broken JSON / invalid UTF-8 / null / unsupported `schema_version`) ack-before-commit; retry success; transient-exhaustion and permanent-failure → DLQ; unresolved failure (handler/DLQ/commit/per-partition commit) closes consumer without later poll; log hygiene; auto-commit rejection; DLQ callback-ack requirements (success/failed/missing/pending/queue-full); real-broker DLQ-outage → same-group restart → committed offset → exact raw-payload preservation; unsupported-version validation locations; shutdown-during-retry leaves uncommitted; `RetryPolicy` bounds.

`tests/test_kafka_consumer.py` (delta): scoped `APP_`-clearing fixture replacing import-time mutation; stale comment fixed.

### Test adequacy

The four required categories are present. The unit tests are concrete (not tautologies): they assert commit ordering relative to DLQ acknowledgement, retry/attempt counts, consumer closure on unresolved failure, and absence of payload leakage. The restart-after-failure requirement is met non-tautologically by the integration test, which asserts the broker's committed offset and delivered DLQ envelope bytes. This is the strongest evidence in the review.

### Independently verified (executed by reviewer)

None. `pytest`, `ruff`, and `mypy` were **not** run (shell execution prohibited by the review workflow).

### Implementation evidence reviewed (not rerun)

`libs/common/kafka_consumer.py`, `libs/common/kafka_errors.py`, `libs/common/kafka_producer.py`, `libs/common/config.py`, `libs/event_contracts/product_observation.py`, `tests/test_kafka_errors.py`, `tests/test_kafka_consumer.py`, `tests/test_kafka_producer.py`, `tests/test_task_workflow.py`, `scripts/manage_kafka_topics.py`, `docs/kafka-consumer.md`, `docs/reviews/FOLLOWUPS.md`, `docs/adr/ADR-001-kafka-topic-configuration.md`, `pyproject.toml`, `.env.example`, `.githooks/pre-push`.

### Unverified

- Unit/integration test execution (`pytest`), including the opt-in `-m integration` real-broker test.
- `ruff check` / format (pyproject selects `E4,E7,E9,F,I`).
- `mypy` (pyproject sets `warn_unused_ignores = true`; the removed `__init__` passthrough also removed the prior `# type: ignore`, and no new ignores were introduced).
- Branch name and working-tree cleanliness (the frozen snapshot reports `feature/TASK-010`, clean; not independently re-verified).

## 5. Findings

### Critical / High (blocking)

None.

### Moderate

None. Prior Moderate findings are resolved in this range: `poll()` no longer uses a broad `except Exception`; `close()` does not commit; the `KafkaConsumerSettings.__init__` passthrough is removed; offset-commit ordering relative to DLQ acknowledgement is enforced by `process_next`; `commit_offsets` now surfaces per-partition errors.

### Minor (non-blocking)

**Min1 — `.env.example` still omits consumer settings.**
File: `.env.example`.
It documents `APP_KAFKA_*` producer variables only; the consumer's `APP_KAFKA_GROUP_ID`, `APP_KAFKA_AUTO_OFFSET_RESET`, and timeout variables appear only in `docs/kafka-consumer.md` prose. This is the continuation of TASK-009 `Min3`, which is already tracked as Open in `docs/reviews/FOLLOWUPS.md`. Cosmetic; no runtime impact.

## 6. Non-Defect Observations

- **O1 — Cross-test-module imports couple `test_kafka_errors.py` to other test modules.** It does `from test_kafka_consumer import _make_valid_event` and `from test_kafka_producer import real_broker`, relying on `pythonpath = ["."]` and importing a fixture that owns Compose-lifecycle side effects. It works, but it is a test-isolation smell. `test_kafka_errors.py` constructs settings with explicit `environment=` kwargs, so it is robust to ambient `APP_` variables.
- **O2 — `process_next()` return value conflates "no record available" and "shutdown requested".** Both return `False`; the docstring does not state the return contract. The documented loop handles both identically, so there is no functional defect — only under-documented API semantics.
- **O3 — `poll()` calls `msg.value()` a second time for `raw_value`.** In the `except` block, `raw_value=msg.value()` re-fetches the payload instead of reusing the already-bound `value`. Harmless with confluent-kafka, but slightly redundant.
- **O4 — `KafkaDeadLetterProducer.close()` does not wrap a `flush()` `KafkaException`.** `publish()` wraps `(KafkaException, BufferError)` into `PublishError`, and `KafkaEventProducer.close()` wraps flush failures, but `KafkaDeadLetterProducer.close()` lets a raw `KafkaException` propagate. Still fail-closed; only an error-typing inconsistency.
- **O5 — The DLQ producer does not forward librdkafka diagnostics to the app logger.** `KafkaEventProducer` sets `"logger": logger`; the DLQ producer omits it. Minor observability inconsistency.
- **O6 — The pre-push hook fix is correct and correctly motivated.** `tests/test_task_workflow.py` invokes `git init` / `git worktree add` / `git commit` in subprocesses over `tmp_path` repos. When the pre-push hook runs `python -m pytest`, Git sets `GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE`/etc.; `unset $(git rev-parse --local-env-vars)` strips those before tests run, so the test subprocesses no longer get redirected into the pushed repository. This is a standard, minimal, safe fix (the `cd "$(git rev-parse --show-toplevel)"` line runs before the unset, so the hook itself still resolves the repo correctly).
- **O7 — The `real_broker` fixture is still named `task008-test-*`.** Its `COMPOSE_PROJECT_NAME` prefix predates TASK-010; purely cosmetic.
- **O8 — `RetryPolicy` validates ranges but not integrality.** A pathological `max_attempts=3.5` would pass `1 <= 3.5 <= 10` and later fail in `range(1, ...)`. Unreachable through documented usage; not a practical defect.
- **O9 — Worst-case retry backoff vs `max.poll.interval.ms` is a documented constraint, not a defect.** With `max_attempts=10`/`backoff=5`, sleep alone is ~225 s; the docs explicitly warn to keep total processing+backoff+DLQ time below `APP_KAFKA_MAX_POLL_INTERVAL_MS` (default 300 s). Defaults (3 × 0.25 s) are negligible.
- **O10 — Metrics and processor-specific validation are correctly deferred.** Invalid-event metrics remain TASK-011; processor-specific validation/DLQ remains TASK-017, matching the roadmap. TASK-010's required observability is delivered via structured log events.
- **O11 — Security posture is sound.** Logs omit payloads and arbitrary exception messages; `diagnostic_envelope` strips Pydantic `msg`/`input` (keeping only `type`/`loc`), so a `json_invalid` error's raw input cannot leak into the DLQ's `validation_errors`; `ConfigurationError` never echoes values; the DLQ producer sets `enable.idempotence=True`/`acks=all`/`allow.auto.create.topics=False`.

## 7. Verdict

**APPROVED**

No blocking (Critical/High) defects exist, and no Moderate findings remain. The implementation realizes every TASK-010 requirement — acknowledged DLQ routing with commit-after-acknowledgement, explicit bounded retry for classified transient failures, lossless diagnostic envelopes that omit secrets from logs, and a deterministic, documented failure policy — while preserving at-least-once semantics and ADR-001 topic ownership.

The single Minor finding (`.env.example` consumer settings) is already documented in `docs/reviews/FOLLOWUPS.md` as TASK-009 `Min3` (Open). The remaining items are non-defect observations, documented in this report and requiring no follow-up entry. The one-line pre-push hook change is a correct, minimal workflow fix for a real interaction between the hook environment and `tests/test_task_workflow.py`.

This report replaces the stale `docs/reviews/TASK-010-review.md` that was recorded against non-HEAD `4a611a1`.

---

WORKFLOW_REVIEW: {"head": "40fec2a34a6fdc6c152e09b510415cd223c7e8a7", "verdict": "APPROVED", "blocking_findings": 0}
