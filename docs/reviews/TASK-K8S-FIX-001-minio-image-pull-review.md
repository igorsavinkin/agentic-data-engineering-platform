# TASK-K8S-FIX-001 (minio-image-pull) Review — MinIO Image Tag and PostgreSQL Security Context Follow-up

## 1. Review Header

- **Task ID:** TASK-K8S-FIX-001 (follow-up fix branch `fix/TASK-K8S-FIX-001-minio-image-pull`)
- **Review date:** 2026-09-21
- **Reviewer:** Qwen Code (independent review, no implementation files modified)
- **Reviewed HEAD (commit):** `d0672ada13b2e047169c8b435e34b3f016bf52cd` on `fix/TASK-K8S-FIX-001-minio-image-pull`
- **Merge base / prior HEAD:** `e0c67a1e80ad495f3ffe552929ce8fa3dbc04159` ("Qwen review of fix task: TASK-K8S-FIX-001 - Verdict: change required")
- **Commit reviewed:** `d0672ad` — `fix(TASK-K8S-FIX-001): correct MinIO image tag and PostgreSQL security context`
- **Diff stat:** 6 files changed, +92 / −8
- **Verdict:** `CHANGES REQUIRED`

Sources of authority consulted: `ai/tasks/TASK-K8S-FIX-001.md` (esp. the Security section); `ai/AGENTS.md` §3/§7/§10/§14; `ai/REVIEWER.md`; the prior review `docs/reviews/TASK-K8S-FIX-001-review.md`; `docker-compose.yml` (the local source of truth for the MinIO image); the raw manifests and Helm templates for MinIO/PostgreSQL.

## 2. Requirements Coverage

This is a corrective follow-up to the already-merged TASK-K8S-FIX-001 work, addressing two runtime defects discovered after the original merge. The relevant requirements are the task's Security guidance and the two concrete fixes.

| Requirement | Status | Evidence |
|---|---|---|
| MinIO image pullable / consistent with the established project version | ✅ Met | `kubernetes/deployments/minio-statefulset.yaml` and `helm/ai-data-platform/values.yaml` (`minio.image.tag`) bumped from `RELEASE.2024-10-02T17-50-41Z` to `RELEASE.2025-09-07T16-13-09Z`, matching `docker-compose.yml`. |
| PostgreSQL workload starts (security context compatible with the image) | ⚠️ Partially met | `capabilities.drop: [ALL]` removed from both the raw manifest and Helm template, so the `postgres:16` `gosu` entrypoint can drop to uid 999. However, the fix is a blanket capability restoration, not the least-privilege alternative. See **F1**. |
| Restrictive security settings where image compatibility permits (`ai/tasks/TASK-K8S-FIX-001.md` Security) | ❌ Not met | PostgreSQL loses `drop: ALL` entirely and runs as root with default capabilities; no `runAsNonRoot`/`runAsUser`/`fsGroup` replacement. See **F1**. |
| Regression tests for the two fixes | ⚠️ Partially met | MinIO image drift is guarded by `test_minio_image_matches_docker_compose`; the PostgreSQL security-context change has **no** test. See **F2**. |
| Scope discipline — only the active task, no unrelated changes (`ai/AGENTS.md` §3) | ⚠️ Partially met | Five of the six new tests cover volume-mount↔volumeClaimTemplate consistency, unrelated to either fix. See **F3**. |
| No secrets, no dependency/config churn beyond the fix | ✅ Met | Diff is two manifests, one Helm value, one Helm template, and two test files. No secrets, no new dependencies. |

## 3. Git Diff Review

Single commit `d0672ad` on top of the merge base `e0c67a1`, so the three-dot diff (`main...fix/TASK-K8S-FIX-001-minio-image-pull`) is exactly this commit: 6 files, +92 / −8.

Files changed:

- `kubernetes/deployments/minio-statefulset.yaml` (+1/−1) — MinIO image tag bump.
- `helm/ai-data-platform/values.yaml` (+1/−1) — `minio.image.tag` bump.
- `kubernetes/deployments/postgresql-statefulset.yaml` (−3) — removes `capabilities.drop: [ALL]`.
- `helm/ai-data-platform/templates/statefulsets/postgresql.yaml` (−3) — removes `capabilities.drop: [ALL]`.
- `tests/test_kubernetes_manifests.py` (+78) — 1 image-consistency test + 4 volume-mount/VCT tests.
- `tests/test_helm_chart.py` (+12) — 1 volume-mount/VCT test.

**Scope correctness:** The MinIO image fix and the PostgreSQL security-context change are both in-scope for TASK-K8S-FIX-001 (a corrective infra task). The raw-manifest and Helm paths are updated in parallel and consistently. No architecture, dependency, secret, or config-model change.

**Unrelated changes:** The volume-mount↔volumeClaimTemplate tests (5 of 6 new tests) are orthogonal to the image tag and security context — see **F3**. They are harmless (and pass), but they do not cover the stated fixes.

**Branch topology note:** The branch is **2 commits behind `main`** (missing `7d0430b` TASK-099 and `7709d88` TASK-100). Verified via `git diff --name-only e0c67a1..main`: those two commits touch only `services/agent/`, `services/api/`, and their tests — none of the files changed here. No conflict is expected, but the branch should be rebased/merged onto `main` before integration.

**Debug/temp/dead code/secrets:** None. No debug artifacts, no dead code, no secrets.

## 4. Test and Verification Review

**Tests added:** 6 total — `test_minio_image_matches_docker_compose` (relevant), plus 5 volume-mount/VCT consistency tests (unrelated; see F3).

**Independently verified (executed by reviewer):**

- `.venv\Scripts\python.exe -m pytest tests/test_kubernetes_manifests.py tests/test_helm_chart.py -q` → **249 passed** (243 on `main` + 6 new).
- `.venv\Scripts\python.exe -m ruff check tests/test_kubernetes_manifests.py tests/test_helm_chart.py` → **All checks passed**.
- `.venv\Scripts\python.exe -m mypy tests/test_kubernetes_manifests.py tests/test_helm_chart.py` → **Success: no issues found in 2 source files**.

**Unverified:** No live kind cluster or Docker daemon was used, so the following are **not** empirically confirmed: (a) that `RELEASE.2024-10-02T17-50-41Z` is no longer pullable and `RELEASE.2025-09-07T16-13-09Z` is pullable (inferred from the branch name and MinIO's known practice of retiring old `RELEASE.*` tags); (b) that `capabilities.drop: ALL` actually breaks `postgres:16` startup (inferred from the official image's `gosu` entrypoint needing `SETUID`/`SETGID`). These are the two premises the commit rests on and should be confirmed with `kubectl get pods` / `kubectl describe pod` during a real kind run.

## 5. Findings

### F1 — High — PostgreSQL `capabilities.drop: ALL` removal is an undocumented security downgrade; the fix should be non-root + `fsGroup`, not blanket capability restoration

- **Files:** `kubernetes/deployments/postgresql-statefulset.yaml` (securityContext at lines 80–83), `helm/ai-data-platform/templates/statefulsets/postgresql.yaml` (equivalent block).
- **Problem:** The commit deletes the entire `capabilities.drop: [ALL]` block from the PostgreSQL container, leaving only `allowPrivilegeEscalation: false` and `seccompProfile: RuntimeDefault`, with **no** `runAsNonRoot`, `runAsUser`, `runAsGroup`, or pod-level `fsGroup` added in its place. The container therefore runs as **root (UID 0)** with Kubernetes' full default capability set (`CHOWN`, `DAC_OVERRIDE`, `FOWNER`, `SETUID`, `SETGID`, `SETPCAP`, `NET_BIND_SERVICE`, `NET_RAW`, `SYS_CHROOT`, `MKNOD`, `AUDIT_WRITE`, `SETFCAP`).
- **Root cause (inferred):** the official `postgres:16` entrypoint runs as root and uses `gosu` to drop to uid 999; `gosu` requires `SETUID`/`SETGID`, so `drop: ALL` blocks startup. The removal is a compatibility workaround — but a blanket one.
- **Why it's a defect:** The task's Security section explicitly requests *"use restrictive security settings such as … dropping capabilities"* and only cautions against *"blindly"* forcing `runAsNonRoot`/numeric UID *without checking image and volume compatibility*. That is a warning to verify UID + volume ownership, not a license to run as root with full capabilities. The correct fix keeps `drop: ALL` and runs non-root: container-level `runAsNonRoot: true`, `runAsUser: 999`, `runAsGroup: 999`, plus pod-level `securityContext.fsGroup: 999` so the PVC is writable by uid 999. With a non-root entrypoint, `docker-entrypoint.sh` skips the `chown`/`gosu` path and runs `postgres` directly, so `drop: ALL` is fine. This violates `ai/AGENTS.md` §10 ("use … least privilege", "never bypass repository security controls for convenience").
- **Additional signal:** MinIO keeps `capabilities.drop: [ALL]` in the same commit while PostgreSQL loses it, with no comment or commit-message explanation of the asymmetry.
- **Recommendation:** Restore `capabilities.drop: ["ALL"]` and add the non-root + `fsGroup` settings above (verify the exact `postgres:16` uid, which is 999). If non-root is genuinely incompatible after verification in kind, at minimum drop all capabilities **except** the specific ones the entrypoint needs (`SETUID`, `SETGID`, `CHOWN`, `DAC_OVERRIDE`, `FOWNER`) and document the decision with an inline comment plus a follow-up task. Do not silently revert to full default capabilities.

### F2 — Moderate — No test covers the PostgreSQL security-context change

- **Files:** `tests/test_kubernetes_manifests.py`, `tests/test_helm_chart.py`.
- **Problem:** The commit title is "correct … PostgreSQL security context", yet none of the 6 new tests asserts it. The existing `test_postgresql_has_security_context` (and `test_minio_has_security_context`) only assert `allowPrivilegeEscalation is False`, which is true **both before and after** the removal — so the security downgrade is invisible to the suite. All 249 tests pass regardless of whether `drop: ALL` is present.
- **Impact:** A security regression merged with a green build; the "regression tests" the task asks for do not actually guard this fix.
- **Recommendation:** Add a test that pins the intended posture for both workloads — e.g. assert `capabilities.drop == ["ALL"]` and (once F1 is applied) `runAsNonRoot is True` and `fsGroup == 999`. The test must go red against the current manifests.

### F3 — Minor — Five of six new tests are unrelated to the two fixes (scope creep)

- **Files:** `tests/test_kubernetes_manifests.py` (class `TestStatefulSetVolumeMountPVCConsistency`, lines 1274–1316), `tests/test_helm_chart.py` (`test_statefulsets_volume_mounts_match_vct_names`).
- **Problem:** The volume-mount↔volumeClaimTemplate consistency tests verify a property that was already satisfied on `main` and is untouched by this commit. They are harmless and pass, but they give the commit the appearance of test coverage it does not actually provide for its stated purpose (image tag + security context). This is scope creep per `ai/AGENTS.md` §3.
- **Recommendation:** Keep `test_minio_image_matches_docker_compose`; move the volume-mount tests to a separate focused change, or retain them only if explicitly intended as incidental hardening — in which case the commit message should say so.

### F4 — Minor — Brittle test helper and inconsistent strictness between the two test layers

- **Files:** `tests/test_kubernetes_manifests.py` (`_persistent_volume_mount_names`, lines 1277–1295), `tests/test_helm_chart.py` (`test_statefulsets_volume_mounts_match_vct_names`).
- **Problem:** Two issues in the new test code:
  1. `_persistent_volume_mount_names` treats any non-`emptyDir` pod volume as "unresolved" — a future legitimate `configMap` or `secret` volume mount would be flagged as a missing VCT and fail spuriously. The method name is also misleading: it returns VCT-backed mounts *plus* unresolved mounts, not strictly "persistent" ones.
  2. The Helm test uses strict equality (`mount_names == vct_names`), while the k8s test tolerates `emptyDir`. The two layers now disagree on whether non-persistent mounts are allowed.
- **Impact:** Maintainability/robustness only; no current failure.
- **Recommendation:** In the helper, explicitly exclude `configMap`/`secret` (and any non-persistent) volume types alongside `emptyDir`, and reconcile the strictness so the Helm and k8s tests enforce the same rule.

## 6. Non-Defect Observations

- **N1 — The MinIO image fix is correct.** Aligning k8s with `docker-compose.yml` (`RELEASE.2025-09-07T16-13-09Z`) is the right approach, and `test_minio_image_matches_docker_compose` prevents future drift. The bump direction is sound given MinIO's practice of retiring old `RELEASE.*` tags.
- **N2 — Minimal and in-scope.** The change is two manifests, one Helm value, one Helm template, and two test files — no architecture change, no dependency change, no secrets.
- **N3 — MinIO retains full hardening.** MinIO keeps `allowPrivilegeEscalation: false` + `capabilities.drop: ALL` + `RuntimeDefault` seccomp, which is what makes the PostgreSQL asymmetry in **F1** stand out and need explanation.

## 7. Verdict

**`CHANGES REQUIRED`**

The MinIO image-tag fix and its regression test are correct, the change is minimal and in-scope, and all checks pass (249 tests, `ruff`, `mypy` clean).

The blocking issue is **F1**: the PostgreSQL `capabilities.drop: ALL` removal runs the database as root with full default capabilities, contradicting the task's own security guidance and `ai/AGENTS.md` §10, and it is undocumented. The correct fix is non-root (`runAsNonRoot`/`runAsUser`/`runAsGroup` = 999) with a pod-level `fsGroup: 999` and `drop: ALL` retained — the task's "do not blindly force `runAsNonRoot`" caveat is a call to verify compatibility, not to abandon least privilege.

**F2** must be closed so this class of security regression is caught by the suite. **F3** and **F4** are non-blocking test-quality issues. None of the findings requires an architecture decision; all are localized fixes to the manifests/templates and the test files.
