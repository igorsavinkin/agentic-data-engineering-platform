# TASK-K8S-FIX-001 Review — Local Kubernetes MinIO and PostgreSQL Infrastructure

## 1. Review Header

- **Task ID:** TASK-K8S-FIX-001 — Complete Local Kubernetes MinIO and PostgreSQL Infrastructure
- **Review date:** 2026-09-21
- **Reviewer:** Qwen Code (independent review, no implementation files modified)
- **Reviewed HEAD (commit):** `0b7cd8603ab1520c049acfbf03c27e05d4c40931` on `fix/TASK-K8S-FIX-001-local-stateful-infrastructure`
- **Merge base / prior HEAD:** `8d5ffa0ee26c9392e9ce03031789e8f0fd95792f` (`main`)
- **Commit reviewed:** `0b7cd86` — `fix(k8s): add local MinIO and PostgreSQL StatefulSet workloads`
- **Diff stat:** 11 files changed, +773 / −14
- **Verdict:** `CHANGES REQUIRED`

Sources of authority consulted: `ai/tasks/TASK-K8S-FIX-001.md`; `ai/AGENTS.md` §3/§7/§10/§14; `ai/REVIEWER.md` (referenced by the task); the existing Kubernetes Services (`kubernetes/deployments/minio-service.yaml`, `postgresql-service.yaml`), Secrets (`kubernetes/secrets/*`), and `scripts/create-local-secrets.sh`; the TASK-080–083 Helm implementation; `kubernetes/kind/kind-config.yaml`.

## 2. Requirements Coverage

| Requirement | Status | Evidence |
|---|---|---|
| MinIO Kubernetes workload | ✅ Met | `kubernetes/deployments/minio-statefulset.yaml` + Helm `templates/statefulsets/minio.yaml`. |
| PostgreSQL Kubernetes workload | ✅ Met | `kubernetes/deployments/postgresql-statefulset.yaml` + Helm `templates/statefulsets/postgresql.yaml`. |
| namespace `ai-data-platform` | ✅ Met | Both raw manifests and Helm templates use `ai-data-platform`. |
| Selected by existing Services | ✅ Met | Pod labels include `app.kubernetes.io/name: minio` / `postgresql`, which the existing Service selectors match. Verified by `test_*_pod_labels_match_service_selector`. |
| Existing Secret contract (no plaintext creds) | ✅ Met | `minio-credentials` (`minio-access-key`/`minio-secret-key`) and `database-credentials` (`db-password`) via `secretKeyRef`, matching the existing Secrets and `create-local-secrets.sh`. |
| Ports 9000/9001 (MinIO) and 5432 (PostgreSQL) | ✅ Met | Ports and the MinIO `--console-address :9001` arg are correct. |
| Liveness/readiness probes | ✅ Met | MinIO HTTP probes; PostgreSQL `pg_isready -U postgres` exec probes. |
| CPU/memory requests and limits | ✅ Met | Present in raw manifests, `values.yaml`, and `values-local.yaml`. |
| **PVC-backed data / restart persistence** | ❌ Not met | No `volumeClaimTemplates` (or any `volumes`/PVC) exists anywhere. See **F1**. |
| No real credentials committed | ✅ Met | Secret values are base64 local-dev placeholders only. |
| Helm reconciliation (raw vs Helm model) | ✅ Met (toggle) | `minio.enabled`/`postgresql.enabled` gate the StatefulSets; production disables them, matching the "managed RDS/S3" comment. |
| Kubernetes README / deployment sequence | ⚠️ Partially met | Deployment sequence updated, but the new README section claims PVC-backed storage and "PVCs should be Bound", which the manifests cannot satisfy. See **F1**. |

## 3. Git Diff Review

Single commit `0b7cd86` on top of `main` (`8d5ffa0`), so the merge-base (three-dot) diff is exactly this commit: 11 files, +773 / −14.

Files changed:

- `helm/ai-data-platform/templates/statefulsets/minio.yaml` (+82, new) — MinIO StatefulSet template.
- `helm/ai-data-platform/templates/statefulsets/postgresql.yaml` (+78, new) — PostgreSQL StatefulSet template.
- `helm/ai-data-platform/values.yaml` (+48/−2) — `minio`/`postgresql` enabled, image, resources, probes.
- `helm/ai-data-platform/values-local.yaml` (+20) — enables both with local resource requests/limits.
- `helm/ai-data-platform/values-production.yaml` (+9) — disables both (managed RDS/S3).
- `kubernetes/deployments/minio-statefulset.yaml` (+90, new) — MinIO StatefulSet.
- `kubernetes/deployments/postgresql-statefulset.yaml` (+86, new) — PostgreSQL StatefulSet.
- `kubernetes/README.md` (+48/−2) — structure list + deployment sequence + verification section.
- `scripts/verify_repository_structure.py` (+18/−10) — accepts `TASK-K8S-FIX-*` task filenames.
- `tests/test_helm_chart.py` (+82/−2) — chart structure, resource counts, StatefulSet tests.
- `tests/test_kubernetes_manifests.py` (+226) — StatefulSet/Service-compatibility tests.

**Scope correctness:** All changes belong to TASK-K8S-FIX-001. No unrelated architecture, dependency, or secret changes. The raw-manifest and Helm paths are intentionally parallel and consistent (same names, ports, probes, secrets, and the same missing-storage defect — see F1).

**Architectural changes:** The task explicitly preferred `StatefulSet + PVC`; StatefulSets were chosen as directed. The Services, ConfigMaps, Secrets, names, and ports are preserved.

**Debug/temp/dead code/secrets:** No secrets or debug artifacts. One minor dead-code branch in `scripts/verify_repository_structure.py` (see F3).

## 4. Test and Verification Review

**Tests added:** `tests/test_kubernetes_manifests.py` (+226) and `tests/test_helm_chart.py` (+82) cover: workload existence, namespace, labels vs Service selectors, ports, Secret references, probes, requests/limits, volume mounts, security context, Service stability, and the production-disable path.

**Independently verified (executed by reviewer):**

- `python -m pytest tests/test_kubernetes_manifests.py tests/test_helm_chart.py -q` → **240 passed**.
- `python -m ruff check scripts/verify_repository_structure.py tests/test_helm_chart.py tests/test_kubernetes_manifests.py` → **All checks passed**.
- `python -m mypy scripts/verify_repository_structure.py tests/test_helm_chart.py tests/test_kubernetes_manifests.py` → **Success: no issues found**.

The 240 passing tests coexist with the broken manifests because the suite never asserts that storage exists (F2). `PyYAML` had to be installed into `.venv` before the tests could collect; this is an environment note, not a defect in the commit.

**Unverified:** No live kind cluster was available, so AC2–AC8 (pods Ready, PVCs Bound, endpoints, in-cluster connectivity, restart persistence) were not exercised end to end. They are ruled *structurally* by F1: without a declared volume, the kubelet cannot mount `minio-data`/`postgresql-data`, the pods never become Ready, and no PVC is ever created.

## 5. Findings

### F1 — Critical — Neither StatefulSet declares any volume or PVC, so the workloads cannot start and AC3/AC7 are impossible

- **Files:** `kubernetes/deployments/minio-statefulset.yaml`, `kubernetes/deployments/postgresql-statefulset.yaml`, `helm/ai-data-platform/templates/statefulsets/minio.yaml`, `helm/ai-data-platform/templates/statefulsets/postgresql.yaml`.
- **Problem:** Each container declares a `volumeMount` (`minio-data` → `/data`; `postgresql-data` → `/var/lib/postgresql/data`), but the pod `spec` has **no `volumes:`** and the StatefulSet `spec` has **no `volumeClaimTemplates:`**. Independently confirmed: a repo-wide search for `volumeClaimTemplates|persistentVolumeClaim|storageClassName` returns zero matches in `kubernetes/`, and there is no `*.pvc.yaml` file anywhere in the repository.
- **Impact:** The kubelet cannot resolve the mounts — the pods remain non-Ready (stuck with a "MountVolume.SetUp failed … no such volume" event), so the endpoints stay `<none>`. No PVC is ever created, so the task's explicit **AC3** ("MinIO/PostgreSQL PVCs become `Bound`") and the "Persistent storage suitable for kind" scope item are unmet, and **AC7** (restart persistence) is impossible. This also makes the newly added README text ("PVC-backed storage", "PVCs should be Bound") and the manifests' own header comments ("Provides a PVC-backed … workload") inaccurate. The commit does not resolve the original `<none>` endpoint defect it was created to fix.
- **Recommendation:** Add a `volumeClaimTemplates` entry to each StatefulSet whose metadata name matches the corresponding `volumeMount` name (e.g. `minio-data`, `postgresql-data`). For kind, omit `storageClassName` to use the cluster's default local-path storage class, or set it explicitly after confirming `kubectl get storageclass`. Example for MinIO:

  ```yaml
  spec:
    serviceName: minio
    replicas: 1
    selector: { … }
    template: { … }
    volumeClaimTemplates:
      - metadata:
          name: minio-data
        spec:
          accessModes: ["ReadWriteOnce"]
          resources:
            requests:
              storage: 1Gi
  ```

  Apply the equivalent to PostgreSQL (`postgresql-data`).

### F2 — High — Required Test #9 ("PVC/storage configuration exists") is missing, so the suite certifies a broken manifest

- **Files:** `tests/test_kubernetes_manifests.py` (`test_minio_has_volume_mount`, `test_postgresql_has_volume_mount`), `tests/test_helm_chart.py` (`test_statefulsets_have_probes_and_resources`).
- **Problem:** The task's Required Tests item 9 explicitly mandates a check that "PVC/storage configuration exists." The added tests assert only that a `volumeMount` entry is present — never that a `volumeClaimTemplates` (or `volumes` PVC reference) exists with a matching name. Consequently all 240 tests pass while the manifests are non-functional (F1).
- **Impact:** False confidence: CI is green, but a fresh kind deployment cannot bring the workloads up. This is the gap that let F1 through.
- **Recommendation:** Add a test asserting each StatefulSet has a `volumeClaimTemplates` entry (or a `persistentVolumeClaim` volume) whose name equals the container's `volumeMount` name, plus a storage request. The test must go **red** against the current manifests and green only after F1's fix.

### F3 — Minor — Dead branch in `_parse_task_number`

- **File:** `scripts/verify_repository_structure.py`.
- **Problem:** In `_parse_task_number`, the branch `if suffix.startswith("K8S-FIX-") and suffix[8:11].isdigit(): return None` and the trailing `return None` are identical, so the `K8S-FIX-` condition is dead — the helper returns `None` either way. The caller's `path.name.startswith("TASK-K8S-FIX-")` guard is what actually skips these files, so behavior is correct, but the helper reads as though it special-cases `K8S-FIX` numbering when it does not.
- **Impact:** Maintainability only; no functional defect.
- **Recommendation:** Reduce the helper to a single `return None` after the numeric check (the K8S-FIX handling already lives in the caller), or return a dedicated sentinel if the distinction is meant to be meaningful.

## 6. Non-Defect Observations

- **N1 — Correct StatefulSet choice and Service/Secret preservation.** The existing ClusterIP Services' selectors (`app.kubernetes.io/name`) are matched by the pod labels, and the `minio-credentials`/`database-credentials` Secret keys align with `scripts/create-local-secrets.sh`. Names and ports are unchanged.
- **N2 — Sensible Helm enable toggle.** Default/local render the StatefulSets; production disables them (`enabled: false`) while the separate Service templates continue to render — consistent with the "managed RDS/S3" model and AC9.
- **N3 — PostgreSQL `PGDATA` subdirectory is a reasonable choice.** Pointing `PGDATA` at `/var/lib/postgresql/data/pgdata` is the standard pattern for the official image on a PVC, and will be correct once the volume actually exists.
- **N4 — Security context is appropriately scoped.** `allowPrivilegeEscalation: false`, `capabilities drop ALL`, and `RuntimeDefault` seccomp are set; the task explicitly cautions against blindly forcing `runAsNonRoot`, so its absence is not flagged here.

## 7. Verdict

**`CHANGES REQUIRED`**

The change is cleanly scoped, preserves the existing Service/Secret/port contracts, adds thorough static tests, and reconciles the raw-manifest and Helm paths with a sensible `enabled` toggle. All 240 tests pass, and `ruff`/`mypy` are clean.

However, the commit does not deliver the core requirement: **neither StatefulSet declares any storage** (no `volumeClaimTemplates`, no `volumes`, no PVC). The pods therefore cannot start, endpoints remain `<none>`, and PVCs can never become `Bound` — leaving the exact defect this corrective task exists to fix unresolved (AC3/AC7, and by extension AC2/AC4/AC5/AC6/AC8).

**F1 (Critical) is blocking.** F2 is a directly related test-coverage gap that must be closed so this class of defect cannot recur; F3 is a minor cleanup. F1 and F2 are localized fixes (add `volumeClaimTemplates` to two manifests and two Helm templates; add a storage assertion to the test suite) and do not require an architecture decision.
