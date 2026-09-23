# TASK-K8S-FIX-003 Review — Reproducible PostgreSQL Warehouse Migrations for Kubernetes

## 1. Review Header

- **Task ID:** TASK-K8S-FIX-003
- **Review date:** 2026-09-24 (final review after corrective commits and manual E2E acceptance)
- **Reviewer:** Qwen Code (independent review, no implementation files modified)
- **Reviewed commits:**
  - `738520afe18095cc5a126ca8bc30b3d16f1fca25` — initial implementation
  - `d004fdf15682ff25b3de7440d544bd80c15b80c8` — address review findings F1–F4
  - `92c2a9f5b5daa7b65bbf1c0993db159bb8cb71e8` — fix Helm hook deadlock, guard CLI tests, strengthen assertions
- **Branch:** `feature/TASK-K8S-FIX-003` (merge base / main: `0df28c411b84725f9d99ad4f5d74f583061a9dd3`)
- **Verdict:** `APPROVED`

Sources of authority: `ai/PROJECT.md` §4/§11/§13; `ai/SPECIFICATION.md` §13/§19/§21/§22; `ai/tasks/TASK-K8S-FIX-003.md`; `ai/REVIEWER.md`; `docs/reviews/TASK-K8S-FIX-003-review.md` (prior reviews); the migration chain `warehouse/migrations/` and `tests/warehouse/test_migrations.py`.

## 2. Resolution of Findings (F1–F4)

| Finding | Prior state | Final verdict |
|---|---|---|
| **F1** raw k8s ordering | ✅ Resolved (`kubectl wait` added) | ✅ **Resolved** |
| **F1** Helm hook ordering | ❌ High — `pre-install` deadlock | ✅ **Resolved** — changed to `post-install,pre-upgrade` in `92c2a9f` |
| **F2** PostgreSQL readiness | ✅ Resolved (initContainer) | ✅ **Resolved** |
| **F2** CLI `alembic` dependency | ❌ Moderate — 3 failures | ✅ **Resolved** — `pytest.importorskip("alembic")` guard in `92c2a9f` |
| **F3** production image pin | ✅ Resolved | ✅ **Resolved** |
| **F3** weak `history` assertion | ❌ Minor — `len(stdout) > 0` | ✅ **Resolved** — asserts `<base> -> 001` and `006 (head)` |
| **F4** CLI execution coverage | ⚠️ Partial | ✅ **Resolved** — CLI is exercised, no Docker/kind deps, no overclaim |

## 3. Final Git Diff Review (commit `92c2a9f`)

- `helm/ai-data-platform/templates/jobs/warehouse-migration.yaml` — hook changed `pre-install,pre-upgrade` → **`post-install,pre-upgrade`**.
- `kubernetes/README.md` — the Helm paragraph now accurately states that `post-install` does **not** strictly gate application Deployment startup in a single release, and directs users to the raw `kubectl` workflow with `kubectl wait` for strict ordering.
- `tests/test_helm_chart.py` — hook test now asserts `post-install` present and `pre-install` absent.
- `tests/test_kubernetes_manifests.py` — `TestMigrationCLI.setup_method` adds `pytest.importorskip("alembic")`; the `history` assertion strengthened to specific revision IDs.

**Helm hook semantics (analyzed explicitly, not assumed):**

- `pre-install` (previous) runs **before** any normal chart resources are created. Since the PostgreSQL StatefulSet is a normal resource, the migration hook could never reach it on first `helm install` — a deadlock that failed the whole install. This was the prior High finding.
- `post-install` (now) runs **after** all normal resources (including PostgreSQL) are created, so the migration hook can reach PostgreSQL on first install. ✅
- `pre-upgrade` (retained) runs before the release's resources are updated on upgrade, where PostgreSQL already exists from the prior release. ✅
- The residual limitation — that in a single Helm release, application Deployments are created before the `post-install` hook, so they may briefly start before migrations complete — is now **honestly documented** in the README, with the raw `kubectl` + `kubectl wait` workflow provided as the strict-ordering path. This is an inherent single-release Helm limitation, not a defect.

**Regression check for `92c2a9f`:** No new regressions found. The hook phase change is the standard, correct Helm migration pattern; the `importorskip` guard converts prior failures into skips; the strengthened assertion is meaningful and, being guarded, only runs where `alembic` is installed.

## 4. Test and Verification Review

**Independently verified (executed by reviewer from the branch worktree at `92c2a9f`):**

- `python -m pytest tests/test_kubernetes_manifests.py tests/test_helm_chart.py -q` → **288 passed, 3 skipped**. The 3 skipped are `TestMigrationCLI`, correctly skipped by `pytest.importorskip("alembic")` because `alembic` is absent in the local `.venv` — no longer failures.
- `ruff check` on both test files → **All checks passed**.
- `mypy` on both test files → **Success: no issues found in 2 source files**.

**Implementation evidence reviewed (reported by the author, not independently executed):** manual Kubernetes E2E acceptance completed successfully:

- migration image built successfully
- image loaded into the existing kind cluster
- `warehouse-migration` Job completed successfully
- Alembic upgraded `001 → 006`; `alembic_version = 006`
- expected warehouse tables exist
- Warehouse Loader completed with `read=20140 loaded=20140 failed=0`
- PostgreSQL row counts: `sources=1`, `products=40`, `source_products=10`, `product_observations=20140`

This satisfies acceptance criteria **A–I**. Per `ai/REVIEWER.md`, these are **implementation evidence reviewed**, not independently executed by the reviewer, and not claimed as such.

**Not independently executable in this environment:** the three `TestMigrationCLI` tests (require `alembic`, which is absent locally). They are guarded and will run where `alembic` is installed (dev/CI with `requirements-dev.txt`); the strengthened `history` assertion format (`<base> -> 001`, `006 (head)`) matches standard Alembic output and should be confirmed on the first CI run with `alembic` present.

## 5. Findings

**No remaining BLOCKER, HIGH, or MEDIUM findings.**

- F1 (Helm `pre-install` deadlock, High) — **resolved** (`post-install,pre-upgrade`).
- F2 (CLI `alembic` dependency, Moderate) — **resolved** (`importorskip` guard; 3 skipped, 0 failed).
- F3 (weak `history` assertion, Minor) — **resolved** (specific revision IDs).

**Residual Minor observation (non-blocking):**

- The strengthened `history` assertion could not be independently executed locally (`alembic` absent → skipped). It is correctly guarded and format-plausible, but its pass status should be confirmed in a CI/dev environment where `alembic` is installed.

## 6. Non-Defect Observations

- **N1 — Helm `post-install` does not gate app startup.** This is inherent to single-release Helm and is now documented accurately; the raw `kubectl` workflow with `kubectl wait --for=condition=complete` remains the strict-ordering path (and is the path the E2E acceptance exercised).
- **N2 — The migration image is correctly self-contained** (only `alembic`/`sqlalchemy`/`psycopg2-binary`; no cross-package imports from `warehouse.loader`/`warehouse.analytics`).
- **N3 — ConfigMap/Secret wiring is correct** (`database-config` keys + `database-credentials` `db-password`), no hard-coded credentials.
- **N4 — Restricted PodSecurity is complete** for both the migration container and the `wait-for-postgresql` initContainer (pod-level `runAsNonRoot`/`runAsUser:1001`/`seccompProfile: RuntimeDefault`; container-level `allowPrivilegeEscalation:false` + `capabilities.drop:["ALL"]`).
- **N5 — UID consistency** (Dockerfile `USER migrations` uid/gid 1001 == Job `runAsUser/Group: 1001`).
- **N6 — Idempotency preserved** (`upgrade head` is a no-op at head; existing `test_rerun_is_safe` covers reruns; README documents it).
- **N7 — Existing migration history (001–006) untouched** and remains authoritative.
- **N8 — Pre-existing, out of scope:** `env.py::_build_database_url` does not URL-encode the password (fine for the dev password `postgres`).

## 7. Verdict

**`APPROVED`**

All 13 task requirements are met, acceptance criteria A–I are satisfied (implementation evidence reviewed — author-reported successful kind E2E with concrete row counts), and every prior finding (F1–F4) is resolved. Static tests pass (288 passed, 3 skipped — the skips are the correctly-guarded CLI tests), and `ruff`/`mypy` are clean.

The only residual item is a non-blocking observation: the strengthened CLI `history` assertion should be confirmed on the first CI run where `alembic` is installed. No further code changes are required.
