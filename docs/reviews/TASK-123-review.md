# TASK-123 Independent Review — AWS Deployment

| Field | Value |
|---|---|
| **Task ID** | TASK-123 — AWS Deployment |
| **Review date** | 2026-09-29 |
| **Reviewer** | Qwen Code (independent review, no code modified) |
| **Reviewed commit** | `8eff888936a163e511aca00edc968399db3e13e8` on `feature/TASK-123` |
| **Git range** | `97c52a84f1c076d165ac356099cbcbabc38fcfd3..8eff888936a163e511aca00edc968399db3e13e8` (three commits) |
| **Scope** | AWS EKS deployment wiring (Helm + Terraform), `scripts/deploy-eks.sh`, `scripts/verify_eks_deployment.py`, `docs/deployment/aws-eks-deployment.md` |
| **Verdict** | **APPROVED WITH NON-BLOCKING FINDINGS** |

> **Note on prior reviews.** Commit `d52c5e4` (feature) and `1ac2744` (first fix) were previously reviewed; the last review (recorded in this file) returned `CHANGES REQUIRED` with H1–H2 and M1–M3 plus minors. Commit `8eff888` ("address Qwen Round 2 findings H1-H2, M1-M3") is the implementation agent's response. This review re-evaluates the **current HEAD** (`8eff888`) in full and verifies whether those findings were actually resolved.

---

## 1. Requirements Coverage

Source of requirements: `ai/tasks/TASK-123-aws-deployment.md`, `ai/PROJECT.md` §8 (Local-First), §11 (Security), §4 (component ownership), `ai/ROADMAP.md` M14 (AWS target architecture).

| # | Requirement | Status | Implementation evidence |
|---|---|---|---|
| 1 | Deploy the platform to AWS using Terraform + Helm | **Met (with documented deferral)** | `scripts/deploy-eks.sh` orchestrates terraform apply → ECR push → Strimzi → Helm. Airflow is disabled on EKS (`airflow.enabled: false`), consistent with the M14 target architecture which does not list Airflow. |
| 2 | Verify E2E: ingestion → processing → Parquet in S3 → PostgreSQL loaded → API responds → agent answers | **Met** | `scripts/verify_eks_deployment.py` checks pods, API health, Kafka topics, bronze/silver Parquet (from IAM-correct pods), RDS connection, warehouse tables, and the agent endpoint. The agent check now targets the real endpoint (see §4). |
| 3 | Document deployment process and prerequisites | **Met** | `docs/deployment/aws-eks-deployment.md` covers architecture, prerequisites, apply steps, verification, access, tear-down, troubleshooting. |
| 4 | Tear-down instructions included | **Met** | `deploy-eks.sh destroy` + documentation. |
| 5 | Never commit credentials/access keys/secrets | **Met** | Diff scan found no secrets. RDS password flows via `TF_VAR_rds_password`; no hardcoded credentials. |
| 6 | Use existing Helm charts and Terraform modules | **Met** | Reuses the existing chart and TASK-116–122 modules; only adds environment wiring and the `aws_region` output. |
| 7 | Add deterministic tests where applicable | **Not met** | No tests added for `deploy-eks.sh` or `verify_eks_deployment.py` (carried over). See m1. |

---

## 2. Git Diff Review

The reviewed range contains three commits:

- `d52c5e473f387dbaef8fb99dc07877e34977e882` — `feat(TASK-123): AWS EKS deployment wiring, scripts, and documentation`
- `1ac2744b86a1dd133060446403337b5d5ea42405` — `fix(TASK-123): address Qwen review findings H1, M1-M5`
- `8eff888936a163e511aca00edc968399db3e13e8` — `fix(TASK-123): address Qwen Round 2 findings H1-H2, M1-M3`

**Changed files (full range):**

```
A docs/deployment/aws-eks-deployment.md
A docs/reviews/TASK-123-review.md
M helm/ai-data-platform/templates/deployments/{api,ingestion,kafka,lake-writer,processor,raw-writer,warehouse-loader}.yaml
M helm/ai-data-platform/templates/jobs/kafka-topics.yaml
A helm/ai-data-platform/templates/serviceaccounts.yaml
M helm/ai-data-platform/templates/services/kafka.yaml
A helm/ai-data-platform/values-eks.yaml
M helm/ai-data-platform/values.yaml
A scripts/deploy-eks.sh
A scripts/verify_eks_deployment.py
M terraform/outputs.tf
```

**Scope correctness.** All changed files are within TASK-123. No unrelated application-code changes; no architecture-boundary changes. The Helm changes are additive (IRSA `serviceAccountName` injection, `kafka.enabled` gating) and consistent with TASK-121/122.

**Architectural changes.** Disabling Airflow on EKS is the only notable decision. This is consistent with the M14 target architecture (no Airflow), is clearly documented in `values-eks.yaml`, and does not break the E2E data path (see Non-Defect Observation N1).

**Accidental changes.** None. No debug code, dead code beyond noted dead config, generated artifacts, or secrets.

**Fix-commit delta (`8eff888` — what actually changed and whether it resolves the prior findings):**

| Prior finding | Fix applied | Resolution |
|---|---|---|
| H1 (Airflow image never built/pushed) | `airflow.enabled: false`; removed `airflow-keys` secret + `metadataPassword` base64 from `deploy-eks.sh`; docs updated | **Resolved** (deferred, M14-consistent) |
| H2 (agent check wrong endpoint/field) | `POST /api/v1/agent/ask` with `{'question': ...}` | **Resolved** (verified against route + schema) |
| M1 (S3 `head_bucket` false negative) | Removed `head_bucket`; `list_objects_v2(Prefix='bronze/')` only | **Resolved** (satisfies raw-writer prefix condition) |
| M2 (silver listed from raw-writer) | Silver check now runs from `warehouse-loader` | **Resolved** (warehouse-loader has `s3_read: silver`) |
| M3 (wrong default bucket name) | `--bucket-name` is now `required=True`; docs show `terraform output -raw s3_data_bucket` | **Resolved** |
| m2 (warehouse check passes when empty) | `ok and table_count > 0` | **Resolved** |
| m4 (base64 line-wrap) | base64 block removed entirely | **Resolved** (moot) |
| m1/m3/m5 (weak probe, dead agent infra, doc drift) | Not addressed | **Partially unresolved** (see M1, m2, m3, m5 below) |

---

## 3. Test and Verification Review

### Tests examined
- No tests were added or changed in any of the three commits.
- Closest adjacent structural coverage: `tests/test_terraform_*.py` (HCL structure parsing, no `terraform` binary required).

### Independently verified (executed by reviewer)

| Check | Result |
|---|---|
| `helm lint helm/ai-data-platform` | **PASS** — 1 chart, 0 failed |
| `helm template` (base `values.yaml`) | **PASS** — renders airflow, kafka, minio, postgresql, 6 service deployments, jobs |
| `helm template` (`values.yaml` + `values-eks.yaml`) | **PASS** — 7 ServiceAccounts; no airflow, no kafka; 6 deployments; NetworkPolicy/HPA/grafana/prometheus present |
| `python -m pytest tests/test_terraform_*.py -q` | **PASS** — 120 passed (structure, ecr, eks, iam, s3, rds, networking, bootstrap) |
| `ast.parse(scripts/verify_eks_deployment.py)` | **PASS** — syntax valid |
| Diff secret scan (AKIA / access keys / PEM / literal passwords) | **PASS** — only `os.environ['WAREHOUSE_DB_PASSWORD']` (env read), no secrets |

The `helm template` run with `values-eks.yaml` confirms the two gating changes work: Airflow resources and the Kafka Deployment/Service/Job are absent, while the six service deployments (api, ingestion, lake-writer, processor, raw-writer, warehouse-loader) render with `serviceAccountName` set.

### Implementation evidence reviewed (not independently re-executed)
- End-to-end AWS deployment (`apply`) — not executed (no AWS credentials; `terraform` not installed here).
- Integration tests (`python -m pytest -m integration`) — not run; not provided. The task touches infrastructure boundaries (Kafka/S3/RDS/EKS), but no Python application code changed, so this is informational rather than blocking.

### Unverified
- Live EKS deployment and the runtime behavior of the verification script's `kubectl exec` checks (bronze/silver listing, agent round-trip) against a real cluster.

---

## 4. Findings

### MODERATE

**M1 — Documentation understates the ECR repository count; the `agent` infrastructure is still provisioned but unused**
- **Affected:** `docs/deployment/aws-eks-deployment.md` (architecture diagram, "ECR (6 repositories)", "6 services"); `terraform/envs/dev.tfvars`, `terraform/envs/staging.tfvars`, `terraform/variables.tf` (`ecr_service_names` — 7 entries incl. `agent`); `terraform/modules/iam/variables.tf` (`service_accounts` incl. `agent`; `db_services` incl. `agent`); `helm/ai-data-platform/values-eks.yaml` (`serviceAccounts.services.agent`); `scripts/deploy-eks.sh` (`SERVICES` incl. `agent`, skipped in `build_and_push_images`).
- **Problem:** The fix commit changed the docs to "6 repositories"/"6 services" and removed `agent` from the EKS diagram. But Terraform still creates **7** ECR repositories (the `agent` repo is never used), 7 IRSA roles, and the `agent` ServiceAccount is still rendered by the chart. There is no `agent` Deployment — the agent runs inside the API pod (`services/api/routes/v1/agent.py`). The M14 target architecture lists `agent` as a separate EKS component, so neither the code nor the docs are fully consistent with it.
- **Impact:** Doc/configuration mismatch (stated 6 repos vs actual 7); dead `agent` ECR repo + IRSA role + `secrets_read` attachment + ServiceAccount. Not a functional blocker, but it misstates the deployment and leaves unused AWS resources.
- **Recommendation:** Pick one direction and align everything: (a) remove `agent` from `ecr_service_names`, `service_accounts`, and `db_services`, and keep the "6" documentation; or (b) keep 7 repos and deploy a real `agent` service as the M14 architecture implies. Also update `docs/deployment/aws-eks-deployment.md` to match whichever is chosen.

### MINOR

**m1 — No tests added for the deployment/verification scripts (carried over).** `scripts/deploy-eks.sh` and `scripts/verify_eks_deployment.py` are new operational code with testable logic (the `VerificationReport` accumulator, the `--bucket-name`/`--api-url` argument handling, and the constructed SQL/Python strings could be unit-tested without a cluster). The task's "add deterministic tests where applicable" criterion remains unmet. Practical caveat: the checks are heavily `kubectl exec`-based, so meaningful coverage requires either mocking `subprocess` or a live cluster.

**m2 — Readiness probes verify only the metrics server, not dependency reachability (carried over).** The five consumer services use `tcpSocket: port: 9100`. The services do bind a metrics HTTP server on `0.0.0.0:9100`, so the probe is valid, but a pod can report Ready before its Kafka/PostgreSQL dependency is reachable. Acceptable, but weaker than the previous TCP dependency check.

**m3 — Dead `airflowMetadata` section remains in `values-eks.yaml`.** With `airflow.enabled: false`, the `airflowMetadata.host/port/name/user` block (pointing at `<RDS_ENDPOINT>`) is now unused and misleading. Harmless, but should be removed or annotated.

**m4 — Dangling `minio` and `postgresql` Services render on EKS.** Unlike the `kafka` Service (which this task correctly gated with `{{- if .Values.kafka.enabled }}`), `templates/services/minio.yaml` and `templates/services/postgresql.yaml` are not gated, so `helm template` with `values-eks.yaml` still emits `minio` and `postgresql` Services with no backing pods. Pre-existing, but visible in the EKS render.

**m5 — ServiceAccount component labels are camelCase.** `templates/serviceaccounts.yaml` emits `app.kubernetes.io/component: {{ $key }}` (`rawWriter`, `lakeWriter`, `warehouseLoader`) while the deployments/pods use kebab-case (`raw-writer`, …). Cosmetic only — `pod_name()` in the verifier selects pods by their kebab-case label and works correctly.

---

## 5. Non-Defect Observations

- **N1 — Disabling Airflow does not break the Silver→PostgreSQL path.** `services/warehouse-loader/runner.py` loads `LakeLayer.SILVER` (not Gold), so the E2E objective "PostgreSQL is loaded" is reachable without Airflow. Note, however, that this is itself a deviation from `PROJECT.md` §4 ("Warehouse Loader owns Gold-to-PostgreSQL loading"), meaning the Gold/Airflow layer is effectively deferred. This is a pre-existing deviation, but it is the reason the Airflow-disable resolution is sound.
- **N2 — State-backend region is hardcoded.** `deploy-eks.sh` `terraform_init()` and `destroy_all()` hardcode `-backend-config="region=eu-north-1"` while `staging.tfvars` deploys to `eu-west-1`. If the bootstrap state bucket/DynamoDB table are intentionally pinned to `eu-north-1`, this is fine but undocumented; otherwise staging would target the wrong backend region.
- **N3 — `GetOffsetShell` is deprecated.** The data-flow check uses `kafka.tools.GetOffsetShell`, present in Kafka 3.9 (Strimzi 0.45) but removed in Kafka 4.0; a future upgrade will require `kafka-get-offsets.sh`.
- **N4 — `S3_BUCKET` is extracted but unused inside `deploy-eks.sh`.** `extract_outputs()` reads `s3_data_bucket`, but the deployment script never passes it to the verifier; verification is a separate manual step (correctly documented with `--bucket-name "$BUCKET"`). Minor.
- **N5 — `SERVICES` still contains `agent`.** `build_and_push_images()` skips it via `agent) continue ;;`, so exactly six images are built, but the array is seven elements long — a source of the M1 confusion.

---

## 6. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The current HEAD (`8eff888`) resolves all blocking and moderate findings from the previous review round:

- **H1 (Airflow image):** resolved by disabling Airflow, consistent with the M14 target architecture and documented. Helm rendering confirms no Airflow resources on EKS.
- **H2 (agent endpoint):** resolved — the check now posts to `POST /api/v1/agent/ask` with the `question` field, matching the actual route (`router prefix=/agent`, `@router.post("/ask")`) and schema (`AgentAskRequest.question`).
- **M1 (S3 bronze false negative):** resolved — `list_objects_v2(Prefix='bronze/')` satisfies raw-writer's `s3:ListBucket` prefix condition.
- **M2 (silver listed from raw-writer):** resolved — silver is now listed from `warehouse-loader`, which holds `s3_read: silver`.
- **M3 (wrong default bucket):** resolved — `--bucket-name` is required and the docs show the correct `terraform output -raw s3_data_bucket` invocation.
- The warehouse check now fails on zero tables, and the removed base64 handling eliminated the line-wrap risk.

Independent verification (helm lint, helm template for both value sets, 120 terraform structural tests, script syntax check, secret scan) all pass. No secrets were introduced, no unrelated code was modified, and the chart renders cleanly.

The only remaining issues are non-blocking: a documentation/configuration inconsistency around the ECR repository count and the unused `agent` infrastructure (M1), plus the minor items m1–m5. These do not prevent acceptance but should be addressed in a follow-up.

---

*This report was written by Qwen Code acting as an independent reviewer. No code was modified as part of this review; the only file changed is this report (`docs/reviews/TASK-123-review.md`).*
