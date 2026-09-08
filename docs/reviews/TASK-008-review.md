# TASK-008 Review — Kafka Producer

## 1. Review Header

| Field | Value |
| --- | --- |
| Task ID | TASK-008 |
| Review date | 2026-09-08 |
| Reviewed commit | `3e496bc7688aad1921a044e9a59c65f49d40dda2` (`Implement TASK-008 canonical Kafka producer`) |
| Branch | `feature/TASK-008` |
| Reviewed Git range | `492b18119879d830dfb63b21268dd773de036b79..3e496bc7688aad1921a044e9a59c65f49d40dda2` |
| Scope | Reusable producer for canonical product observation events |
| Verdict | **APPROVED** |

Sources of authority consulted: `ai/PROJECT.md`, `ai/SPECIFICATION.md` (§7 Event Contract, §8 Kafka Architecture, §9 Delivery Semantics), `docs/adr/ADR-001-kafka-topic-configuration.md`, `ai/tasks/TASK-008-kafka-producer.md`, and the referenced `TASK-006`/`TASK-007` artifacts (`libs/event_contracts`, `scripts/manage_kafka_topics.py`).

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
| --- | --- | --- |
| Reusable producer for canonical product observation events | Met | `KafkaEventProducer` in `libs/common/kafka_producer.py`; takes a `ProductObservationEvent` and returns a `DeliveryReceipt`. |
| Serialize and publish to configured raw topic | Met | `serialize_event(event)` → UTF-8 JSON; default `kafka_raw_topic = "products.raw.v1"`; enqueues with `partitioner="murmur2_random"`. |
| Preserve event identity | Met | Producer never mutates the event; key = `source:external_id` via `partition_key` (matches ADR-001); `event_id`, `source`, `produced_at`, and payload are preserved in the wire value. |
| Do not silently drop publish failures | Met | Raises `PublishError` on enqueue failure, broker-reported delivery failure, and unconfirmed delivery; `EventSerializationError` when the event cannot be encoded/validated; `close()` drains with a bounded timeout and raises on unconfirmed shutdown. |
| Configuration from environment/configuration | Met | `KafkaProducerSettings(AppSettings)` loaded via `load_settings`; `APP_`-prefixed variables, immutability, and unknown-`APP_` rejection inherited from TASK-003. |
| Compatible with at-least-once processing | Met | `acks=all` + `enable.idempotence=true`; documentation explicitly disclaims end-to-end exactly-once and describes duplicate/retry behavior and downstream deduplication ownership. |

### Acceptance criterion

A valid event can be published to `products.raw.v1` and verified by a consumer — **Met** by `test_real_publish_and_consume` (independently executed, see §4).

## 3. Git Diff Review

Files changed (6, +703):

- `.env.example` — added commented `APP_KAFKA_*` settings matching defaults.
- `docs/kafka-producer.md` — new producer guide (config, delivery/failure behavior, verification).
- `libs/common/README.md` — added producer entry.
- `libs/common/kafka_producer.py` — new producer module (+186).
- `requirements.txt` — added `confluent-kafka>=2.15,<3`.
- `tests/test_kafka_producer.py` — new unit + integration tests (+379).

Assessment:

- **Scope correctness:** All changes belong to TASK-008. No out-of-scope files were modified.
- **Unrelated changes:** None observed.
- **Architectural changes:** None. The change adds a new library module; it does not alter service boundaries, event semantics, topic ownership, or ADR-001 partitioning.
- **Accidental changes:** None. No debug code, temporary files, dead code, generated artifacts, or secrets found. `.env.example` additions are commented placeholders consistent with the module defaults.
- **Dependency change:** `confluent-kafka` (librdkafka) is justified by the task and pinned with an upper bound (`<3`). `requirements-dev.txt` already includes `-r requirements.txt`, so dev tooling picks it up.

### Branch and task isolation

Reviewed commit is the only commit in the range (parent `492b181` is the TASK-007 merge). Branch is exactly `feature/TASK-008`. Working tree is clean. No cross-task contamination detected.

## 4. Test and Verification Review

### Tests examined

`tests/test_kafka_producer.py` covers all four required test categories:

- **Successful publish** — `test_publish_preserves_wire_identity_and_key`, `test_environment_configures_actual_publish`, plus the real-broker integration test.
- **Serialization failure** — `test_serialization_failure_never_enqueues` (mocked serializer raising, verifies nothing is enqueued and the failure text is not logged) and `test_mutated_invalid_event_never_enqueues` (invalid `schema_version` rejected pre-enqueue).
- **Kafka unavailable** — `test_real_kafka_unavailable` (reserved non-listening port, bounded `PublishError`), supported by unit-level `test_enqueue_failure_raises` and `test_failed_delivery_is_not_success_even_when_queue_empty`.
- **Invalid configuration** — `test_invalid_configuration` (13 parametrized cases including broker/topic/client-id/timeout and unknown `APP_` var, with secret-value non-echo asserted), plus `test_settings_are_immutable`.

Additional coverage: client reliability config (`enable.idempotence`, `acks`, `max.in.flight`, `allow.auto.create.topics=false`, `partitioner`, `delivery.timeout.ms`), enqueue/flush failure paths, missing-callback/unconfirmed handling, retry-after-failure event preservation, bounded/retryable shutdown, publish-after-close rejection, and shutdown-not-masking-original-error.

### Independently verified (executed by reviewer)

| Check | Result |
| --- | --- |
| `pytest tests/test_kafka_producer.py -q` | **31 passed, 2 deselected** (integration excluded by default) |
| `pytest tests/test_kafka_producer.py -m integration -v` | **2 passed** (real publish/consume + unavailable broker; 49.83s) |
| `ruff check` + `ruff format --check` (changed files) | **All checks passed / 2 files already formatted** |
| `mypy` (changed files) | **Success: no issues found** |

### Implementation evidence reviewed (not rerun by reviewer)

- `scripts/task_check.ps1` (reported 112 unit tests, Ruff, mypy, structure validation). The reviewer instead ran the targeted unit, integration, lint, format, and type checks above; results are consistent with the report.

### Unverified

None — all task-relevant checks were independently executed by the reviewer.

## 5. Findings

No Critical, High, or Moderate findings.

- **Minor — untested branch in the delivery callback** (`libs/common/kafka_producer.py`, `delivered`). The guard that treats missing broker metadata (`topic`/`partition`/`offset` is `None` or `offset < 0`) as an unconfirmed delivery is not directly exercised by a unit test. Impact: low (behavior is defensive and the surrounding `pending or receipt is None` path is covered). Recommendation: add a unit case where the callback receives `None` metadata and assert `PublishError("unconfirmed")`, if desired.

## 6. Non-Defect Observations

- **`produced_at` is set by the caller, not the producer.** The producer preserves identity and does not stamp `produced_at` on first publication; the documentation states the caller sets it and retries reuse the same event. This is a reasonable boundary for a reusable producer, and the event contract makes `produced_at` a required field so it cannot be silently absent. The ingestion service (a later task) must stamp it at event-creation time.
- **Bootstrap-server hostname validation is intentionally permissive.** `valid_brokers` accepts any non-space `host:port` token and validates only shape + port range (1–65535). Its stated purpose is to reject credential-bearing URLs and enforce `host:port`/port-range, which it does; it is not a full DNS validator. Non-blocking.
- **Metrics are explicitly deferred to TASK-011.** `PROJECT.md` §10 requires observability for major boundaries; the producer emits structured logs now and documents that metrics are out of scope for this task. Reasonable given task scope.
- **At-least-once honesty is well handled.** The code and documentation repeatedly and correctly distinguish "idempotent producer within a session" from end-to-end exactly-once, and describe the crash/no-durable-outbox and duplicate-retry consequences. This aligns with `PROJECT.md` §5 and `SPECIFICATION.md` §9.

## 7. Verdict

**APPROVED**

The implementation satisfies every task requirement and the acceptance criterion, is correctly scoped and isolated to `feature/TASK-008`, introduces no unnecessary changes or secrets, and is backed by passing unit and integration tests plus clean lint, format, and type checks. The single Minor finding (an untested defensive callback branch) is non-blocking and can be addressed opportunistically.
