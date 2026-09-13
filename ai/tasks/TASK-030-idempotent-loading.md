# TASK-030 — Idempotent Loading

## Objective
Make Warehouse Loader execution safe under replay and repeated batch execution so the same logical observations are not duplicated.

## Dependencies
TASK-029 and the project-wide at-least-once + idempotent-processing contract.

## Requirements
- Define and implement warehouse-level idempotency keys/constraints.
- Reprocessing the same observation must not create a second logical observation.
- Use `event_id` or the canonical observation identity defined by higher-authority docs consistently.
- Legitimate later observations of the same product must still be stored.
- Use stable upsert/insert semantics for sources/products.
- Enforce invariants with DB constraints plus application logic where appropriate.
- Do not claim exactly-once semantics.
- Retry after a partial failure must converge to the correct state.
- Conflicting payloads for the same immutable observation identity must be surfaced, not silently overwritten.
- Avoid race-prone check-then-insert when PostgreSQL can enforce uniqueness atomically.

## Tests Required
- same batch twice
- same observation through two files
- same product at new observation time remains new history
- retry after partial failure
- conflicting duplicate identity
- concurrent/repeated insertion where practical
- reference-table upsert behavior

## Acceptance Criteria
Replay of identical input creates no duplicate logical observations while legitimate historical observations remain intact.

## Agent Instructions
Implement TASK-030 only. Escalate identity conflicts rather than inventing new semantics.
