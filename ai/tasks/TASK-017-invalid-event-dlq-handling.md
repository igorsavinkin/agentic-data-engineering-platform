# TASK-017 — Invalid Event / DLQ Handling

## Objective
Route processor outcomes to the canonical Kafka output paths while preserving diagnostics and correct at-least-once/offset behavior.

## Dependencies
- TASK-015
- TASK-016
- TASK-008 producer abstraction
- TASK-009/TASK-010 consumer/error handling
- TASK-007 topics

## Requirements
1. Valid records publish to `products.validated.v1`.
2. Invalid records publish to `products.invalid.v1`.
3. Invalid representation preserves event identity/source, validation reason(s), and enough original context for diagnosis without leaking secrets.
4. Malformed input should retain diagnosable context where possible.
5. Input offset/ack behavior must remain compatible with documented at-least-once semantics.
6. Do not mark input complete if required output publication failed.
7. Retry/replay consequences must be documented.
8. Invalid records must never silently disappear.
9. Kafka remains transport, not permanent analytical storage.

## Out of Scope
- DLQ persistence to S3/PostgreSQL
- automated replay tooling
- processor metrics

## Tests Required
- valid → validated topic only
- invalid → invalid topic only
- multiple reasons preserved
- output publish failure
- malformed input diagnostics
- retry/replay behavior

## Acceptance Criteria
- Every outcome reaches the correct canonical topic.
- Invalid outcomes are diagnosable.
- Failure/offset behavior matches current Kafka semantics.
- Tests pass.

## Agent Instructions
Implement TASK-017 only. If offset commit semantics conflict with TASK-010 or ADRs, stop and report.
