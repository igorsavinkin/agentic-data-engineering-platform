I have completed a thorough read-only investigation. Here is the complete review report.

---

# TASK-010 Review — Kafka Consumer Error Handling

## 1. Review Header

| Field | Value |
| --- | --- |
| Task ID | TASK-010 |
| Review date | 2026-09-09 |
| Reviewed HEAD | `4a611a1680a41366fa594defcd4c2a7d84b4da5f` |
| Reviewed Git range | `b3ece11b3651ab0aa06cf03717452e3ca7613c15..4a611a1680a41366fa594defcd4c2a7d84b4da5f` |
| Scope | Initial failure path for invalid/unprocessable Kafka messages: acknowledged DLQ routing, explicit bounded retry, diagnostic envelope, documented offset/commit semantics |
| Verdict | **APPROVED** |

Sources of authority consulted: `ai/PROJECT.md` (§5 at-least-once + idempotent processing; §9 reliability), `ai/SPECIFICATION.md` (§8 Kafka Architecture, §9 Delivery Semantics, §10 Invalid Events and DLQ), `docs/adr/ADR-001-kafka-topic-configuration.md`, `ai/tasks/TASK-010-kafka-error-handling.md`, `ai/tasks/TASK-009-kafka-consumer.md`, `ai/REVIEWER.md`, `ai/AGENTS.md`, `ai/ROADMAP.md` (Milestone 1 sequencing), and the TASK-008/TASK-009 artifacts (`libs/common/kafka_producer.py`, `libs/common/config.py`, `libs/event_contracts/`, `scripts/manage_kafka_topics.py`).

This review was performed **read-only**: shell commands (`git status`, `pytest`, `ruff`, `mypy`) were prohibited by plan mode, so branch cleanliness and test/lint/type execution were not independently verified.

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
| --- | --- | --- |
| Invalid events must not disappear | Met | `poll()` surfaces `DeserializationError` (invalid JSON, UTF-8, null value, unsupported/invalid schema); `process_next()` routes every deserialization failure to an acknowledged DLQ and only then commits `offset + 1`. Unresolved DLQ/commit/handler failures close the consumer so a later commit cannot skip the record. |
| Transient failures have explicit retry behavior | Met | `RetryPolicy` (1–10 attempts, 0–5 s linear backoff, validated in `__post_init__`); `process_next()` retries only `TransientProcessingError`, with delays `backoff * attempt` (default 0.25 s then 0.5 s), then routes to DLQ on exhaustion. |
| Diagnostic context must be preserved | Met | `diagnostic_envelope()` preserves `event_id` (deterministic UUID5 over group/topic/partition/offset), `event_type`, `schema_version`, `source`, `produced_at`, and a payload with topic/partition/offset/group/attempts/`error_type`/validation locations/exact input bytes as base64. Logs omit payloads and arbitrary exception messages (`test_logs_do_not_expose_input`). |
| Offset behavior must be documented | Met | `docs/kafka-consumer.md` failure/offset policy table; module docstrings; `commit_offsets` per-partition error check; `enable.auto.commit` typed `Literal[False]`, `enable.auto.offset.store=False`, `allow.auto.create.topics=False`, close-never-commits. |
| Tests: invalid payload; unsupported schema; transient failure; restart after failure | Met | `tests/test_kafka_errors.py` covers all four; restart is exercised by the real-broker `test_real_dlq_failure_restart_and_offset` (opt-in `-m integration`). |
| Acceptance: deterministic, documented, observable | Met | Deterministic DLQ `event_id` + documented replay/duplication trade-offs; structured events `kafka_processing_retry`, `kafka_dead_letter_delivered`, `kafka_processing_stopped`, `kafka_deserialization_failed`. |

## 3. Git Diff Review

Files in the reviewed range:

- `docs/kafka-consumer.md` — rewritten from a TASK-009 guide into a TASK-010 failure-policy and DLQ-contract guide.
- `docs/reviews/FOLLOWUPS.md` — updates five TASK-009 follow-up rows (M1, M2, Min1, Min4, Min5) to reflect resolution/partial-resolution in TASK-010.
- `libs/common/kafka_consumer.py` — adds `raw_value`, narrows `poll()` exception types, adds `process_next()`, hardens `commit_offsets()` with per-partition error checks, removes the `__init__` passthrough, adds `enable.auto.offset.store=False`/`allow.auto.create.topics=False`, types auto-commit as `Literal[False]`.
- `libs/common/kafka_errors.py` — new module: `TransientProcessingError`, `RetryPolicy`, `KafkaDeadLetterProducer`, `DeadLetterSink`, `diagnostic_envelope`.
- `tests/test_kafka_consumer.py` — replaces module-level env mutation with an autouse scoped fixture; fixes a stale comment.
- `tests/test_kafka_errors.py` — new failure-path test module (unit + one real-broker integration test).

Assessment:

- **Scope correctness:** All changes belong to TASK-010. No unrelated product behavior changed.
- **Unrelated changes:** None observed. The `FOLLOWUPS.md` updates are legitimate review-cycle bookkeeping.
- **Architectural changes:** None. No service boundary, event-contract, ADR-001 partitioning, or consumer-group change. The DLQ producer reuses `KafkaProducerSettings`/`PublishError` from TASK-008 rather than introducing a parallel pattern.
- **Accidental changes:** None. No debug code, temporary files, generated artifacts, or secrets.
- **Dependency/configuration change:** None new. `confluent-kafka`, `pydantic` already present. Consumer config now disables auto-offset-store and auto-topic-create (defense-in-depth consistent with ADR-001).
- **Backward compatibility:** `ConsumerMessage.raw_value` and `DeserializationError.raw_value` are defaulted fields, so existing constructors (and TASK-009 tests) still work.

## 4. Test and Verification Review

### Tests examined

`tests/test_kafka_errors.py`: invalid payload (broken JSON / invalid UTF-8 / null / unsupported `schema_version`) ack-before-commit; retry success; transient-exhaustion and permanent failure → DLQ; unresolved failure (handler/DLQ/commit/per-partition commit) closes consumer without later poll; log hygiene; auto-commit rejection; DLQ callback-ack requirements (success/failed/missing/pending/queue-full); real-broker DLQ-outage → same-group restart → committed offset → exact raw-payload preservation; unsupported-version validation locations; shutdown-during-retry leaves uncommitted; `RetryPolicy` bounds.

`tests/test_kafka_consumer.py` (delta): scoped `APP_` environment fixture replacing import-time mutation; stale comment fixed.

### Test adequacy

The four required categories are present, and the failure-path unit tests are concrete (not tautologies): they assert commit ordering relative to DLQ acknowledgement, retry/attempt counts, consumer closure on unresolved failure, and absence of payload leakage in logs. The restart-after-failure requirement is met non-tautologically by the real-broker integration test, which asserts the broker's committed offset and the delivered DLQ envelope bytes.

### Independently verified (executed by reviewer)

None. `pytest`, `ruff`, and `mypy` were **not** run (shell execution prohibited).

### Implementation evidence reviewed (not rerun)

`libs/common/kafka_consumer.py`, `libs/common/kafka_errors.py`, `libs/common/kafka_producer.py`, `libs/common/config.py`, `libs/event_contracts/`, `tests/test_kafka_errors.py`, `tests/test_kafka_consumer.py`, `tests/test_kafka_producer.py`, `scripts/manage_kafka_topics.py`, `docs/kafka-consumer.md`, `docs/reviews/FOLLOWUPS.md`, `docs/adr/ADR-001-kafka-topic-configuration.md`, `pyproject.toml`, `.env.example`. No test-run report was supplied for this HEAD.

### Unverified

- Unit/integration test execution.
- `ruff check` / `ruff format --check` (pyproject selects `E4,E7,E9,F,I`).
- `mypy` (pyproject has `warn_unused_ignores = true`; the removed `__init__` passthrough also removed the prior `# type: ignore`, and no new ignores were introduced).
- Branch name and working-tree cleanliness.

## 5. Findings

### High (blocking)

None.

### Moderate (non-blocking)

None. Prior Moderate/blocking findings are resolved: `poll()` no longer uses a broad `except Exception`; `close()` does not commit; `KafkaConsumerSettings.__init__` passthrough removed; offset-commit ordering relative to DLQ acknowledgement is enforced by `process_next`; `commit_offsets` now surfaces per-partition errors.

### Minor (non-blocking)

**Min1 — `.env.example` still omits consumer settings.**
File: `.env.example`.
It documents `APP_KAFKA_*` producer variables only; the consumer's `APP_KAFKA_GROUP_ID`, `APP_KAFKA_AUTO_OFFSET_RESET`, and timeouts are documented in `docs/kafka-consumer.md` prose but not in `.env.example`. Carried forward from TASK-009 `Min3`, already tracked in `docs/reviews/FOLLOWUPS.md` as Open. Cosmetic; no runtime impact.

**Min2 — Cross-test-module imports couple `test_kafka_errors.py` to `test_kafka_producer.py`/`test_kafka_consumer.py`.**
File: `tests/test_kafka_errors.py` (top-level `from test_kafka_producer import real_broker` and `from test_kafka_consumer import _make_valid_event`).
This relies on pytest's rootdir `sys.path` insertion (no `tests/__init__.py`) and imports a fixture that owns Compose-lifecycle side effects. It works with `pythonpath = ["."]`, but it is a test-isolation smell. `test_kafka_errors.py` also lacks the autouse `APP_`-clearing fixture the other two test modules use (its settings are constructed with explicit `environment=` kwargs, so it is robust, but the inconsistency is worth noting).

**Min3 — `process_next()` return value conflates "no record available" and "shutdown requested".**
File: `libs/common/kafka_consumer.py`, `process_next()`.
Both conditions return `False`; the method docstring does not state the return contract. The documented loop (`while not consumer.is_shutdown_requested(): consumer.process_next(...)`) handles this correctly, so there is no functional defect — only under-documented API semantics.

## 6. Non-Defect Observations

- **O1 — Real-broker integration test partially pre-empts TASK-012.** `test_real_dlq_failure_restart_and_offset` covers TASK-012's "consumer restart" and "failure/retry" scenarios. This is justified: TASK-010's required test is "consumer restart after failure", which is only non-tautological against a real broker. TASK-012 should extend rather than duplicate.
- **O2 — DLQ `event_id` includes `group_id`, so cross-group deduplication is not provided.** The deterministic ID deduplicates replays *within* a group; if `processor` and `raw-writer` both route the same invalid raw record, `products.invalid.v1` receives two envelopes with different `event_id`s. This is consistent with the documented identity (`group/topic/partition/offset`) and the DLQ topic's round-robin/no-key design, but worth stating explicitly.
- **O3 — `except BaseException` in `process_next`.** Intentional and documented ("Any unresolved failure closes this consumer before propagating"); it guarantees close-and-propagate on any failure, including handler programming errors. Slightly broader than `Exception`, but consistent with the fail-closed design.
- **O4 — DLQ `source` is the consumer group, not the original source adapter.** Documented ("source (consumer group)") and lossless — the original source is recoverable from the base64 raw payload.
- **O5 — Worst-case retry backoff vs `max.poll.interval.ms`.** With `max_attempts=10`/`backoff=5`, sleep alone is ~225 s; the docs explicitly warn to keep total processing+backoff+DLQ time below `APP_KAFKA_MAX_POLL_INTERVAL_MS` (default 300 s). Defaults (3 × 0.25 s) are negligible. A documented constraint, not a hidden defect.
- **O6 — Metrics and processor validation correctly deferred.** Invalid-event metrics remain TASK-011; processor-specific validation remains TASK-017, matching the roadmap. Structured log events provide the required TASK-010 observability.
- **O7 — Security posture is sound.** Logs omit payloads and arbitrary exception messages; `diagnostic_envelope` strips Pydantic `msg`/`input` (keeping only `type`/`loc`); `ConfigurationError` messages never echo values; the DLQ producer sets `enable.idempotence=True`/`acks=all`/`allow.auto.create.topics=False`.

## 7. Verdict

**APPROVED**

No blocking (Critical/High) defects exist. The implementation realizes the TASK-010 requirements — acknowledged DLQ routing with commit-after-acknowledgement, explicit bounded retry for classified transient failures, lossless diagnostic envelopes that omit secrets from logs, and a deterministic, documented failure policy — while preserving at-least-once semantics and ADR-001 topic ownership.

All prior non-blocking findings are fixed or documented in `docs/reviews/FOLLOWUPS.md` (the diff resolves M1, Min1, Min4, Min5 and partially resolves M2; Min2/Min3 remain Open). The new observations above are Minor and are documented in this report; none require follow-up entries.

---

WORKFLOW_REVIEW: {"head": "4a611a1680a41366fa594defcd4c2a7d84b4da5f", "verdict": "APPROVED", "blocking_findings": 0}
