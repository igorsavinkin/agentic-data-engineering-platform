# TASK-DOCS — Platform Architecture Inventory after Milestone 13

## Objective

Create an evidence-based architecture and platform inventory representing
the actual implemented state of the Agentic Data Engineering Platform after
completion of Milestone 13 — Performance.

The inventory must describe what exists in the repository and what has been
verified through tests, E2E runs, runtime observations, and benchmarks.

It must distinguish:

- implemented architecture;
- runtime-verified architecture;
- implemented but not runtime-verified capabilities;
- known limitations;
- performance findings;
- future architecture planned for M14 and M15.

This is a documentation-only task.

Do not redesign, optimize, or modify runtime behavior.


## Motivation

The platform has evolved substantially since the previous architecture
inventory.

Milestones completed since earlier architecture documentation include
Kubernetes deployment, Helm packaging, observability, LangGraph agent
capabilities, failure engineering, and performance measurement.

TASK-108 through TASK-115 also produced new evidence about actual runtime
behavior and performance limitations.

The architecture documentation should now be reconciled with the repository
and runtime evidence before beginning Milestone 14 — Terraform / AWS.


## Sources of Truth

Follow repository authority rules.

Use, in order where applicable:

1. `ai/PROJECT.md`
2. Architecture Decision Records
3. `ai/SPECIFICATION.md`
4. implemented repository code/configuration
5. committed E2E and benchmark evidence
6. `ai/ROADMAP.md`

The ROADMAP describes intended work and must not override actual
implementation evidence.

Do not describe planned architecture as already implemented.


## Required Repository Inspection

Inspect the current repository rather than relying only on existing
architecture documentation.

At minimum inspect:

- `services/`
- `libs/`
- `airflow/`
- `sql/`
- `kubernetes/`
- `helm/`
- `terraform/`
- `monitoring/`
- `scripts/`
- relevant `docs/`
- ADRs
- benchmark artifacts
- E2E reports

Determine the actual implemented relationships between components.


## Actual Runtime Data Flow

Document the currently implemented runtime flow.

Verify it from repository evidence before documenting it.

The inventory should reconcile the implemented flow around:

```text
External Sources
      ↓
Ingestion
      ↓
Kafka — products.raw.v1
      │
      ├── Raw Writer
      │       ↓
      │     Bronze
      │
      └── Processor
              ↓
       products.validated.v1
              ↓
          Lake Writer
              ↓
            Silver
              ↓
       Warehouse Loader
              ↓
         PostgreSQL
          │       │
          │       └── LangGraph Agent
          │
          ├── FastAPI
          │
          └── Airflow analytical transformations
                    ↓
              analytical / Gold tables
```
Do not copy this diagram blindly.

Verify the actual implementation and correct the documentation if the
repository demonstrates a different runtime path.

Platform Inventory

Document the major implemented platform components.

For every component identify where applicable:

responsibility;
implementation location;
inputs;
outputs;
storage used;
communication mechanism;
deployment mechanism;
operational dependencies;
verification status.
Required Sections

The resulting architecture inventory should contain at least the following.

1. Platform Status

Summarize the implemented platform through Milestone 13.

Clearly distinguish completed functionality from future roadmap work.

2. Runtime Architecture

Document the actual runtime architecture and component relationships.

Include a concise architecture diagram.

3. Service Inventory

Document the implemented services:

ingestion;
processor;
raw-writer;
lake-writer;
warehouse-loader;
API;
agent;

and any additional runtime service discovered in the repository.

4. Kafka Architecture

Document:

brokers/runtime topology;
topics;
producers;
consumers;
partitioning where relevant;
event contracts;
delivery semantics;
idempotency behavior.

At minimum reconcile the current topics:

products.raw.v1
products.validated.v1
products.invalid.v1
pipeline.events.v1
data-quality.events.v1

5. Storage Architecture

Document actual usage of:

Bronze;
Silver;
Gold / analytical data;
MinIO / S3-compatible object storage;
PostgreSQL.

Explain which component writes and reads each layer.

6. Airflow

Document actual Airflow responsibilities.

Distinguish scheduled analytical/maintenance workflows from the streaming
runtime path.

Inspect implemented DAGs rather than assuming the conceptual ROADMAP flow.

Document relevant DAGs such as:

daily metrics;
data quality;
ingestion health;
Parquet compaction;

where confirmed by the repository.

7. Serving Layer

Document:

FastAPI;
PostgreSQL interaction;
key API responsibilities;
LangGraph Agent;
how the agent accesses platform data.

Do not claim capabilities that are only planned.

8. Kubernetes

Document the actual Kubernetes deployment model:

namespace;
Deployments / StatefulSets / Jobs;
Services;
ConfigMaps;
Secrets;
persistent storage;
migration mechanism;
readiness/liveness behavior where implemented.

Distinguish raw Kubernetes deployment from Helm deployment.

9. Helm

Document:

chart structure;
configurable components;
deployment responsibilities;
migration handling;
known Helm/runtime limitations.

10. Observability

Document implemented observability capabilities.

Inspect the repository for actual use of:

Prometheus;
Grafana;
OpenTelemetry;
application metrics;
health/readiness endpoints;
operational dashboards/alerts.

Do not mark a tool as operational merely because it appears in the
specification.

11. Reliability and Failure Engineering

Summarize implemented failure-handling capabilities from Milestone 12.

Include only repository-supported behavior such as:

retries;
idempotency;
duplicate handling;
malformed events;
dependency failures;
restart/recovery behavior;

where actually implemented.

12. Performance — Milestone 13

Summarize the authoritative results from TASK-108 through TASK-115.

Reference:

docs/performance/bottleneck-analysis.md

and the underlying benchmark artifacts.

Distinguish configured target rates from measured throughput.

At minimum include the authoritative producer throughput results:

Target	Measured throughput
100 eps  	95.55 eps
500 eps	    305.88 eps
1000 eps	333.43 eps

Do not infer complete downstream processing capacity from producer-side
throughput measurements.

Include TASK-114 API latency findings only as supported by committed
benchmark evidence.

Use TASK-115 classifications rather than inventing new root-cause claims.

13. Verified E2E Paths

Document which architecture paths have actually been demonstrated end-to-end.

Distinguish:

implemented;
tested;
runtime verified.

Include the source-to-PostgreSQL and PostgreSQL-to-API evidence where
supported by committed E2E reports.

14. Runtime Reality vs Conceptual Architecture

Explicitly identify differences between:

conceptual/project architecture;
ROADMAP assumptions;
actual current implementation.

This section is important.

For example, verify the actual relationship between Silver,
Warehouse Loader, PostgreSQL, Airflow, Gold/analytical tables, FastAPI,
and the Agent.

Do not silently rewrite the conceptual architecture to make it appear that
implementation matches the original design.

15. Architecture Findings and Follow-ups

Classify architecture findings into:

Confirmed

Architecture facts or limitations directly supported by repository,
runtime, test, or benchmark evidence.

Known Limitations

Implemented behavior that is intentionally limited or not yet
production-ready.

Requires Further Investigation

Observed behavior for which the root cause has not been demonstrated.

Do not present hypotheses as confirmed bottlenecks or defects.

Deferred to M14

Findings that naturally belong to Terraform / AWS work.

Deferred to M15

Findings that belong to Production Polish.

Every finding should reference supporting repository or benchmark evidence
where available.

Do not fix findings as part of this task unless the change is strictly
documentation-only.

16. Remaining Roadmap

Describe what remains after M13.

Clearly separate:

Milestone 14 — Terraform / AWS

Planned infrastructure/cloud work.

Milestone 15 — Production Polish

Planned production-readiness work.

Do not describe these capabilities as already implemented unless repository
evidence demonstrates otherwise.

Architecture Diagrams

Update or create architecture diagrams if the repository's existing
architecture diagrams no longer represent the implemented system.

Prefer source-controlled diagram formats already used by the repository
where available.

Diagrams must represent actual implementation.

Do not introduce a new diagramming technology unless necessary.

### Evidence Rules

All architecture claims must be traceable to repository evidence.

Use:

- source code;
- configuration;
- manifests;
- ADRs;
- tests;
- E2E reports;
- benchmark artifacts.

Existing documentation may be outdated and must be verified against the
implementation.

Do not invent benchmark results.

Do not infer root causes from performance observations.

Do not treat ROADMAP intentions as implementation evidence.

### Deliverables

Create or update the appropriate architecture documentation under:

docs/architecture/

The exact existing architecture document structure should be inspected
before deciding whether to update existing documents or create a new
inventory document.

At minimum the final documentation must provide:

current platform inventory;
actual runtime architecture;
data-flow diagram;
component/service inventory;
deployment architecture;
verified E2E status;
M13 performance summary;
architecture findings and follow-ups;
remaining M14/M15 boundary.
Scope Constraints

This task is documentation-only.

Do NOT:

modify application behavior;
modify infrastructure behavior;
refactor services;
change Kafka configuration;
change database schema;
optimize performance;
fix discovered runtime problems;
implement M14 or M15 work;
silently resolve architectural inconsistencies.

Document findings instead.

### Acceptance Criteria
 Repository has been inspected rather than relying solely on existing docs.
 Architecture documentation represents the actual implementation after M13.
 Current runtime data flow is documented.
 Service inventory is documented.
 Kafka architecture is documented.
 Bronze / Silver / Gold / PostgreSQL responsibilities are documented.
 Actual Airflow responsibilities are documented.
 FastAPI and LangGraph Agent serving paths are documented.
 Kubernetes deployment architecture is documented.
 Helm deployment architecture is documented.
 Implemented observability capabilities are documented.
 Reliability/failure-engineering capabilities are documented.
 TASK-108–115 performance findings are summarized using committed evidence.
 Verified E2E paths are identified.
 Conceptual architecture and runtime reality are explicitly reconciled.
 Architecture findings and follow-ups are documented.
 Findings distinguish confirmed facts, known limitations, and hypotheses.
 Relevant findings are assigned to M14, M15, or further investigation.
 Remaining M14/M15 work is clearly separated from implemented functionality.
 Existing architecture diagrams are updated where necessary.
 No runtime behavior is changed.
 No unsupported architecture or performance claims are introduced.
 Independent Qwen review passes according to the normal review workflow.