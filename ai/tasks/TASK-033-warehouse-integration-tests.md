# TASK-033 — Warehouse Integration Tests

## Objective
Prove Milestone 4 end-to-end from curated Parquet through Warehouse Loader into PostgreSQL and analytical SQL.

## Dependencies
TASK-027–032 and TASK-026.

## Required Flow
```text
Parquet
   ↓
Warehouse Loader
   ↓
PostgreSQL
   ↓
Analytical SQL
```

## Integration Scenarios
- clean DB → migrations → load
- multiple sources/products/observations
- same input replayed twice
- same product at multiple timestamps
- loader failure + retry
- reference entity upsert behavior
- latest-observation query
- price-change query
- ranking/window-function query
- source statistics
- empty/partial dataset behavior where relevant

## Requirements
- Use real local PostgreSQL integration infrastructure.
- Apply real migrations.
- Load representative Parquet through the real Warehouse Loader; do not bypass it with direct INSERTs for main E2E scenarios.
- Tests must be deterministic and isolated.
- Validate DB state and analytical results, not just process exit codes.
- Preserve at-least-once + idempotent semantics.
- Do not begin FastAPI/Airflow/Kubernetes/cloud work.

## Acceptance Criteria
The milestone path works end-to-end. Repeated loading creates no duplicate logical observations, historical observations remain queryable, and required analytical SQL returns correct results. Full quality checks pass.

## Agent Instructions
Implement TASK-033 only. This is the Milestone 4 integration gate.
