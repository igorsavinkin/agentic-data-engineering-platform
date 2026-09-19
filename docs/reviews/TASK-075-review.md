# TASK-075 Review — Warehouse Loader Deployment

## 1. Review Header

- **Task ID:** TASK-075
- **Review date:** 2026-09-19
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:**
  `5cb3d15a9987a0fb32d507f70fa45747ea9d26b9..f33e91900c13a8c2f9ca326d7dc58ea5e5d3e617`
  (single commit `f33e919` — `feat(TASK-075): Kubernetes Deployment for Warehouse Loader Service`)
- **Reviewed HEAD:** `f33e91900c13a8c2f9ca326d7dc58ea5e5d3e617` on `feature/TASK-075`
- **Scope:** Kubernetes deployment for the Warehouse Loader service, its runtime
  entry point (`services/warehouse-loader/runner.py`), manifest tests, and
  `kubernetes/README.md` documentation.
- **Verdict:** **CHANGES REQUIRED**

---

## 2. Requirements Coverage

| # | Requirement | Status | Evidence |
|---|---|---|---|
| R1 | Add a Warehouse Loader Deployment (declarative manifest) | Met | `kubernetes/deployments/warehouse-loader-deployment.yaml` (new, 81 lines) — `apps/v1/Deployment`, `name: warehouse-loader`, `namespace: ai-data-platform`. |
| R2 | Preserve the Parquet→PostgreSQL loading boundary | **Conflict** | The deployment wires the existing `WarehouseLoader`, but that loader reads **Silver** (`bucket="silver"`), while `SPECIFICATION.md §6.5`, `PROJECT.md §4`, and the task objective state **Gold**. See finding **M2**. |
| R3 | Preserve idempotent loading | Met (in intent) | The runner invokes `WarehouseLoader.load_from_lake`, whose pre-existing `batch_loader.py` implements `INSERT … ON CONFLICT (event_id) DO NOTHING` idempotency. Not altered by this task. |
| R4 | Externalize DB/storage config | Met | `WAREHOUSE_DB_HOST/PORT/NAME/USER/PASSWORD` and `APP_MINIO_ENDPOINT/ACCESS_KEY/SECRET_KEY` are env-driven; DB password and MinIO credentials sourced from `secretKeyRef` (`optional: true`). |
| R5 | Avoid concurrent migration ownership | Met | Deployment comment and runner docstring explicitly state "does NOT run Alembic migrations"; no migration command present. |
| R6 | Consistent labels/selectors | Met | Uses `app.kubernetes.io/name|part-of|component`; selector matches template; mirrors `raw-writer` / `lake-writer` deployments. |
| R7 | Never commit real secrets | Met | No credentials in the manifest; only `secretKeyRef` references (optional until TASK-078). |
| R8 | Remain Helm-compatible without implementing Helm | Met | Plain manifests; no Helm artifacts added. |
| R9 | No unrelated changes / real secrets | Met | Diff is limited to 5 task-scoped files; see §3. |
| R10 | Documentation updated | Met | `kubernetes/README.md` directory tree, load-image commands, and a Warehouse Loader section added. |
| R11 | Human Kubernetes practice (kubectl, not opaque automation) | Met | README documents `kubectl apply/get/logs` for the new Deployment. |
| R12 | Validate manifests/tests | **Partial** | Manifest structure tests added and passing, but no test exercises the new `runner.py` runtime entry point (see **M1**, **C1**, **C2**). |

---

## 3. Git Diff Review

Range contains a single commit (`f33e919`) touching 5 files, +242/−2:

- `kubernetes/README.md` — doc updates (tree, image-load commands, new section). In scope.
- `kubernetes/deployments/warehouse-loader-deployment.yaml` — new manifest. In scope.
- `services/warehouse-loader/__init__.py` — new package init. In scope.
- `services/warehouse-loader/runner.py` — new runtime entry point. In scope.
- `tests/test_kubernetes_manifests.py` — new `TestWarehouseLoaderDeployment` class. In scope.

- **Scope correctness:** All changes belong to TASK-075. No unrelated files touched.
- **Unrelated changes:** None.
- **Architectural changes:** None. The deployment does not collapse or alter service
  boundaries; it wires the pre-existing `WarehouseLoader` from `warehouse/loader/batch_loader.py`.
- **Accidental changes / debug code / generated artifacts / secrets:** None found.
- **Dependencies:** No new Python dependencies introduced (`pyproject.toml` unchanged).
- **Branch/task isolation:** Reviewed on `feature/TASK-075`, working tree clean; the range
  contains only the TASK-075 commit. Correct isolation.

One scope observation: the deployment references `image: ai-data-platform/warehouse-loader:dev`
and `APP_MINIO_ENDPOINT: http://minio:9000`, `WAREHOUSE_DB_HOST: postgresql`. No `Dockerfile`
exists anywhere in the repository yet, and the Kubernetes `minio` / `postgresql` services are
created in later tasks (TASK-077+). This is consistent with the sibling `lake-writer` /
`raw-writer` deployments, so it is not a TASK-075 defect, but the image build and K8s service
names remain unreconciled downstream.

---

## 4. Test and Verification Review

### Tests examined

- `tests/test_kubernetes_manifests.py::TestWarehouseLoaderDeployment` — 10 tests validating
  manifest file presence, `kind`, `namespace`, labels, selector/template match, DB+MinIO env,
  absence of Kafka env, secret optionality, absence of inbound ports, and module invocation
  command. These validate **YAML structure only** — they do not import or execute `runner.py`.
- Pre-existing warehouse-loader tests (`tests/warehouse/test_loader.py`,
  `tests/warehouse/test_idempotent_loader.py`) are `integration`-marked and exercise only
  `load_from_parquet_files`, never `load_from_lake` (the method the runner calls).

### Test adequacy

Inadequate for the runtime entry point. The two Critical defects below (wrong import, wrong
lake layer) both live in `runner.py` and are not caught by any test. No test imports
`services.warehouse-loader.runner`, so the `ImportError` at module load is invisible; no test
asserts the loader is invoked with a `SILVER`-layer `PartitionFilter`.

### Verification classification

- **Independently verified (reviewer-executed):**
  - `python -m pytest tests/test_kubernetes_manifests.py -q -m "not integration"` → **50 passed**.
  - `python -m ruff check services/warehouse-loader/` → **All checks passed** (note: ruff does
    not resolve cross-module named imports, so it does not flag the bad `MinIOSettings` import).
  - `python -c "from libs.common.config import MinIOSettings"` → **ImportError** (confirms C1);
    `from libs.common.minio_storage import MinIOSettings` → succeeds.
  - `python -m pytest tests/warehouse/test_loader.py -m "not integration"` → **8 deselected**
    (the loader's DB behavior is integration-gated and not run by default).
- **Implementation evidence reviewed:** none provided beyond the manifest tests (no evidence of
  a successful `kubectl apply`/logs run or an end-to-end load in the commit).
- **Unverified:** end-to-end `python -m integration` behavior and any live cluster run. Not
  re-run here (requires Docker + PostgreSQL + MinIO); the runtime defect was instead confirmed
  statically and via an import probe.

---

## 5. Findings

### C1 — Critical: `runner.py` imports `MinIOSettings` from the wrong module

- **Severity:** Critical
- **File / line:** `services/warehouse-loader/runner.py:19`
- **Problem:** `from libs.common.config import MinIOSettings` — `MinIOSettings` is defined in
  `libs.common.minio_storage`, not `libs.common.config`. This raises `ImportError` at module
  import time.
- **Impact:** `python -m services.warehouse-loader.runner` (the container `command`) crashes
  immediately, before `run()` is ever reached. The pod would `CrashLoopBackOff` and the
  warehouse loader never starts. Independently confirmed by import probe.
- **Recommendation:** Import from the correct module, matching every other service
  (`raw-writer`, `lake-writer`, Airflow DAGs):
  `from libs.common.minio_storage import MinIOSettings, MinIOStorage`.

### C2 — Critical: `runner.py` reads the wrong lake layer (BRONZE instead of SILVER)

- **Severity:** Critical
- **File / line:** `services/warehouse-loader/runner.py:57`
- **Problem:** `loader.load_from_lake(PartitionFilter())` uses the `PartitionFilter` default
  `layer=LakeLayer.BRONZE` (`libs/parquet_reader/reader.py`), but `WarehouseLoader` constructs
  its reader as `LakeReader(storage, bucket="silver")`
  (`warehouse/loader/batch_loader.py::WarehouseLoader.__init__`). Partition discovery builds the
  object prefix from the filter's layer, so it lists the `silver` bucket for a `bronze/` prefix,
  finds nothing, and `LazyScanner.scan()` raises `ValueError("No Parquet files found for
  layer=bronze …")`; `load_from_lake` re-raises.
- **Impact:** Even after C1 is fixed, every load cycle fails with "No Parquet files found" and
  no Silver data is ever loaded into PostgreSQL. The deployment is non-functional.
- **Recommendation:** Pass the correct layer explicitly:
  `loader.load_from_lake(PartitionFilter(layer=LakeLayer.SILVER))` (import `LakeLayer` from
  `libs.partitioning`), as the existing reader tests do.

### M1 — Moderate: no test coverage for the runtime entry point

- **Severity:** Moderate
- **File / line:** `tests/test_kubernetes_manifests.py` (only manifest-structure tests added);
  no `tests/**/test_warehouse_loader_runner*.py`
- **Problem:** The only new tests validate YAML structure. `runner.py` is never imported, and
  the loader's `load_from_lake` path (the path the runner uses) is untested anywhere.
- **Impact:** Both Critical defects shipped green: `pytest` passes (50 passed), `ruff` passes,
  and `mypy` does not cover `services/` (`pyproject.toml` → `files = ["scripts", "tests",
  "libs"]`). The Definition of Done's "relevant checks pass" and "acceptance behavior is
  demonstrated" are not satisfied for the actual runtime code.
- **Recommendation:** Add a unit test that imports `services.warehouse-loader.runner` (catches
  C1) and one that asserts the loader is invoked with a `SILVER` filter / that the runner passes
  `LakeLayer.SILVER` (catches C2). Consider extending mypy coverage to `services/`, or at least
  this package, so the bad named import is caught statically.

### M2 — Moderate: Silver vs Gold architecture conflict

- **Severity:** Moderate
- **File / line:** `kubernetes/deployments/warehouse-loader-deployment.yaml` (comment),
  `kubernetes/README.md` ("reads Silver Parquet"), `services/warehouse-loader/runner.py`
  (docstring "periodic Silver-to-PostgreSQL loading")
- **Problem:** `SPECIFICATION.md §6.5` and `PROJECT.md §4` define the Warehouse Loader as loading
  "curated Gold Parquet datasets", and the task objective says "preserving Gold/Parquet→
  PostgreSQL". The implementation (`warehouse/loader/batch_loader.py`, pre-existing) and all new
  TASK-075 artifacts describe and read **Silver**.
- **Impact:** The normative architecture (Gold → Warehouse Loader → PostgreSQL) is not what the
  code does; the new deployment manifest and docs restate "Silver" verbatim. This is a spec/code
  conflict that should be reconciled rather than silently accepted.
- **Recommendation:** Report/escalate the Gold-vs-Silver discrepancy for a human architectural
  decision. Either the loader must target Gold (per `SPECIFICATION.md §6.5`, once Airflow Gold
  construction exists), or the governance docs must be updated to reflect that the loader
  currently reads Silver as an interim. The deployment's wording should be aligned with whichever
  decision is made.

### m1 — Minor: duplicated DB URL construction

- **Severity:** Minor
- **File / line:** `services/warehouse-loader/runner.py:35-41` (`_build_db_url`)
- **Problem:** Re-implements `DatabaseSettings.from_env()` from
  `services/api/config.py`, using the same `WAREHOUSE_DB_*` convention but a subtly different
  scheme (`postgresql+psycopg2://` vs `postgresql://`).
- **Impact:** Duplication and drift risk between two DB URL builders.
- **Recommendation:** Reuse the shared `DatabaseSettings` (or extract a shared helper into
  `libs.common`).

### m2 — Minor: `MinIOStorage` never closed on shutdown

- **Severity:** Minor
- **File / line:** `services/warehouse-loader/runner.py:44-72` (`run`)
- **Problem:** `run()` has no `finally: storage.close()`, unlike `services/lake-writer/consumer.py`.
- **Impact:** Resource leak on termination (boto3 client left open); minor for a long-lived loop.
- **Recommendation:** Close the storage client on shutdown.

---

## 6. Non-Defect Observations

- **No secrets committed:** confirmed; credentials are `secretKeyRef` (optional until TASK-078).
- **Correct network shape:** no inbound ports, no Kafka env — appropriate for a batch
  DB + object-store service. Manifest test asserts this.
- **Label/selector consistency:** matches the `raw-writer`/`lake-writer` convention (selector uses
  `name`+`part-of`; template additionally carries `component`).
- **Resource requests/limits** (`100m/256Mi` request, `500m/512Mi` limit) match sibling deployments.
- **No liveness/readiness probes:** consistent with sibling deployments; probes are deferred to
  TASK-079.
- **DB naming drift across environments:** the manifest defaults `WAREHOUSE_DB_HOST=postgresql`,
  `WAREHOUSE_DB_NAME=warehouse`, `WAREHOUSE_DB_USER=postgres`, whereas `docker-compose.yml` names
  the service `postgres` with `POSTGRES_DB/USER=platform`. These are separate environments and the
  K8s PostgreSQL is created in TASK-077; reconcile there rather than in this task.
- **Graceful shutdown granularity:** `SIGTERM`/`SIGINT` only set `_shutdown`; an in-flight load
  cycle is not interrupted, and the sleep loop checks the flag every 1s. Acceptable for a batch
  loader; worst-case shutdown latency is one load cycle plus interval.
- **Hyphenated service package names** (`services/warehouse-loader`) are non-idiomatic for Python
  tooling (mypy reports "not a valid Python package name") but resolve at runtime via `-m` and
  are consistent with the existing `lake-writer`/`raw-writer` services; not introduced by this task.

---

## 7. Verdict

**CHANGES REQUIRED**

Two Critical defects in the newly-added runtime entry point
(`services/warehouse-loader/runner.py`) make the deployment non-functional:

1. **C1** — `MinIOSettings` is imported from `libs.common.config` instead of
   `libs.common.minio_storage`, causing an `ImportError` at startup (crash loop).
2. **C2** — `load_from_lake(PartitionFilter())` uses the default `BRONZE` layer against the
   `silver` bucket, so the loader finds no partitions and fails every cycle.

Both must be fixed before acceptance. The manifest structure itself is sound and the task is
otherwise well-scoped (no secrets, no unrelated changes, consistent labels/config), but the
runtime code it deploys cannot start and would not load data. The Silver-vs-Gold architecture
conflict (M2) should also be resolved, and runtime-path test coverage (M1) should be added so
these defects are caught by CI.
