# TASK-FIX — Add Kafka Lag Probe Regression Tests

## Objective

Add deterministic regression tests for the Kafka lag probe introduced in TASK-112.

The tests must protect against the `confluent_kafka` API incompatibility discovered during live TASK-112 verification.

## Background

During live TASK-112 verification against the kind Kafka cluster,
`kafka_lag_probe.py` failed because the installed `confluent_kafka`
version expects `ConsumerGroupTopicPartitions` objects when calling
`AdminClient.list_consumer_group_offsets()`.

The original TASK-112 tests covered `LagCollector`, but did not exercise
the Kafka-facing probe API contract.

The implementation was subsequently fixed and verified against the live
cluster. This task adds regression coverage for that fix.

## Scope

Add focused tests for:

`libs/load_test/kafka_lag_probe.py`

At minimum verify:

1. `list_consumer_group_offsets()` is called using the API shape expected
   by the installed `confluent_kafka` version.

2. Returned `ConsumerGroupTopicPartitions.topic_partitions` are handled
   correctly.

3. Committed offsets are mapped to the correct:
   - consumer group
   - topic
   - partition

4. Lag is calculated correctly from:
   - committed offset
   - high watermark

5. Multiple partitions are handled correctly.

6. Kafka/API errors are handled according to the current probe contract.

Tests should be deterministic and MUST NOT require a running Kafka broker.

## Preferred Test Location

`tests/test_load_test/test_kafka_lag_probe.py`

Use mocks/fakes for Kafka AdminClient / Consumer APIs.

## Out of Scope

Do not:

- redesign the lag measurement architecture
- change consumer-group semantics
- change TASK-112 benchmark results
- modify operational thresholds
- refactor unrelated Kafka code
- modify unrelated tests

## Acceptance Criteria

- Regression test reproduces the API contract that previously failed.
- Test would fail if the old bare-group-ID implementation were restored.
- Correct `ConsumerGroupTopicPartitions` handling is verified.
- Lag calculation is verified.
- Tests run without Kafka.
- Focused tests pass.
- Ruff passes.
- Mypy passes for modified files.
- No unrelated changes.

## Required Context

Read:

- `ai/PROJECT.md`
- `ai/SPECIFICATION.md`
- applicable Kafka ADRs
- `ai/tasks/TASK-112-measure-kafka-lag.md`
- `docs/kafka-lag-measurement.md`
- current `libs/load_test/kafka_lag_probe.py`
- TASK-112 Qwen review

## Agent Instructions

Implement this FIX only.
Do not change unrelated architecture or benchmark evidence.# TASK-FIX — Add Kafka Lag Probe Regression Tests

## Objective

Add deterministic regression tests for the Kafka lag probe introduced in TASK-112.

The tests must protect against the `confluent_kafka` API incompatibility discovered during live TASK-112 verification.

## Background

During live TASK-112 verification against the kind Kafka cluster,
`kafka_lag_probe.py` failed because the installed `confluent_kafka`
version expects `ConsumerGroupTopicPartitions` objects when calling
`AdminClient.list_consumer_group_offsets()`.

The original TASK-112 tests covered `LagCollector`, but did not exercise
the Kafka-facing probe API contract.

The implementation was subsequently fixed and verified against the live
cluster. This task adds regression coverage for that fix.

## Scope

Add focused tests for:

`libs/load_test/kafka_lag_probe.py`

At minimum verify:

1. `list_consumer_group_offsets()` is called using the API shape expected
   by the installed `confluent_kafka` version.

2. Returned `ConsumerGroupTopicPartitions.topic_partitions` are handled
   correctly.

3. Committed offsets are mapped to the correct:
   - consumer group
   - topic
   - partition

4. Lag is calculated correctly from:
   - committed offset
   - high watermark

5. Multiple partitions are handled correctly.

6. Kafka/API errors are handled according to the current probe contract.

Tests should be deterministic and MUST NOT require a running Kafka broker.

## Preferred Test Location

`tests/test_load_test/test_kafka_lag_probe.py`

Use mocks/fakes for Kafka AdminClient / Consumer APIs.

## Out of Scope

Do not:

- redesign the lag measurement architecture
- change consumer-group semantics
- change TASK-112 benchmark results
- modify operational thresholds
- refactor unrelated Kafka code
- modify unrelated tests

## Acceptance Criteria

- Regression test reproduces the API contract that previously failed.
- Test would fail if the old bare-group-ID implementation were restored.
- Correct `ConsumerGroupTopicPartitions` handling is verified.
- Lag calculation is verified.
- Tests run without Kafka.
- Focused tests pass.
- Ruff passes.
- Mypy passes for modified files.
- No unrelated changes.

## Required Context

Read:

- `ai/PROJECT.md`
- `ai/SPECIFICATION.md`
- applicable Kafka ADRs
- `ai/tasks/TASK-112-measure-kafka-lag.md`
- `docs/kafka-lag-measurement.md`
- current `libs/load_test/kafka_lag_probe.py`
- TASK-112 Qwen review

## Agent Instructions

Implement this FIX only.
Do not change unrelated architecture or benchmark evidence.# TASK-FIX — Add Kafka Lag Probe Regression Tests

## Objective

Add deterministic regression tests for the Kafka lag probe introduced in TASK-112.

The tests must protect against the `confluent_kafka` API incompatibility discovered during live TASK-112 verification.

## Background

During live TASK-112 verification against the kind Kafka cluster,
`kafka_lag_probe.py` failed because the installed `confluent_kafka`
version expects `ConsumerGroupTopicPartitions` objects when calling
`AdminClient.list_consumer_group_offsets()`.

The original TASK-112 tests covered `LagCollector`, but did not exercise
the Kafka-facing probe API contract.

The implementation was subsequently fixed and verified against the live
cluster. This task adds regression coverage for that fix.

## Scope

Add focused tests for:

`libs/load_test/kafka_lag_probe.py`

At minimum verify:

1. `list_consumer_group_offsets()` is called using the API shape expected
   by the installed `confluent_kafka` version.

2. Returned `ConsumerGroupTopicPartitions.topic_partitions` are handled
   correctly.

3. Committed offsets are mapped to the correct:
   - consumer group
   - topic
   - partition

4. Lag is calculated correctly from:
   - committed offset
   - high watermark

5. Multiple partitions are handled correctly.

6. Kafka/API errors are handled according to the current probe contract.

Tests should be deterministic and MUST NOT require a running Kafka broker.

## Preferred Test Location

`tests/test_load_test/test_kafka_lag_probe.py`

Use mocks/fakes for Kafka AdminClient / Consumer APIs.

## Out of Scope

Do not:

- redesign the lag measurement architecture
- change consumer-group semantics
- change TASK-112 benchmark results
- modify operational thresholds
- refactor unrelated Kafka code
- modify unrelated tests

## Acceptance Criteria

- Regression test reproduces the API contract that previously failed.
- Test would fail if the old bare-group-ID implementation were restored.
- Correct `ConsumerGroupTopicPartitions` handling is verified.
- Lag calculation is verified.
- Tests run without Kafka.
- Focused tests pass.
- Ruff passes.
- Mypy passes for modified files.
- No unrelated changes.

## Required Context

Read:

- `ai/PROJECT.md`
- `ai/SPECIFICATION.md`
- applicable Kafka ADRs
- `ai/tasks/TASK-112-measure-kafka-lag.md`
- `docs/kafka-lag-measurement.md`
- current `libs/load_test/kafka_lag_probe.py`
- TASK-112 Qwen review

## Agent Instructions

Implement this FIX only.
Do not change unrelated architecture or benchmark evidence.
