# TASK-078 Review — Services, ConfigMaps and Secrets

## 1. Review Header

- **Task ID:** TASK-078
- **Review date:** 2026-09-19
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:**
  `1ad4e8ec36b7ccbae75550fbc5e716e544e4f71d...d29fdd4db3e2d12fd810545003ce7f2a74aee0c6`
  (single commit: `d29fdd4` feat(TASK-078): Services ConfigMaps and Secrets)
- **Reviewed HEAD:** `d29fdd4db3e2d12fd810545003ce7f2a74aee0c6` on `feature/TASK-078`
- **Scope:** Service definitions (MinIO, PostgreSQL), two ConfigMaps
  (`platform-config`, `database-config`), three Secrets (`minio-credentials`,
  `database-credentials`, `ingestion-api-keys`), a local secret-creation script,
  updates to all six application Deployments to consume the ConfigMaps/Secrets,
  `kubernetes/README.md` documentation, and manifest validation tests.
- **Verdict:** **APPROVED WITH NON-BLOCKING FINDINGS**

---

## 2. Requirements Coverage

The task objective is: standardize Services, ConfigMaps and Secret references;
match application settings names; define stable service discovery; document
local secret creation; commit no real secrets; and keep configuration
Helm-ready.

| # | Requirement | Status | Evidence |
|---|---|---|---|
| R1 | Standardize Service/ConfigMap/Secret references | Met | Six Deployments now reference shared ConfigMaps via `configMapKeyRef` and shared Secrets via `secretKeyRef` instead of hardcoded values or per-service Secret names. |
| R2 | Match application settings names | Met (one value mismatch, F1) | ConfigMap keys `APP_ENVIRONMENT`, `APP_KAFKA_BOOTSTRAP_SERVERS`, `APP_MINIO_ENDPOINT`, `WAREHOUSE_DB_HOST/PORT/NAME/USER` match the `APP_`-prefixed `BaseAppSettings` (env_prefix `APP_`, case-insensitive) and the `WAREHOUSE_DB_*` `os.getenv` convention. The `secretKeyRef.key` names (`minio-access-key`, `minio-secret-key`, `db-password`, `bestbuy-api-key`) are arbitrary Secret keys correctly mapped to the `APP_MINIO_*`/`WAREHOUSE_DB_PASSWORD`/`BESTBUY_API_KEY` env names. |
| R3 | Define stable service discovery | Partially met | `kafka` (NodePort), `api`, `minio`, `postgresql` (ClusterIP) Services defined. **MinIO/PostgreSQL Services are dangling** — no backing pods exist and no Milestone-8 task creates them (F2). |
| R4 | Document local secret creation | Met | `scripts/create-local-secrets.sh` + README section with script/manual/manifest alternatives. |
| R5 | Commit no real secrets | Met | Values are documented local-dev placeholders (`minioadmin`, `postgres`, `placeholder-replace-me`); no production credentials. |
| R6 | Keep configuration Helm-ready | Met | ConfigMap/Secret split maps cleanly to Helm `values.yaml`/`templates/`; no Helm artifacts introduced (per task constraint). |
| R7 | Preserve service boundaries / no architecture redesign | Met | No service-boundary, event-contract, or topic-ownership change; ingestion remains Kafka-producer-only, warehouse-loader remains batch-only (no Kafka bootstrap), Raw/Lake writers remain MinIO consumers. |
| R8 | Declarative manifests + consistent labels/selectors | Met | All new resources use `app.kubernetes.io/name`, `part-of`, and `component` labels; Deployments reference ConfigMap/Secret keys explicitly. |
| R9 | Do not weaken tests | Met | Tests strengthened: `optional: true` assertions replaced with shared-Secret name assertions, plus new ConfigMap/Secret/Service test classes. |
| R10 | No unrelated changes | Met | Diff limited to `kubernetes/`, `scripts/`, `tests/` (see §3). |

---

## 3. Git Diff Review

Single-commit range. Aggregate diffstat:

| File | Change |
|---|---|
| `kubernetes/config/platform-config.yaml` | new ConfigMap (19 lines) |
| `kubernetes/config/database-config.yaml` | new ConfigMap (20 lines) |
| `kubernetes/secrets/minio-credentials.yaml` | new Secret (30 lines) |
| `kubernetes/secrets/database-credentials.yaml` | new Secret (26 lines) |
| `kubernetes/secrets/ingestion-api-keys.yaml` | new Secret (24 lines) |
| `kubernetes/deployments/minio-service.yaml` | new ClusterIP Service (33 lines) |
| `kubernetes/deployments/postgresql-service.yaml` | new ClusterIP Service (29 lines) |
| `kubernetes/deployments/{ingestion,processor,raw-writer,lake-writer,warehouse-loader,api}-deployment.yaml` | env sources rewritten to ConfigMap/Secret refs |
| `scripts/create-local-secrets.sh` | new helper script (51 lines) |
| `kubernetes/README.md` | +173/-? tree, config/secrets/service sections, apply-all, troubleshooting |
| `tests/test_kubernetes_manifests.py` | +271/-? (5 new test classes + rewritten secret assertions) |

- **Scope correctness:** All changes belong to TASK-078. No application Python
  code, no `pyproject.toml`/dependency, no CI, no kind-config or namespace
  change. The six Deployment edits are the intended consumption-side wiring.
- **Unrelated changes:** None. No file outside `kubernetes/`, `scripts/`,
  `tests/` was touched.
- **Architectural changes:** None. Service boundaries and canonical data flow are
  preserved. The old per-service Secret names (`raw-writer-secrets`,
  `lake-writer-secrets`, `warehouse-loader-secrets`, `api-secrets`,
  `ingestion-secrets`) are fully removed from active manifests in favor of the
  three shared Secrets — a naming/consolidation change within the task's
  explicit "standardize Secret references" objective, not an architecture change.
  No lingering references remain in active manifests/scripts (only historical
  `docs/reviews/*` records mention the old names).
- **Accidental changes / debug code / generated artifacts / secrets:** None.
  The committed Secrets carry documented local-dev placeholder values, not real
  credentials (see §6).
- **Dependencies:** None added.
- **Branch/task isolation:** Reviewed on `feature/TASK-078`; working tree clean;
  the range contains exactly one TASK-078 commit. Correct isolation.

---

## 4. Test and Verification Review

### Tests examined

`tests/test_kubernetes_manifests.py` is the only test file changed. New/changed
coverage:

- `TestPlatformConfigMap` / `TestDatabaseConfigMap` — existence, `kind`, namespace,
  required keys, and specific values (`kafka:29092`, `http://minio:9000`,
  `postgresql`).
- `TestMinioCredentialsSecret` / `TestDatabaseCredentialsSecret` /
  `TestIngestionApiKeysSecret` — existence, `kind`, namespace, required keys,
  Opaque type.
- `TestMinioService` / `TestPostgreSQLService` — existence, `kind`, namespace,
  ClusterIP type, ports (9000, 5432), labels.
- `TestDeploymentsUseConfigMaps` — asserts each Deployment references the expected
  ConfigMap names.
- Rewritten `*_secret` assertions — now assert shared Secret **names** and that
  `optional` is no longer set, replacing the previous `optional is True` checks.

These are **structural only** (YAML file-content validation, no live cluster),
consistent with the TASK-070+ convention.

### Verification classification

- **Independently verified (reviewer-executed):**
  - `python -m pytest tests/test_kubernetes_manifests.py -q` → **128 passed** (1.13s).
- **Implementation evidence reviewed:** the full diff was inspected; every
  ConfigMap/Secret key and Deployment env name was cross-checked against
  `libs/common/config.py` (`env_prefix="APP_"`), `libs/common/minio_storage.py`,
  `libs/common/kafka_producer.py`, and `services/api/config.py`, and the names
  match. The `kafka:29092` internal-broker endpoint was cross-checked against
  `kubernetes/deployments/kafka-service.yaml` (port 29092) and matches.
- **Unverified:** `python -m pytest -m integration` and any live
  `kubectl apply/get/describe` run against a kind cluster. The submitted change
  contains no evidence that these manifests were applied to a running cluster, so
  "acceptance behavior demonstrated" (Definition of Done) is **not independently
  confirmed**. TASK-079 is explicitly scoped to add Kubernetes integration smoke
  tests, so this deferral is architecturally sanctioned and is not treated as
  blocking; but the reviewer flags it because this task touches the
  infrastructure/configuration boundary.

---

## 5. Findings

### F1 — Moderate: MinIO secret-key value does not match the platform default

- **Affected:** `kubernetes/secrets/minio-credentials.yaml` (`minio-secret-key:
  bWluaW9hZG1pbg==`) and `scripts/create-local-secrets.sh`
  (`--from-literal=minio-secret-key=minioadmin`).
- **Problem:** `bWluaW9hZG1pbg==` decodes to `minioadmin`. The platform-wide MinIO
  root password is `minioadmin-local`, established in `docker-compose.yml`
  (`MINIO_ROOT_PASSWORD: minioadmin-local`), `libs/common/minio_storage.py`
  (`minio_secret_key = SecretStr("minioadmin-local")`), `.env.example`
  (`APP_MINIO_SECRET_KEY=minioadmin-local`), and `docs/minio-storage.md`. The
  manifest's own comment claims the values "match the Docker Compose MinIO setup",
  which is false for the secret key. (The access key `minioadmin` is correct —
  it matches `MINIO_ROOT_USER`.)
- **Impact:** When the kind cluster's MinIO is backed by the documented
  `minioadmin`/`minioadmin-local` credentials, raw-writer, lake-writer, and
  warehouse-loader will fail MinIO authentication. This is the exact
  application↔infrastructure contract this task is responsible for.
- **Recommendation:** Change the secret key to `minioadmin-local` (base64
  `bWluaW9hZG1pbi1sb2NhbA==`) in both the manifest and the script so the shared
  `minio-credentials` Secret matches the established MinIO root password.

### F2 — Moderate: MinIO and PostgreSQL Services are dangling (no backing workloads, no roadmap task)

- **Affected:** `kubernetes/deployments/minio-service.yaml`,
  `kubernetes/deployments/postgresql-service.yaml`, and the ConfigMap values they
  support (`APP_MINIO_ENDPOINT: http://minio:9000`,
  `WAREHOUSE_DB_HOST: postgresql`).
- **Problem:** Both Services select `app.kubernetes.io/name: minio` /
  `app.kubernetes.io/name: postgresql`, but no MinIO or PostgreSQL Deployment
  exists in `kubernetes/`, and Milestone 8 (TASK-070–TASK-079) contains no task to
  create them. The comments state the backing workload is "expected to be provided
  by the local development environment (Docker Compose or a later task)", but a
  ClusterIP Service with a pod selector cannot be backed by Docker Compose
  containers running outside the cluster — so in-cluster endpoints `minio:9000`
  and `postgresql:5432` will have empty endpoints.
- **Impact:** "Stable service discovery" is not achieved for the data-lake and
  warehouse dependencies. The kind deployment cannot function end-to-end for the
  MinIO- and PostgreSQL-dependent services (raw-writer, lake-writer,
  warehouse-loader, api) until those workloads exist in-cluster. This is a
  roadmap/scope gap rather than a syntax defect in the manifests, but it is
  architecture-significant and should be surfaced, not left silent.
- **Recommendation:** Escalate for a human decision: either add MinIO and
  PostgreSQL Deployments (with PVCs/StatefulSet) to the Milestone-8 roadmap, or
  document an explicit plan for how the kind pods reach externally-hosted
  MinIO/PostgreSQL. Correct the misleading "Docker Compose" comment in both
  Service manifests.

### F3 — Minor: README "Applying All Manifests" misrepresents MinIO/PostgreSQL deployment

- **Affected:** `kubernetes/README.md` (Applying All Manifests, step 3).
- **Problem:** Step 3 is titled "Infrastructure services (Kafka, MinIO,
  PostgreSQL)" but applies only `kafka-deployment.yaml`/`kafka-service.yaml` plus
  the two *Service* manifests for MinIO/PostgreSQL. A reader following the steps
  would believe MinIO and PostgreSQL are being deployed when only their Services
  are.
- **Impact:** Documentation inaccuracy that could mislead deployment/debugging.
- **Recommendation:** Clarify that MinIO/PostgreSQL have no in-cluster Deployment
  yet (see F2), or relabel the step.

### F4 — Minor: structural tests do not validate secret values or Service→Deployment pairing

- **Affected:** `tests/test_kubernetes_manifests.py`
  (`TestMinioCredentialsSecret`, `TestMinioService`, `TestPostgreSQLService`).
- **Problem:** Tests assert the Secret *keys* exist and that Services exist with
  ClusterIP type, but never base64-decode the Secret values (so F1 is not caught)
  and never assert a matching Deployment exists (so F2 is not caught). The tests
  therefore certify more than they actually verify for these two concerns.
- **Impact:** The structural safety net would remain green through the F1/F2
  regressions.
- **Recommendation:** Add an assertion that `minio-secret-key` decodes to
  `minioadmin-local`, and (once F2 is resolved) an assertion that a Deployment
  with the Service's selector labels exists.

---

## 6. Non-Defect Observations

- **No real secrets committed.** All three Secrets contain documented local-dev
  placeholders (`minioadmin`, `postgres`, `placeholder-replace-me`). The
  `ingestion-api-keys` value is a placeholder (`placeholder-replace-me`), not a
  real BestBuy key — acceptable per "commit no real secrets".
- **Base64-encoded Secrets in Git** is a mild anti-pattern (scanner noise), but
  the task explicitly permits local-dev placeholders and documents the
  `create-local-secrets.sh` path as preferred; this is acceptable for the stated
  local-kind goal. For Helm/real environments these should move to a proper
  secrets mechanism (already the documented plan).
- **`APP_ENVIRONMENT: production`** in `platform-config` is valid per the
  `Literal["development", "production"]` contract and continues the pattern from
  TASK-071+; arguably semantically odd for a local kind cluster but not a defect.
- **`BESTBUY_API_KEY` remains `optional: true`** in the ingestion Deployment while
  MinIO/DB secrets dropped `optional`. This is deliberate and correct: the
  FakeStore source runs without a BestBuy key, and the README documents the
  `ingestion-api-keys` Secret as optional.
- **ConfigMap/Secret key naming is sound.** The `APP_`-prefixed settings are read
  case-insensitively by Pydantic (`env_prefix="APP_"`), so the uppercase keys
  resolve correctly; the `WAREHOUSE_DB_*` and `BESTBUY_API_KEY` names match the
  `os.getenv` usage exactly. The `secretKeyRef.key` values are arbitrary Secret
  keys and are correctly mapped to the env names.
- **`database-config` is self-consistent for a future kind PostgreSQL** (`postgres`
  user / `warehouse` DB / `postgresql` host) but does not match Docker Compose
  (`platform` / `platform-local` / DB `platform`). A future PostgreSQL Deployment
  must create a `warehouse` database and set these exact credentials, or the
  ConfigMap/Secret must be adjusted. Tracked as a forward dependency, not a
  defect in this task.
- **`warehouse-loader` correctly does not consume Kafka.** It references
  `platform-config` only for `APP_ENVIRONMENT`/`APP_MINIO_ENDPOINT`; no
  `APP_KAFKA_BOOTSTRAP_SERVERS` is injected, preserving its batch-only boundary.
- **Old per-service Secret names fully retired** from active manifests/scripts.
  The only remaining mentions are in frozen historical `docs/reviews/*` records,
  which are correctly left untouched.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The implementation is correctly scoped, secret-free (local-dev placeholders
only), preserves service boundaries, and consolidates the six application
Deployments onto two shared ConfigMaps and three shared Secrets whose key names
correctly match the application settings conventions (`APP_` /
`WAREHOUSE_DB_*`). The documentation is thorough, the manifests are declarative
with consistent labels, and no Helm artifacts or architecture redesigns were
introduced. The structural test suite (128 tests) passes when independently
executed by the reviewer.

The findings are non-blocking:

- **F1 (Moderate)** — the MinIO `minio-secret-key` value is `minioadmin`, but the
  platform-wide MinIO root password is `minioadmin-local`. This contradicts the
  manifest's own "match Docker Compose" comment and would break MinIO
  authentication. Trivial to fix; should be fixed before any live MinIO
  connectivity is attempted.
- **F2 (Moderate)** — the MinIO and PostgreSQL ClusterIP Services are dangling
  (no backing Deployments, no roadmap task to create them), so `minio:9000` and
  `postgresql:5432` have empty endpoints and the "stable service discovery"
  objective is only partially met. This is a roadmap/scope gap that warrants a
  human architectural decision.
- **F3 (Minor)** — README "Applying All Manifests" step 3 implies MinIO/PostgreSQL
  are deployed when only their Services are applied.
- **F4 (Minor)** — structural tests do not validate Secret values or
  Service→Deployment pairing, so F1/F2 would not be caught.

Live-kind `kubectl apply` verification and Kubernetes integration smoke tests
remain unverified by the submitted change and are deferred to TASK-079 by design;
this is noted but not treated as blocking.
