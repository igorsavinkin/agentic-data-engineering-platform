# TASK-008 — Kafka Producer

## Status
Ready

## Objective
Implement a reusable producer for canonical product observation events.

## References
- `ai/SPECIFICATION.md`
- `TASK-006`
- `TASK-007`

## Scope
Serialize and publish canonical events to the configured raw topic while preserving event identity.

## Requirements
- Do not silently drop publish failures.
- Configuration comes from environment/configuration.
- Behavior is compatible with at-least-once processing.

## Tests Required
Successful publish; serialization failure; Kafka unavailable; invalid configuration.

## Acceptance Criteria
A valid event can be published to `products.raw.v1` and verified by a consumer.
