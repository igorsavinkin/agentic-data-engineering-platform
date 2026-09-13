# TASK-029 — Warehouse Loader

## Objective
Implement the Warehouse Loader that reads curated Parquet data and loads PostgreSQL analytical tables.

## Dependencies
TASK-025, TASK-026, TASK-027, TASK-028.

## Architectural Boundary
The loader consumes curated Parquet and writes PostgreSQL. It must not bypass the data lake by consuming source APIs directly.

## Requirements
- Read the curated/analytical Parquet dataset defined by the current architecture.
- Map Parquet columns into `sources`, `products`, and `product_observations` as required.
- Preserve source/product/observation identity.
- Use transactions for atomic work units.
- Fail explicitly; do not silently drop rows.
- Prefer batched/chunked processing over loading the whole lake into Python memory.
- Use safe parameterized SQL/DB APIs.
- Separate row mapping from DB I/O where practical.
- Add structured load logging/result metadata.
- Implement only minimal correctness for duplicates; TASK-030 owns replay-safe idempotency.
- Do not implement indexes or analytical queries.

## Tests Required
- Parquet fixture → PostgreSQL rows
- sources/products created correctly
- historical observations loaded
- nullable fields
- rollback on failure
- malformed/unmappable input fails clearly
- multiple input files/batches

## Acceptance Criteria
Curated Parquet loads into PostgreSQL with history preserved and transactionally safe failure behavior.

## Agent Instructions
Implement TASK-029 only. Keep the loader reusable for later Airflow orchestration.
