# TASK-076 Review — API Deployment

## 1. Review Header

- **Task ID:** TASK-076
- **Review date:** 2026-09-19
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:**
  `7fa116c5064be971f2c23268e8af581ce3272743..bd675c5835cc31baf202101069d7d6cbc84a68dd`
  (single commit: `bd675c5` — `feat(TASK-076): Kubernetes Deployment and Service for API`)
- **Reviewed HEAD:** `bd675c5835cc31baf202101069d7d6cbc84a68dd` on `feature/TASK-076`
- **Scope:** Kubernetes Deployment + ClusterIP Service for the FastAPI service,
  database configuration via Secret references, liveness/readiness probe wiring,
  manifest validation tests, and `kubernetes/README.md` documentation.
- **Verdict:** **APPROVED WITH NON-BLOCKING FINDINGS**

---

## 2. Requirements Coverage

| # | Requirement | Status | Evidence |
|---|---|---|---|
| R1 | Deploy FastAPI with Deployment + Service | Met | `kubernetes/deployments/api-deployment.yaml` (`apps/v1/Deployment`, `name: api`) and `kubernetes/deployments/api-service.yaml` (`v1/Service`, `type: ClusterIP`, `name: api`). |
| R2 | Configure DB via Secret references | Met | `WAREHOUSE_DB_HOST/PORT/NAME/USER` externalized via `env`; `WAREHOUSE_DB_PASSWORD` sourced from `secretKeyRef` (`name: api-secrets`, `key: db-password`, `optional: true`). No literal password. |
| R3 | Expose established health/readiness endpoints | Met | `livenessProbe` → `GET /api/v1/health`; `readinessProbe` → `GET /api/v1/ready`. Paths verified against `services/api/routes/v1/health.py` + `app.include_router(v1_router, prefix="/api/v1")`. |
| R4 | Document kubectl port-forward | Met | README "API (TASK-076)" section documents `kubectl port-forward svc/api 8000:8000 -n ai-data-platform` and `curl http://localhost:8000/api/v1/health`. |
| R5 | No Ingress unless higher docs require it | Met | No Ingress manifest added; `SPECIFICATION.md §19` lists Ingress as a later (Milestone 9/Helm) feature, so omission is correct. |
| R6 | Preserve service boundaries / canonical data flow | Met | Deployment runs the existing `python -m services.api` entry point unchanged; no architectural change; the API remains a read-only serving layer (PROJECT.md §4). |
| R7 | Consistent labels/selectors | Met | `app.kubernetes.io/name|part-of|component`; Service selector (`name`+`part-of`) is a subset of the template labels; mirrors sibling deployments. |
| R8 | Never commit real secrets | Met | No credential values; only `secretKeyRef` references. |
| R9 | Remain Helm-compatible without implementing Helm | Met | Plain declarative manifests; no Helm artifacts. |
| R10 | Validate manifests/tests | Met | 17 new manifest tests added (`TestAPIDeployment` + `TestAPIService`); independently verified passing. |
| R11 | Documentation updated | Met | `kubernetes/README.md` tree, image-load commands, and a dedicated API section updated. |
| R12 | No unrelated changes / no real secrets | Met | Diff limited to four task-scoped files (see §3). |

---

## 3. Git Diff Review

Single commit in range (`bd675c5`). Diffstat:

| File | Change |
|---|---|
| `kubernetes/deployments/api-deployment.yaml` | new manifest (70 lines) |
| `kubernetes/deployments/api-service.yaml` | new manifest (19 lines) |
| `tests/test_kubernetes_manifests.py` | +17 manifest tests |
| `kubernetes/README.md` | tree, image-load, and API section updates |

- **Scope correctness:** All changes belong to TASK-076. No application code was
  modified — the deployment wires the pre-existing `services.api` application.
- **Unrelated changes:** None.
- **Architectural changes:** None. The API stays a read-only serving layer; no
  boundary collapse, no Kafka/MinIO coupling introduced.
- **Accidental changes / debug code / generated artifacts / secrets:** None found.
  The only credential handling is `secretKeyRef` with `optional: true`.
- **Dependencies:** `pyproject.toml` unchanged; no new Python dependencies.
- **Configuration/infrastructure changes:** Two new manifests (Deployment + Service),
  consistent in shape with `warehouse-loader`/`lake-writer` siblings. No changes to
  kind config, namespace, or CI.
- **Branch/task isolation:** Reviewed on `feature/TASK-076`; working tree clean; the
  range contains exactly one TASK-076 commit. Correct isolation.

---

## 4. Test and Verification Review

### Tests examined

- `tests/test_kubernetes_manifests.py::TestAPIDeployment` — 11 tests: existence,
  resource kind, namespace, labels, selector/template match, DB env presence
  (HOST/PORT/NAME), port 8000 exposure, liveness probe path, readiness probe path,
  secret optionality, and `python -m services.api` command.
- `tests/test_kubernetes_manifests.py::TestAPIService` — 6 tests: existence, resource
  kind, namespace, labels, selector→deployment-template match, and port 8000.

These validate **manifest structure only** (YAML file content), which is the correct
level for a deployment-only task. The actual health/readiness endpoint behavior is
already covered by the TASK-063/TASK-069 API test suite, not re-exercised here.

### Verification classification

- **Independently verified (reviewer-executed):**
  - `python -m pytest tests/test_kubernetes_manifests.py -v` → **67 passed** (0.77s).
  - `python -m ruff check tests/test_kubernetes_manifests.py` → **All checks passed**.
  - `python -m mypy tests/test_kubernetes_manifests.py` → **Success: no issues found**.
  - Static confirmation that `services/api/__main__.py` exists and runs
    `uvicorn.run("services.api.app:create_app", factory=True)`, so
    `command: ["python", "-m", "services.api"]` is a valid entry point.
- **Implementation evidence reviewed:** the commit diff is minimal and targeted;
  manifest YAML parses successfully (confirmed by the passing `_load_yaml`-based tests).
- **Unverified:** `python -m pytest -m integration` and any live
  `kubectl apply/get/logs/port-forward` run. Not re-run here — they require Docker,
  a kind cluster, built `ai-data-platform/api:dev` image, and a PostgreSQL instance
  (all deferred to TASK-077/078). Integration tests are **not required** for a
  manifest-only deployment with no Kafka/persistence/MinIO/DB boundary changes.

---

## 5. Findings

No Critical, High, or Moderate findings.

### m1 — Minor: test could pass even if the DB password secret reference were removed

- **Severity:** Minor
- **Affected:** `tests/test_kubernetes_manifests.py::TestAPIDeployment`
  (`test_api_deployment_has_db_env`, `test_api_deployment_secrets_are_optional`)
- **Problem:** `test_api_deployment_has_db_env` asserts only HOST/PORT/NAME are present
  (not `WAREHOUSE_DB_USER` or `WAREHOUSE_DB_PASSWORD`), and
  `test_api_deployment_secrets_are_optional` iterates over the *existing* `secretKeyRef`
  entries — it would pass vacuously if the password env were deleted entirely (an empty
  `secret_envs` list still satisfies the loop).
- **Impact:** A regression that removes the `WAREHOUSE_DB_PASSWORD` secret reference
  (the core "Configure DB via Secret references" requirement) would still ship green.
- **Recommendation:** Assert `WAREHOUSE_DB_USER` and `WAREHOUSE_DB_PASSWORD` are present
  by name, and assert that `WAREHOUSE_DB_PASSWORD` uses a `secretKeyRef` (not a literal
  `value`) targeting `api-secrets`/`db-password`.

### m2 — Minor: kind config FastAPI port mapping assumes NodePort, but the Service is ClusterIP

- **Severity:** Minor
- **Affected:** `kubernetes/kind/kind-config.yaml` (`containerPort: 30080` →
  `hostPort: 8000`, pre-existing from TASK-070) vs `kubernetes/deployments/api-service.yaml`
  (`type: ClusterIP`).
- **Problem:** The kind config's FastAPI host-port mapping routes host `8000` → a
  `NodePort`-style `30080`, but TASK-076 creates a **ClusterIP** Service with no
  `nodePort`. Consequently `localhost:8000` will not reach the API via that mapping; the
  documented `kubectl port-forward` is the only working access path.
- **Impact:** No functional breakage (port-forward works and is correctly documented),
  but the README "Port Mappings" table (FastAPI `8000 | 30080`) is potentially misleading
  to an operator.
- **Recommendation:** Reconcile in TASK-078/079: either publish the API via a
  `NodePort` with `nodePort: 30080`, or update the kind config / README port table to
  reflect ClusterIP + port-forward. This is a pre-existing TASK-070 inconsistency
  surfaced by this task, not introduced by it.

### m3 — Minor: `APP_ENVIRONMENT=production` is set but unused by the API service

- **Severity:** Minor
- **Affected:** `kubernetes/deployments/api-deployment.yaml` (`env`)
- **Problem:** Unlike `services/warehouse-loader` (whose `MinIOSettings` inherits a
  required `AppSettings.environment`), neither `APISettings` nor `DatabaseSettings` in
  `services/api/config.py` reads `APP_ENVIRONMENT`. The variable is therefore inert for
  this container.
- **Impact:** None at runtime; it is harmless and consistent with sibling deployments.
- **Recommendation:** Leave as-is for consistency, or drop it if the API later gains a
  shared `AppSettings` base that would consume it.

---

## 6. Non-Defect Observations

- **No secrets committed:** confirmed — credentials are `secretKeyRef` only, `optional: true`.
- **Correct probe semantics:** liveness (`/api/v1/health`) always returns 200;
  readiness (`/api/v1/ready`) runs `SELECT 1` and raises `APIError(status_code=503)`
  when the database is unreachable (verified in `services/api/routes/v1/health.py` and
  `services/api/errors.py`). The API engine is lazy (`create_engine`), so the pod starts
  with liveness OK and becomes ready only once PostgreSQL is reachable — correct behavior.
- **No startup probe:** acceptable given FastAPI's fast startup; SPEC §19 says "where
  necessary". TASK-079 (probes/resources) may add one if needed.
- **Forward references to later tasks:** `WAREHOUSE_DB_HOST=postgresql`, the
  `api-secrets` Secret name, and the `ai-data-platform/api:dev` image all resolve in
  TASK-077 (Kafka/PostgreSQL kind) and TASK-078 (Services/ConfigMaps/Secrets). Consistent
  with the `warehouse-loader` sibling.
- **DB naming drift across environments:** manifests use
  `postgresql` / `warehouse` / `postgres`, while `docker-compose.yml` uses
  `postgres` / `platform` / `platform`. Carried over from TASK-075; reconcile at the
  TASK-077 PostgreSQL work, not here.
- **No Dockerfile for `api`:** consistent with all sibling services; image build remains
  unreconciled downstream (the manifest references `ai-data-platform/api:dev`).
- **Resource requests/limits** (`100m/256Mi` request, `500m/512Mi` limit) match siblings.
- **`replicas: 1`** and **`imagePullPolicy: IfNotPresent`** match siblings.
- **Label/selector consistency:** Service selector uses `name`+`part-of`; the deployment
  template additionally carries `component`. Service `metadata.labels` also carries
  `component: api`. Consistent with the established convention.
- **No ADRs apply:** the only ADR in the repository (ADR-001, Kafka topic configuration)
  is unrelated to this deployment task.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The TASK-076 implementation is correct, well-scoped, secret-free, and consistent with
its sibling deployments. It:

- creates a Deployment that runs the established `python -m services.api` entry point;
- externalizes DB configuration and sources the password from an optional `secretKeyRef`;
- wires liveness/readiness probes to the established `/api/v1/health` and `/api/v1/ready`
  endpoints (readiness correctly returns 503 until the database is reachable);
- creates a matching ClusterIP Service on port 8000;
- omits Ingress, as required;
- documents kubectl port-forward;
- adds 17 manifest validation tests that pass independently.

The three remaining findings are **Minor** (test-completeness for the password secret
reference, a pre-existing kind-config NodePort-vs-ClusterIP port-mapping inconsistency,
and an inert `APP_ENVIRONMENT` variable). None blocks acceptance.

m1 should be addressed in a cheap follow-up to harden the manifest test; m2 should be
reconciled during TASK-078/079 (Service/ConfigMap/Secret standardization and
probe/port work).
