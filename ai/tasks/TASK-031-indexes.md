# TASK-031 — Database Indexes

## Objective

Add strategic database indexes to the warehouse PostgreSQL schema to support analytical queries and common access patterns efficiently.

## Dependencies

TASK-027 (PostgreSQL schema) and TASK-030 (Idempotent Loading with event_id).

## Requirements

### Query Patterns to Optimize

Based on Milestone 4 acceptance criteria, the following query patterns must be performant:

1. **Latest observation per product** - `ROW_NUMBER()` / `RANK()` over partition
2. **Price change analysis** - `LAG()` window function on collected_at
3. **Rolling averages** - time-series aggregation by date ranges
4. **Source statistics** - GROUP BY source_id with COUNT/AVG aggregations
5. **Time-range filtering** - WHERE collected_at BETWEEN ... AND ...
6. **Product lookup** - JOIN on source_products.product_id
7. **Event deduplication checks** - UNIQUE constraint lookups on event_id

### Required Indexes

Create a migration (003) that adds:

1. **product_observations indexes:**
   - Composite index: `(source_product_id, collected_at DESC)` - supports latest observation and time-series queries
   - Index: `(collected_at DESC)` - supports time-range filtering across all products
   - Index: `(event_id)` - already exists from migration 002, verify it's present

2. **source_products indexes:**
   - Index: `(product_id)` - supports JOINs when querying observations by canonical product
   - Unique constraint on `(source_id, external_id)` - already exists in initial schema, verify

3. **data_quality_results indexes:**
   - Index: `(pipeline_run_id)` - supports quality result lookups by pipeline run
   - Index: `(observation_id)` - supports quality result lookups by observation
   - Index: `(check_name, passed)` - supports quality check filtering

### Performance Verification

For each index created:
- Write an EXPLAIN ANALYZE test showing the index is used
- Demonstrate at least one representative query benefits from the index
- Document expected vs actual query plan improvements

### Migration Strategy

- Use Alembic migration 003_add_indexes.py
- All index creation must be idempotent (use IF NOT EXISTS where supported)
- Include downgrade path that drops all new indexes
- No data migration required (indexes only)

## Tests Required

- Verify all indexes exist after migration upgrade
- Verify indexes are dropped after migration downgrade
- EXPLAIN ANALYZE tests demonstrating index usage for:
  - Latest observation query (uses source_product_id + collected_at)
  - Time-range filter (uses collected_at)
  - Product lookup (uses product_id on source_products)
  - Quality check filtering (uses check_name + passed)

## Acceptance Criteria

All required indexes are created and verified through EXPLAIN ANALYZE to improve query performance for the specified analytical patterns. Downgrade cleanly removes all indexes without data loss.

## Agent Instructions

Focus on index design for analytical query performance. Do not modify table schemas or data. Use PostgreSQL-specific index features where beneficial (e.g., partial indexes, expression indexes if needed). Ensure indexes support the window functions (ROW_NUMBER, LAG, RANK) mentioned in ROADMAP.md.
