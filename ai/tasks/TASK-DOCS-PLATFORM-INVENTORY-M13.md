# TASK-DOCS-PLATFORM-INVENTORY-M13 — Platform Architecture Inventory after Milestone 13

## Objective

Perform a repository-backed inventory of the platform after completion of
Milestone 13 and update the architecture documentation so that it describes
the actual implemented and measured system before Terraform/AWS work begins.

This task is documentation/architecture reconciliation.

Do not change production behavior.

## Context

The previous major architecture inventory was performed around Milestone 6.

Since then the platform has added:

- FastAPI serving layer
- Kubernetes deployment
- Helm packaging
- Prometheus / Grafana / OpenTelemetry observability
- LangGraph Data Engineer Agent
- failure engineering and replay mechanisms
- load/performance testing
- Kafka consumer-lag measurement
- processing-latency measurement
- API-latency measurement
- documented performance bottlenecks

The architecture documentation must now be reconciled with the actual
repository state after M13.

## Source of Truth

Use repository evidence, not assumptions.

Read, in authority order:

1. `ai/PROJECT.md`
2. relevant ADRs
3. `ai/SPECIFICATION.md`
4. implemented source code and deployment manifests
5. benchmark/performance artifacts from TASK-108–TASK-115
6. existing architecture documentation
7. `ai/ROADMAP.md`

When documentation and implementation disagree, document the discrepancy.
Do not silently change the architecture to match an old roadmap assumption.

## Required Inventory

### 1. Platform implementation status

Inventory Milestones M0–M13.

For every major subsystem classify it as:

- Implemented
- Implemented and E2E verified
- Implemented and measured
- Planned / target only

Do not mark something verified merely because code exists.

### 2. Actual runtime data flow

Verify the actual implemented data path from source to serving layer.

In particular verify the relationship between:

- Ingestion
- Kafka
- Raw Writer
- Processor
- Bronze
- Lake Writer
- Silver
- Warehouse Loader
- PostgreSQL
- Airflow
- Gold analytical tables
- FastAPI
- LangGraph Agent

Do not assume the original conceptual roadmap flow is still accurate.

### 3. Service inventory

Document every currently implemented service and its responsibility.

For each service identify:

- inputs
- outputs
- owned data
- external dependencies
- relevant Kafka consumer group where applicable
- deployment mechanism

### 4. Kafka inventory

Verify and document:

- topics
- partition counts/configuration
- producers
- consumer groups
- delivery semantics
- DLQ behavior
- lag monitoring

Distinguish configuration defaults from values observed in benchmark/runtime
environments.

### 5. Storage inventory

Document actual roles of:

- Bronze
- Silver
- PostgreSQL base tables
- PostgreSQL analytical / Gold tables

Explicitly state whether Gold exists as Parquet, PostgreSQL tables, or both,
based on implementation evidence.

### 6. Airflow inventory

Document implemented DAGs and their real data dependencies.

For every DAG identify:

input → operation → output

Do not describe Airflow as a mandatory linear stage if the implementation
does not behave that way.

### 7. Serving layer

Document:

- FastAPI
- principal endpoints/capabilities
- PostgreSQL dependency
- readiness/health behavior
- LangGraph Agent access path
- read/write boundaries

### 8. Kubernetes and Helm

Document the actual deployment topology:

- namespace
- Deployments
- Services
- ConfigMaps
- Secrets
- Jobs/init containers
- persistent/storage dependencies
- Helm chart structure

Separate local kind-specific configuration from future AWS production
architecture.

### 9. Observability

Inventory:

- Prometheus
- Grafana
- OpenTelemetry
- application metrics
- Kafka metrics
- health/data-quality metrics
- tracing

Distinguish implemented instrumentation from deployed/verified monitoring.

### 10. Reliability / failure engineering

Document implemented:

- retries
- idempotency
- replay
- DLQ
- circuit breakers where applicable
- deterministic storage keys
- failure recovery behavior

Only claim guarantees demonstrated by implementation/tests.

### 11. Performance evidence

Summarize TASK-108–TASK-115.

Clearly separate:

- configured target rate
- actual achieved rate
- Kafka consumer lag
- processing latency
- API latency
- observed bottlenecks
- hypotheses

Do not invent benchmark numbers.

Do not turn correlations into causal bottleneck claims without evidence.

### 12. Verified E2E paths

Document which paths have actually been demonstrated end-to-end.

Use explicit evidence where available.

Separate:

Implemented ≠ Tested ≠ E2E verified ≠ Performance measured.

### 13. Runtime reality vs conceptual architecture

Add a dedicated section comparing earlier conceptual architecture with
current implementation where they differ.

Example areas to verify:

- Silver → Warehouse Loader → PostgreSQL
- PostgreSQL → Airflow → analytical/Gold tables
- role of Airflow
- Gold storage semantics
- Agent access boundaries

### 14. Remaining roadmap

Clearly identify what remains after M13:

- M14 Terraform / AWS
- M15 Production Polish

Do not render these components as already implemented.

## Architecture Artifacts

Update existing architecture source files rather than creating competing
diagrams where possible.

Update at minimum:

- container/component architecture
- data-flow architecture
- rendered SVG versions

Diagrams must visually distinguish:

- implemented
- verified/measured where useful
- future/target components

AWS/Terraform must remain target/future at this point.

## Evidence

Architecture claims should point to relevant repository paths.

Examples:

- service implementation
- Kubernetes manifest
- Helm template
- DAG
- migration
- benchmark report
- observability implementation
- Agent implementation

The inventory should be auditable from the repository.

## Out of Scope

Do NOT:

- implement Terraform
- deploy AWS infrastructure
- redesign service boundaries
- optimize performance
- change benchmark results
- refactor production services
- fix unrelated issues
- change Kafka semantics
- change database schema

If an architectural problem is discovered, document it as a finding or
follow-up instead of silently fixing it.

## Acceptance Criteria

- [ ] M0–M13 implementation status is accurately inventoried.
- [ ] Actual runtime data flow is documented.
- [ ] Service boundaries match current implementation.
- [ ] Kafka producers/consumers/topics are inventoried.
- [ ] Bronze/Silver/Gold semantics match implementation.
- [ ] Warehouse Loader and Airflow roles are correctly represented.
- [ ] FastAPI serving architecture is documented.
- [ ] LangGraph Agent boundaries are documented.
- [ ] Kubernetes/Helm topology is documented.
- [ ] Observability stack is documented.
- [ ] Reliability/failure mechanisms are documented.
- [ ] TASK-108–115 evidence is summarized without invented measurements.
- [ ] Verified E2E paths are distinguished from merely implemented paths.
- [ ] Runtime-vs-conceptual architecture differences are explicitly documented.
- [ ] M14/M15 remain clearly marked as future work.
- [ ] Architecture DOT/source diagrams are updated.
- [ ] SVG diagrams are regenerated from their sources.
- [ ] Documentation contains repository evidence references.
- [ ] No production behavior is changed.
- [ ] Relevant documentation/structure checks pass.
- [ ] Architecture findings and follow-ups are documented.
- [ ] Findings distinguish confirmed facts, known limitations, and hypotheses.
- [ ] Relevant findings are assigned to M14, M15, or further investigation.
- [ ] No architectural finding is silently fixed by this documentation task.

## Deliverable

The result should provide a reliable architectural snapshot of the platform
at the end of Milestone 13 suitable for:

- planning M14 AWS/Terraform work
- onboarding developers and AI agents
- architecture review
- portfolio/interview explanation
- future production-readiness assessment

### 15. Architecture Findings and Follow-ups

Create a dedicated section in the architecture inventory:

`## Architecture Findings and Follow-ups`

Classify findings into:

### Confirmed
Architecture facts or limitations directly supported by repository,
runtime, test, or benchmark evidence.

### Known limitations
Implemented behavior that is intentionally limited or not yet
production-ready.

### Requires further investigation
Observed behavior for which the root cause has not been demonstrated.
Do not present hypotheses as confirmed bottlenecks or defects.

### Deferred to M14
Findings that should be addressed during Terraform / AWS work.

### Deferred to M15
Findings that belong to Production Polish.

Every finding must reference supporting repository or benchmark evidence
where available.

Do not fix findings as part of this task unless the change is strictly
documentation-only.
