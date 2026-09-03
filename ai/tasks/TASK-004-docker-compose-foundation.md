# TASK-004 — Docker Compose Foundation

## Status
Ready

## Objective
Create the minimal local infrastructure for incremental development.

## References
- `ai/SPECIFICATION.md`
- `ai/ROADMAP.md`

## Scope
- Kafka.
- MinIO.
- PostgreSQL.
- Shared local network/configuration.

## Out of scope
Airflow, observability stack, application services, Kubernetes.

## Tests Required
Start the stack, verify reachability, and verify restart behavior.

## Acceptance Criteria
A developer can start the local infrastructure using the documented procedure.
