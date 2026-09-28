# TASK-123 Qwen Review — AWS Deployment

**Reviewer:** Qwen Code (independent review, no code modified)
**Date:** 2026-09-29
**Task:** TASK-123 — AWS Deployment
**Reviewed commit:** `d52c5e473f387dbaef8fb99dc07877e34977e882` on `feature/TASK-123`
**Git range:** `97c52a84f1c076d165ac356099cbcbabc38fcfd3...d52c5e473f387dbaef8fb99dc07877e34977e882` (single commit)
**Scope:** Helm EKS wiring, `values-eks.yaml`, `scripts/deploy-eks.sh`, `scripts/verify_eks_deployment.py`, `docs/deployment/aws-eks-deployment.md`
**Verdict:** CHANGES REQUIRED

---

## 1. Requirements Coverage

| # | Requirement (TASK-123 / ROADMAP M14) | Status | Evidence |
|---|---|---|---|
| 1 | Deploy the platform to AWS using Terraform + Helm | **Partial** | `scripts/deploy-eks.sh` orchestrates terraform apply → ECR push → Strimzi → Helm. Helm renders cleanly for EKS (independently verified). |
| 2 | Verify end-to-end: ingestion produces events, processing works, Parquet in S3, PostgreSQL loaded, API responds, agent answers | **Partial** | `scripts/verify_eks_deployment.py` checks pods, API health, topic existence, S3/Postgres connectivity, and raw-topic offsets only. Does not verify processing, Parquet content, PostgreSQL data, or the agent (Finding 5). |
| 3 | Document deployment process and prerequisites | **Met** | `docs/deployment/aws-eks-deployment.md` covers architecture, prerequisites, step-by-step apply, verification, access, tear-down, troubleshooting. |
| 4 | Tear-down instructions included | **Met** | `destroy` command in `deploy-eks.sh`; documented in the guide. |
| 5 | Never commit credentials/access keys/secrets | **Met** | No secrets in the diff. Placeholders (`<…>`) in `values-eks.yaml`; RDS password via `TF_VAR_rds_password`; API keys default to `placeholder`. |
| 6 | Use existing Helm charts and Terraform modules | **Met** | Reuses the existing chart and TASK-116–122 modules; adds only environment wiring. |
| 7 | Add deterministic tests where applicable | **Not met** | No tests added for `deploy-eks.sh` or `verify_eks_deployment.py` (Finding 8). |

---

## 2. Git Diff Review

**Scope correctness:** The 15 changed files are all plausibly within TASK-123 (EKS deployment wiring + docs + scripts). No unrelated application-code changes.

**Changed files:**
- `docs/deployment/aws-eks-deployment.md` (new, 245 lines)
- `helm/ai-data-platform/values-eks.yaml` (new, 260 lines)
- `helm/ai-data-platform/values.yaml` (+32 lines: `serviceAccounts` block, `kafka.enabled`)
- `helm/ai-data-platform/templates/serviceaccounts.yaml` (new, 20 lines)
- `helm/ai-data-platform/templates/deployments/{api,ingestion,kafka,lake-writer,processor,raw-writer,warehouse-loader}.yaml`
- `helm/ai-data-platform/templates/jobs/kafka-topics.yaml`
- `helm/ai-data-platform/templates/services/kafka.yaml`
- `scripts/deploy-eks.sh` (new, 427 lines)
- `scripts/verify_eks_deployment.py` (new, 302 lines)

**Architectural changes:** ServiceAccount/IRSA wiring (new template + `serviceAccountName` on deployments) is additive and consistent with TASK-122. Gating the Kafka Deployment/Service/Job on `kafka.enabled` is a reasonable environment toggle; `kafka.enabled: true` was added to base `values.yaml` so kind behavior is preserved (independently verified: kind render still emits the Kafka Deployment).

**Notable change flagged:** Readiness probes for five consumer services were changed from a real TCP dependency check to `os.kill(1, 0)` (see Finding 4). The API service retains its HTTP readiness probe.

**Accidental changes:** None observed. No debug code, dead code, generated artifacts, or secrets committed.

---

## 3. Test and Verification Review

### Tests examined
- No tests added or changed in this commit.
- Existing structural tests unaffected by this change set; `tests/test_terraform_eks.py` (23 tests) is the closest adjacent coverage.

### Independently verified (executed by reviewer)
| Check | Result |
|---|---|
| `helm lint helm/ai-data-platform` | **PASS** — 1 chart linted, 0 failed |
| `helm template` with base `values.yaml` (kind) | **PASS** — 27 resources, no render errors; Kafka Deployment/Service/Job present |
| `helm template` with `values.yaml` + `values-eks.yaml` | **PASS** — 39 resources, no render errors; 7 ServiceAccounts with `eks.amazonaws.com/role-arn`, Kafka Deployment absent |
| `python -m pytest tests/test_terraform_eks.py -q` | **PASS** — 23 passed |

### Implementation evidence reviewed (not independently executed)
- No CI or test-run evidence is present in the commit body.

### Unverified
- **End-to-end AWS deployment** — cannot be executed (no AWS credentials; `terraform` not installed on this machine). All claims about the live deployment are unverified.
- **Integration tests** (`python -m pytest -m integration`) — not run and no evidence provided. The task touches infrastructure boundaries (Kafka/S3/RDS/EKS), but no Python application code changed, so this is informational rather than blocking.

---

## 4. Findings

### HIGH

**H1 — Airflow is enabled on EKS but its required secrets are never provisioned**
- **Affected:** `scripts/deploy-eks.sh` `create_eks_secrets()`; `helm/ai-data-platform/values-eks.yaml`; `helm/ai-data-platform/templates/secrets/airflow-credentials.yaml`; `helm/ai-data-platform/values.yaml` (`secrets.airflow.*`)
- **Problem:** `values-eks.yaml` sets `airflow.enabled: true` and the deployment guide lists Airflow as part of the stack, but:
  1. `airflow-keys` (fernet key + web secret key) is only created by Helm when `secrets.airflow.fernetKey` and `secretKey` are non-empty (both default to `""`), and `create_eks_secrets()` does **not** create it. The `airflow-init` job and the `airflow-webserver`/`airflow-scheduler` deployments all mount `airflow-keys` (verified across 31 references).
  2. `airflow-metadata-credentials.db-password` comes from `secrets.airflow.metadataPassword`, whose base value decodes to `"postgres"` — not the RDS master password. The `airflow-init` `create-database` init container connects to RDS as `platform_admin` with this password, so it will fail authentication.
- **Impact:** On EKS, the `airflow-init` hook fails and the Airflow webserver/scheduler pods cannot start. The "complete platform" deployment documented by this task is broken for Airflow.
- **Recommendation:** Either (a) generate a Fernet key + secret key and create `airflow-keys` in `create_eks_secrets()`, and override `secrets.airflow.metadataPassword` with the RDS password; or (b) explicitly disable Airflow for TASK-123 and document it as out of scope, matching the M14 target architecture (which does not list Airflow).

### MODERATE

**M1 — Strimzi OCI Helm registry path appears incorrect**
- **Affected:** `scripts/deploy-eks.sh` `install_strimzi()` (~`helm install strimzi oci://quay.io/strimzi-operator/strimzi-kafka-operator`)
- **Problem:** The official Strimzi Helm chart is published under the `strimzi-helm` organization on quay.io (`oci://quay.io/strimzi-helm/strimzi-kafka-operator`), not `strimzi-operator`. The historical HTTP repo is `https://strimzi.io/charts/`.
- **Impact:** If the path is wrong, the deployment fails at the Strimzi install step, blocking the entire apply.
- **Recommendation:** Verify and correct the registry path before running `apply`. (Independent confirmation was not possible from the repo; flagged for owner verification.)

**M2 — `verify_eks_deployment.py` S3 check uses `ListAllMyBuckets`, which the least-privilege roles do not grant**
- **Affected:** `scripts/verify_eks_deployment.py` `check_s3()`; `terraform/modules/iam/main.tf` (`s3_write`/`s3_read`)
- **Problem:** The check runs `boto3.client('s3').list_buckets()` inside the `raw-writer` pod. The IAM `s3_write` policy grants only `s3:ListBucket` on the specific bucket (with prefix condition) and `s3:PutObject` — it does **not** grant `s3:ListAllMyBuckets`.
- **Impact:** The S3 verification produces a false negative: IRSA can be correctly configured and the writer able to write Bronze Parquet, yet the check reports FAIL due to `AccessDenied` on `ListAllMyBuckets`.
- **Recommendation:** Verify S3 access against the data bucket/prefix (e.g. `head_bucket` or `list_objects_v2` on the configured bucket/prefix), not `list_buckets()`.

**M3 — Readiness probes for five consumer services weakened to a no-op process check**
- **Affected:** `templates/deployments/{ingestion,processor,raw-writer,lake-writer,warehouse-loader}.yaml`
- **Problem:** The readiness probe changed from a TCP connect to the dependency (Kafka `kafka:29092` / PostgreSQL `postgresql:5432`) to `os.kill(1, 0)`, which only confirms PID 1 is alive — i.e. it duplicates the liveness probe and no longer signals "ready to process."
- **Impact:** These pods report Ready even when Kafka/PostgreSQL is unreachable, degrading readiness semantics, rollout ordering, and failure detection for the streaming consumers. (The API service correctly retains its HTTP readiness probe.)
- **Recommendation:** Make the probe target configurable (e.g. a `kafkaBootstrapServers`-derived host/port) instead of dropping the check, or document why the check was removed.

**M4 — End-to-end verification does not satisfy the task's own objective**
- **Affected:** `scripts/verify_eks_deployment.py`
- **Problem:** The task objective requires verifying that "ingestion produces events, processing works, Parquet is written to S3, PostgreSQL is loaded, API responds, and the agent can answer questions." The script verifies: pod readiness, API `/health`, topic existence, `list_buckets()` (S3), `SELECT 1` (PostgreSQL), and that `products.raw.v1` has any offsets. It does **not** verify: `products.validated.v1` (processing), Parquet objects in S3, warehouse data loaded, or the agent (`/agent/query`). The guide calls this "Full E2E verification," which overstates it.
- **Impact:** The "Definition of Done" end-to-end claim is not actually demonstrated by the shipped verification.
- **Recommendation:** Extend the checks (validated-topic offsets, object listing on the bronze/silver prefix, a row-count or known-observation query, and an agent query round-trip) or narrow the documented claim.

**M5 — Deploy script references a non-existent `aws_region` Terraform output and falls back to a hardcoded region**
- **Affected:** `scripts/deploy-eks.sh` `ecr_login()`, `configure_kubectl()`, `destroy_all()`; `terraform/outputs.tf`
- **Problem:** The script calls `terraform output -raw aws_region`, but `outputs.tf` defines no such output, so it always falls through to the hardcoded `eu-north-1`. This is correct only for the `dev` environment (`envs/dev.tfvars` = `eu-north-1`); `staging.tfvars` uses `eu-west-1`.
- **Impact:** For any non-dev environment, ECR login, `aws eks update-kubeconfig`, and destroy would target the wrong region.
- **Recommendation:** Add an `aws_region` output to `outputs.tf` (or read the region from the `.tfvars`), and drop the silently-wrong fallback.

### MINOR

**m1 — `values-eks.yaml` Airflow comment claims CeleryExecutor but the value is not set.** The comment reads "enabled with CeleryExecutor for multi-worker," but `airflow.executor` is not overridden (defaults to `LocalExecutor`), and there is no Celery worker template. Either set the executor or correct the comment.

**m2 — The `agent` ServiceAccount and IAM role are provisioned but unused.** There is no `agent` Deployment in the chart (the agent runs inside the API pod, which uses the `api` service account), and `build_and_push_images()` skips `agent` (`agent) continue`). The `agent` IRSA role/SA are dead resources and slightly misleading.

**m3 — No tests added for the new scripts.** `deploy-eks.sh` and `verify_eks_deployment.py` are untested. Pure logic in the verify script (e.g. `VerificationReport`, topic-list parsing, argument handling) is unit-testable and would fit the repo's deterministic-test convention.

**m4 — `serviceaccounts.yaml` uses camelCase map keys for the component label.** `app.kubernetes.io/component: {{ $key }}` yields `rawWriter`, `lakeWriter`, `warehouseLoader`, inconsistent with the kebab-case component labels used everywhere else (`raw-writer`, etc.).

**m5 — Strimzi Kafka CR uses deprecated ZooKeeper mode.** `strimzi-kafka-eks.yaml` declares a `zookeeper` section with Kafka 3.9.0. Strimzi 0.45.0 still supports this, but ZooKeeper mode is deprecated (removed in Strimzi 1.0). Consider KRaft to match the local kind Kafka (KRaft) and future-proof the deployment.

---

## 5. Non-Defect Observations

- **Region documentation is internally consistent for dev.** `deploy-eks.sh` hardcodes `eu-north-1` for the backend/kubectl fallback, and `envs/dev.tfvars` sets `aws_region = "eu-north-1"` with matching AZs. The docs' "AWS (eu-north-1)" is accurate for the default environment. (The latent issue is M5 for other environments.)
- **Airflow database creation is correctly delegated to a Helm hook.** The `airflow` database is created by the `airflow-init` job's `create-database` init container rather than Terraform, which is a sound design — but it depends on the secret wiring flagged in H1.
- **`minio-credentials` is created empty on EKS**, with `minio.enabled: false` and `minioEndpoint: ""`. This relies on services falling back to boto3/IRSA when the MinIO endpoint is empty; this application-level behavior was not verified in this review.
- **IRSA wiring is clean.** The `serviceAccounts` template and `eks.amazonaws.com/role-arn` annotations render correctly for all seven services, matching the TASK-122 IAM role ARNs keyed by service name.
- **`GetOffsetShell` in `check_data_flow` is deprecated** in modern Kafka (present in 3.9 but removed in 4.0); a future Kafka upgrade will require replacing it with `kafka-get-offsets.sh`.

---

## 6. Verdict

**CHANGES REQUIRED**

The implementation is well-structured and the Helm/IRSA wiring is correct (independently rendered and linted successfully), but it is not ready for acceptance:

- **Blocking (High):** Airflow is enabled on EKS yet its required secrets (`airflow-keys`, and the RDS password for `airflow-metadata-credentials`) are never provisioned, so the documented "complete platform" deployment fails for Airflow.
- **Should fix (Moderate):** the Strimzi OCI registry path is likely wrong; the S3 verification check is a false negative against least-privilege IAM; the readiness probes were weakened to no-ops; the end-to-end verification does not cover the task's stated objective; and the `aws_region` output fallback is silently region-incorrect for non-dev environments.

No secrets were introduced, no unrelated code was modified, and the existing structural tests remain green.
