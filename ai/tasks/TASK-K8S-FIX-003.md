# TASK-K8S-FIX-003 — Add reproducible PostgreSQL warehouse migrations for Kubernetes

## Status

In Progress

## Context

During manual Kubernetes E2E testing, warehouse-loader successfully connected to MinIO, discovered Silver partitions, read Parquet files, and connected to PostgreSQL, but failed on the first batch with:

```
psycopg2.errors.UndefinedTable: relation "sources" does not exist
```

The warehouse-loader runtime intentionally does not execute migrations. The repository contains the authoritative Alembic migration chain (`warehouse/migrations/versions/001-006`), but Alembic is only in `requirements-dev.txt` and no Kubernetes migration Job exists.

## Objective

Provide a reproducible Kubernetes mechanism for applying the existing warehouse Alembic migrations before warehouse-loader/API/Airflow depend on the warehouse schema.

## Requirements

1. Do NOT make warehouse-loader itself responsible for migrations.
2. Do NOT manually reproduce the schema with CREATE TABLE statements.
3. Alembic migrations remain the authoritative schema mechanism.
4. Provide a reproducible migration-capable container build (dedicated Dockerfile).
5. Add a Kubernetes Job for warehouse migrations executing `python -m warehouse.migrations upgrade head`.
6. Database configuration from existing ConfigMap `database-config` and Secret `database-credentials`.
7. Do not hard-code credentials.
8. Job must comply with restricted PodSecurity policy (securityContext).
9. Migration execution must be idempotent.
10. Add/update tests covering migration image/build, K8s Job structure, command, ConfigMap/Secret wiring, securityContext.
11. Update Kubernetes documentation with required deployment order.
12. Do not modify existing Alembic migration history.
13. Do not modify application service boundaries.

## Implementation

- `Dockerfile.migrations` — dedicated image with alembic + warehouse migrations
- `kubernetes/deployments/warehouse-migration-job.yaml` — K8s Job manifest
- `helm/ai-data-platform/templates/jobs/warehouse-migration.yaml` — Helm template
- `helm/ai-data-platform/values.yaml` — migration Job configuration
- `scripts/build-local-images.sh` — migration image build support
- Tests in `tests/test_kubernetes_manifests.py` and `tests/test_helm_chart.py`
- Updated `kubernetes/README.md` with migration step

## Acceptance Criteria

A. Build migration-capable image successfully.
B. Load image into existing kind cluster.
C. Run Kubernetes migration Job.
D. Job reaches Completed.
E. Verify alembic_version at head.
F. Verify expected warehouse tables exist.
G. Scale warehouse-loader back to 1.
H. Warehouse-loader completes load cycle without UndefinedTable.
I. Query PostgreSQL and verify actual product_observations rows.
