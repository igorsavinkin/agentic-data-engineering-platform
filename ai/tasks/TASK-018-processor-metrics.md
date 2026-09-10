# TASK-018 — Processor Metrics

## Objective
Expose bounded-cardinality processor metrics for throughput, validation outcomes, duplicates, failures, latency, and basic processing health.

## Dependencies
- TASK-013–017
- reuse TASK-011 metrics conventions where applicable

## Requirements
1. Counters for processed, valid, invalid, duplicate, and failed events/records.
2. Processing latency histogram/summary consistent with project conventions.
3. Batch-size/throughput metric where useful.
4. No high-cardinality labels such as event ID, external/product ID, URL, or raw error message.
5. Source/reason labels only if bounded and justified.
6. Metrics failure must not alter processing semantics.
7. Reuse naming/conventions from TASK-011 where applicable.
8. Document metric names and meanings.

## Out of Scope
- Grafana dashboards
- alert rules
- full tracing
- cluster monitoring

## Tests Required
- counters increment for outcomes
- failure metric
- latency observation
- label cardinality guard
- processor remains correct without metrics backend

## Acceptance Criteria
- Documented stable metrics expose processor health/outcomes.
- Cardinality is bounded.
- Tests and quality checks pass.

## Agent Instructions
Implement TASK-018 only. Instrument existing behavior; do not redesign processor semantics.
