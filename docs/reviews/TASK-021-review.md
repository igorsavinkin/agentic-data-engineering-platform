# TASK-021 review

- Date: 2026-09-12
- Verdict: **BLOCKED**
- Change set: supplied review.diff; `cb8ad24..34ec396` on `feature/TASK-021`.
- Scope: review only; no implementation or test changes.

## Requirements coverage

| Requirement | Assessment |
| --- | --- |
| Consume canonical raw events | Subscribes to products.raw.v1 and uses the shared canonical consumer, but persistence/commit coordination is incorrect. |
| Bronze Parquet through TASK-020 | Uses Polars and MinIOStorage, retaining the Raw Writer service boundary. |
| Preserve identity, source, version, timestamps and payload | Fields are mapped, but Decimal price conversion is lossy (F3). |
| At-least-once and idempotency | Deterministic keys support identical-event replay, but early commits and the log-only DLQ violate delivery guarantees (F1/F2). |
| Explicit storage failures and retry semantics | StorageError is raised, but failed batches are discarded. Documented RetryPolicy behavior does not match exception handling. |
| Tests: success, nulls, replay, failure | Writer-level coverage exists; consumer commit/crash/rebalance/retry coverage is absent. Integration test selection is broken (F4). |
| No Silver or later milestone implementation | Preserved; no service redesign or unrelated implementation changes found. |

Reviewed PROJECT, AGENTS, AGENT_WORKFLOW, REVIEWER, relevant SPECIFICATION/ROADMAP sections, ADR-001, shared Kafka consumer/error contracts, canonical event contract, TASK-020 storage and CI configuration. No TASK-021 file exists under ai/tasks in this checkout; the supplied task specification was used. No authority conflict identified.

## Blocking findings

### F1 — Critical: offsets committed before Bronze persistence

`services/raw-writer/consumer.py:58-61,78,87-91`; `libs/raw_writer/bronze_writer.py:186`.

The runtime uses batch_size=100. For the first 99 events, process_message only appends to memory and returns successfully. KafkaConsumer.process_next commits offset+1 immediately after that return. A crash or rebalance before the flush therefore skips records that never reached Bronze. A single event can remain unwritten indefinitely while the service is idle. If a later batch flush partially fails, flush_batch clears all buffered events before raising; previously committed failed records cannot be recovered through ordinary consumer restart.

Persist each message before its process_next callback returns, or implement explicit partition-aware batch offset tracking that never commits beyond unpersisted records, including shutdown/rebalance/partial-failure handling. Preserve retryable pending events. Add tests using the shared consumer contract for below-threshold processing, crash/restart, partial upload failure, and replay after upload-before-commit failure.

### F2 — High: log-only DLQ acknowledges discarded records

`services/raw-writer/consumer.py:33-46,89`.

The dead-letter sink merely logs and returns. KafkaConsumer.process_next treats its successful return as durable acknowledgement and commits malformed/unsupported records. No persistent DLQ receives them. This violates the shared sink contract and removes normal replay recovery. The configured log formatter does not even include the envelope extra field.

Use an acknowledged durable DLQ sink or fail closed without committing. Add a deserialization-failure test proving the offset remains uncommitted when durable DLQ delivery is unavailable.

### F3 — High: Decimal payload values are not preserved

`libs/raw_writer/bronze_writer.py:91`.

The canonical contract accepts Decimal prices without a fixed precision limit, but event_to_row converts them to float. For example, valid Decimal("9007199254740993") becomes 9007199254740992.0; sufficiently large finite Decimal values become infinity. Bronze then permanently loses the raw value. Existing tests use simple float-compatible values and cannot detect this.

Use a lossless representation compatible with the canonical contract (for example an exact decimal string, or a decimal column with explicitly supported precision). Test high precision, large values, zero, and null through Parquet read-back.

### F4 — High: new infrastructure tests break default CI selection

`tests/test_bronze_writer_integration.py:18-44`.

The module has no integration marker. pyproject.toml excludes marked integration tests from ordinary pytest, while CI runs pytest without starting MinIO. These five new tests therefore attempt localhost:9000 during unit CI and fail fixture setup. Conversely, `pytest -m integration` does not select them.

Mark the module with pytest.mark.integration, document the matching command, and run the marked tests against MinIO separately. Keep ordinary pytest hermetic.

## Other findings

- Moderate: consumer.py:90 advertises retries, but StorageError is not TransientProcessingError, so the shared consumer closes and propagates it immediately rather than performing the configured three attempts. Document restart-based recovery accurately or implement a bounded storage retry that cannot acknowledge failed persistence. Do not simply translate the exception without considering exhausted retries and DLQ behavior.
- Minor: README's `python -m services.raw_writer.consumer` does not match the actual `services/raw-writer` directory. Provide a working invocation and the required dedicated raw-writer consumer-group configuration.
- Minor: tests use datetime.now rather than fixed timestamps; the partial-failure assertion matches the generic word "failed" rather than verifying the actual failed event ID. Strengthen assertions and make fixtures deterministic.
- Non-blocking follow-up: a one-row inferred schema makes null-price files differ from populated-price files. Test reading mixed-null files together and consider an explicit stable writer schema without implementing the later schema-management task.

## Git and architecture review

Seven implementation files changed, all attributable to TASK-021; no dependency or infrastructure changes. Branch and commit match the task. The pre-existing untracked review.diff attachment was left untouched. The review report is the only file written by this review.

Polars serialization, TASK-020 reuse, separate Raw Writer ownership, source/date object prefixes and deterministic replay keys are appropriate. No Silver normalization, PostgreSQL writes, cloud expansion or actual new secret was identified. Kafka remains transport and MinIO/S3 remains the intended analytical storage, but F1 prevents the claimed at-least-once persistence guarantee.

## Verification

- Independently verified by source inspection: callback commit timing, DLQ acknowledgement behavior, failure-batch clearing, lossy price conversion, and missing integration marker against repository configuration.
- Execution attempted: `.venv/Scripts/python.exe -m pytest tests/test_bronze_writer.py -q`, Ruff format/check, and mypy. All were prevented from starting because the venv refers to `C:\Users\igors\AppData\Local\Python\pythoncore-3.14-64\python.exe`, which returns Access is denied.
- Unverified: executable test results, full pytest, lint/format/type success, real MinIO round-trip and Kafka-to-MinIO integration. No final-tree successful implementation check evidence was supplied or established by this review.
- Tests inspected: both new Bronze test modules. They exercise isolated serialization, individual null files, storage exceptions and repeated keys; neither exercises the runtime consumer or offset safety. The MinIO replay assertion only confirms the expected key exists, rather than verifying object count and contents after replay.

## Verdict

**BLOCKED.** Resolve F1-F4 and add the corresponding regression coverage before acceptance. Structure and task scope are reasonable, but delivery guarantees, payload fidelity and the configured test gate are not currently satisfied.
