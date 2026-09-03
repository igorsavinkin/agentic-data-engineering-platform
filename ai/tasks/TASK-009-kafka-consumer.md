# TASK-009 — Kafka Consumer

## Status
Ready

## Objective
Implement the first reusable Kafka consumer.

## References
- `ai/SPECIFICATION.md`
- `TASK-006` through `TASK-008`

## Scope
- Consumer group configuration.
- Deserialization and validation.
- Explicit offset handling.
- Graceful shutdown.

## Requirements
Document when offsets are committed and what happens when processing fails.

## Tests Required
Valid event; malformed event; restart; duplicate delivery.

## Acceptance Criteria
The consumer reliably consumes canonical events without claiming exactly-once semantics.
