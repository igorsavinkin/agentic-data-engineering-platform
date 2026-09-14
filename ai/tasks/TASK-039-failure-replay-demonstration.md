# TASK-039 — Failure / Replay Demonstration

## Objective
Demonstrate and document the platform's at-least-once, retry, replay, and recovery behavior across the vertical slice.

## Required Scenarios
- consumer/process restart after reading an event
- duplicate event delivery
- replay from Kafka
- storage/warehouse retry after transient failure
- invalid event routed to invalid/DLQ
- replay does not create duplicate logical observations in the final serving layer

## Requirements
1. Do not claim exactly-once semantics.
2. Document offset commit timing.
3. Document crash behavior before persistence and after persistence but before offset commit.
4. Explain where idempotency is enforced.
5. Make recovery steps reproducible.
6. Do not introduce distributed transactions just for the demonstration.

## Acceptance Criteria
Failure/replay behavior is reproducible, documented, and final logical data remains correct after replay.

## Agent Instructions
Implement TASK-039 only.
