# TASK-K8S-FIX-003 Review — Reproducible PostgreSQL Warehouse Migrations for Kubernetes

## 1. Review Header

- **Task ID:** TASK-K8S-FIX-003
- **Review date:** 2026-09-24 (re-review after corrective commit)
- **Reviewer:** Qwen Code (independent review, no implementation files modified)
- **Reviewed commits:** `738520afe18095cc5a126ca8bc30b3d16f1fca25` (initial) + `d004fdf15682ff25b3de7440d544bd80c15b80c8` (corrective, "address review findings F1-F4")
- **Branch:** `feature/TASK-K8S-FIX-003` (merge base / main: `0df28c411b84725f9d99ad4f5d74f583061a9dd3`)
- **Corrective diff stat:** 6 files changed, +258 / −5
- **Verdict:** `CHANGES REQUIRED`

Sources of authority: `ai/PROJECT.md` §4/§11/§13; `ai/SPECIFICATION.md` §13/§19/§21/§22; `ai/tasks/TASK-K8S-FIX-003.md`; `ai/REVIEWER.md`; `docs/reviews/TASK-K8S-FIX-003-review.md` (prior review); the migration chain `warehouse/migrations/` and `tests/warehouse/test_migrations.py`.

## 2. Resolution of Previous Findings (F1–F4)

| Finding | Verdict | Detail |
|---|---|---|
| **F1** raw k8s ordering | ✅ **Resolved** | `kubernetes/README.md` no longer bulk-applies `kubernetes/deployments/`; it now applies infra → `kubectl apply warehouse-migration-job.yaml` → `kubectl wait --for=condition=complete job/warehouse-migration` → app services. |
| **F1** Helm hook ordering | ❌ **Not resolved — new High finding** | The migration Job is now a `pre-install,pre-upgrade` hook, which deadlocks on first install (see **F1-new** below). |
| **F2** PostgreSQL readiness | ✅ **Resolved** | `wait-for-postgresql` initContainer added (bounded socket loop), valid, ConfigMap-wired, restricted-PodSecurity-compliant, blocks the migration container. |
| **F3** production image pin | ✅ **Resolved** | `values-production.yaml` pins `images.warehouseMigration.tag: "1.0.0"`; `test_production_migration_image_not_dev` guards it. |
| **F4** CLI execution coverage | ⚠️ **Partially resolved** | New `TestMigrationCLI` does exercise the real CLI path without Docker/kind/PostgreSQL, but introduces an unguarded `alembic` dependency that fails the default suite when `alembic` is absent (see **F2-new** below). |

## 3. Git Diff Review (corrective commit `d004fdf`)

- `helm/ai-data-platform/templates/jobs/warehouse-migration.yaml` — adds `helm.sh/hook: pre-install,pre-upgrade`, `hook-weight: 0`, `hook-delete-policy: before-hook-creation`, and a `wait-for-postgresql` initContainer.
- `helm/ai-data-platform/values-production.yaml` — pins `images.warehouseMigration.tag: "1.0.0"`.
- `kubernetes/deployments/warehouse-migration-job.yaml` — adds the same `wait-for-postgresql` initContainer.
- `kubernetes/README.md` — replaces the bulk `kubectl apply -f kubernetes/deployments/` with ordered per-file applies and adds `kubectl wait` for Job completion; documents the initContainer and the Helm hook claim.
- `tests/test_helm_chart.py` — +4 tests (hook annotations, initContainer, initContainer securityContext, production image not `:dev`).
- `tests/test_kubernetes_manifests.py` — +9 tests (initContainer structure/image/command/env/securityContext/resources, and a new `TestMigrationCLI` of 3 subprocess tests).

**Scope correctness:** All changes are in-scope corrective work. No architectural boundary change, no secrets, no new third-party runtime dependency, no debug/dead code. `hook-delete-policy: before-hook-creation` is an appropriate choice (deletes the prior completed/failed hook Job before the next run, avoiding "Job already exists" on re-install/upgrade).

**Raw ↔ Helm consistency:** The initContainer is identical in the raw manifest and the Helm template (command, env, securityContext, resources). The hook annotations exist only in Helm, which is correct.

## 4. Test and Verification Review

**Tests examined:** 13 new tests in `d004fdf` (4 Helm + 9 manifest/CLI). The Helm tests assert hook annotations (`pre-install`/`pre-upgrade` in `helm.sh/hook`, `before-hook-creation`), initContainer presence, initContainer securityContext, and production image ≠ `:dev`. The manifest tests assert the initContainer name/image/command/env/securityContext/resources. The CLI tests run `python -m warehouse.migrations` via `subprocess` for: no-args usage, `history` (no DB), and unknown-command rejection.

**Independently verified (executed by reviewer from the branch worktree at `d004fdf`):**

- `python -m pytest tests/test_kubernetes_manifests.py tests/test_helm_chart.py -q` → **288 passed, 3 failed**.
  - The 3 failures are all in `TestMigrationCLI`, caused by `ModuleNotFoundError: No module named 'alembic'` in the local `.venv` (the CLI subprocess imports `alembic` at module load).
- `ruff check` on both test files → **All checks passed**.
- `mypy` on both test files → **Success: no issues found in 2 source files**.

**Implementation evidence reviewed (not rerun):** pre-existing `tests/warehouse/test_migrations.py` (integration-marked; exercises the Alembic API, not the CLI wrapper).

**Unverified (manual acceptance, not executed):** acceptance criteria A–I (image build, kind load, Job `Completed`, `alembic_version` at head, table existence, loader re-run, `product_observations` rows), and an actual `helm install`/`helm upgrade` run. These remain **UNVERIFIED** per `ai/REVIEWER.md`.

## 5. Findings

### F1 — High — Helm `pre-install` hook deadlocks on first install (regression from `d004fdf`)

- **Files:** `helm/ai-data-platform/templates/jobs/warehouse-migration.yaml` (`helm.sh/hook: pre-install,pre-upgrade`, `hook-weight: "0"`); `helm/ai-data-platform/templates/statefulsets/postgresql.yaml` (normal resource, no hook).
- **Problem (first-install semantics):** Helm executes `pre-install` hooks **before any normal chart resources are created**, and it blocks the release until the hook completes. On `helm install`, the migration Job (a `pre-install` hook) runs while the PostgreSQL StatefulSet is a *normal* resource that has not yet been created. The migration Job's `wait-for-postgresql` initContainer therefore cannot reach `postgresql:5432`; it retries 30×2s (~60s), the Job fails, `backoffLimit: 3` exhausts, and the hook failure fails the entire `helm install`.
- **Why the `pre-upgrade` half works but `pre-install` does not:** on `helm upgrade`, the PostgreSQL StatefulSet already exists from the prior release, so `pre-upgrade` can reach it. This is confirmed by the chart config: default/local `values.yaml` renders `postgresql.enabled: true` (in-cluster StatefulSet), whereas `values-production.yaml` sets `postgresql.enabled: false` (external RDS). So the deadlock is specific to the local-first path — the exact target of this task — while production (external DB) would coincidentally work.
- **Impact:** `helm install` with default/local values fails on first install. This is a regression: before `d004fdf`, the Job was a normal resource and the install did not deadlock (it merely lacked ordering). The README's new claim — "the migration Job runs automatically as a pre-install/pre-upgrade hook, ensuring migrations complete before application workloads start" — is factually wrong for first install.
- **Recommendation:** Use `post-install,pre-upgrade` (so the migration runs *after* PostgreSQL is created on first install, while `pre-upgrade` still orders it ahead of resource updates on upgrades), or document a two-phase install (infrastructure release, then app release with the hook). Note that `post-install` still leaves a startup race with app workloads, which is the inherent single-release limitation — if strict "before app services" ordering is required, the migration must live in a separate release or use a `post-install` hook combined with an app-side readiness gate. Correct the README claim accordingly.

### F2 — Moderate — `TestMigrationCLI` hard-depends on `alembic` without a skip guard (regression from `d004fdf`)

- **Files:** `tests/test_kubernetes_manifests.py` (`class TestMigrationCLI`, lines ~1573–1613).
- **Problem:** The three CLI tests invoke `python -m warehouse.migrations`, whose `run_migrations.py` imports `alembic` at module load. `alembic` is in `requirements-dev.txt` but **not** in `requirements.txt`, and the tests are neither `integration`-marked nor guarded with `pytest.importorskip`. As a result, the default (non-integration) pytest suite now requires `alembic`, and it fails outright when `alembic` is absent — reproduced independently here (3 failures, `ModuleNotFoundError: No module named 'alembic'`). The pre-existing alembic-dependent `tests/warehouse/test_migrations.py` is `integration`-marked (excluded by default), so this is an inconsistency in how alembic-dependent tests are handled.
- **Impact:** A minimal/partially-provisioned dev environment (base requirements + pytest, but without `alembic`) fails the default suite. In a fully-provisioned environment (`pip install -r requirements-dev.txt`) the tests pass.
- **Recommendation:** Guard each CLI test with `pytest.importorskip("alembic")` (or a module-level skip), or explicitly document/ensure `alembic` is a default-test dependency. This keeps the default suite robust while still exercising the CLI where `alembic` is available.

### F3 — Minor — CLI `history` assertion is trivially weak

- **Files:** `tests/test_kubernetes_manifests.py` (`test_cli_history_command_works_without_database`).
- **Problem:** The assertion `"001" in stdout or "rev" in stdout.lower() or len(stdout) > 0` accepts any non-empty stdout, so it does not meaningfully verify the history output (only that the subprocess produced something).
- **Impact:** Low — the test still verifies the CLI runs and returns 0 without a DB, but it would pass even if `history` output were malformed.
- **Recommendation:** Assert on a specific revision id (e.g. `"001"` and/or `"006"`) in the stdout rather than falling back to `len(stdout) > 0`.

## 6. Non-Defect Observations

- **N1 — F2 readiness gate is otherwise correct.** The `wait-for-postgresql` initContainer is a bounded `socket.create_connection` loop (30 attempts × 2s), reads `WAREHOUSE_DB_HOST`/`PORT` from `database-config`, uses the same migration image, and is restricted-PodSecurity-compliant (pod-level `runAsNonRoot`/`runAsUser:1001`/`seccompProfile` apply to init containers; container-level `allowPrivilegeEscalation:false` + `capabilities.drop:["ALL"]`). Kubernetes runs initContainers to completion before the migration container, so the migration cannot start before readiness succeeds. Minor note: it checks TCP connectivity only, not query-level readiness; acceptable for this use, and `backoffLimit: 3` provides additional retries.
- **N2 — F3 fix is correct.** `values-production.yaml` pins `warehouseMigration.tag: "1.0.0"`, and the guard test asserts the production image does not end in `:dev`.
- **N3 — F4 CLI tests correctly avoid Docker/kind/PostgreSQL.** They use `sys.executable -m warehouse.migrations` in a subprocess; no Docker/kind/database dependency, and they do not claim Kubernetes/Docker execution. The residual issue is only the unguarded `alembic` import (F2).
- **N4 — The initContainer uses inline `python -c "..."`.** Functional and stdlib-only, but a dedicated wait script would be more maintainable than a YAML-embedded multiline snippet.
- **N5 — Pre-existing, out of scope:** `env.py::_build_database_url` interpolates the DB password into the URL without URL-encoding (fine for `postgres`, breaks on special characters).

## 7. Verdict

**`CHANGES REQUIRED`**

Good progress: the raw-Kubernetes ordering (F1) is now correctly enforced with `kubectl wait`, the PostgreSQL readiness initContainer (F2) is valid and compliant, the production image is pinned (F3), and the CLI is genuinely exercised by tests (F4).

Two issues block acceptance:

1. **F1 (High)** — the Helm `pre-install` hook deadlocks on first install: it runs before the in-cluster PostgreSQL StatefulSet is created, so the migration hook can never connect and `helm install` fails with default/local values. The `pre-upgrade` half is correct; the `pre-install` half is not.
2. **F2 (Moderate)** — the new CLI tests hard-depend on `alembic` without a skip guard, causing 3 default-suite failures when `alembic` is absent (independently reproduced).

Additionally, manual acceptance criteria **A–I remain UNVERIFIED** and must be executed and evidenced before acceptance. `F3` (weak `history` assertion) is a minor non-blocking fix.

None of these requires an architecture decision; all are localized to the Helm hook phase, a test guard, a test assertion, and completion of the manual E2E run.
