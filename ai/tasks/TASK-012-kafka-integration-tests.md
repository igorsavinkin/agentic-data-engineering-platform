# TASK-012 — Kafka Integration Tests

## Status
Ready

## Objective
Create integration tests for the initial event transport.

## References
- `ai/SPECIFICATION.md`
- `TASK-006` through `TASK-011`

## Test Scenarios
- Producer → Kafka → Consumer.
- Invalid event.
- Duplicate event.
- Consumer restart.
- Failure/retry path.

## Acceptance Criteria
Tests run against the project Kafka environment and demonstrate the Milestone 1 acceptance criteria.
