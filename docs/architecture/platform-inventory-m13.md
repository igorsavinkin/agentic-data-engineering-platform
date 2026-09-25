# Platform Architecture Inventory — Milestone 13

Evidence-based snapshot of the implemented platform after completion of
Milestones M0 through M13.

**Date:** 2026-09-25
**Source of truth:** Repository code, manifests, benchmark reports, and test
artifacts — not roadmap intent or prior documentation assumptions.
**Previous inventory:** Around Milestone 6 (`docs/architecture-communication/`).

---

## Table of Contents

1. [Platform Implementation Status](#1-platform-implementation-status)
2. [Actual Runtime Data Flow](#2-actual-runtime-data-flow)
3. [Service Inventory](#3-service-inventory)
4. [Kafka Inventory](#4-kafka-inventory)
5. [Storage Inventory](#5-storage-inventory)
6. [Airflow Inventory](#6-airflow-inventory)
7. [Serving Layer](#7-serving-layer)
8. [Kubernetes and Helm](#8-kubernetes-and-helm)
9. [Observability](#9-observability)
10. [Reliability and Failure Engineering](#10-reliability-and-failure-engineering)
11. [Performance Evidence](#11-performance-evidence)
12. [Verified E2E Paths](#12-verified-e2e-paths)
13. [Runtime Reality vs Conceptual Architecture](#13-runtime-reality-vs-conceptual-architecture)
14. [Remaining Roadmap](#14-remaining-roadmap)
15. [Architecture Findings and Follow-ups](#15-architecture-findings-and-follow-ups)

---

## 1. Platform Implementation Status

### Milestone Status Matrix

| Milestone | Title | Status | Evidence |
|-----------|-------|--------|----------|
| M0 | Repository Foundation | **Implemented** | `services/`, `libs/`, `ai/`, `docker-compose.yml`, CI |
| M1 | Event Platform | **Implemented and E2E verified** | `libs/common/kafka_producer.py`, `kafka_consumer.py`, `libs/event_contracts/`, integration tests |
| M2 | Processing Pipeline | **Implemented and E2E verified** | `services/processor/`, Polars transforms, validation, deduplication, DLQ |
| M3 | Data Lake | **Implemented and E2E verified** | `services/raw-writer/`, `services/lake-writer/`, Bronze/Silver Parquet on MinIO |
| M4 | PostgreSQL Warehouse | **Implemented and E2E verified** | `warehouse/`, 8 tables, 6 Alembic migrations, idempotent loader |
| M5 | E2E Vertical Slice + Sources | **Implemented and E2E verified** | 5 source adapters, `tests/test_pipeline_e2e.py`, `tests/test_ingestion_e2e.py` |
| M5A | Marketplace Source (eBay) | **Implemented** | `libs/adapters/ebay/`, marketplace identity models |
| M5B | Web Retailer Source | **Implemented** | `libs/adapters/web_retailer/`, HTML scraping |
| M5C | Difficult Source | **Implemented** | `libs/adapters/difficult_retailer/`, browser automation, tenacity retries |
| M6 | Data Quality + Airflow | **Implemented and E2E verified** | 4 DAGs, quality framework, health evaluation, compaction |
| M7 | FastAPI | **Implemented** | `services/api/`, 13+ endpoints, health/readiness, Prometheus metrics |
| M8 | Kubernetes (kind) | **Implemented** | `kubernetes/` manifests, 7 Deployments, 2 StatefulSets, 2 Jobs, probes |
| M9 | Helm | **Implemented** | `helm/ai-data-platform/`, Chart.yaml, values.yaml, all templates |
| M10 | Observability | **Implemented** | Prometheus, Grafana (3 dashboards), OpenTelemetry, Jaeger, 30+ metrics |
| M11 | LangGraph Agent | **Implemented** | `services/agent/`, 4 read-only tools, deterministic classifier, graph routing |
| M12 | Failure Engineering | **Implemented and tested** | `tests/test_failure_replay.py`, `tests/test_duplicate_replay.py`, recovery docs |
| M13 | Performance Testing | **Implemented and measured** | `scripts/run_load_test.py`, 3 benchmark reports, TASK-108–115 artifacts |
| M14 | Terraform / AWS | **Planned / target only** | No terraform/ directory exists |
| M15 | Production Polish | **Planned / target only** | Not started |

### Classification Legend

- **Implemented**: Code exists and passes tests.
- **Implemented and E2E verified**: End-to-end test or runtime demonstration exists.
- **Implemented and measured**: Performance benchmark with recorded results exists.
- **Planned / target only**: Specified in roadmap but no implementation exists.

---

## 2. Actual Runtime Data Flow

### Implemented Data Path

```
External Sources (5 adapters)
    |
    v
[INGESTION] ─── publish ──> products.raw.v1
    |                              |
    |                         +----+----+
    |                         |         |
    |                         v         v
    |                   [RAW WRITER]  [PROCESSOR]
    |                         |         |
    |                         v    +----+----+
    |                   [Bronze]   |         |
    |                   (MinIO)    v         v
    |                   [PROCESSOR]  products.validated.v1  products.invalid.v1
    |                                              |
    |                                              v
    |                                        [LAKE WRITER]
    |                                              |
    |                                              v
    |                                        [Silver]
    |                                        (MinIO)
    |                                              |
    |                                              v
    |                                   [WAREHOUSE LOADER]
    |                                    (reads Silver Parquet,
    |                                     periodic 300s loop)
    |                                              |
    |                                              v
    |                                      [PostgreSQL]
    |                                     (8 tables, base +
    |                                      analytical via Airflow)
    |                                              |
    |                         +--------------------+--------------------+
    |                         |                    |                    |
    |                         v                    v                    v
    |                   [FastAPI]          [LangGraph Agent]    [Airflow DAGs]
    |                  (read-only SQL)     (read-only SQL,      (quality, metrics,
    |                                        4 tools)            health, compaction)
    |
    v
[Prometheus / Grafana / OpenTelemetry / Jaeger] — observe all services
```

### Key Differences from Conceptual Architecture

The conceptual architecture in `ai/PROJECT.md` Section 3 shows:

> Silver Parquet -> Airflow batch transformations -> Gold Parquet -> Warehouse Loader -> PostgreSQL

The **actual implementation** differs:

1. **Warehouse Loader reads Silver directly**, not Gold Parquet. It loads raw
   observation data into PostgreSQL base tables (`product_observations`,
   `sources`, `products`, `source_products`).

2. **Airflow operates on PostgreSQL**, not on Silver/Gold Parquet (except
   `parquet_compaction` which operates on Bronze). Airflow DAGs read from
   PostgreSQL and write analytical results back to PostgreSQL tables
   (`daily_metrics`, `data_quality_results`, `ingestion_health_results`).

3. **Gold exists only as PostgreSQL tables**, not as Parquet files. There is no
   Gold Parquet layer on MinIO/S3.

Evidence:
- Warehouse Loader: `services/warehouse-loader/runner.py` reads Silver via
  `LakeReader` with `PartitionFilter(layer=LakeLayer.SILVER)`
- Airflow DAGs: `airflow/dags/daily_data_quality_dag.py` queries PostgreSQL
  `product_observations` table
- No Gold bucket exists in `libs/common/minio_storage.py` — only `bronze` and
  `silver` buckets are configured

---

## 3. Service Inventory

### 3.1 Ingestion Service

| Attribute | Value |
|-----------|-------|
| **Path** | `services/ingestion/` |
| **Entry point** | `python -m services.ingestion` |
| **Inputs** | 5 source adapters (FakeStore, BestBuy, eBay, web_retailer, difficult_retailer) |
| **Outputs** | `products.raw.v1` Kafka topic |
| **Owned data** | None (stateless publisher) |
| **External dependencies** | Source APIs (REST, OAuth, HTTP/HTML, browser automation) |
| **Kafka** | Producer only; `products.raw.v1`; partition key `source:external_id` |
| **Deployment** | Kubernetes Deployment; Helm template `deployments/ingestion.yaml` |
| **Metrics port** | 9100 (`/metrics`) |
| **Probes** | Liveness: PID 1 check; Readiness: Kafka socket connect |

Evidence: `services/ingestion/__main__.py`, `services/ingestion/runner.py`,
`libs/adapters/`

### 3.2 Processor Service

| Attribute | Value |
|-----------|-------|
| **Path** | `services/processor/` |
| **Entry point** | `python -m services.processor` |
| **Inputs** | `products.raw.v1` (consumer group: `processor`) |
| **Outputs** | `products.validated.v1` (valid), `products.invalid.v1` (DLQ) |
| **Owned data** | In-memory deduplication state (cross-batch `event_id -> payload_hash`) |
| **External dependencies** | Kafka |
| **Kafka** | Consumer group `processor`; produces to `products.validated.v1` and `products.invalid.v1` |
| **Processing pipeline** | `events_to_polars()` -> `normalize()` -> `validate()` -> `deduplicate()` |
| **Deployment** | Kubernetes Deployment |
| **Metrics port** | 9100 |
| **Probes** | Liveness: PID 1; Readiness: Kafka socket |

Evidence: `services/processor/__main__.py`, `services/processor/pipeline.py`

### 3.3 Raw Writer Service

| Attribute | Value |
|-----------|-------|
| **Path** | `services/raw-writer/` |
| **Entry point** | `python -m services.raw-writer.consumer` |
| **Inputs** | `products.raw.v1` (consumer group: `raw-writer`) |
| **Outputs** | Bronze Parquet files on MinIO |
| **Owned data** | Bronze layer (`bronze/source=<s>/year=.../month=.../day=.../<event_id>.parquet`) |
| **External dependencies** | Kafka, MinIO/S3 |
| **Kafka** | Consumer group `raw-writer`; independent offsets from processor |
| **Idempotency** | Deterministic object keys by `event_id`; offset committed after write |
| **DLQ** | Fail-closed: raises RuntimeError on DLQ failure, refuses offset commit |
| **Deployment** | Kubernetes Deployment |

Evidence: `services/raw-writer/consumer.py`, `libs/raw_writer/bronze_writer.py`

### 3.4 Lake Writer Service

| Attribute | Value |
|-----------|-------|
| **Path** | `services/lake-writer/` |
| **Entry point** | `python -m services.lake-writer.consumer` |
| **Inputs** | `products.validated.v1` (consumer group: `lake-writer`) |
| **Outputs** | Silver Parquet files on MinIO |
| **Owned data** | Silver layer (`silver/source=<s>/year=.../month=.../day=.../<event_id>.parquet`) |
| **External dependencies** | Kafka, MinIO/S3 |
| **Kafka** | Consumer group `lake-writer` |
| **Idempotency** | Same deterministic key strategy as Raw Writer |
| **Deployment** | Kubernetes Deployment |

Evidence: `services/lake-writer/consumer.py`, `libs/lake_writer/silver_writer.py`

### 3.5 Warehouse Loader Service

| Attribute | Value |
|-----------|-------|
| **Path** | `services/warehouse-loader/` |
| **Entry point** | `python -m services.warehouse-loader.runner` |
| **Inputs** | Silver Parquet files from MinIO (via `LakeReader`) |
| **Outputs** | PostgreSQL tables: `sources`, `products`, `source_products`, `product_observations` |
| **Owned data** | PostgreSQL base tables (write owner) |
| **External dependencies** | MinIO/S3, PostgreSQL |
| **Kafka** | None — reads from object storage, not Kafka |
| **Idempotency** | `INSERT ... ON CONFLICT (event_id) DO NOTHING`; conflicting payloads raise `ValueError` |
| **Interval** | Configurable, default 300 seconds |
| **Deployment** | Kubernetes Deployment |

Evidence: `services/warehouse-loader/runner.py`, `warehouse/loader/batch_loader.py`

### 3.6 API Service (FastAPI)

| Attribute | Value |
|-----------|-------|
| **Path** | `services/api/` |
| **Entry point** | `python -m services.api` |
| **Inputs** | HTTP requests; PostgreSQL queries |
| **Outputs** | JSON API responses; Prometheus metrics |
| **Owned data** | None (read-only) |
| **External dependencies** | PostgreSQL |
| **Kafka** | None |
| **Port** | 8000 |
| **Probes** | Liveness: `GET /api/v1/health`; Readiness: `GET /api/v1/ready` (checks DB via `SELECT 1`) |
| **Deployment** | Kubernetes Deployment + Service (ClusterIP:8000) |

Evidence: `services/api/app.py`, `services/api/routes/v1/router.py`

### 3.7 Agent (LangGraph Data Engineer Agent)

| Attribute | Value |
|-----------|-------|
| **Path** | `services/agent/` |
| **Entry point** | `POST /api/v1/agent/ask` (invoked via API service) |
| **Inputs** | Natural-language question string |
| **Outputs** | Structured response: answer, intent, confidence, sources |
| **Owned data** | None (read-only) |
| **External dependencies** | PostgreSQL (via API service process) |
| **Kafka** | None |
| **Read-only enforcement** | Connection-level `SET TRANSACTION READ ONLY` + query-level keyword validation |
| **Tools** | `get_dataset_metadata`, `get_pipeline_status`, `get_data_quality`, `get_source_health` |

Evidence: `services/agent/graph.py`, `services/agent/tools.py`,
`services/agent/db_adapter.py`, `services/api/routes/v1/agent.py`

---

## 4. Kafka Inventory

### 4.1 Topics

| Topic | Partitions | Replication | Retention | Partition Key | Purpose |
|-------|-----------|-------------|-----------|---------------|---------|
| `products.raw.v1` | 3 | 1 | 7 days | `source:external_id` | Canonical observations from ingestion |
| `products.validated.v1` | 3 | 1 | 7 days | `source:external_id` | Validated/normalized events |
| `products.invalid.v1` | 1 | 1 | 7 days | None (round-robin) | DLQ — invalid/dead-letter events |
| `pipeline.events.v1` | 1 | 1 | 3 days | None | Pipeline lifecycle events |
| `data-quality.events.v1` | 1 | 1 | 3 days | None | Data quality check results |

**Naming convention:** `{domain}.{status/purpose}.v{version}`
**Auto-create:** Disabled (`KAFKA_AUTO_CREATE_TOPICS_ENABLE: "false"`)
**Topic creation:** `scripts/manage_kafka_topics.py` (idempotent, `--if-not-exists`)

Evidence: `docs/adr/ADR-001-kafka-topic-configuration.md`,
`scripts/manage_kafka_topics.py`,
`kubernetes/deployments/kafka-topics-job.yaml`

### 4.2 Consumer Groups

| Consumer Group | Service | Topic | Offset Independence |
|---------------|---------|-------|-------------------|
| `processor` | Processor | `products.raw.v1` | Independent |
| `raw-writer` | Raw Writer | `products.raw.v1` | Independent |
| `lake-writer` | Lake Writer | `products.validated.v1` | Independent |

Both `processor` and `raw-writer` consume `products.raw.v1` with separate
consumer groups, maintaining independent offsets.

### 4.3 Producers

| Producer | Service | Topics Written |
|----------|---------|---------------|
| `KafkaEventProducer` | Ingestion | `products.raw.v1` |
| `KafkaValidatedOutputProducer` | Processor | `products.validated.v1` |
| `KafkaDeadLetterProducer` | Processor | `products.invalid.v1` |
| Load test harness | Load test | `products.raw.v1` |

### 4.4 Delivery Semantics

- **At-least-once** with idempotent processing
- Offsets committed ONLY after successful processing and output publication
- Crash before commit causes redelivery on restart
- Kafka producer: `enable.idempotence: true`, `acks: all`
- No exactly-once semantics claimed

Evidence: `libs/common/kafka_consumer.py`, `libs/common/kafka_producer.py`

### 4.5 DLQ Behavior

| Service | DLQ Mechanism | Behavior |
|---------|--------------|----------|
| Processor | `KafkaDeadLetterProducer` -> `products.invalid.v1` | Publishes diagnostic envelope (base64 raw, error type, attempts, consumer group); commits offset after DLQ publish |
| Raw Writer | Fail-closed sink | Raises RuntimeError; does NOT commit offset; message redelivered |
| Lake Writer | Fail-closed sink | Same as Raw Writer |

Diagnostic envelope includes deterministic `event_id` (UUID5 from
`[group_id, topic, partition, offset]`), `raw_value_base64`, `error_type`,
`validation_errors`, `attempts`.

Evidence: `libs/common/kafka_errors.py`

### 4.6 Lag Monitoring

Consumer lag is exposed as a Prometheus gauge:
- Metric: `kafka_consumer_lag{service, topic, partition}`
- Implementation: `libs/observability/kafka_metrics.py`
- Dashboard: `monitoring/grafana/dashboards/kafka-processing.json`

Evidence: `libs/observability/kafka_metrics.py`

---

## 5. Storage Inventory

### 5.1 Bronze Layer

| Attribute | Value |
|-----------|-------|
| **Technology** | Apache Parquet on MinIO (locally) / S3 (AWS target) |
| **Bucket** | `bronze` |
| **Owner** | Raw Writer service |
| **Path layout** | `bronze/source=<source>/year=<YYYY>/month=<MM>/day=<DD>/<event_id>.parquet` |
| **Content** | Raw/minimally transformed canonical events |
| **Idempotency** | Deterministic object key by `event_id`; replay overwrites |
| **Compaction** | Airflow `parquet_compaction` DAG merges small files |

Evidence: `libs/raw_writer/bronze_writer.py`, `libs/common/minio_storage.py`

### 5.2 Silver Layer

| Attribute | Value |
|-----------|-------|
| **Technology** | Apache Parquet on MinIO / S3 |
| **Bucket** | `silver` |
| **Owner** | Lake Writer service |
| **Path layout** | `silver/source=<source>/year=<YYYY>/month=<MM>/day=<DD>/<event_id>.parquet` |
| **Content** | Validated, normalized, deduplicated events |
| **Idempotency** | Same deterministic key strategy as Bronze |

Evidence: `libs/lake_writer/silver_writer.py`

### 5.3 Gold Layer

**Gold does not exist as Parquet files.** Gold exists exclusively as PostgreSQL
analytical tables populated by Airflow DAGs.

| Table | Populated By | Content |
|-------|-------------|---------|
| `daily_metrics` | `build_daily_metrics` DAG | Per-date analytical aggregates |
| `data_quality_results` | `daily_data_quality` DAG | Quality check results |
| `ingestion_health_results` | `ingestion_health` DAG | Source health assessments |

Evidence: `airflow/dags/build_daily_metrics_dag.py`,
`airflow/dags/daily_data_quality_dag.py`,
`airflow/dags/ingestion_health_dag.py`

### 5.4 PostgreSQL Base Tables

| Table | Migration | Purpose | Writer |
|-------|-----------|---------|--------|
| `sources` | 001 | Registry of external data sources | Warehouse Loader |
| `products` | 001 | Canonical product identity | Warehouse Loader |
| `source_products` | 001 | Source-to-product mapping | Warehouse Loader |
| `product_observations` | 001, 002 | Historical fact table (UNIQUE on `event_id`) | Warehouse Loader |
| `pipeline_runs` | 001 | Pipeline execution metadata | Ingestion/Processor |

### 5.5 PostgreSQL Analytical Tables

| Table | Migration | Purpose | Writer |
|-------|-----------|---------|--------|
| `data_quality_results` | 001, 004 | Quality check results with JSONB details | Airflow `daily_data_quality` |
| `ingestion_health_results` | 005 | Source health assessments | Airflow `ingestion_health` |
| `daily_metrics` | 006 | Daily analytical aggregates | Airflow `build_daily_metrics` |

**Total: 8 tables, 6 Alembic migrations** (chain: `None -> 001 -> 002 -> 003 -> 004 -> 005 -> 006`)

Evidence: `warehouse/migrations/versions/`, `warehouse/schema/init.sql`

---

## 6. Airflow Inventory

### 6.1 Implemented DAGs

| DAG ID | Schedule | Input | Operation | Output |
|--------|----------|-------|-----------|--------|
| `ingestion_health` | Every 15 min | PostgreSQL `sources`, `source_products`, `product_observations` | Evaluates source freshness, health, degradation | `ingestion_health_results` table |
| `daily_data_quality` | Every 24 h | PostgreSQL `product_observations` (last 24h, up to 100K rows) | Runs 4 quality checks (required_fields, price_validity, freshness, duplicates) via Polars | `data_quality_results` table |
| `parquet_compaction` | Every 6 h | MinIO Bronze Parquet files | Merges partitions with >= 5 files into single compacted file; validates record count | Compacted Bronze Parquet (old files deleted after validation) |
| `build_daily_metrics` | Every 24 h | PostgreSQL `product_observations` (one day) | Computes per-source daily analytical aggregates | `daily_metrics` table |

### 6.2 Airflow Role Clarification

Airflow is **not** a mandatory linear stage in the data pipeline. The actual
data path does not pass through Airflow:

- **Warehouse Loader** reads Silver Parquet and writes PostgreSQL base tables
  directly, without Airflow involvement.
- **Airflow** reads from PostgreSQL base tables and writes analytical/metadata
  tables back to PostgreSQL.
- **Airflow** also compacts Bronze Parquet files on MinIO.

Airflow is a **scheduled batch processor** that operates on already-loaded
data, not a pipeline stage between Silver and PostgreSQL.

All DAGs use `retries=2`, `retry_delay=5 minutes`. All use deterministic
`replay_key` with `ON CONFLICT DO NOTHING` for idempotency.

Evidence: `airflow/dags/ingestion_health_dag.py`,
`airflow/dags/daily_data_quality_dag.py`,
`airflow/dags/parquet_compaction_dag.py`,
`airflow/dags/build_daily_metrics_dag.py`

---

## 7. Serving Layer

### 7.1 FastAPI

**Path:** `services/api/`
**Port:** 8000
**Database:** PostgreSQL (read-only via SQLAlchemy ORM with psycopg2)

#### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | Liveness probe (always 200) |
| `GET` | `/api/v1/ready` | Readiness probe (checks DB via `SELECT 1`; 503 if unavailable) |
| `GET` | `/api/v1/products` | Paginated product list |
| `GET` | `/api/v1/products/{id}` | Product detail |
| `GET` | `/api/v1/products/{id}/history` | Historical observations |
| `GET` | `/api/v1/analytics/price-changes` | Price changes with LAG deltas |
| `GET` | `/api/v1/analytics/price-movers` | Top products by price change |
| `GET` | `/api/v1/analytics/price-statistics` | Per-source aggregate stats |
| `GET` | `/api/v1/pipelines` | Pipeline run history |
| `GET` | `/api/v1/pipelines/source-health` | Source health assessments |
| `GET` | `/api/v1/quality` | Data quality check results |
| `GET` | `/api/v1/quality/summary` | Aggregate quality summary |
| `POST` | `/api/v1/agent/ask` | Natural-language agent queries |
| `GET` | `/api/v1/metrics` | Prometheus scrape endpoint |

#### Database Tables Accessed

`sources`, `products`, `source_products`, `product_observations`,
`pipeline_runs`, `ingestion_health_results`, `data_quality_results`

Evidence: `services/api/routes/v1/router.py`, `services/api/app.py`,
`services/api/models.py`

### 7.2 LangGraph Agent

**Path:** `services/agent/`
**Access:** Via `POST /api/v1/agent/ask` in the API service (not a separate deployment)

#### Graph Flow

```
START -> classify -> [conditional edges] -> compose -> END
                        |
           +------------+----------------+--------------+
           |            |                |              |
           v            v                v              v
      execute_sql  pipeline_status  data_quality  source_health
           |
           v
       fallback
```

#### Intent Classification

| Intent | Tool | Description |
|--------|------|-------------|
| `PRICE_ANALYTICS` | `execute_sql` | Dataset metadata, SQL generation |
| `PRODUCT_HISTORY` | `execute_sql` | Dataset metadata, SQL generation |
| `PIPELINE_STATUS` | `pipeline_status` | Recent runs, consumer lag, alerts |
| `DATA_QUALITY` | `data_quality` | Check results, pass rates, trends |
| `SOURCE_HEALTH` | `source_health` | Per-source freshness, degradation |
| `GENERAL` | `fallback` | No tool match; static response |

#### Read-Only Guarantees

1. **Connection-level:** `SET TRANSACTION READ ONLY` + `default_transaction_read_only=on`
2. **Query-level:** Keyword validation blocks INSERT, UPDATE, DELETE, DROP,
   CREATE, ALTER, TRUNCATE, and side-effecting functions (setval, nextval,
   pg_notify, etc.)
3. **Classifier:** Deterministic keyword-based (no LLM calls); regex matching
   with confidence scoring

Evidence: `services/agent/graph.py`, `services/agent/intents.py`,
`services/agent/classifier.py`, `services/agent/db_adapter.py`,
`services/agent/tools.py`

---

## 8. Kubernetes and Helm

### 8.1 Namespace

`ai-data-platform` — defined in `kubernetes/namespaces/platform-namespace.yaml`
and Helm template `templates/namespace.yaml`

### 8.2 Deployments (7 application + 2 monitoring)

| Deployment | Image | Port | Command |
|-----------|-------|------|---------|
| `ingestion` | `ai-data-platform/ingestion:dev` | 9100 (metrics) | `python -m services.ingestion` |
| `processor` | `ai-data-platform/processor:dev` | 9100 | `python -m services.processor` |
| `raw-writer` | `ai-data-platform/raw-writer:dev` | 9100 | `python -m services.raw-writer.consumer` |
| `lake-writer` | `ai-data-platform/lake-writer:dev` | 9100 | `python -m services.lake-writer.consumer` |
| `warehouse-loader` | `ai-data-platform/warehouse-loader:dev` | 9100 | `python -m services.warehouse-loader.runner` |
| `api` | `ai-data-platform/api:dev` | 8000 | `python -m services.api` |
| `kafka` | `apache/kafka:4.3.1` | 29092, 9092 | KRaft combined broker+controller |
| `prometheus` | `prom/prometheus:v3.1.0` | 9090 | Conditional: `prometheus.enabled` |
| `grafana` | `grafana/grafana:11.4.0` | 3000 | Conditional: `grafana.enabled` |

### 8.3 StatefulSets (2)

| StatefulSet | Image | Storage |
|------------|-------|---------|
| `postgresql` | `postgres:16` | 1Gi PVC |
| `minio` | `minio/minio:RELEASE.2025-09-07T16-13-09Z` | 1Gi PVC |

### 8.4 Services

| Service | Type | Ports |
|---------|------|-------|
| `api` | ClusterIP | 8000 |
| `kafka` | NodePort | 29092 (internal), 9092->30092 (external) |
| `minio` | ClusterIP | 9000 (API), 9001 (console) |
| `postgresql` | ClusterIP | 5432 |
| `prometheus` | ClusterIP | 9090 |
| `grafana` | ClusterIP | 3000 |

### 8.5 ConfigMaps

| ConfigMap | Keys |
|-----------|------|
| `platform-config` | `APP_ENVIRONMENT`, `APP_KAFKA_BOOTSTRAP_SERVERS`, `APP_MINIO_ENDPOINT` |
| `database-config` | `WAREHOUSE_DB_HOST`, `WAREHOUSE_DB_PORT`, `WAREHOUSE_DB_NAME`, `WAREHOUSE_DB_USER` |
| `prometheus-config` | `prometheus.yml` (scrape configs) |
| `grafana-provisioning` | `datasources.yml`, `dashboards.yml` |
| `grafana-dashboards` | Auto-includes all `dashboards/*.json` |

### 8.6 Secrets

| Secret | Keys |
|--------|------|
| `database-credentials` | `db-password` |
| `ingestion-api-keys` | `bestbuy-api-key` |
| `minio-credentials` | `minio-access-key`, `minio-secret-key` |
| `grafana-credentials` | `admin-user`, `admin-password` (conditional) |

### 8.7 Jobs

| Job | Purpose | Helm Hook |
|-----|---------|-----------|
| `kafka-topics-setup` | Creates 5 Kafka topics idempotently | None |
| `warehouse-migration` | Runs Alembic `upgrade head` | `post-install,pre-upgrade` with `before-hook-creation` delete policy |

### 8.8 Optional Resources

| Resource | Condition | Details |
|----------|-----------|---------|
| HorizontalPodAutoscaler | `hpa.enabled` | API deployment; min 1, max 5, CPU 80% |
| Ingress | `ingress.enabled` | API service |
| NetworkPolicy | `networkPolicy.enabled` | Default deny |

### 8.9 Helm Chart Structure

```
helm/ai-data-platform/
  Chart.yaml              (name: ai-data-platform, version: 0.1.0)
  values.yaml             (517 lines, all knobs)
  values-local.yaml       (kind/local dev overrides)
  values-production.yaml  (HPA, Ingress, NetworkPolicy, pinned tags)
  dashboards/             (3 Grafana dashboard JSON files)
  templates/
    _helpers.tpl
    namespace.yaml
    hpa.yaml
    ingress.yaml
    networkpolicy.yaml
    configmaps/           (database-config, platform-config)
    secrets/              (database-credentials, ingestion-api-keys, minio-credentials)
    deployments/          (api, ingestion, kafka, lake-writer, processor, raw-writer, warehouse-loader)
    services/             (api, kafka, minio, postgresql)
    statefulsets/         (minio, postgresql)
    jobs/                 (kafka-topics, warehouse-migration)
    monitoring/           (Prometheus and Grafana resources)
```

### 8.10 Local kind Configuration

- Cluster: `kind-ai-data-platform`
- Config: `kubernetes/kind/kind-config.yaml`
- Kafka exposed via NodePort 30092 on host

Evidence: `kubernetes/`, `helm/ai-data-platform/`

---

## 9. Observability

### 9.1 Prometheus

- **Image:** `prom/prometheus:v3.1.0`
- **Retention:** 7 days (configurable)
- **Scrape interval:** 15 seconds
- **Scrape targets:**
  - API service: `GET /api/v1/metrics` on port 8000
  - Background services: `GET /metrics` on port 9100
- **Service discovery:** Kubernetes pod role (in-cluster); static config (Docker Compose)
- **Health probes:** `/-/healthy` (liveness), `/-/ready` (readiness)

Evidence: `helm/ai-data-platform/templates/monitoring/prometheus-configmap.yaml`,
`monitoring/prometheus.yml`

### 9.2 Grafana

- **Image:** `grafana/grafana:11.4.0`
- **Port:** 3000
- **Datasources:** Prometheus (`http://prometheus:9090`), Jaeger (`http://jaeger:16686`)
- **Dashboards (3):**

| Dashboard | UID | Panels |
|-----------|-----|--------|
| Platform Overview | `ai-data-platform-overview` | 11 panels: service availability, event rates, error rates, processor latency/throughput, API request rate/latency, source freshness, ingestion events |
| Kafka Processing | `ai-data-platform-kafka` | 12 panels: consumer throughput, consumer lag, error rates, DLQ rate, processor pipeline health |
| Data Quality | `ai-data-platform-data-quality` | 12 panels: validation pass rate, freshness, invalid/dedup/failure rates, source metrics |

Evidence: `monitoring/grafana/dashboards/`,
`helm/ai-data-platform/dashboards/`

### 9.3 OpenTelemetry

- **Collector:** `otel/opentelemetry-collector-contrib:0.115.1`
  - Receivers: OTLP gRPC (:4317), OTLP HTTP (:4318)
  - Processors: `batch` (5s timeout, 100 batch size), `memory_limiter` (256MiB)
  - Exporters: `debug`, `otlp/jaeger` (jaeger:4317)
- **Backend:** `jaegertracing/all-in-one:1.62` (UI at :16686)
- **Propagation:** W3C Trace Context via Kafka message headers

#### Active Span Instrumentation

| Service | Span Name | File |
|---------|-----------|------|
| ingestion | `ingestion.publish` | `services/ingestion/runner.py` |
| processor | `processor.process_batch` | `services/processor/__main__.py` |
| raw-writer | `raw-writer.process_message` | `services/raw-writer/consumer.py` |
| lake-writer | `lake-writer.process_message` | `services/lake-writer/consumer.py` |

Evidence: `libs/observability/otel_config.py`,
`monitoring/otel-collector-config.yaml`

### 9.4 Application Metrics

#### Kafka Metrics (`libs/observability/kafka_metrics.py`)

| Type | Name | Description |
|------|------|-------------|
| Counter | `ingestion_events_total` | Canonical publish confirmations |
| Counter | `ingestion_errors_total` | Failed publish calls |
| Counter | `kafka_events_consumed_total` | Non-error Kafka records fetched |
| Counter | `kafka_events_processed_total` | Successfully processed and committed |
| Counter | `events_invalid_total` | Records rejected by validation |
| Counter | `kafka_consumer_errors_total` | Kafka poll/commit/close errors |
| Counter | `kafka_processing_errors_total` | Failed handler attempts |
| Counter | `kafka_dead_letter_events_total` | Records sent to DLQ |
| Counter | `kafka_lag_errors_total` | Failed lag queries |
| Gauge | `kafka_consumer_lag` | Consumer group lag by topic/partition |

#### Processor Metrics (`libs/observability/processor_metrics.py`)

| Type | Name | Description |
|------|------|-------------|
| Counter | `processor_events_processed_total` | Records completing processing chain |
| Counter | `processor_events_valid_total` | Published to `products.validated.v1` |
| Counter | `processor_events_invalid_total` | Published to `products.invalid.v1` |
| Counter | `processor_events_duplicate_total` | Exact duplicates skipped |
| Counter | `processor_events_failed_total` | Processing chain failures |
| Counter | `processor_batches_total` | Non-empty batches |
| Counter | `processor_batch_records_total` | Cumulative record count |
| Summary | `processor_processing_seconds` | Batch processing duration |

#### Source Metrics (`libs/observability/source_metrics.py`)

| Type | Name | Description |
|------|------|-------------|
| Counter | `source_fetch_attempts_total` | Fetch attempts |
| Counter | `source_fetch_success_total` | Successful fetches |
| Counter | `source_fetch_failure_total` | Failed fetches |
| Counter | `source_records_collected_total` | Records collected |
| Counter | `source_records_emitted_total` | Valid canonical events emitted |
| Counter | `source_zero_record_fetches_total` | Zero-record fetches |
| Counter | `source_pages_fetched_total` | Pages fetched |
| Counter | `source_retry_attempts_total` | Retry attempts |
| Counter | `source_malformed_records_total` | Malformed records |
| Counter | `source_partial_failures_total` | Partial failures |
| Summary | `source_fetch_latency_seconds` | Fetch latency |
| Gauge | `source_freshness_age_seconds` | Seconds since last successful fetch |

#### API Metrics (`services/api/routes/v1/metrics.py`)

| Type | Name | Labels | Description |
|------|------|--------|-------------|
| Counter | `api_requests_total` | method, endpoint, status | HTTP request count |
| Summary | `api_request_duration_seconds` | method, endpoint | Request latency |

### 9.5 Implemented vs Deployed/Verified

**Implemented instrumentation:** All services emit metrics on port 9100
(background) or port 8000 (API). OTel tracing spans are created in 4 services.
Prometheus scrape configs target both ports.

**Deployed monitoring:** Prometheus and Grafana are deployed as part of the
Helm chart (conditional on `prometheus.enabled` / `grafana.enabled`). In the
local kind deployment, monitoring is **disabled** by default
(`values-local.yaml` sets `prometheus.enabled: false`, `grafana.enabled: false`).

**Docker Compose monitoring:** Prometheus and Grafana are included in
`docker-compose.yml` and are operational in the Compose-based local dev
environment.

Evidence: `helm/ai-data-platform/values-local.yaml`,
`docker-compose.yml`, `monitoring/`

---

## 10. Reliability and Failure Engineering

### 10.1 Retries

| Component | Mechanism | Configuration |
|-----------|-----------|---------------|
| Kafka Consumer | `RetryPolicy` in `process_next()` | `max_attempts=3`, `backoff_seconds=0.25` (linear) |
| Kafka Producer | Idempotent producer config | `enable.idempotence: true`, `acks: all` |
| Ingestion Runner | Exponential backoff on `SourceFetchError` | `max_retries=3`, delays: 1s, 2s, 4s |
| Source Adapters (web) | tenacity `AsyncRetrying` | `stop_after_attempt(3)`, exponential backoff, retries on 5xx/429/timeouts |
| Difficult Retailer | tenacity with Retry-After | `max_retries=3`, respects `Retry-After` header (capped at 60s) |
| Airflow DAGs | `default_args` | `retries=2`, `retry_delay=5 minutes` |

### 10.2 Idempotency

| Component | Mechanism | Details |
|-----------|-----------|---------|
| Kafka Producer | Broker-side dedup | `enable.idempotence: true` |
| Bronze/Silver Writer | Deterministic object keys | `<event_id>.parquet`; replay overwrites |
| Processor | In-memory dedup state | Cross-batch `event_id -> payload_hash` tracking |
| Warehouse Loader | PostgreSQL UNIQUE constraint | `ON CONFLICT (event_id) DO NOTHING`; conflicting payloads raise `ValueError` |
| Airflow quality | Deterministic replay key | `check_name:pipeline_run_id:observation_id:source[:logical_date]` |
| Airflow health | Deterministic replay key | `source_name:logical_date` |
| Airflow metrics | Deterministic replay key | `metric_name:metric_date:dimension` |

### 10.3 Replay

- **Kafka offset-based:** Offsets committed only after successful processing;
  crash before commit causes redelivery (at-least-once)
- **Parquet replay:** Deterministic keys mean replaying same event overwrites
  existing file
- **Warehouse replay:** `ON CONFLICT DO NOTHING` makes re-loading a no-op
- **Compaction replay safety:** Already-compacted files (`compacted-*`)
  excluded from source set; record count validation before deletion

### 10.4 DLQ

- **Processor:** Publishes diagnostic envelope to `products.invalid.v1`;
  commits offset after DLQ publish
- **Raw Writer / Lake Writer:** Fail-closed; raises RuntimeError; does NOT
  commit offset; message redelivered on restart

### 10.5 Circuit Breakers

**No circuit breaker implementations exist.** The closest mechanisms are:
- Source degradation detection (`libs/observability/health_evaluation.py`)
- Bounded retry budgets in adapter clients
- Error isolation in `IngestionRunner` (one failing adapter does not block others)

### 10.6 Deterministic Storage Keys

Both Bronze and Silver layers use deterministic object keys based on
`event_id`:

```
<bronze|silver>/source=<source>/year=<YYYY>/month=<MM>/day=<DD>/<event_id>.parquet
```

Path segments are sanitized against directory traversal.

Evidence: `libs/partitioning/partition_key.py`,
`tests/test_failure_replay.py`, `tests/test_duplicate_replay.py`,
`tests/warehouse/test_idempotent_loader.py`

---

## 11. Performance Evidence

### 11.1 TASK-108: Load Test Harness

- **Script:** `scripts/run_load_test.py`
- **Components:** `LoadTestRunner`, `KafkaEventProducer`, `EventGenerator`, `MetricsCollector`
- **Auto-scaling:** `ceil(target_rate / 50 * 1.5)` effective workers
- **Execution:** In-cluster inside `ingestion` pod (Linux)

### 11.2 TASK-109: 100 events/sec Target

| Metric | Value |
|--------|-------|
| **Configured target** | 100 events/sec |
| **Actual throughput** | **95.55 events/sec** (Linux in-cluster, 3 effective workers) |
| Events produced | 5,734 |
| Producer errors | 0 |
| Mean produce latency | 5.142 ms |
| p50 latency | 2.767 ms |
| p99 latency | 47.626 ms |
| Peak RSS | 59.8 MB |
| **% of target** | **95.6%** |

Original Windows run: 18.86 eps (single-worker limitation). Linux in-cluster
verification with 3 effective workers achieved 95.55 eps.

### 11.3 TASK-110: 500 events/sec Target

| Metric | Value |
|--------|-------|
| **Configured target** | 500 events/sec |
| **Actual throughput** | **305.88 events/sec** (Linux in-cluster, 15 effective workers) |
| Events produced | 18,382 |
| Producer errors | 0 |
| Mean produce latency | 48.383 ms |
| p50 latency | 45.138 ms |
| p99 latency | 141.851 ms |
| Peak RSS | 62.5 MB |
| **% of target** | **61.2%** |

### 11.4 TASK-111: 1000 events/sec Target

| Metric | Value |
|--------|-------|
| **Configured target** | 1000 events/sec |
| **Actual throughput** | **333.43 events/sec** (Linux in-cluster, 30 effective workers) |
| Events produced | 20,040 |
| Producer errors | 0 |
| Mean produce latency | 89.494 ms |
| p50 latency | 81.829 ms |
| p99 latency | 255.885 ms |
| Peak RSS | 62.2 MB |
| **% of target** | **33.3%** |

### 11.5 Throughput Progression

| Benchmark | Target | Actual | % of Target | Effective Workers |
|-----------|--------|--------|-------------|------------------|
| TASK-109 | 100 eps | 95.55 eps | 95.6% | 3 |
| TASK-110 | 500 eps | 305.88 eps | 61.2% | 15 |
| TASK-111 | 1000 eps | 333.43 eps | 33.3% | 30 |

### 11.6 TASK-112: Kafka Consumer Lag

Consumer lag is instrumented as a Prometheus gauge
(`kafka_consumer_lag{service, topic, partition}`). The metric is defined and
exposed but dedicated lag measurement under load was scoped to TASK-112 as a
separate measurement from the producer-side benchmarks.

### 11.7 TASK-113: Processing Latency

Processor latency is instrumented via `processor_processing_seconds` summary
metric. End-to-end processing latency (produce-to-PostgreSQL) was not measured
as a single metric; each stage has its own instrumentation.

### 11.8 TASK-114: API Latency

API latency is instrumented via `api_request_duration_seconds` summary metric
with method and endpoint labels. Dedicated API latency benchmark under load was
scoped to TASK-114.

### 11.9 TASK-115: Bottleneck Documentation

**Observed bottleneck:** The synchronous produce-wait loop in the load
generator limits throughput. When per-worker producer-call duration exceeds
the pacing interval, workers are fully occupied and throughput plateaus.

At 100 eps: mean producer-call 5.1 ms vs 30 ms pacing interval — within budget.
At 500 eps: mean producer-call 48.4 ms vs 30 ms pacing interval — exceeds budget.
At 1000 eps: mean producer-call 89.5 ms vs 30 ms pacing interval — far exceeds budget.

The producer-call duration increases with concurrent worker count, suggesting
producer lock contention or broker-side queueing under higher in-flight
message volume. The root cause was not independently isolated by TASK-115.

**Important:** These are **load-generator-side** constraints. They do not
establish the maximum capacity of Kafka or the downstream pipeline.

Evidence: `docs/benchmark-100-eps.md`, `docs/benchmark-500-eps.md`,
`docs/benchmark-1000-eps.md`

---

## 12. Verified E2E Paths

### 12.1 Implementation vs Verification Matrix

| Path | Implemented | Unit Tested | Integration Tested | E2E Verified | Performance Measured |
|------|:-----------:|:-----------:|:-----------------:|:------------:|:-------------------:|
| Source -> Kafka | Yes | Yes | Yes | Yes | Yes (producer-side) |
| Kafka -> Processor -> validated topic | Yes | Yes | Yes | Yes | No |
| Kafka -> Raw Writer -> Bronze | Yes | Yes | Yes | Yes | No |
| Processor -> Lake Writer -> Silver | Yes | Yes | Yes | Yes | No |
| Silver -> Warehouse Loader -> PostgreSQL | Yes | Yes | Yes | Yes | No |
| PostgreSQL -> FastAPI -> HTTP response | Yes | Yes | Yes | Yes | Instrumented only |
| FastAPI -> Agent -> read-only SQL | Yes | Yes | Yes | Yes | No |
| Airflow -> quality/health/metrics | Yes | Yes | N/A | Partial | No |
| Full pipeline: Source -> API response | Yes | Yes | Yes | Yes | No |
| Full pipeline under load (100 eps) | Yes | N/A | N/A | No | Yes (producer-side) |
| Full pipeline under load (500 eps) | Yes | N/A | N/A | No | Yes (producer-side) |
| Full pipeline under load (1000 eps) | Yes | N/A | N/A | No | Yes (producer-side) |

### 12.2 E2E Test Evidence

| Test | File | What It Verifies |
|------|------|-----------------|
| Pipeline E2E | `tests/test_pipeline_e2e.py` | Both sources through adapter -> Kafka -> processor -> validated topic; stable identifiers; error isolation; invalid DLQ path |
| Ingestion E2E | `tests/test_ingestion_e2e.py` | Adapter -> Kafka for both sources; unified downstream; error isolation; malformed handling |
| Agent E2E | `tests/agent/test_agent_e2e.py` | Full graph pipeline for all intents; tool usage; read-only guarantee; failure handling |
| Failure replay | `tests/test_failure_replay.py` | At-least-once semantics; crash recovery; duplicate delivery; Kafka replay; transient retry; DLQ routing |
| Duplicate replay | `tests/test_duplicate_replay.py` | Integration with real Kafka+PostgreSQL; duplicate detection with metrics; Silver Parquet replay idempotency |
| Idempotent loader | `tests/warehouse/test_idempotent_loader.py` | Same batch twice; same observation in two files; conflicting duplicate detection |

### 12.3 What Is NOT E2E Verified

- **End-to-end pipeline sustainability under load**: Benchmarks measure
  producer-side throughput only. Consumer lag, downstream processing
  throughput, and end-to-end latency under load are not reconciled.
- **Airflow DAG execution against real data**: DAGs are tested in isolation
  but not demonstrated as part of a continuous E2E pipeline run.
- **Grafana dashboard rendering with real metrics**: Dashboards are defined
  but visual verification against live data in kind is not automated.
- **OpenTelemetry trace end-to-end visibility**: Spans are created in 4
  services but Jaeger trace visualization is not automated.

---

## 13. Runtime Reality vs Conceptual Architecture

### 13.1 Silver -> Warehouse Loader -> PostgreSQL

**Conceptual (PROJECT.md Section 3):**
> Silver Parquet -> Airflow batch transformations -> Gold Parquet -> Warehouse Loader -> PostgreSQL

**Actual implementation:**
Warehouse Loader reads **Silver Parquet directly** and loads PostgreSQL base
tables. Airflow is not in this path. There is no Gold Parquet intermediate.

**Evidence:** `services/warehouse-loader/runner.py` uses
`LakeReader` with `PartitionFilter(layer=LakeLayer.SILVER)`.

### 13.2 PostgreSQL -> Airflow -> Analytical/Gold Tables

**Conceptual:** Airflow owns Gold construction (reads Silver, writes Gold
Parquet).

**Actual:** Airflow reads from **PostgreSQL base tables** (not Silver Parquet)
and writes analytical results back to **PostgreSQL tables** (not Gold Parquet).
Airflow also compacts Bronze Parquet on MinIO.

**Evidence:** `airflow/dags/daily_data_quality_dag.py` queries PostgreSQL;
`airflow/dags/build_daily_metrics_dag.py` queries PostgreSQL.

### 13.3 Role of Airflow

**Conceptual:** Airflow is the Gold construction engine, sitting between
Silver Parquet and Warehouse Loader.

**Actual:** Airflow is a **scheduled batch processor** that operates on
already-loaded PostgreSQL data. It is not a mandatory pipeline stage. The
streaming path (Kafka -> Processor -> Lake Writer -> Warehouse Loader ->
PostgreSQL) functions independently of Airflow.

### 13.4 Gold Storage Semantics

**Conceptual:** Gold as Parquet files on object storage.

**Actual:** Gold exists exclusively as PostgreSQL tables: `daily_metrics`,
`data_quality_results`, `ingestion_health_results`. No Gold bucket or Gold
Parquet files exist.

### 13.5 Agent Access Boundaries

**Conceptual:** Agent uses controlled tools and read-only SQL.

**Actual:** Matches the conceptual design. Agent is invoked via the API
service (not a separate deployment). Read-only is enforced at both connection
level (`SET TRANSACTION READ ONLY`) and query level (keyword validation).
Classifier is deterministic (no LLM calls for intent classification).

### 13.6 Warehouse Loader Data Source

**Conceptual (SPECIFICATION.md Section 6.5):**
> Loads Gold Parquet into PostgreSQL

**Actual:** Loads **Silver Parquet** into PostgreSQL base tables. The
Warehouse Loader has no awareness of Gold.

---

## 14. Remaining Roadmap

### M14: Terraform / AWS (Planned / Target Only)

| Task | Description | Status |
|------|-------------|--------|
| TASK-116 | Terraform project structure | Not started |
| TASK-117 | AWS networking (VPC) | Not started |
| TASK-118 | ECR (container registry) | Not started |
| TASK-119 | S3 (data lake) | Not started |
| TASK-120 | RDS PostgreSQL | Not started |
| TASK-121 | EKS (including Kafka in EKS) | Not started |
| TASK-122 | IAM | Not started |
| TASK-123 | AWS deployment | Not started |
| TASK-124 | CI/CD cloud deployment | Not started |

**No `terraform/` directory exists.** All AWS infrastructure is target state only.

### M15: Production Polish (Planned / Target Only)

| Task | Description | Status |
|------|-------------|--------|
| TASK-125 | Architecture documentation | Not started |
| TASK-126 | ADRs | Not started |
| TASK-127 | Failure demonstrations | Not started |
| TASK-128 | Performance results | Not started |
| TASK-129 | Security review | Not started |
| TASK-130 | README rewrite | Not started |
| TASK-131 | Architecture diagram | Not started |
| TASK-132 | Demo walkthrough | Not started |
| TASK-133 | Final code review | Not started |

---

## 15. Architecture Findings and Follow-ups

### Confirmed

These findings are directly supported by repository, runtime, test, or
benchmark evidence.

**C1: Warehouse Loader reads Silver, not Gold.**
The Warehouse Loader reads Silver Parquet from MinIO and loads PostgreSQL
base tables. There is no Gold Parquet layer. This differs from the conceptual
architecture in PROJECT.md Section 3 and SPECIFICATION.md Section 6.5.
Evidence: `services/warehouse-loader/runner.py`, `libs/parquet_reader/reader.py`.

**C2: Airflow operates on PostgreSQL, not Silver/Gold Parquet.**
Three of four Airflow DAGs read from PostgreSQL and write back to PostgreSQL.
Only `parquet_compaction` operates on MinIO (Bronze layer). Airflow is not
a pipeline stage between Silver and PostgreSQL.
Evidence: `airflow/dags/daily_data_quality_dag.py`,
`airflow/dags/build_daily_metrics_dag.py`,
`airflow/dags/ingestion_health_dag.py`.

**C3: Gold exists only as PostgreSQL tables.**
No Gold Parquet bucket or files exist. Gold analytical data is stored in
`daily_metrics`, `data_quality_results`, and `ingestion_health_results`
PostgreSQL tables.
Evidence: `libs/common/minio_storage.py` (only `bronze` and `silver` buckets).

**C4: No circuit breakers are implemented.**
No circuit breaker pattern exists in the codebase. Source degradation is
detected via health evaluation but does not trigger circuit-breaking behavior.
Evidence: `grep` for `circuit.?breaker` returns zero results.

**C5: Agent is deployed as part of the API service, not as a separate service.**
The LangGraph agent is invoked via `POST /api/v1/agent/ask` within the FastAPI
process. It is not a separately deployed container.
Evidence: `services/api/routes/v1/agent.py`, no `agent` deployment in
`kubernetes/deployments/`.

**C6: Load benchmarks measure producer-side throughput only.**
TASK-109/110/111 benchmarks measure produce-to-ack latency and throughput.
They do not measure end-to-end pipeline latency or confirm that all produced
events were processed by every downstream component.
Evidence: `docs/benchmark-100-eps.md` Limitations section,
`docs/benchmark-500-eps.md` Scope and Deferrals section.

**C7: Producer-call duration increases with concurrent worker count.**
At 100 eps (3 workers): 5.1 ms mean. At 500 eps (15 workers): 48.4 ms mean.
At 1000 eps (30 workers): 89.5 ms mean. This creates a throughput ceiling
below the configured target at higher rates.
Evidence: `docs/benchmark-1000-eps.md` comparison table.

**C8: Monitoring disabled in kind by default.**
`values-local.yaml` sets `prometheus.enabled: false` and
`grafana.enabled: false`. Monitoring is available via Docker Compose but not
in the default Kubernetes local deployment.
Evidence: `helm/ai-data-platform/values-local.yaml`.

**C9: `pipeline.events.v1` and `data-quality.events.v1` topics are defined but not actively produced to.**
The topics are created by the Kafka topics Job, but no service currently
publishes to these topics as part of normal operation.
Evidence: Topic creation in `scripts/manage_kafka_topics.py`; no producer
references found in service code.

### Known Limitations

**L1: Single Kafka broker with replication factor 1.**
The Kafka deployment uses a single broker with no replication. Broker failure
causes complete event transport loss. This is acceptable for local development
but not for production.
Evidence: `docker-compose.yml`, ADR-001 (replication factor 1 for local
single-broker).

**L2: No end-to-end pipeline sustainability verification under load.**
Benchmarks demonstrate producer-side throughput but do not verify that
downstream components (processor, lake-writer, warehouse-loader) sustain the
same rate. Consumer lag under load is instrumented but not reconciled.
Evidence: Benchmark reports explicitly state this limitation.

**L3: Pre-existing service restart patterns.**
Benchmark observations noted raw-writer (11 restarts) and warehouse-loader
(30-35 restarts) had histories of restarts. These services were Running during
benchmark windows but the restart patterns indicate stability issues.
Evidence: `docs/benchmark-500-eps.md` Pod Status sections.

**L4: Windows execution environment significantly degrades load generation.**
Windows/localhost runs showed 18-19 eps vs Linux in-cluster 95-333 eps for
the same target rates. The cause is multi-factorial (networking, timer
resolution, port-forward overhead) and was not isolated.
Evidence: Benchmark reports comparison tables.

### Requires Further Investigation

**H1: Root cause of producer-call duration increase at higher concurrency.**
The producer-call duration increases from 5.1 ms (3 workers) to 89.5 ms
(30 workers). Possible contributors include producer internal lock contention,
broker-side queueing under higher in-flight message volume, or kind cluster
network characteristics. The cause was not independently isolated.

**H2: Root cause of raw-writer and warehouse-loader restart patterns.**
Both services showed multiple restarts during benchmark observation windows.
The cause was not investigated as part of the performance testing scope.

**H3: Whether the pipeline can sustain 100 eps end-to-end.**
Producer-side achieved 95.55 eps (95.6% of target). Whether all downstream
components can sustain this rate continuously has not been demonstrated.

### Deferred to M14

**D1: Single-broker Kafka must be replaced with replicated cluster for AWS.**
Terraform/EKS work should deploy Kafka with replication factor >= 3.

**D2: MinIO must be replaced with S3 for production.**
The `bronze` and `silver` buckets currently on MinIO need S3 equivalents
with proper IAM policies.

**D3: PostgreSQL must be replaced with RDS for production.**
The single-instance PostgreSQL StatefulSet with 1Gi PVC needs RDS with
appropriate instance sizing, backups, and read replicas.

**D4: Monitoring must be enabled for production.**
Either in-cluster Prometheus/Grafana or AWS-managed alternatives (AMP, AMP)
need to be provisioned.

**D5: Warehouse Loader data source discrepancy should be resolved.**
The conceptual architecture specifies Gold Parquet -> Warehouse Loader, but
the implementation reads Silver Parquet. An ADR should document whether the
conceptual architecture or the implementation is the intended target state.

**D6: `pipeline.events.v1` and `data-quality.events.v1` topics should be activated or removed.**
These topics are defined and created but not actively used. M14 should decide
whether to implement producers for these topics or remove them from the
configuration.

### Deferred to M15

**D7: End-to-end pipeline sustainability under load should be verified.**
A dedicated E2E load test that measures produced-to-consumed reconciliation
across all pipeline stages would close the gap identified in L2.

**D8: Circuit breaker pattern should be evaluated for source adapters.**
Source degradation is detected but not acted upon. A circuit breaker could
prevent repeated failing calls to degraded sources.

**D9: Architecture documentation should be reconciled with implementation.**
PROJECT.md Section 3 and SPECIFICATION.md Section 6.5 describe a Gold Parquet
layer that does not exist. These documents should be updated to match the
implemented architecture, or an ADR should explain the divergence.

**D10: Grafana dashboards should be verified against live data.**
Dashboard JSON definitions exist but visual verification against live
Prometheus data in kind is not automated.

---

## Evidence Index

Key repository paths referenced in this inventory:

| Area | Path |
|------|------|
| Project constitution | `ai/PROJECT.md` |
| Implementation specification | `ai/SPECIFICATION.md` |
| Engineering roadmap | `ai/ROADMAP.md` |
| Agent operating rules | `ai/AGENTS.md` |
| ADR-001 Kafka topics | `docs/adr/ADR-001-kafka-topic-configuration.md` |
| Source adapters | `libs/adapters/` |
| Event contracts | `libs/event_contracts/` |
| Kafka producer/consumer | `libs/common/kafka_producer.py`, `libs/common/kafka_consumer.py` |
| Kafka DLQ | `libs/common/kafka_errors.py` |
| MinIO storage | `libs/common/minio_storage.py` |
| Partition key strategy | `libs/partitioning/partition_key.py` |
| Bronze writer | `libs/raw_writer/bronze_writer.py` |
| Silver writer | `libs/lake_writer/silver_writer.py` |
| Parquet reader | `libs/parquet_reader/reader.py` |
| Processor pipeline | `services/processor/pipeline.py` |
| Warehouse loader | `warehouse/loader/batch_loader.py` |
| API routes | `services/api/routes/v1/router.py` |
| Agent graph | `services/agent/graph.py` |
| Agent tools | `services/agent/tools.py` |
| Agent DB adapter | `services/agent/db_adapter.py` |
| Airflow DAGs | `airflow/dags/` |
| Kubernetes manifests | `kubernetes/` |
| Helm chart | `helm/ai-data-platform/` |
| Prometheus config | `monitoring/prometheus.yml`, `helm/ai-data-platform/templates/monitoring/` |
| Grafana dashboards | `monitoring/grafana/dashboards/` |
| OTel config | `libs/observability/otel_config.py`, `monitoring/otel-collector-config.yaml` |
| Kafka metrics | `libs/observability/kafka_metrics.py` |
| Processor metrics | `libs/observability/processor_metrics.py` |
| Source metrics | `libs/observability/source_metrics.py` |
| Load test harness | `scripts/run_load_test.py` |
| Benchmark 100 eps | `docs/benchmark-100-eps.md` |
| Benchmark 500 eps | `docs/benchmark-500-eps.md` |
| Benchmark 1000 eps | `docs/benchmark-1000-eps.md` |
| E2E pipeline test | `tests/test_pipeline_e2e.py` |
| Failure replay test | `tests/test_failure_replay.py` |
| Duplicate replay test | `tests/test_duplicate_replay.py` |
| Agent E2E test | `tests/agent/test_agent_e2e.py` |
| Idempotent loader test | `tests/warehouse/test_idempotent_loader.py` |
| DB migrations | `warehouse/migrations/versions/` |
| Kafka topic management | `scripts/manage_kafka_topics.py` |
| Docker Compose | `docker-compose.yml` |
