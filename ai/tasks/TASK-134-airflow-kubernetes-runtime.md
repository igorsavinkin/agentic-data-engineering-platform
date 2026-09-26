# TASK-134 — Productionize Airflow Runtime for Kubernetes

## Objective

Deploy the existing Airflow runtime into the local Kubernetes environment
and remove the temporary Docker + port-forward topology used by the
Airflow/PostgreSQL runtime verification.

## Required Context

Read current:

- `ai/PROJECT.md`
- applicable ADRs
- `ai/SPECIFICATION.md`
- `ai/ROADMAP.md`
- `ai/AGENTS.md`
- `ai/AGENT_WORKFLOW.md`
- `docs/architecture/platform-inventory-m13.md`
- `docs/runtime-verification/airflow-postgres-build-daily-metrics.md`

Higher-authority repository documents win on conflicts.

## Verified Starting Findings

The upstream runtime verification established that:

1. the Airflow image requires `polars`;
2. DAG runtime code requires actual `WAREHOUSE_DB_*` environment variables,
   not only `AIRFLOW_VAR_WAREHOUSE_DB_*`;
3. `ingestion_health` and `parquet_compaction` require
   `pydantic_settings`.

Treat the verification report as the authoritative evidence.

## Required Runtime

Move from:

Airflow Docker
→ host.docker.internal / port-forward
→ Kubernetes PostgreSQL

to:

Airflow Kubernetes
→ Kubernetes Service DNS
→ PostgreSQL / MinIO

Normal Airflow operation must not depend on `host.docker.internal` or
`kubectl port-forward`.

## Requirements

- Build a reproducible project Airflow image.
- Install required DAG dependencies at image build time, including
  `polars` and `pydantic-settings`.
- Do not use runtime `pip install` for required dependencies.
- Deploy Airflow using existing Kubernetes/Helm conventions.
- Select and document an executor appropriate for the current local
  Kubernetes environment; do not assume SequentialExecutor from the
  verification setup.
- Make all existing project DAGs discoverable without unresolved
  project dependency import errors.
- Provide actual `WAREHOUSE_DB_*` configuration to Airflow.
- Keep credentials out of source control and use the existing Kubernetes
  secret/configuration conventions.
- Connect to PostgreSQL through Kubernetes Service DNS.
- Connect MinIO-dependent DAGs through Kubernetes Service DNS.
- Keep Airflow metadata logically separate from the application warehouse.
- Preserve the existing architecture:
  Warehouse Loader loads Silver → PostgreSQL; Airflow performs downstream
  analytical/operational workloads.
- Do not introduce Gold Parquet storage.

## Runtime Verification

Verify from the Kubernetes-hosted Airflow runtime:

1. expected DAGs import successfully;
2. `build_daily_metrics` reads actual `product_observations`;
3. results are persisted into `daily_metrics`;
4. replay for the same logical date preserves existing idempotency;
5. `daily_data_quality`, `ingestion_health`, and `parquet_compaction`
   have documented import/runtime status;
6. Airflow remains operational after a relevant workload restart.

Record actual results only.

Create:

`docs/runtime-verification/airflow-kubernetes-runtime.md`

Clearly distinguish imported, executed, verified, not verified, and
deferred behavior.

## Tests

Add focused deterministic tests where appropriate and run the repository's
relevant quality checks.

Verify at minimum:

- Airflow image/dependency configuration;
- Kubernetes/Helm rendering or configuration;
- required environment contract;
- DAG importability;
- no regression to relevant existing platform behavior.

## Out of Scope

- EKS, RDS, S3 or other AWS provisioning
- Terraform AWS implementation
- production HA Airflow design
- unrelated DAG business-logic redesign
- Warehouse Loader redesign
- Kafka semantics changes
- Gold Parquet
- unrelated performance optimization

AWS infrastructure remains part of Milestone 14.

## Acceptance Criteria

- Project Airflow image builds reproducibly with required dependencies.
- Expected DAGs have no unresolved project dependency import errors.
- Airflow runs in the existing local Kubernetes environment.
- Airflow reaches PostgreSQL using Kubernetes Service DNS and
  `WAREHOUSE_DB_*`.
- MinIO-dependent workloads use Kubernetes-native connectivity.
- Required secrets are not committed in plaintext.
- `build_daily_metrics` executes against real warehouse data and persists
  results.
- Replay/idempotency behavior is verified.
- Remaining DAG import/runtime status is documented.
- Restart behavior is verified.
- Relevant automated checks pass.
- `docs/runtime-verification/airflow-kubernetes-runtime.md` contains actual
  runtime evidence.
- Existing platform architecture is preserved.

## Definition of Done

Acceptance criteria are verified, relevant tests and quality checks pass,
runtime evidence is documented, final diff contains only TASK-134 changes,
no secrets or unrelated architecture changes are introduced, and the task
is ready for independent Qwen review.

## Agent Instructions

Implement TASK-134 only.

Use the dedicated TASK-134 branch/worktree according to repository
governance. Do not modify the main worktree.

Do not invent runtime results or benchmark values. Escalate
architecture-significant conflicts instead of silently changing the
architecture.
