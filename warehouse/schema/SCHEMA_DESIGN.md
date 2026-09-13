# PostgreSQL Warehouse Schema Design (TASK-027)

## Overview

This document describes the initial PostgreSQL warehouse schema for the AI Data Platform's serving and analytical layer. The schema supports historical observations, source-product mapping, pipeline metadata, and data quality tracking.

## Entity Relationship Diagram

```
sources (1) ──────< source_products >────── (1) products (1)
                         │
                         │ (many observations over time)
                         ▼
                  product_observations

pipeline_runs (1) ──────< data_quality_results >────── product_observations
```

## Tables

### `sources`

Registry of external data sources feeding the platform.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PRIMARY KEY | Internal source identifier |
| name | TEXT | NOT NULL, UNIQUE | Source identifier (e.g. 'bestbuy', 'ebay') |
| description | TEXT | | Human-readable explanation |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Creation timestamp |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Last update timestamp |

**Rationale:** Keeps source identity explicit and stable. New sources are added here before any data flows through them.

---

### `products`

Canonical/logical product identity independent of source-specific listings.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | BIGSERIAL | PRIMARY KEY | Canonical product identifier |
| canonical_name | TEXT | | Normalized product name after deduplication |
| category | TEXT | | Normalized category assigned during processing |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Creation timestamp |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Last update timestamp |

**Rationale:** A single logical product (e.g. "iPhone 15 Pro") may have multiple source-specific listings (Best Buy SKU, eBay listing). This table captures the deduplicated identity.

---

### `source_products`

Maps source-specific listings to canonical products.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | BIGSERIAL | PRIMARY KEY | Internal mapping identifier |
| source_id | INTEGER | NOT NULL, FK → sources(id) | Which source this listing belongs to |
| product_id | BIGINT | NOT NULL, FK → products(id) | Which canonical product this maps to |
| external_id | TEXT | NOT NULL | Source-specific listing ID (SKU, listing ID) |
| url | TEXT | | Source listing URL |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Creation timestamp |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Last update timestamp |

**Unique constraint:** `(source_id, external_id)` — prevents duplicate listings from the same source.

**Rationale:** Preserves the distinction between source identity and canonical product identity. One canonical product can have many source listings; one source listing maps to exactly one canonical product.

---

### `product_observations`

Historical record of every observed product listing state. **This is the core fact table.**

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | BIGSERIAL | PRIMARY KEY | Observation identifier |
| source_product_id | BIGINT | NOT NULL, FK → source_products(id) | Which source listing was observed |
| name | TEXT | | Observed name at collection time |
| price | NUMERIC(12, 2) | CHECK >= 0 or NULL | Exact decimal price (not floating point) |
| currency | TEXT | | ISO 4217 currency code (USD, EUR, etc.) |
| availability | TEXT | NOT NULL | e.g. 'in_stock', 'out_of_stock' |
| collected_at | TIMESTAMPTZ | NOT NULL | When observation was made at source (business time) |
| ingested_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | When loaded into warehouse (system time) |

**Rationale:** Multiple rows per source_product capture price changes, availability shifts, and other temporal dynamics. This enables queries for latest observation, price history, rolling calculations, and trend analysis.

**Price type:** `NUMERIC(12, 2)` provides exact decimal arithmetic for money, avoiding binary floating-point precision errors. Supports prices up to $99,999,999.99.

**Timestamps:** Two timestamps serve different purposes:
- `collected_at`: Business time when the observation was made at the source
- `ingested_at`: System time when the observation was loaded into the warehouse

---

### `pipeline_runs`

Metadata about each pipeline execution that loads data into the warehouse.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | BIGSERIAL | PRIMARY KEY | Run identifier |
| run_type | TEXT | NOT NULL | e.g. 'full_load', 'incremental', 'replay' |
| status | TEXT | NOT NULL | 'running', 'success', 'failed' |
| started_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Run start time |
| finished_at | TIMESTAMPTZ | | Run completion time |
| records_loaded | BIGINT | | Number of records loaded in this run |
| error_message | TEXT | | Error details if failed |
| metadata | JSONB | | Arbitrary run metadata |

**Rationale:** Provides lineage and debugging capability. Each load operation is tracked for freshness monitoring and troubleshooting.

---

### `data_quality_results`

Results of data quality checks applied during loading.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | BIGSERIAL | PRIMARY KEY | Result identifier |
| pipeline_run_id | BIGINT | FK → pipeline_runs(id) | Which run this check belongs to |
| observation_id | BIGINT | FK → product_observations(id) | Specific observation (if applicable) |
| check_name | TEXT | NOT NULL | e.g. 'price_null', 'duplicate_external_id' |
| severity | TEXT | NOT NULL | 'info', 'warning', 'error' |
| passed | BOOLEAN | NOT NULL | Whether the check passed |
| message | TEXT | | Human-readable explanation |
| checked_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | When check was performed |

**Rationale:** Tracks data quality issues separately from the core data. Links to specific observations or runs enable targeted investigation.

---

## Design Decisions

### Historical Observations

The schema preserves **all** observations over time rather than only the latest state. This enables:
- Price change detection and history
- Trend analysis and rolling calculations
- Replay and debugging of past states
- Time-travel queries for analytics

To get the latest observation for a product:
```sql
SELECT po.*
FROM product_observations po
JOIN source_products sp ON po.source_product_id = sp.id
WHERE sp.product_id = :product_id
ORDER BY po.collected_at DESC
LIMIT 1;
```

### Source vs. Product Identity

The `source_products` junction table keeps source identity distinct from canonical product identity. This supports:
- Multiple source listings for one logical product
- Source-specific URLs and identifiers
- Independent tracking of source health
- Deduplication logic during ingestion

### Exact Numeric for Money

`NUMERIC(12, 2)` is used for prices instead of `FLOAT`/`DOUBLE PRECISION`. This avoids:
- Binary floating-point precision errors (e.g., 0.1 + 0.2 ≠ 0.3)
- Rounding inconsistencies in financial calculations
- Comparison issues in price-change detection

### Timezone-Aware Timestamps

All timestamps use `TIMESTAMPTZ` (timestamp with time zone). PostgreSQL stores these internally as UTC and converts on input/output based on session timezone. This ensures:
- Consistent storage regardless of server timezone
- Correct arithmetic across daylight saving boundaries
- Proper comparison of observations from different timezones

### No Speculative Entities

The schema includes only the five entities explicitly required by the task:
- `sources`, `products`, `product_observations`, `pipeline_runs`, `data_quality_results`

No additional tables (e.g., categories, brands, reviews) are added prematurely.

### Constraint-Only Indexes

Per TASK-027 scope, only constraint-required indexes exist:
- Primary key indexes on all tables
- Unique index on `sources.name`
- Unique index on `source_products(source_id, external_id)`
- Foreign key indexes (implicit in PostgreSQL)

Performance indexes for analytical queries are deferred to TASK-031.

---

## Supported Query Patterns

The schema supports the following query patterns without redesign:

1. **Latest observation per product:** Filter by `product_id`, order by `collected_at DESC`, limit 1
2. **Price change detection:** Self-join or window functions on `product_observations` ordered by `collected_at`
3. **Rolling calculations:** Window functions (AVG, SUM, LAG) over `product_observations` partitioned by `source_product_id`
4. **Product history:** Select all observations for a `source_product_id` ordered by `collected_at`
5. **Source statistics:** Aggregate `product_observations` joined with `source_products` grouped by `source_id`
6. **Pipeline lineage:** Join `data_quality_results` with `pipeline_runs` for run-level quality summary
7. **Freshness monitoring:** Compare `MAX(collected_at)` per source against current time

---

## Future Extensions (Out of Scope for TASK-027)

The following are intentionally excluded but could be added later:
- Performance indexes (TASK-031)
- Materialized views for common aggregations
- Partitioning strategies for large observation tables
- Additional product attributes (brand, manufacturer, dimensions)
- Review/rating data
- Inventory quantity tracking
- Price alert subscriptions
