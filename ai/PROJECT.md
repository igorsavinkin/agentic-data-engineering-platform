# PROJECT.md

# AI Data Platform — Project Constitution

**Status:** Stable architectural constitution
**Version:** 1.0

This document defines the durable architectural principles and non-negotiable boundaries of the AI Data Platform. It has higher authority than `SPECIFICATION.md`, `ROADMAP.md`, task files, and implementation details.

## 1. Project Objective

Build a production-oriented distributed data platform that demonstrates senior-level Data Engineering, Backend Engineering, cloud infrastructure, reliability engineering, and controlled Agentic AI.

The portfolio value comes from the coherent platform: ingestion, event transport, processing, data lake, warehouse, orchestration, APIs, observability, failure recovery, Kubernetes, AWS, and a controlled data-analysis agent. Scraping complexity is secondary.

## 2. Technology Baseline

- Python 3.12+
- Kafka for event transport and replay
- Polars and PyArrow for analytical processing
- Apache Parquet for the data lake
- MinIO locally and Amazon S3 in AWS
- PostgreSQL for serving and analytical queries
- Apache Airflow for scheduled/batch workflows
- FastAPI for the service/API layer
- LangGraph for the controlled Data Engineer Agent
- Docker for local packaging
- Kubernetes/kind locally and AWS EKS in the cloud
- Helm for Kubernetes packaging
- Prometheus and Grafana for metrics/visualization
- OpenTelemetry for tracing
- Terraform for AWS infrastructure
- GitHub Actions for CI/CD

Required Python engineering tooling:

- pytest
- Ruff for linting and formatting
- mypy for static type checking

Equivalent tools may be introduced only through an explicit architectural/documentation change.

## 3. Core Architecture

The normative platform boundary is:

```text
External Sources
      │
      ▼
Source Adapters / Ingestion
      │
      ▼
    Kafka
      │
      ▼
   Processor
      │
      ├──────────────► products.validated.v1 ──► Lake Writer ──► Silver Parquet
      │
      └──────────────► products.invalid.v1 / DLQ

Kafka raw events ──► Raw Writer ──► Bronze Parquet

Silver Parquet ──► Airflow batch transformations ──► Gold Parquet
                                                   │
                                                   ▼
                                           Warehouse Loader
                                                   │
                                                   ▼
                                             PostgreSQL
                                               │    │
                                               │    └──────────────► FastAPI
                                               │
                                               └────────────────────► LangGraph Agent

Prometheus / Grafana / OpenTelemetry observe the platform.
Kubernetes runs services. Terraform provisions AWS infrastructure.
```

The LangGraph agent may query PostgreSQL only through controlled, read-only tools. FastAPI exposes the agent endpoint but is not an intermediate data-access requirement for the agent.

## 4. Component Responsibilities

### Source Adapters / Ingestion

Own source communication, authentication, pagination, rate limiting, retries, parsing, source-specific normalization, event creation, and publication to Kafka. Never write directly to PostgreSQL.

### Kafka

Own event transport, buffering, decoupling, consumer groups, offsets, retention, and replay. Kafka is not the permanent analytical store.

### Processor

Consumes raw events, validates and normalizes them, performs Polars transformations and deduplication, publishes valid canonical events to `products.validated.v1`, and routes invalid events to `products.invalid.v1`.

### Raw Writer

Consumes `products.raw.v1` and persists raw/minimally transformed events as Bronze Parquet.

### Lake Writer

Consumes `products.validated.v1` and persists validated/normalized records as Silver Parquet. It is a separate service so lake persistence is decoupled from processing and can be independently scaled/restarted/replayed.

### Airflow

Owns scheduled/batch work such as quality checks, compaction, historical transformations, freshness checks, and Gold dataset construction. Airflow does not replace Kafka for streaming transport.

### Warehouse Loader

Consumes curated Gold Parquet datasets and loads PostgreSQL idempotently. It is the only component responsible for the Parquet-to-PostgreSQL loading boundary.

### PostgreSQL

Owns serving data, historical observations, pipeline metadata, data-quality results, and analytical SQL workloads.

### FastAPI

Provides synchronous HTTP access to serving/analytics data and the agent entry point. It does not become the streaming pipeline.

### LangGraph Agent

Provides controlled analytical/operational assistance using explicit read-only tools. It must not mutate platform state or execute arbitrary SQL writes.

## 5. Event Semantics

The platform uses **at-least-once delivery plus idempotent processing**. Duplicate delivery is expected. End-to-end exactly-once semantics must not be claimed unless explicitly demonstrated and documented.

The canonical product observation event uses:

- `external_id` for the source-specific product/listing identifier
- a platform-assigned internal product identity where needed downstream
- `collected_at` for the observation time
- `produced_at` for event publication time

Kafka partitioning must preserve the ordering required by the processor for the selected identity model. The concrete partition count and key are recorded in ADR-001 during Kafka foundation work.

## 6. Data Lake Boundaries

The data lake has three logical layers:

```text
Bronze → raw/minimally transformed
Silver → validated/normalized
Gold   → curated/analytical
```

Bronze is written by Raw Writer. Silver is written by Lake Writer. Gold is produced by Airflow batch transformations. Warehouse Loader reads Gold and loads PostgreSQL.

Partitioning should primarily use source and temporal dimensions. High-cardinality product identifiers must not be the primary partitioning dimension.

## 7. Source Expansion Principle

New external sources are implemented as adapters against the canonical event contract. Adding a source must not require changes to the core Kafka, processor, lake, warehouse, API, or agent architecture except where an explicit new source capability is required.

Initial source progression:

1. Fake Store API + Best Buy API
2. eBay Marketplace API
3. One retailer web source
4. Amazon or an equivalent difficult source, subject to access and legal/operational constraints

## 8. Local-First Principle

The platform must become functional locally before cloud deployment. The intended progression is:

```text
Docker Compose → kind/Kubernetes → AWS EKS
```

Cloud infrastructure must not be used to hide unresolved local architecture or reliability problems.

## 9. Reliability Principles

The system must explicitly address:

- retries and backoff
- idempotency
- offset/commit behavior
- replay
- invalid-event handling and DLQ
- source degradation
- freshness failures
- service restarts
- downstream outages

Failure behavior is part of the architecture, not an afterthought.

## 10. Observability Principles

Major service boundaries must expose useful logs, metrics, and traces. Source health, Kafka lag, processing throughput, data quality, API latency, and agent activity must be observable. Secrets must never be logged.

## 11. Security Principles

- no credentials in Git
- least-privilege service accounts where practical
- read-only SQL for the agent
- no unrestricted agent database access
- no hardcoded cloud credentials
- separate development and production configuration

## 12. Testing Principles

The platform must contain unit, integration, end-to-end, failure, and performance tests appropriate to each milestone. A feature is not complete merely because its implementation exists.

## 13. Architecture Change Policy

Fundamental architectural changes require an ADR and human approval. Agents may identify and propose changes but may not silently redefine the architecture.

Examples include changing:

- service boundaries
- event semantics
- Kafka responsibilities
- data-lake layer ownership
- warehouse ownership
- agent permissions
- cloud topology

## 14. Non-Goals

The project is not intended to:

- become a general-purpose scraping framework
- solve every anti-bot challenge
- ingest dozens of sources merely for quantity
- build an unrestricted autonomous infrastructure agent
- replace Kafka with Airflow or PostgreSQL
- optimize prematurely before measuring real bottlenecks

## 15. Portfolio Principle

The final project should demonstrate that its author can reason about and operate a distributed data platform end to end: data contracts, event streaming, processing, storage, SQL, orchestration, Kubernetes, observability, reliability, cloud infrastructure, and controlled AI tooling.

When a shortcut improves code volume but weakens architectural clarity, prefer architectural clarity.
