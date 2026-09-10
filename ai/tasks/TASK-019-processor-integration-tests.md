# TASK-019 — Processor Integration Tests

## Objective
Demonstrate the complete Milestone 2 processor flow against local Kafka: consume raw events, normalize/validate/dedupe them, route valid/invalid outputs, and prove restart/replay behavior.

## Dependencies
- TASK-013–018
- TASK-012 Kafka integration infrastructure

## Requirements
1. Start from `products.raw.v1`.
2. Exercise real processor wiring, not only pure functions.
3. Valid event → expected `products.validated.v1` output.
4. Invalid event → `products.invalid.v1` with diagnostic reason(s).
5. Duplicate delivery does not create duplicate logical valid output within documented guarantees.
6. Demonstrate processor restart/re-consumption behavior.
7. Include output-publication failure/retry scenario where practical.
8. Assert no silent data loss.
9. Isolate topics/consumer groups/test state for deterministic runs.
10. Keep integration tests separable from default fast unit tests if that is current CI policy.

## Integration Scenarios
- valid event
- malformed/invalid event
- duplicate event
- restart
- validated/invalid topic routing
- offset/replay behavior
- metrics smoke check where practical

## Acceptance Criteria
Milestone 2 is demonstrated locally:

```text
products.raw.v1
      ↓
processor consumer
      ↓
normalization → validation → dedupe
      ↓                 ↓
products.validated.v1  products.invalid.v1
```

Invalid events do not disappear, duplicates do not create duplicate logical outputs within documented guarantees, restart behavior is demonstrated, and CI-quality checks pass.

## Expected Deliverables
- processor integration suite
- Kafka fixtures/helpers
- run instructions
- minimal processor Docker/local wiring if required

## Agent Instructions
Implement TASK-019 only. Do not introduce MinIO/Parquet/PostgreSQL work from later milestones.
