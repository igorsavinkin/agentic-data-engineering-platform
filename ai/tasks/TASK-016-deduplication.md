# TASK-016 — Deduplication

## Objective
Implement replay-safe deduplication for valid processor records so at-least-once Kafka delivery does not create duplicate logical processor output.

## Dependencies
- TASK-015
- TASK-006 event identity
- TASK-007 partitioning/ordering ADR

## Requirements
1. Use `event_id` as observation-event identity unless current higher-authority docs say otherwise.
2. Repeated delivery of the same event must not create duplicate logical valid output within the documented processor guarantee.
3. Keep deduplication deterministic.
4. Never claim exactly-once.
5. Do not collapse legitimate repeated observations of the same product at different times.
6. Respect Kafka partition/ordering assumptions; do not invent global order.
7. Conflicting payloads with the same event ID must be surfaced explicitly.
8. Keep dedupe logic independently testable where possible.
9. Document state lifetime and what later durable persistence must still enforce.

## Out of Scope
- PostgreSQL uniqueness/idempotent warehouse loading
- cross-cluster exactly-once
- performance tuning
- final DLQ publication

## Tests Required
- exact duplicate in one batch
- duplicate across processor calls according to documented state boundary
- same product at different collection times remains separate
- same event ID + conflicting payload
- replay-order determinism

## Acceptance Criteria
- Duplicate delivery does not duplicate logical processor output within documented guarantees.
- Legitimate historical observations remain.
- Semantics remain at-least-once + idempotent.
- Tests pass.

## Agent Instructions
Implement TASK-016 only. Escalate if dedupe requires an undocumented durable-state architecture decision.
