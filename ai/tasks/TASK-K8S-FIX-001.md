# TASK-K8S-FIX-001 — Complete Local Kubernetes MinIO and PostgreSQL Infrastructure

## Type
Corrective integration task / Milestone 8 remediation.

## Context
This issue was discovered during the manual halfway end-to-end Kubernetes test **after TASK-093 had already been implemented**.

Do **not** renumber, regenerate, or rewrite TASK-080–093. This is an out-of-band corrective task required to make the existing local kind deployment runnable end to end.

Manual verification showed:

```text
kubectl get endpoints -n ai-data-platform

kafka        10.244.0.5:9092,10.244.0.5:29092
minio        <none>
postgresql   <none>
```

The repository has Kubernetes Services for MinIO and PostgreSQL but no backing Kubernetes workloads. Docker Compose MinIO/PostgreSQL are intentionally stopped during kind deployment because their host ports conflict with kind.

This blocks Raw Writer, Lake Writer, Warehouse Loader, and FastAPI.

## Goal
Make the local kind deployment self-contained for MinIO and PostgreSQL so workloads can reach:

```text
minio:9000
postgresql:5432
```

Preserve existing Services, ConfigMaps, Secrets, service names, ports, application architecture, and later Helm work.

## Scope
Implement the minimum correct local-kind infrastructure:

- MinIO Kubernetes workload.
- PostgreSQL Kubernetes workload.
- Persistent storage suitable for kind.
- Liveness/readiness probes.
- CPU/memory requests and limits.
- Existing Secret integration.
- Existing Service selector compatibility.
- Kubernetes README/deployment-sequence update.
- Appropriate automated/static Kubernetes tests.
- Exact manual verification instructions.
- Reconcile the correction with TASK-080–083 Helm implementation.

Prefer `StatefulSet + PVC` for these stateful services unless higher-authority project documentation explicitly establishes another design. If it conflicts, stop and report the conflict.

## Out of Scope
Do not redesign Kafka, event contracts, Bronze/Silver/Gold, warehouse schema, LangGraph/TASK-092–093, AWS/EKS/RDS/S3, production HA, distributed MinIO, or introduce operators merely for technology count.

Do not reconnect Kubernetes Services to Docker Compose containers, create manual Endpoints as a workaround, change established ports without necessity, or commit real credentials.

## Inspect Before Editing
Inspect at minimum:

```text
ai/PROJECT.md
ai/SPECIFICATION.md
ai/ROADMAP.md
relevant ADRs
kubernetes/README.md
kubernetes/kind/kind-config.yaml
kubernetes/config/platform-config.yaml
kubernetes/config/database-config.yaml
kubernetes/secrets/minio-credentials.yaml
kubernetes/secrets/database-credentials.yaml
kubernetes/deployments/minio-service.yaml
kubernetes/deployments/postgresql-service.yaml
kubernetes/deployments/raw-writer-deployment.yaml
kubernetes/deployments/lake-writer-deployment.yaml
kubernetes/deployments/warehouse-loader-deployment.yaml
kubernetes/deployments/api-deployment.yaml
Helm files created by TASK-080–083
```

Because the repository is already through TASK-093, inspect current Helm behavior before implementing the correction. If Helm already defines these workloads, reconcile raw manifests with that established design rather than creating a competing design.

## Required Implementation

### PostgreSQL
Create the missing local Kubernetes PostgreSQL workload.

Requirements:
- namespace `ai-data-platform`;
- selected by existing `postgresql` Service;
- existing configuration/Secret contract;
- port 5432;
- suitable liveness/readiness checks;
- explicit requests/limits;
- PVC-backed data;
- restart without losing PVC-backed state;
- no real credentials in Git.

Do not assume Service selectors: inspect and preserve the existing selector contract.

### MinIO
Create the missing local Kubernetes MinIO workload.

Requirements:
- namespace `ai-data-platform`;
- selected by existing `minio` Service;
- existing MinIO Secret;
- API 9000 and console 9001 where expected by existing Service;
- suitable liveness/readiness checks;
- explicit requests/limits;
- PVC-backed object data;
- established project image/version where possible;
- no real credentials.

### Storage
Use PVCs compatible with the existing kind `local-path-storage` environment. Do not introduce cloud-specific storage classes.

Verify:

```bash
kubectl get storageclass
kubectl get pvc -n ai-data-platform
```

Claims must become `Bound`.

### Service compatibility
Preserve:

```text
kafka:29092
minio:9000
postgresql:5432
```

After deployment:

```bash
kubectl get endpoints -n ai-data-platform
```

must show real backend endpoints for all three. Merely creating Service objects does not satisfy this task.

### Configuration compatibility
Preserve the established ConfigMap/Secret model. Do not work around configuration validation defects in YAML. If the previously discovered cross-settings `APP_*` validation issue remains and blocks the workloads, stop and report it.

### Helm reconciliation
TASK-080–083 are already implemented. Inspect whether Helm currently creates MinIO/PostgreSQL, treats them as external, or only creates Services.

Raw Kubernetes and Helm deployment paths must have an intentional compatible model. Make a small Helm correction if required for consistency. If this becomes a significant architecture redesign, stop and escalate.

### Documentation
Update `kubernetes/README.md` so its deployment sequence actually creates runnable infrastructure:

```text
namespace
↓
ConfigMaps / Secrets
↓
Kafka
↓
MinIO workload + Service
↓
PostgreSQL workload + Service
↓
Kafka topics
↓
application workloads
↓
API
```

Document verification with Pods, PVCs, Services and endpoints.

## Acceptance Criteria

- **AC1:** Fresh kind deployment creates Kafka, MinIO and PostgreSQL workloads without Docker Compose dependencies.
- **AC2:** Infrastructure Pods become Ready.
- **AC3:** MinIO/PostgreSQL PVCs become `Bound`.
- **AC4:** `kubectl get endpoints -n ai-data-platform` no longer shows `<none>` for MinIO/PostgreSQL.
- **AC5:** Actual in-cluster connection to `postgresql:5432` succeeds; DNS-only proof is insufficient.
- **AC6:** Actual in-cluster connection to `minio:9000` succeeds; where practical verify authenticated access without printing secrets.
- **AC7:** Delete/restart MinIO and PostgreSQL Pods and verify minimal deterministic PVC-backed test state survives.
- **AC8:** Raw Writer, Lake Writer, Warehouse Loader and API are no longer blocked merely because MinIO/PostgreSQL have no endpoints. Do not hide unrelated application defects.
- **AC9:** Helm and raw Kubernetes paths use a documented compatible MinIO/PostgreSQL model.
- **AC10:** `kubernetes/README.md` accurately describes deployment and verification.

## Required Tests
Add/update repository-appropriate checks verifying at minimum:

1. MinIO workload exists.
2. PostgreSQL workload exists.
3. namespace is correct.
4. Pod labels match existing Service selectors.
5. expected ports exist.
6. Secrets are referenced rather than credentials hardcoded.
7. requests/limits exist.
8. probes exist.
9. PVC/storage configuration exists.
10. existing service names/ports remain stable.
11. Helm/raw-manifest assumptions are consistent where testable.

Extend existing Kubernetes test infrastructure rather than creating a duplicate framework. CI must not require live external MinIO/PostgreSQL.

## Manual Verification
After implementation:

```bash
kubectl get pods -n ai-data-platform
kubectl get pvc -n ai-data-platform
kubectl get services -n ai-data-platform
kubectl get endpoints -n ai-data-platform
kubectl get events -n ai-data-platform --sort-by='.lastTimestamp'
```

Expected endpoint concept:

```text
kafka        <pod-ip>:...
minio        <pod-ip>:9000,...
postgresql   <pod-ip>:5432
```

For failures use:

```bash
kubectl describe pod <pod> -n ai-data-platform
kubectl logs <pod> -n ai-data-platform
kubectl describe pvc <pvc> -n ai-data-platform
kubectl get events -n ai-data-platform --sort-by='.lastTimestamp'
```

Do not weaken probes or remove persistence merely to make status green.

## Security
Do not commit real secrets. Where image compatibility permits, use restrictive security settings such as `allowPrivilegeEscalation: false`, dropping capabilities and `RuntimeDefault` seccomp.

Do not blindly force `runAsNonRoot`/numeric UID without checking image and volume compatibility. The existing Kafka PodSecurity warning is not the primary scope unless it can be safely corrected without scope expansion.

## Definition of Done
Complete only when:
- own branch and commit;
- required tests pass;
- Qoder final checks pass;
- Qwen independent review completed;
- blocking/high findings resolved;
- Helm/raw Kubernetes assumptions reconciled;
- docs updated;
- human can deploy MinIO/PostgreSQL in kind;
- real MinIO/PostgreSQL endpoints appear;
- halfway E2E test can continue.

## Git Workflow
Suggested branch:

```text
fix/TASK-K8S-FIX-001-local-stateful-infrastructure
```

Before editing:

```bash
git status
git branch --show-current
git pull --ff-only
git switch -c fix/TASK-K8S-FIX-001-local-stateful-infrastructure
```

If dirty, stop. Do not auto-stash/reset/clean.

Before commit:

```bash
git status
git diff
```

Suggested commit:

```text
fix(k8s): add local MinIO and PostgreSQL workloads
```

Do not automatically merge or start another task.

---

# Qoder Execution Prompt

Implement `TASK-K8S-FIX-001` exactly as specified.

Important:
- repository has already progressed through TASK-093;
- do not renumber/regenerate/rewrite TASK-080–093;
- this is a corrective task discovered by manual halfway E2E testing;
- Kafka has a healthy endpoint;
- MinIO/PostgreSQL Services have `<none>` endpoints because no backing Kubernetes workloads exist;
- Docker Compose is not an acceptable workaround;
- inspect TASK-080–083 Helm implementation before choosing the correction;
- preserve service names, configuration contracts, Secrets and application architecture;
- keep scope minimal.

Follow project architecture authority and branch/process rules. Run focused tests during development and required final verification once immediately before commit.

At completion report:
1. files changed;
2. architecture used for MinIO/PostgreSQL;
3. Service selector/Pod-label relationship;
4. PVC/storage behavior;
5. Helm reconciliation;
6. tests/results;
7. exact manual kind verification commands;
8. commit hash.

Do not start another task.

---

# Qwen Independent Review Prompt

Review `TASK-K8S-FIX-001` according to `ai/REVIEWER.md`.

Focus on:
- whether the original `<none>` endpoint defect is genuinely solved;
- Service selector ↔ Pod label correctness;
- no Docker Compose dependency/workaround;
- PVC/storage correctness for kind;
- Secret handling;
- probes;
- image/security-context compatibility;
- resource requests/limits;
- PostgreSQL/MinIO initialization;
- restart persistence;
- TASK-080–083 Helm consistency;
- no unrelated architecture changes;
- documentation accuracy;
- useful static tests rather than superficial green checks.

Do not redesign the system.

Use established severity/blocking rules. Write only:

```text
docs/reviews/TASK-K8S-FIX-001-review.md
```

Do not modify implementation files.
