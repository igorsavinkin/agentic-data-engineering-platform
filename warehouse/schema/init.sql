-- PostgreSQL Warehouse Schema (TASK-027)
-- Initial schema for serving/analytical layer downstream of Gold Parquet data.
--
-- Design principles:
-- - Preserve historical observations (not just latest state)
-- - Keep source identity distinct from canonical product identity
-- - Use NUMERIC for money (not binary floating point)
-- - Use TIMESTAMPTZ for timezone-aware timestamps
-- - Support queries for latest observation, price changes, rolling calculations,
--   product history, and source statistics
-- - No speculative entities or performance indexes beyond constraints

BEGIN;

-- ---------------------------------------------------------------------------
-- sources
-- ---------------------------------------------------------------------------
-- Canonical registry of external data sources. Each source adapter maps to one
-- row here. This table is intentionally small and stable.

CREATE TABLE sources (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,           -- e.g. 'bestbuy', 'ebay'
    description TEXT,                           -- human-readable explanation
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE sources IS
    'Registry of external data sources feeding the platform.';

COMMENT ON COLUMN sources.name IS
    'Unique source identifier used throughout the platform (e.g. bestbuy, ebay).';


-- ---------------------------------------------------------------------------
-- products
-- ---------------------------------------------------------------------------
-- Canonical/logical product identity. One row per unique product across all
-- sources. Products are deduplicated by business rules during ingestion/processing.
-- A single logical product may have many source-specific listings.

CREATE TABLE products (
    id              BIGSERIAL PRIMARY KEY,
    canonical_name  TEXT,                       -- normalized product name
    category        TEXT,                       -- normalized category
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE products IS
    'Canonical product identity independent of source-specific listings.';

COMMENT ON COLUMN products.canonical_name IS
    'Normalized product name after deduplication across sources.';

COMMENT ON COLUMN products.category IS
    'Normalized category assigned during processing.';


-- ---------------------------------------------------------------------------
-- source_products
-- ---------------------------------------------------------------------------
-- Maps a source-specific listing (external_id) to a canonical product.
-- One canonical product can have multiple source listings; one source listing
-- maps to exactly one canonical product.

CREATE TABLE source_products (
    id              BIGSERIAL PRIMARY KEY,
    source_id       INTEGER NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
    product_id      BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    external_id     TEXT NOT NULL,              -- source-specific listing ID
    url             TEXT,                       -- source listing URL
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uk_source_external_id UNIQUE (source_id, external_id)
);

COMMENT ON TABLE source_products IS
    'Maps source-specific product listings to canonical product identity.';

COMMENT ON COLUMN source_products.external_id IS
    'Source-specific product/listing identifier (e.g. Best Buy SKU, eBay listing ID).';


-- ---------------------------------------------------------------------------
-- product_observations
-- ---------------------------------------------------------------------------
-- Historical record of every observed product listing state. Multiple rows per
-- source_product over time capture price changes, availability shifts, etc.
-- This is the core fact table for analytics.

CREATE TABLE product_observations (
    id                  BIGSERIAL PRIMARY KEY,
    source_product_id   BIGINT NOT NULL REFERENCES source_products(id) ON DELETE CASCADE,
    name                TEXT,                   -- observed name at collection time
    price               NUMERIC(12, 2),         -- exact decimal for money
    currency            TEXT,                   -- ISO 4217 currency code (USD, EUR, etc.)
    availability        TEXT NOT NULL,          -- e.g. 'in_stock', 'out_of_stock'
    collected_at        TIMESTAMPTZ NOT NULL,   -- when the observation was made at source
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),  -- when loaded into warehouse

    CONSTRAINT chk_price_non_negative CHECK (price IS NULL OR price >= 0)
);

COMMENT ON TABLE product_observations IS
    'Historical record of every observed product listing state over time.';

COMMENT ON COLUMN product_observations.price IS
    'Observed price as exact decimal (NUMERIC), not binary floating point.';

COMMENT ON COLUMN product_observations.collected_at IS
    'Timestamp when the observation was made at the source (business time).';

COMMENT ON COLUMN product_observations.ingested_at IS
    'Timestamp when the observation was loaded into the warehouse (system time).';


-- ---------------------------------------------------------------------------
-- pipeline_runs
-- ---------------------------------------------------------------------------
-- Metadata about each batch/streaming run that loads data into the warehouse.
-- Used for lineage, debugging, and freshness monitoring.

CREATE TABLE pipeline_runs (
    id              BIGSERIAL PRIMARY KEY,
    run_type        TEXT NOT NULL,              -- e.g. 'full_load', 'incremental', 'replay'
    status          TEXT NOT NULL,              -- 'running', 'success', 'failed'
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    records_loaded  BIGINT,
    error_message   TEXT,
    metadata        JSONB                       -- arbitrary run metadata (source filters, etc.)
);

COMMENT ON TABLE pipeline_runs IS
    'Metadata about each pipeline execution that loads data into the warehouse.';

COMMENT ON COLUMN pipeline_runs.run_type IS
    'Type of load: full_load, incremental, replay, etc.';

COMMENT ON COLUMN pipeline_runs.metadata IS
    'Arbitrary JSON metadata about the run (filters, configuration, etc.).';


-- ---------------------------------------------------------------------------
-- data_quality_results
-- ---------------------------------------------------------------------------
-- Results of data quality checks applied during loading. Links to specific
-- observations or runs for traceability.

CREATE TABLE data_quality_results (
    id                  BIGSERIAL PRIMARY KEY,
    pipeline_run_id     BIGINT REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    observation_id      BIGINT REFERENCES product_observations(id) ON DELETE SET NULL,
    check_name          TEXT NOT NULL,          -- e.g. 'price_null', 'duplicate_external_id'
    severity            TEXT NOT NULL,          -- 'info', 'warning', 'error'
    passed              BOOLEAN NOT NULL,
    message             TEXT,                   -- human-readable explanation
    checked_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    records_checked     BIGINT NOT NULL DEFAULT 0,
    failed_records      BIGINT NOT NULL DEFAULT 0,
    details             JSONB,                  -- check-specific diagnostic metadata
    replay_key          TEXT NOT NULL DEFAULT '',

    CONSTRAINT uk_data_quality_results_replay_key UNIQUE (replay_key)
);

COMMENT ON TABLE data_quality_results IS
    'Results of data quality checks applied during warehouse loading.';

COMMENT ON COLUMN data_quality_results.check_name IS
    'Name of the quality check (e.g. price_null, duplicate_external_id).';

COMMENT ON COLUMN data_quality_results.severity IS
    'Severity level: info, warning, or error.';

COMMENT ON COLUMN data_quality_results.replay_key IS
    'Deterministic identity key for replay-safe idempotent writes.';


COMMIT;
