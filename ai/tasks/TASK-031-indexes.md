# TASK-031 — PostgreSQL Indexes

## Objective
Add and justify PostgreSQL indexes for expected serving and analytical query patterns.

## Dependencies
TASK-027–030.

## Expected Query Patterns
Latest observation, product history, price changes, source statistics, time-range analytics, and later FastAPI serving.

## Requirements
- Add only evidence-based indexes.
- Avoid indexes already covered by PK/unique constraints.
- Consider composite column order deliberately.
- Favor indexes that support product+observed time, source+observed time, and other proven access patterns.
- Do not create one index per column.
- Manage all indexes through migrations.
- Use `EXPLAIN`/`EXPLAIN ANALYZE` on representative queries where practical.
- Briefly document read benefit versus write/storage cost.
- Do not introduce table partitioning/sharding unless a higher-authority document requires it.

## Tests Required
- expected indexes exist after migration
- downgrade behavior if applicable
- representative plans use suitable indexes on meaningful fixture data where practical
- no redundant duplicate definitions

## Acceptance Criteria
Required serving/analytics query patterns have a justified, migration-managed indexing strategy without speculative index explosion.

## Agent Instructions
Implement TASK-031 only.
