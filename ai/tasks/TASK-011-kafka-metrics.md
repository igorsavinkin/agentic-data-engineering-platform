# TASK-011 — Kafka Metrics

## Status
Ready

## Objective
Expose initial Kafka producer/consumer operational metrics.

## References
- `ai/SPECIFICATION.md` — Observability
- `TASK-008`
- `TASK-009`

## Metrics
At minimum cover produced events, consumed events, errors, invalid events, and consumer lag visibility.

## Acceptance Criteria
Metrics/hooks are available for later Prometheus integration and contain no secrets.
