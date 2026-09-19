# TASK-075 Review — Warehouse Loader Deployment (Round 2)

## 1. Review Header

- **Task ID:** TASK-075
- **Review date:** 2026-09-19
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:**
  `5cb3d15a9987a0fb32d507f70fa45747ea9d26b9..b27f7cd23b620b5587254b7f908726df33e3f5a3`
  (three commits: `f33e919` feat, `8745c41` fix, `b27f7cd` docs)
- **Reviewed HEAD:** `b27f7cd23b620b5587254b7f908726df33e3f5a3` on `feature/TASK-075`
- **Scope:** Kubernetes deployment for the Warehouse Loader service, its runtime
  entry point (`services/warehouse-loader/runner.py`), manifest tests, and
  `kubernetes/README.md` documentation.
- **Verdict:** **APPROVED WITH NON-BLOCKING FINDINGS**

This is a **round-2** review. Round 1 (recorded in commit `b27f7cd`) returned
**CHANGES REQUIRED** with two **Critical** findings in `runner.py`. Commit
`8745c41` (`fix(TASK-075): correct MinIOSettings import and use Silver layer`)
addresses both. This review re-evaluates the full range at HEAD, confirms the
fixes, and re-assesses the remaining findings.

---

## 2. Requirements Coverage

| # | Requirement | Status | Evidence |
|---|---|---|---|
| R1 | Add a Warehouse Loader Deployment (declarative manifest) | Met | `kubernetes/deployments/warehouse-loader-deployment.yaml` — `apps/v1/Deployment`, `name: warehouse-loader`, `namespace: ai-data-platform`. |
| R2 | Preserve the Parquet→PostgreSQL loading boundary | Met (with architecture note) | The deployment wires the existing `WarehouseLoader`; no boundary collapse. The loader reads **Silver**, not **Gold** — see finding **M2**. |
| R3 | Preserve idempotent loading | Met (inherited) | Runner invokes `WarehouseLoader.load_from_lake`; the pre-existing `batch_loader.py` keeps `INSERT … ON CONFLICT (event_id) DO NOTHING`. Unchanged by this task. |
| R4 | Externalize DB/storage config | Met | `WAREHOUSE_DB_HOST/PORT/NAME/USER/PASSWORD` and `APP_MINIO_ENDPOINT/ACCESS_KEY/SECRET_KEY` are env-driven; credentials sourced from `secretKeyRef` (`optional: true`). |
| R5 | Avoid concurrent migration ownership mistakes | Met | Deployment comment and runner docstring explicitly state "does NOT run Alembic migrations"; no migration command present. |
| R6 | Consistent labels/selectors | Met | `app.kubernetes.io/name|part-of|component`; selector matches template; mirrors `raw-writer`/`lake-writer`. |
| R7 | Never commit real secrets | Met | No credentials in the manifest; only `secretKeyRef` references (optional until TASK-078). |
| R8 | Remain Helm-compatible without implementing Helm | Met | Plain manifests; no Helm artifacts added. |
| R9 | No unrelated changes / no real secrets | Met | Diff limited to task-scoped files (plus the review doc itself); see §3. |
| R10 | Documentation updated | Met | `kubernetes/README.md` tree, image-load commands, and a Warehouse Loader section added. |
| R11 | Human Kubernetes practice (kubectl, not opaque automation) | Met | README documents `kubectl apply/get/logs` for the new Deployment. |
| R12 | Validate manifests/tests | Partial | Manifest structure tests added and passing; no test exercises `runner.py` — see **M1**. |

---

## 3. Git Diff Review

The range contains three commits:

- `f33e919` — `feat(TASK-075): Kubernetes Deployment for Warehouse Loader Service`
  (the initial implementation).
- `8745c41` — `fix(TASK-075): correct MinIOSettings import and use Silver layer`
  (fixes the two round-1 Critical findings).
- `b27f7cd` — `docs: Record TASK-075 Qwen review (CHANGES REQUIRED, round 1)`
  (the round-1 review artifact; expected under `docs/reviews/`).

Combined diffstat (implementation files, excluding the review doc):

| File | Change |
|---|---|
| `kubernetes/deployments/warehouse-loader-deployment.yaml` | new manifest (81 lines) |
| `services/warehouse-loader/__init__.py` | new package init (1 line) |
| `services/warehouse-loader/runner.py` | new runtime entry point (77 lines) |
| `tests/test_kubernetes_manifests.py` | new `TestWarehouseLoaderDeployment` (10 tests) |
| `kubernetes/README.md` | doc updates |

- **Scope correctness:** All implementation changes belong to TASK-075. The only
  additional file is `docs/reviews/TASK-075-review.md`, which is the authorized
  review artifact and is not an implementation change.
- **Unrelated changes:** None.
- **Architectural changes:** None introduced. The deployment wires the pre-existing
  `WarehouseLoader` without collapsing or altering service boundaries.
- **Accidental changes / debug code / generated artifacts / secrets:** None found.
- **Dependencies:** No new Python dependencies (`pyproject.toml` unchanged).
- **Branch/task isolation:** Reviewed on `feature/TASK-075`; working tree clean;
  the range contains only TASK-075 commits. Correct isolation.

---

## 4. Test and Verification Review

### Round-1 Critical findings — resolution confirmed

| Finding | Status | Evidence |
|---|---|---|
| **C1** `MinIOSettings` imported from wrong module | **Fixed** | `runner.py:19` now imports `from libs.common.minio_storage import MinIOSettings, MinIOStorage`. Independently verified `MinIOSettings`/`MinIOStorage` are defined in `libs/common/minio_storage.py`; `importlib.import_module('services.warehouse-loader.runner')` succeeds. |
| **C2** wrong lake layer (BRONZE default vs `silver` bucket) | **Fixed** | `runner.py:57` now calls `loader.load_from_lake(PartitionFilter(layer=LakeLayer.SILVER))`. Verified statically: `WarehouseLoader.__init__` builds `LakeReader(storage, bucket="silver")`, and `LazyScanner`/`list_partitions` use `layer.value` (`"silver"`) as the object prefix against the `silver` bucket. |

### Tests examined

- `tests/test_kubernetes_manifests.py::TestWarehouseLoaderDeployment` — 10 tests
  validating manifest structure (kind, namespace, labels, selector/template match,
  DB+MinIO env, absence of Kafka env, secret optionality, no inbound ports, and the
  `python -m services.warehouse-loader.runner` command). These validate **YAML only**;
  they never import or execute `runner.py`.
- Pre-existing warehouse-loader tests (`tests/warehouse/test_loader.py`,
  `tests/warehouse/test_idempotent_loader.py`) are `integration`-marked and exercise
  only `load_from_parquet_files`, not the `load_from_lake` path the runner uses.

### Test adequacy

The manifest tests are structurally sound and consistent with the sibling
`raw-writer`/`lake-writer` suites. However, there is still no unit test that imports
`services.warehouse-loader.runner` or asserts the loader is invoked with a `SILVER`
filter. This is why both round-1 Critical defects shipped green; see **M1**.

### Verification classification

- **Independently verified (reviewer-executed):**
  - `python -m pytest tests/test_kubernetes_manifests.py -q -m "not integration"` → **50 passed**.
  - `python -c "import importlib; importlib.import_module('services.warehouse-loader.runner')"` → **imports OK** (confirms C1 fixed).
  - `python -c "from libs.common.minio_storage import MinIOSettings, MinIOStorage; from libs.partitioning import LakeLayer; from libs.parquet_reader.reader import PartitionFilter; from warehouse.loader.batch_loader import WarehouseLoader"` → **all resolve**.
  - `python -m ruff check services/warehouse-loader/ kubernetes/ tests/test_kubernetes_manifests.py` → **All checks passed**.
  - `python -m pytest tests/warehouse/test_loader.py tests/warehouse/test_idempotent_loader.py -q -m "not integration"` → **14 deselected** (loader DB behavior is integration-gated and not run by default).
- **Implementation evidence reviewed:** the fix commit `8745c41` diff (3 insertions /
  3 deletions) is minimal and targeted; no other behavior changed.
- **Unverified:** end-to-end `python -m pytest -m integration` and any live
  `kubectl apply`/`logs` run. Not re-run here (requires Docker + PostgreSQL + MinIO).
  The loader read path was confirmed statically and via import probes instead.

---

## 5. Findings

### M2 — Moderate: Silver vs Gold architecture conflict (carried over, unresolved)

- **Severity:** Moderate
- **Affected:** `kubernetes/deployments/warehouse-loader-deployment.yaml` (comment),
  `kubernetes/README.md` ("reads Silver Parquet"), `services/warehouse-loader/runner.py`
  (docstring "Silver-to-PostgreSQL"), and pre-existing
  `warehouse/loader/batch_loader.py` (`bucket="silver"`).
- **Problem:** `PROJECT.md §4` and `SPECIFICATION.md §6.5` define the Warehouse Loader
  as loading **curated Gold Parquet datasets**; the task objective says "preserving
  Gold/Parquet→PostgreSQL". The actual loader reads **Silver**, and every new TASK-075
  artifact restates "Silver" verbatim.
- **Impact:** The normative Gold→Warehouse Loader→PostgreSQL boundary is not what the
  code implements. This is a pre-existing spec/code conflict (the loader has read Silver
  since Milestone 4, before Airflow Gold construction existed in Milestone 6) that
  TASK-075 perpetuates but does not introduce.
- **Recommendation:** Escalate for a human architectural decision. Either (a) the loader
  is later migrated to Gold once Airflow Gold construction is wired, or (b) governance
  docs are updated to reflect Silver as an explicit interim. This is an architecture
  change that is correctly **out of scope** for a deployment task per the TASK-075
  Engineering Rules ("Do not redesign application architecture merely to simplify
  Kubernetes" / "Implement this task only"), so it must not be silently "fixed" here.

### M1 — Moderate: no test coverage for the runtime entry point (carried over)

- **Severity:** Moderate
- **Affected:** `tests/test_kubernetes_manifests.py` (manifest-structure only); no
  `tests/**/test_warehouse_loader_runner*.py`.
- **Problem:** The only new tests validate YAML structure. `runner.py` is never imported,
  and the `load_from_lake` path the runner uses is untested. mypy also does not cover
  `services/` (`pyproject.toml` → `files = ["scripts", "tests", "libs"]`).
- **Impact:** Both round-1 Critical defects passed CI green (50 passed, ruff clean).
  The fixes are now in place, but a future regression in the import or the layer
  selection would again be invisible.
- **Recommendation:** Add a unit test that imports `services.warehouse-loader.runner`
  (catches C1-class regressions) and one that asserts the loader is invoked with a
  `SILVER` filter (catches C2-class regressions). Consider extending mypy coverage to
  `services/` (or at least this package) so a bad named import is caught statically.

### m1 — Minor: duplicated DB URL construction

- **Severity:** Minor
- **Affected:** `services/warehouse-loader/runner.py:34-40` (`_build_db_url`)
- **Problem:** Re-implements `DatabaseSettings.from_env()` from `services/api/config.py`,
  using the same `WAREHOUSE_DB_*` convention but a different scheme
  (`postgresql+psycopg2://` vs `postgresql://`), and it always emits `:password@` even
  when the password is empty (whereas `DatabaseSettings.from_env` omits it).
- **Impact:** Duplication and drift risk. Functionally correct today because
  `batch_loader._load_batch` normalizes `postgresql+psycopg2://` → `postgresql://`
  before connecting.
- **Recommendation:** Reuse `DatabaseSettings` (or extract a shared helper into
  `libs.common`) to eliminate the second URL builder.

### m2 — Minor: `MinIOStorage` never closed on shutdown

- **Severity:** Minor
- **Affected:** `services/warehouse-loader/runner.py:44-72` (`run`)
- **Problem:** `run()` has no `finally: storage.close()`, unlike
  `services/lake-writer/consumer.py`.
- **Impact:** The boto3 client is left open on termination; negligible for a long-lived
  loop (the OS reclaims the socket on process exit).
- **Recommendation:** Close the storage client on shutdown for symmetry with the lake
  writer.

---

## 6. Non-Defect Observations

- **No secrets committed:** confirmed; credentials are `secretKeyRef` (`optional: true`).
- **Correct network shape:** no inbound ports and no Kafka env — appropriate for a batch
  DB + object-store service; the manifest test asserts this.
- **Label/selector consistency:** matches the `raw-writer`/`lake-writer` convention
  (selector uses `name`+`part-of`; template additionally carries `component`).
- **Resource requests/limits** (`100m/256Mi` request, `500m/512Mi` limit) match siblings.
- **No liveness/readiness/startup probes:** consistent with sibling deployments; probes
  are deferred to TASK-079.
- **`APP_ENVIRONMENT=production` is required and correctly supplied:** `MinIOSettings`
  inherits `AppSettings.environment` (a required field); the manifest provides it.
- **No Dockerfile for `warehouse-loader`:** consistent with the sibling deployments; image
  build remains unreconciled downstream (the manifest references
  `ai-data-platform/warehouse-loader:dev`). Not a TASK-075 defect.
- **DB naming drift across environments:** the manifest defaults
  `WAREHOUSE_DB_HOST=postgresql`, `WAREHOUSE_DB_NAME=warehouse`, `WAREHOUSE_DB_USER=postgres`,
  whereas `docker-compose.yml` names differ. Separate environments; reconcile at the
  TASK-077 PostgreSQL work, not here.
- **Graceful shutdown granularity:** `SIGTERM`/`SIGINT` only set `_shutdown`; an in-flight
  load cycle is not interrupted, and the loop checks the flag every 1s. Acceptable for a
  batch loader.
- **Hyphenated service package names** (`services/warehouse-loader`) are non-idiomatic for
  `import` (and mypy flags them) but resolve via `python -m` and are consistent with the
  existing `lake-writer`/`raw-writer` services; not introduced by this task.
- **No ADRs present** in the repository; none apply to this deployment task.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The two **Critical** findings from round 1 are resolved and independently verified:

1. **C1** — `MinIOSettings` is now imported from `libs.common.minio_storage` (runner
   module imports successfully).
2. **C2** — `load_from_lake` is now called with `PartitionFilter(layer=LakeLayer.SILVER)`,
   matching the loader's `bucket="silver"` reader.

No Critical or High findings remain. The deployment manifest is well-formed, correctly
scoped, secret-free, and consistent with its siblings; the runtime entry point is now
importable and correctly targets the Silver layer.

The remaining findings are non-blocking:

- **M2 (Moderate)** — a pre-existing Silver-vs-Gold architecture conflict that requires a
  human decision, not a TASK-075 change (changing it would exceed deployment scope).
- **M1 (Moderate)** — add runtime entry-point test coverage so C1/C2-class regressions are
  caught by CI.
- **m1, m2 (Minor)** — DB-URL duplication and storage-client cleanup.

M2 should be recorded in `docs/reviews/FOLLOWUPS.md` (or escalated) with an owner
decision; M1 and the minors should be addressed in a cheap follow-up.
