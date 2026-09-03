# SPECIFICATION.md

# AI Data Platform
## Distributed Data Engineering & Agentic AI Platform

**Status:** Draft / Implementation Specification  
**Version:** 1.0  
**Constitution:** `ai/PROJECT.md`  
**Agent Rules:** `AGENTS.md`  
**Development Workflow:** `ai/AGENT_WORKFLOW.md`

---

## 1. Purpose

The AI Data Platform is a production-oriented distributed data platform demonstrating modern Data Engineering, Backend Engineering, Cloud Infrastructure, and Agentic AI capabilities.

The platform ingests product and market observations from external sources, transports events through Kafka, validates and transforms data using Python and Polars, stores analytical data as Parquet in an S3-compatible data lake, loads curated data into PostgreSQL, orchestrates scheduled data operations with Airflow, exposes data through FastAPI, and provides a controlled LangGraph-based Data Engineer Agent.

The primary objective is not to build a sophisticated scraper.

The primary objective is to demonstrate the ability to design, implement, operate, test, observe, and troubleshoot a distributed data platform.

---

# 2. Engineering Goals

The system must demonstrate:

- Python backend engineering
- Event-driven architecture
- Kafka producers and consumers
- At-least-once processing
- Idempotent event processing
- Data validation and data-quality handling
- ETL/ELT processing
- Polars-based data transformations
- Apache Parquet
- S3-compatible object storage
- PostgreSQL data modelling and analytics
- SQL including CTEs and window functions
- Airflow orchestration
- Docker
- Kubernetes
- Helm
- Prometheus
- Grafana
- OpenTelemetry
- Terraform
- AWS deployment
- CI/CD
- Failure recovery
- Load testing
- LangGraph agent orchestration

---

# 3. Primary Use Case

The reference use case is **e-commerce competitive intelligence**.

The platform collects observations such as:

- product ID
- product name
- source
- URL
- price
- currency
- availability
- category
- timestamp

The same product may be observed repeatedly over time.

This allows the platform to answer analytical questions such as:

- Which products experienced the largest price increase during the last 7 days?
- Which products changed availability?
- Which sources stopped producing data?
- Which products have missing observations?
- What was the average price by category?
- Why did yesterday's observation count decrease?
- Which data-quality rules failed?

The source adapters should remain simple enough that the project focuses on the platform rather than anti-bot engineering. The initial source strategy is defined in Section 4.

---


# 4. Data Sources and Source Strategy

The platform is designed to ingest product, pricing, availability, and marketplace observations from heterogeneous external sources.

The initial source set should be intentionally small and should represent different ingestion patterns rather than maximize source count.

## 4.1 Initial Data Sources

| Source | Type | Primary Role | Target Phase |
|---|---|---|---|
| Fake Store API | REST API / synthetic source | Deterministic development and integration testing | Phase 1 |
| Best Buy | REST API | Stable production-like product source | Phase 1 |
| eBay | Marketplace API | Multiple listings, sellers, price observations, marketplace normalization | Phase 2 |
| Retailer Website | Web scraping | Dynamic web source and scraper reliability testing | Phase 3 |
| Amazon or equivalent difficult source | Web scraping / external data source | Failure handling, rate limiting, freshness and source degradation testing | Phase 4 |

The specific difficult source may be replaced if access conditions, legal constraints, anti-bot behavior, or source availability make another retailer more appropriate.

The objective is to demonstrate heterogeneous ingestion while keeping downstream processing source-agnostic.

## 4.2 Source Adapter Architecture

Every external source must be implemented behind a source-specific adapter.

A source adapter is responsible for:

- communication with the source
- authentication and credentials where required
- pagination
- retries and exponential backoff
- rate limiting
- source-specific error handling
- parsing source-specific responses or HTML
- mapping source data into the canonical platform event model
- exposing source-level health information

Downstream components must not depend on source-specific response formats.

Expected flow:

```text
External Source
      ↓
Source Adapter
      ↓
Canonical Event
      ↓
Kafka
      ↓
Processing Pipeline
```

Adding a new source should normally require implementing a new adapter rather than modifying Kafka consumers, the processing layer, data lake, warehouse, API, or agent architecture.

## 4.3 Source Categories

The platform should support the following source categories.

### REST/API Sources

Characteristics:

- structured responses
- API authentication where required
- pagination
- rate limits
- transient HTTP/API failures

### Marketplace Sources

Characteristics:

- multiple listings for one logical product
- seller-specific prices
- availability
- shipping or listing metadata where available
- product/listing identity resolution

### Web Sources

Characteristics:

- HTML parsing
- JavaScript-rendered content where necessary
- pagination
- missing or inconsistent fields
- changes in page structure
- source-specific failures

Web scraping complexity must remain secondary to the platform objective. Source adapters should use the simplest reliable collection mechanism suitable for the selected source.

### Synthetic/Test Sources

Synthetic sources are used to create deterministic test scenarios such as:

- missing price
- invalid category
- duplicate event
- malformed payload
- unsupported schema version
- stale timestamp
- simulated source outage

Synthetic sources are testing infrastructure and must not be presented as production business data.

## 4.4 Canonical Source Data Contract

Regardless of source, normalized observations must conform to the common event contract defined in the Event Contract section.

Source-specific fields must not be added directly to the core event model without an explicit schema change.

Where source-specific details must be retained, they may be stored in an extensible metadata structure provided that:

- the core analytical fields remain source-independent
- metadata does not become required by downstream generic consumers
- schema evolution remains explicit

## 4.5 Source Health and Freshness

Source-level health must be independently observable.

Where applicable, the platform should track:

- successful requests
- failed requests
- HTTP/API errors
- parsing errors
- authentication failures
- rate-limit responses
- records received
- records accepted
- records rejected
- last successful observation timestamp
- source freshness
- ingestion latency

Source degradation must be visible through metrics, logs, data-quality checks, pipeline status, and the source-health tool used by the LangGraph agent.

## 4.6 Source Expansion Rule

The initial source list is not exhaustive.

Additional sources may be added later if they demonstrate a useful ingestion pattern or engineering challenge.

A new source must not require a new downstream architecture.

The preferred extension model is:

```text
New Source
   ↓
New Adapter
   ↓
Existing Canonical Event Contract
   ↓
Existing Platform
```

---

# 5. Repository and Service Boundaries

The repository must make the platform service boundaries explicit. The initial service decomposition is:

```text
services/
├── ingestion/
├── processor/
├── raw-writer/
├── lake-writer/
├── warehouse-loader/
├── api/
└── agent/

libs/
├── event-contracts/
├── common/
└── observability/
```

Supporting top-level areas include:

```text
ai/
docs/
airflow/dags/
sql/
kubernetes/
helm/
terraform/
monitoring/
scripts/
tests/
```

These boundaries are normative for the initial implementation. A task may refine internal module structure, but must not collapse the Raw Writer, Lake Writer, or Warehouse Loader into another service without an ADR and human approval.

# 6. High-Level Architecture

The following topology is normative and must remain consistent with `PROJECT.md`.

```text
                    External Sources
                          │
                          ▼
              Source Adapters / Ingestion
                          │
                          ▼
                     ┌────────┐
                     │ Kafka  │
                     └───┬────┘
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
       ┌────────────┐        ┌────────────┐
       │ Processor  │        │ Raw Writer │
       │ Python +   │        │            │
       │ Polars     │        └─────┬──────┘
       └─────┬──────┘              │
             │                     ▼
             │              Bronze Parquet
             │                     │
             ▼                     ▼
 products.validated.v1       S3 / MinIO
             │
             ▼
       ┌────────────┐
       │ Lake Writer│
       └─────┬──────┘
             │
             ▼
       Silver Parquet
             │
             ▼
          Airflow
       batch transformations
             │
             ▼
        Gold Parquet
             │
             ▼
     Warehouse Loader
             │
             ▼
        PostgreSQL
          │      │
          │      └──────────────┐
          ▼                     ▼
       FastAPI           LangGraph Agent
          │                     │
          └──────────┬──────────┘
                     ▼
               Users / Clients

Prometheus / Grafana / OpenTelemetry observe the platform.
Kubernetes runs the services. Terraform provisions AWS infrastructure.
```

## 6. Architectural Components

### 6.1 Ingestion Service

The ingestion service executes source adapters and publishes canonical observations to `products.raw.v1`. It owns source communication, authentication, pagination, retries/backoff, rate limiting, parsing, source-specific normalization, event ID generation, basic event validation, and source health information.

It must not write directly to PostgreSQL.

### 6.2 Processor Service

The processor consumes `products.raw.v1`, validates and normalizes observations, applies Polars transformations and deduplication, and publishes valid canonical records to `products.validated.v1`. Invalid records are published to `products.invalid.v1` with sufficient diagnostic context.

The processor does not write directly to PostgreSQL.

### 6.3 Raw Writer Service

The Raw Writer consumes `products.raw.v1` and persists raw or minimally transformed events to the Bronze data-lake layer in Parquet. It must be independently restartable and replayable.

### 6.4 Lake Writer Service

The Lake Writer consumes `products.validated.v1` and persists validated/normalized records to Silver Parquet. It owns the validated-event-to-Silver boundary and must not be coupled to PostgreSQL.

### 6.5 Warehouse Loader Service

The Warehouse Loader loads curated Gold Parquet datasets into PostgreSQL. Loading must be idempotent and must preserve the historical observation model. It is the only component responsible for the Parquet-to-PostgreSQL loading boundary.

### 6.6 Scheduled Processing and Serving Components

Airflow owns scheduled/batch workflows including Gold dataset construction, compaction, data-quality checks, and freshness checks. FastAPI exposes serving and analytics endpoints. The LangGraph agent uses controlled read-only tools over platform state; it is not an infrastructure control plane.

# 7. Event Contract

Every Kafka event must contain a common envelope.

Example:

```json
{
  "event_id": "uuid",
  "event_type": "product.observation",
  "schema_version": 1,
  "source": "example-source",
  "produced_at": "2026-09-03T08:00:00Z",
  "payload": {
    "external_id": "123",
    "name": "Example Product",
    "url": "https://example.com/product/123",
    "price": 149.99,
    "currency": "EUR",
    "availability": "in_stock",
    "category": "electronics",
    "collected_at": "2026-09-03T07:59:30Z"
  }
}
```

Required fields:

- `event_id`
- `event_type`
- `schema_version`
- `source`
- `produced_at`
- `payload`

Payload required fields include:

- `external_id` — source-specific product/listing identifier
- `name`
- `url`
- `price` (nullable when unavailable and explicitly represented)
- `currency`
- `availability` — one of `in_stock`, `out_of_stock`, `preorder`, `unknown`
- `category`
- `collected_at` — observation timestamp from the source/collector

`produced_at` records event publication time and must not be used as a substitute for `collected_at`.

### Event ID

`event_id` must uniquely identify an observation event.

Consumers must assume that an event can be delivered more than once.

---

# 8. Kafka Architecture

Initial topics:

```text
products.raw.v1
products.validated.v1
products.invalid.v1
pipeline.events.v1
data-quality.events.v1
```

### Topic responsibilities

- `products.raw.v1`: canonical observations emitted by ingestion; consumed by the processor and Raw Writer.
- `products.validated.v1`: validated/normalized observations emitted by the processor; consumed by the Lake Writer and any explicitly approved downstream consumers.
- `products.invalid.v1`: invalid/dead-letter observations with diagnostic context.
- `pipeline.events.v1`: lifecycle events such as `job.started`, `job.completed`, `job.failed`, and `run.heartbeat` emitted by pipeline services and consumed by monitoring/metadata workflows.
- `data-quality.events.v1`: data-quality events such as `quality.check.started`, `quality.check.failed`, and `quality.check.completed`, consumed by quality/metadata workflows.

The event schema for lifecycle topics must use the same versioned envelope pattern and explicitly define event-specific payloads.

### Partitioning and ordering

The partitioning decision must preserve ordering for observations of the same source/product identity where ordering is required by downstream logic. The initial implementation should use a deterministic key derived from `source` + `external_id`; the exact partition count is an implementation parameter recorded in ADR-001 during TASK-007. Retention must be long enough to support the documented replay demonstrations and local development without treating Kafka as permanent storage. Consumers must not assume global ordering across partitions.

Kafka responsibilities:

- event transport
- buffering
- decoupling services
- replay
- consumer-group based processing

Kafka must not be treated as the permanent analytical datastore.

---

# 9. Delivery Semantics

The platform uses:

> **At-least-once delivery + idempotent processing**

The system must not claim end-to-end exactly-once semantics unless this is explicitly demonstrated and justified.

Consumers must tolerate duplicate events.

A duplicate event must not result in duplicate logical observations in the final analytical/serving layer.

The implementation must document:

- when offsets are committed
- what happens if processing fails
- what happens if the process crashes after writing data but before committing the offset
- how duplicate processing is detected
- how replay is performed

---

# 10. Invalid Events and DLQ

Events that cannot be validated must not silently disappear.

Examples:

- missing required field
- invalid timestamp
- invalid price
- unsupported schema version
- malformed JSON
- invalid data type

Invalid events must be routed to the invalid/DLQ path.

The system must preserve enough information to diagnose the failure.

Metrics must expose invalid-event counts.

---

# 11. Processing Layer

The processor consumes Kafka events and transforms them into analytical records.

Primary technology:

- Python
- Polars
- PyArrow where appropriate

Processing operations include:

- schema normalization
- type conversion
- null handling
- deduplication
- filtering
- joins
- aggregations
- derived fields

Where practical, Parquet should be processed using Polars/PyArrow rather than converting large datasets unnecessarily into Python lists/dictionaries.

---

# 12. Data Lake

Object storage:

- local development: MinIO
- AWS deployment: S3

Storage format:

> Apache Parquet

Logical layers:

```text
Bronze
  ↓
Silver
  ↓
Gold
```

### Bronze

Raw or minimally transformed observations.

### Silver

Validated and normalized records.

### Gold

Curated analytical datasets and derived metrics.

Partitioning should primarily use temporal/source dimensions, for example:

```text
source=example/year=2026/month=09/day=03/
```

Do not partition primarily by high-cardinality fields such as `product_id`.

---

# 13. PostgreSQL

PostgreSQL is the serving and analytical query layer.

Initial logical entities and required invariants:

| Entity | Key fields | Important constraints |
|---|---|---|
| `sources` | `id`, `name`, `type`, `base_url`, `enabled`, `created_at` | unique source name |
| `products` | `id`, `canonical_key`, `name`, `category`, `created_at`, `updated_at` | unique canonical product identity |
| `product_observations` | `id`, `event_id`, `product_id`, `source_id`, `external_id`, `observed_at`, `price`, `currency`, `availability`, `url`, `raw_metadata` | `UNIQUE(event_id)`; indexed by `(source_id, external_id, observed_at)` |
| `pipeline_runs` | `id`, `run_id`, `pipeline_name`, `source`, `status`, `started_at`, `finished_at`, `records_received`, `records_processed`, `records_failed`, `error_message` | unique `run_id` |
| `data_quality_results` | `id`, `run_id`, `check_name`, `source`, `status`, `checked_at`, `records_checked`, `failed_records`, `details` | indexed by run/source/check |

`product_observations` must preserve historical observations. `external_id` is source-specific; `products.id` is the platform identity and must not be conflated with it.

The loader must enforce the duplicate-event invariant through database constraints and/or idempotent upsert logic.

The design should support historical observations rather than storing only the current product state.

Required analytical SQL examples should include:

- CTEs
- `ROW_NUMBER`
- `RANK`
- `LAG`
- rolling averages
- price-change calculations
- latest-observation queries
- anomaly detection queries
- source-level statistics

---

# 14. Data Quality

The platform must perform data-quality checks.

Initial checks:

- schema validity
- required fields
- type validity
- price validity
- timestamp validity
- duplicate rate
- null rate
- record count
- freshness
- unexpected source behavior

Validation may use Pandera or an equivalent explicit validation layer.

Data-quality results must be persisted and exposed through the API.

---

# 15. Airflow

Airflow is responsible for scheduled/batch workflows.

Airflow must not replace Kafka as the streaming mechanism.

Initial DAGs:

```text
ingestion_health
daily_data_quality
parquet_compaction
build_daily_metrics
```

DAG responsibilities include:

- scheduled quality checks
- historical processing
- Parquet maintenance
- aggregation jobs
- freshness monitoring
- pipeline health

---

# 16. FastAPI

Initial endpoints:

```text
GET  /health

GET  /products
GET  /products/{id}
GET  /products/{id}/history

GET  /analytics/price-changes
GET  /analytics/anomalies

GET  /pipelines
GET  /pipelines/{id}

GET  /quality

POST /agent/query
```

The API should return structured JSON.

Long-running operations should not block normal request handling.

---

# 17. LangGraph Data Engineer Agent

The agent is a controlled operational/analytical assistant.

It is not an unrestricted autonomous agent.

Example requests:

> Which products experienced the largest price increase during the last 7 days?

> Why did product observations drop yesterday?

> Which sources have failed their freshness checks?

> Show me the products with the largest price changes.

The agent may use controlled tools such as:

```text
dataset_metadata
read_only_sql
pipeline_status
data_quality_status
source_status
```

The SQL tool must be read-only.

The agent must not have arbitrary write access to PostgreSQL.

---

# 18. Agent State

Example LangGraph state:

```text
question
intent
dataset
generated_sql
sql_result
pipeline_status
quality_results
answer
errors
```

Possible graph:

```text
Question
   ↓
Classify Intent
   ↓
Select Route
   ├── Analytics → SQL
   ├── Data Quality → Quality Tool
   ├── Pipeline → Pipeline Tool
   └── Source Health → Source Tool
   ↓
Validate Result
   ↓
Generate Explanation
   ↓
Answer
```

The graph should remain deterministic wherever possible.

---

# 19. Kubernetes

The platform must eventually run locally on Kubernetes.

Development progression:

```text
Docker Compose
      ↓
kind
      ↓
AWS EKS
```

Initial Kubernetes resources should include:

- Namespace
- Deployment
- Service
- ConfigMap
- Secret
- ServiceAccount
- probes
- resource requests/limits

Later Kubernetes features must be implemented explicitly in the roadmap:

- Ingress
- HPA
- NetworkPolicy
- Helm
- optional KEDA

These are not implied to be present in the first kind deployment.

Services should include appropriate:

- liveness probes
- readiness probes
- startup probes where necessary

---

# 20. Observability

The platform must provide operational visibility.

## Metrics

Initial metrics:

```text
ingestion_events_total
ingestion_errors_total
kafka_events_processed_total
events_invalid_total
pipeline_processing_seconds
pipeline_records_processed
api_requests_total
api_request_duration_seconds
agent_requests_total
agent_tool_calls_total
```

Kafka consumer lag should also be observable.

## Logging

Use structured logs.

Logs should contain contextual information such as:

```text
timestamp
service
level
event_id
source
operation
error
trace_id
```

Do not log secrets.

## Tracing

OpenTelemetry should provide distributed traces across major service boundaries.

---

# 21. Security

Minimum requirements:

- no credentials committed to Git
- secrets supplied through environment/configuration mechanisms
- read-only SQL agent
- least-privilege service accounts where practical
- no unrestricted database access from the agent
- no hardcoded AWS credentials
- separate development and production configuration
- sensitive values excluded from logs

---

# 22. Testing

The project must contain:

### Unit tests

For:

- validation
- transformations
- business rules
- SQL generation
- agent routing

### Integration tests

For:

- Kafka
- PostgreSQL
- MinIO
- Parquet
- processor
- API

### End-to-end tests

At least one complete flow:

```text
source
 ↓
Kafka
 ↓
processor
 ↓
Parquet
 ↓
PostgreSQL
 ↓
API
 ↓
Agent
```

### Failure tests

At minimum:

- Kafka unavailable
- PostgreSQL unavailable
- invalid event
- duplicate event
- processor crash
- source stops producing
- Parquet write failure
- consumer restart
- replay

---

# 23. Performance Testing

The project should measure rather than merely claim performance.

Initial load scenarios:

```text
100 events/sec
500 events/sec
1000 events/sec
```

Measure:

- ingestion throughput
- processing throughput
- Kafka consumer lag
- processing latency
- API latency
- error rate
- resource utilization

The README should report actual measured results and test environment.

---

# 24. CI/CD

GitHub Actions should perform:

```text
lint
↓
unit tests
↓
integration tests
↓
build Docker images
↓
security checks
↓
publish images
```

Cloud deployment should be separated from ordinary CI where appropriate.

---

# 25. Infrastructure

Terraform should eventually provision the AWS environment.

Target components:

```text
VPC
EKS
ECR
S3
RDS PostgreSQL
IAM
CloudWatch / supporting AWS resources
```

For the AWS milestone, Kafka must be reachable by the EKS-hosted ingestion and processor services. The default portfolio topology is Kafka deployed inside EKS using Strimzi or equivalent Kubernetes manifests; Amazon MSK is optional. A permanently local Kafka broker is not considered a complete AWS deployment topology.

Managed Kafka such as MSK should only be introduced if there is a demonstrated operational reason.

---

# 26. Local Development Environment

The entire MVP must work locally.

Target local stack:

```text
Docker
Kafka
MinIO
PostgreSQL
Airflow
FastAPI
Python services
Prometheus
Grafana
```

Kubernetes development uses `kind`.

AWS should be introduced only after the local/Kubernetes implementation is stable.

---

# 27. Definition of Done

A feature is not complete merely because its code exists.

A task is Done when:

- implementation exists
- tests exist
- tests pass
- linting passes
- configuration is documented
- failure behavior is considered
- logs/metrics are added where appropriate
- architecture rules are respected
- no secrets are introduced
- Git diff has been reviewed
- acceptance criteria are satisfied

A milestone is complete only when its end-to-end behavior has been demonstrated.

---

# 28. Architecture Change Policy

Fundamental architecture decisions must not be silently changed.

If implementation reveals a genuine architectural problem:

1. Stop.
2. Document the issue.
3. Propose an ADR.
4. Explain alternatives.
5. Make the architectural decision.
6. Update the relevant specification.
7. Continue implementation.

`PROJECT.md` remains the highest-level architectural authority.

---

# 29. AI-Assisted Development

The project is explicitly designed for AI-assisted engineering.

The workflow is:

```text
Human architecture
      ↓
Specification
      ↓
Small task
      ↓
Qoder implementation
      ↓
Automated tests
      ↓
Independent review
      ↓
Human decision
      ↓
Merge
```

Qoder is the primary implementation environment.

Qwen/DeepSeek are preferred for high-volume implementation and review tasks where appropriate.

Claude Code is reserved primarily for difficult architectural, distributed-systems, debugging, and independent-review problems.

AI agents must not silently change fundamental architectural decisions.

---

# 30. Portfolio Objective

The finished project should allow an engineer to demonstrate:

> I can design and operate a distributed data platform, not merely write individual Python services.

The final repository should therefore make the following visible:

- architecture
- event contracts
- data modelling
- Kafka semantics
- ETL/ELT
- data quality
- orchestration
- Kubernetes
- observability
- cloud infrastructure
- CI/CD
- failure recovery
- performance measurements
- controlled Agentic AI integration

The project should prioritize **engineering depth over feature count**.