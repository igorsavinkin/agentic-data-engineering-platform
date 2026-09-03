# ROADMAP.md

# AI Data Platform — Engineering Roadmap

**Specification:** `ai/SPECIFICATION.md`  
**Constitution:** `ai/PROJECT.md`  
**Agent Workflow:** `ai/AGENT_WORKFLOW.md`

---

# 1. Roadmap Philosophy

The platform will be developed incrementally.

Each milestone must produce a working increment rather than a collection of disconnected components.

The preferred progression is:

```text
Foundation
    ↓
Working Vertical Slice
    ↓
Reliable Data Pipeline
    ↓
Data Lake
    ↓
Warehouse
    ↓
Orchestration
    ↓
Kubernetes
    ↓
Observability
    ↓
Agent
    ↓
AWS
    ↓
Performance + Failure Engineering
```

Do not start with Kubernetes, Terraform, or LangGraph.

First build a working data pipeline.

---

# 2. Agent Assignment Model

## Qoder — Primary Builder

Qoder owns the majority of implementation tasks.

Use Qoder for:

- Python implementation
- tests
- Polars
- SQL
- Docker
- Kubernetes manifests
- Helm
- Airflow
- CI/CD
- documentation
- refactoring

Tasks should be small and independently testable.

---

## DeepSeek / Qwen Models — High-Volume Engineering

Use inexpensive models for:

- boilerplate
- straightforward Python
- Pydantic models
- tests
- SQL
- Dockerfiles
- YAML
- documentation
- simple refactoring

Do not use the cheapest model automatically for architecture-critical logic.

---

## Qwen Code — Independent Reviewer

Use Qwen Code primarily as an independent reviewer.

It should often operate in:

> review-only / do-not-modify mode.

Focus:

- correctness
- missed requirements
- test coverage
- edge cases
- architectural violations
- security
- code quality

---

## Claude Code — Senior Engineer / Difficult Problems

Use Claude Code selectively.

Primary uses:

- architecture review
- distributed-systems reasoning
- Kafka semantics
- concurrency bugs
- difficult debugging
- Kubernetes failures
- Terraform/AWS review
- security review
- performance analysis
- independent final audit

Claude should not be used to generate routine boilerplate unless necessary.

---

# 3. Git Strategy

Each task should use a dedicated branch:

```text
main
│
├── feature/TASK-001-repository-foundation
├── feature/TASK-008-kafka-producer
├── feature/TASK-009-kafka-consumer
└── ...
```

One logical task should correspond to one focused branch/PR where practical.

Do not allow multiple agents to modify the same working tree simultaneously.

Qoder Worktrees may be used for parallel development after the architecture stabilizes.

---

# 4. Milestone 0 — Repository Foundation

## Objective

Create the project skeleton and development conventions.

### Tasks

```text
TASK-001
Repository structure

TASK-002
Python project configuration

TASK-003
Configuration and environment handling

TASK-004
Docker Compose foundation

TASK-005
CI foundation
```

### Deliverables

```text
ai/
docs/
services/
libs/
tests/
airflow/
sql/
kubernetes/
terraform/
monitoring/
scripts/
```

The repository must also reserve the following service boundaries:

```text
services/
├── ingestion/
├── processor/
├── raw-writer/
├── lake-writer/
├── warehouse-loader/
├── api/
└── agent/
```

Shared libraries belong under `libs/`; no service boundary may be silently collapsed during TASK-001.

Plus:

- Python tooling
- pytest
- Ruff linting/formatting
- mypy type checking
- pytest
- Docker Compose
- CI

### Agent

**Qoder + cheap model**

### Review

**Qwen Code**

### Human responsibility

Confirm repository structure and architectural conventions.

---

# 5. Milestone 1 — Event Platform

## Objective

Establish the event contract and Kafka foundation.

### Tasks

```text
TASK-006
Product observation event schema

TASK-007
Kafka topic configuration

TASK-008
Kafka producer

TASK-009
Kafka consumer

TASK-010
Consumer error handling

TASK-011
Kafka metrics

TASK-012
Integration tests
```

### Acceptance

A test event must travel:

```text
Producer
   ↓
Kafka
   ↓
Consumer
```

The consumer must correctly handle:

- valid event
- malformed event
- duplicate event
- restart

### Critical engineering concepts

You must understand and document:

- topic
- partition
- offset
- consumer group
- retention
- ordering
- rebalance
- commit
- consumer lag
- at-least-once processing

### Agent

**Qoder**

### Reviewer

**Qwen Code**

### Escalation

**Claude Code** for delivery-semantics questions.

---

# 6. Milestone 2 — Processing Pipeline

## Objective

Transform Kafka events into normalized analytical records.

### Tasks

```text
TASK-013
Polars processing layer

TASK-014
Schema normalization

TASK-015
Data validation

TASK-016
Deduplication

TASK-017
Invalid event / DLQ handling

TASK-018
Processor metrics

TASK-019
Processor integration tests
```

### Acceptance

```text
Kafka
 ↓
Consumer
 ↓
Validation
 ↓
Polars
 ↓
Valid / Invalid
```

Duplicate events must not create duplicate logical records.

### Agent

**Qoder + DeepSeek/Qwen**

### Reviewer

**Qwen Code**

### Escalation

Claude for idempotency and failure semantics.

---

# 7. Milestone 3 — Data Lake

## Objective

Persist raw and processed data as Parquet.

### Tasks

```text
TASK-020
MinIO integration

TASK-021
Raw Writer / Bronze Parquet service

TASK-022
Lake Writer / Silver Parquet service

TASK-023
Partitioning strategy

TASK-024
Parquet schema management

TASK-025
Parquet read/query utilities

TASK-026
Data lake integration tests
```

### Acceptance

A complete raw event must produce Bronze Parquet and a validated event must produce Silver Parquet through the separate Raw Writer and Lake Writer service boundaries. The processor must publish `products.validated.v1`; the Lake Writer consumes it.

Example:

```text
s3://data-platform/
  bronze/
    source=example/
      year=2026/
        month=09/
          day=03/
```

### Agent

Qoder + cheap model.

### Review

Qwen.

### Architectural review

Claude if schema evolution or partition strategy becomes problematic.

---

# 8. Milestone 4 — PostgreSQL Warehouse

## Objective

Create a serving/analytics layer.

### Tasks

```text
TASK-027
PostgreSQL schema

TASK-028
Database migrations

TASK-029
Warehouse loader

TASK-030
Idempotent loading

TASK-031
Indexes

TASK-032
Analytical SQL queries

TASK-033
Warehouse integration tests
```

### Required SQL examples

Implement queries involving:

- CTE
- `ROW_NUMBER`
- `RANK`
- `LAG`
- rolling average
- latest record
- price changes
- source statistics

### Acceptance

```text
Parquet
   ↓
Warehouse Loader
   ↓
PostgreSQL
   ↓
Analytical SQL
```

### Agent

Qoder + DeepSeek.

### Human focus

Understand and defend the data model.

This milestone should be treated as interview preparation.

---

# 9. Milestone 5 — End-to-End Vertical Slice + Initial Sources

## Objective

Connect the complete pipeline using real and deterministic reference sources before adding more infrastructure.

Initial source strategy:

```text
Fake Store API  ─┐
                 ├── Source Adapters → Canonical Event → Kafka → Processor → Parquet → PostgreSQL
Best Buy API    ─┘
```

### Tasks

```text
TASK-034
Source adapter interface and shared ingestion contract

TASK-035
Fake Store API adapter

TASK-036
Best Buy API adapter

TASK-037
End-to-end pipeline

TASK-038
End-to-end tests

TASK-039
Failure/replay demonstration (basic replay only; systematic failure matrix is M12)

TASK-040
Source-level metrics and freshness (PostgreSQL + structured logs; Prometheus deferred to M10) tracking
```

### Acceptance

At least one product observation from each initial source must be traceable through every layer.

The same downstream pipeline must process both sources without source-specific branching outside the adapter/normalization boundary.

The README should contain an example showing the complete journey of an event and the source adapter boundary.

### Important

**Do not proceed to Kubernetes until this works reliably.**

---

# 10. Milestone 5A — Marketplace Source

## Objective

Add eBay as a marketplace-style source after the canonical ingestion contract is stable.

### Tasks

```text
TASK-041
eBay API adapter

TASK-042
Marketplace listing model

TASK-043
Seller/listing normalization

TASK-044
Product/listing identity mapping

TASK-045
eBay integration tests
```

### Acceptance

The platform must represent multiple marketplace listings for the same logical product without breaking the canonical product-observation pipeline.

---

# 11. Milestone 5B — Web Retailer Source

## Objective

Add one real retailer website using HTTP or browser automation as required.

### Tasks

```text
TASK-046
Retailer source selection and adapter

TASK-047
HTML/dynamic-content parsing

TASK-048
Pagination and retry handling

TASK-049
Source-health metrics

TASK-050
Retailer integration tests
```

### Acceptance

The source may fail independently without causing silent data loss or downstream schema changes.

---

# 12. Milestone 5C — Difficult Source

## Objective

Introduce Amazon or an equivalent difficult source only after source abstraction, observability, and failure handling are established.

### Tasks

```text
TASK-051
Difficult-source adapter

TASK-052
Rate-limit/backoff strategy

TASK-053
Source degradation detection

TASK-054
Freshness failure scenarios

TASK-055
Difficult-source integration tests
```

### Acceptance

The platform must demonstrate graceful degradation when the source becomes unavailable, rate limited, structurally changed, or partially parseable.

The difficult source must remain replaceable without changing downstream architecture.

---

# 13. Milestone 6 — Data Quality + Airflow

## Objective

Introduce scheduled orchestration and quality monitoring.

### Tasks

```text
TASK-056
Data-quality framework

TASK-057
Quality result persistence

TASK-058
Airflow local deployment

TASK-059
ingestion_health DAG

TASK-060
daily_data_quality DAG

TASK-061
parquet_compaction DAG

TASK-062
build_daily_metrics DAG
```

### Acceptance

Airflow must be able to:

- detect missing/freshness problems
- execute data-quality checks
- record results
- execute scheduled transformations

Airflow must remain outside the real-time Kafka transport path.

Airflow is the owner of Gold dataset construction: it reads Silver Parquet, performs scheduled/batch transformations, and writes Gold Parquet. It does not load PostgreSQL directly; the Warehouse Loader owns the Gold-to-PostgreSQL boundary.

---

# 14. Milestone 7 — FastAPI

## Objective

Expose the platform through a clean API.

### Tasks

```text
TASK-063
FastAPI foundation

TASK-064
Product endpoints

TASK-065
Product history

TASK-066
Price analytics

TASK-067
Pipeline status API

TASK-068
Data-quality API

TASK-069
API tests
```

### Acceptance

The API must expose meaningful data generated by the pipeline.

---

# 15. Milestone 8 — Kubernetes with kind

## Objective

Deploy the platform locally on real Kubernetes.

### Tasks

```text
TASK-070
kind cluster and namespaces

TASK-071
Ingestion Deployment

TASK-072
Processor Deployment

TASK-073
Raw Writer Deployment

TASK-074
Lake Writer Deployment

TASK-075
Warehouse Loader Deployment

TASK-076
API Deployment

TASK-077
Kafka deployment/configuration for kind

TASK-078
Service definitions, ConfigMaps and Secrets

TASK-079
Health probes, resources and Kubernetes integration tests
```

### Required Kubernetes skills

You should personally practice:

```bash
kubectl get
kubectl describe
kubectl logs
kubectl exec
kubectl apply
kubectl delete
kubectl rollout
kubectl port-forward
kubectl get events
```

### Failure exercises

Intentionally create:

```text
CrashLoopBackOff
ImagePullBackOff
readiness failure
OOMKilled
missing configuration
```

Then diagnose them.

### Agent

Qoder generates manifests.

### Human

You diagnose and understand the cluster.

### Claude

Use for difficult Kubernetes failures.

---

# 16. Milestone 9 — Helm

## Objective

Package the platform cleanly.

### Tasks

```text
TASK-080
Helm chart structure

TASK-081
Values configuration

TASK-082
Environment-specific values

TASK-083
Helm deployment tests
```

### Acceptance

The platform can be deployed using:

```bash
helm install
```

Helm packaging must include configuration paths for Ingress, HPA, and NetworkPolicy. These resources may be disabled by default in local development, but their templates/values must have an explicit roadmap implementation path.

and configured for different environments.

---

# 17. Milestone 10 — Observability

## Objective

Make the platform operationally observable.

### Tasks

```text
TASK-084
Prometheus metrics

TASK-085
Grafana deployment

TASK-086
Platform dashboard

TASK-087
Data-quality dashboard

TASK-088
Kafka lag dashboard

TASK-089
Structured logging

TASK-090
OpenTelemetry

TASK-091
Distributed tracing
```

### Required dashboards

At minimum:

1. Platform health
2. Kafka/processing
3. Data quality
4. API
5. Agent

---

# 18. Milestone 11 — LangGraph Agent

## Objective

Add controlled Agentic AI capabilities after the underlying data platform is stable.

### Tasks

```text
TASK-092
Agent state model

TASK-093
Intent classifier

TASK-094
Read-only SQL and dataset metadata tools

TASK-095
Pipeline status tool

TASK-096
Data-quality tool

TASK-097
Source-health tool

TASK-098
LangGraph routing

TASK-099
Agent API

TASK-100
Agent tests
```

### Acceptance

The agent must answer questions such as:

```text
Which products had the largest price increases?

Why did observations drop yesterday?

Which sources have freshness problems?
```

It must use tools rather than hallucinating platform state.

---

# 19. Milestone 12 — Failure Engineering

## Objective

Demonstrate that the platform can recover from realistic failures.

### Tasks

```text
TASK-101
Kafka failure test

TASK-102
PostgreSQL failure test

TASK-103
Processor crash test

TASK-104
Duplicate/replay test

TASK-105
DLQ test

TASK-106
Source freshness failure

TASK-107
Recovery documentation
```

### Required demonstration

Show:

```text
Failure
  ↓
Detection
  ↓
Metric / log
  ↓
Recovery
  ↓
No silent data loss
```

This milestone has high portfolio value.

---

# 20. Milestone 13 — Performance Testing

## Objective

Measure the system under load.

### Tasks

```text
TASK-108
Load-test harness

TASK-109
100 events/sec

TASK-110
500 events/sec

TASK-111
1000 events/sec

TASK-112
Measure Kafka lag

TASK-113
Measure processing latency

TASK-114
Measure API latency

TASK-115
Document bottlenecks
```

Do not invent benchmark numbers.

Record actual results.

---

# 21. Milestone 14 — Terraform + AWS

## Objective

Deploy the platform to AWS.

### Tasks

```text
TASK-116
Terraform project structure

TASK-117
AWS networking

TASK-118
ECR

TASK-119
S3

TASK-120
RDS PostgreSQL

TASK-121
EKS, including reachable Kafka deployment in EKS

TASK-122
IAM

TASK-123
AWS deployment

TASK-124
CI/CD cloud deployment
```

### Target architecture

```text
AWS
│
├── VPC
│
├── EKS
│   ├── Kafka
│   ├── ingestion
│   ├── processor
│   ├── raw-writer
│   ├── lake-writer
│   ├── warehouse-loader
│   ├── API
│   └── agent
│
├── S3
│
├── RDS PostgreSQL
│
└── ECR
```

Kafka must be reachable from the EKS-hosted ingestion and processor services. The default portfolio topology is Kafka deployed inside EKS using Strimzi or equivalent Kubernetes manifests. Managed Kafka such as MSK is optional.

Do not introduce MSK merely to increase the technology count.

---

# 22. Milestone 15 — Production Polish

## Objective

Turn the repository into a strong portfolio project.

### Tasks

```text
TASK-125
Architecture documentation

TASK-126
ADRs

TASK-127
Failure demonstrations

TASK-128
Performance results

TASK-129
Security review

TASK-130
README rewrite

TASK-131
Architecture diagram

TASK-132
Demo walkthrough

TASK-133
Final code review
```

---

# 23. Final Portfolio Demonstration

The final README should demonstrate this sequence:

```text
1. Start the platform

2. Generate/ingest product observations

3. Observe Kafka events

4. Process with Polars

5. Write Parquet

6. Load PostgreSQL

7. Query analytics

8. Inspect Grafana

9. Ask the LangGraph agent a question

10. Demonstrate a failure

11. Recover

12. Run a load test

13. Show Kubernetes deployment

14. Show AWS architecture
```

This is much more compelling than a list of technologies.

---

# 24. Recommended Development Order

The practical order is:

```text
PROJECT.md
    ↓
SPECIFICATION.md
    ↓
AGENTS.md
    ↓
AGENT_WORKFLOW.md
    ↓
Milestone 0
    ↓
Milestone 1 — Kafka
    ↓
Milestone 2 — Processing
    ↓
Milestone 3 — Data Lake
    ↓
Milestone 4 — PostgreSQL
    ↓
Milestone 5 — Vertical Slice + Fake Store / Best Buy
    ↓
Milestone 5A — eBay Marketplace Source
    ↓
Milestone 5B — Retailer Web Source
    ↓
Milestone 5C — Difficult Source
    ↓
Milestone 6 — Airflow/Data Quality
    ↓
Milestone 7 — FastAPI
    ↓
Milestone 8 — Kubernetes
    ↓
Milestone 9 — Helm
    ↓
Milestone 10 — Observability
    ↓
Milestone 11 — LangGraph
    ↓
Milestone 12 — Failure Engineering
    ↓
Milestone 13 — Performance
    ↓
Milestone 14 — AWS
    ↓
Milestone 15 — Portfolio Polish
```

---

# 25. Agent Workflow Per Task

Every task should follow:

```text
1. Human selects TASK
        ↓
2. Qoder reads:
   PROJECT.md
   SPECIFICATION.md
   AGENTS.md
   AGENT_WORKFLOW.md
   TASK-xxx.md
        ↓
3. Qoder implements
        ↓
4. Qoder runs tests
        ↓
5. Qoder reviews git diff
        ↓
6. Qwen Code performs independent review
        ↓
7. Fix issues
        ↓
8. Claude Code consulted when required
        ↓
9. Human reviews
        ↓
10. Merge
```

---

# 26. Escalation Rules

Use a cheap model when:

```text
task is repetitive
requirements are clear
implementation is straightforward
```

Use Qoder's stronger model when:

```text
task requires repo-wide reasoning
multiple components interact
debugging requires context
```

Use Claude when:

```text
distributed-systems semantics are unclear
architecture trade-off is significant
production failure is difficult
Kubernetes behavior is difficult to diagnose
security implications are significant
performance bottleneck is unclear
```

Use Qwen Code when:

```text
you need an independent second opinion
```

---

# 27. Parallel Development Rules

Do not parallelize aggressively at the beginning.

During the foundation phase:

```text
ONE TASK
 ↓
ONE IMPLEMENTATION
 ↓
REVIEW
 ↓
MERGE
```

After the architecture stabilizes, parallel work may be used:

```text
              main
                │
        ┌───────┼────────┐
        ▼       ▼        ▼
      task A  task B    task C
      Qoder   Qoder     Qoder
        │       │        │
        └───────┼────────┘
                ▼
              Review
                │
              Merge
```

Only parallelize tasks that have clearly separated interfaces.

---

# 28. Definition of Milestone Complete

A milestone is complete when:

- all required tasks are implemented
- tests pass
- acceptance criteria pass
- integration behavior is demonstrated
- documentation is updated
- metrics/logging are present where required
- no unresolved critical review findings remain
- architecture remains consistent with `PROJECT.md`

---

# 29. The Human Learning Rule

AI must not remove the educational value of the project.

For each major technology, the human owner should understand the fundamentals sufficiently to explain and troubleshoot it.

Priority areas:

```text
Kafka
  partitions / offsets / consumer groups / rebalancing

Data Engineering
  ETL / ELT / lake / warehouse / schemas

Polars
  lazy execution / transformations / Parquet

PostgreSQL
  indexing / transactions / query plans / window functions

Airflow
  DAGs / scheduling / retries / dependencies

Kubernetes
  pods / deployments / services / probes / resources

AWS
  EKS / S3 / RDS / IAM

Observability
  metrics / logs / traces

Distributed Systems
  retries / idempotency / failure / replay
```

The AI writes much of the code.

**You must understand why the code works.**

---

# 30. Final Success Criterion

The project succeeds when an experienced engineer reviewing the repository can conclude:

> This is not a collection of AI-generated demos. The author understands distributed data systems, event-driven processing, data engineering, cloud infrastructure, Kubernetes, observability, and agentic AI, and has connected them into a coherent production-oriented architecture.