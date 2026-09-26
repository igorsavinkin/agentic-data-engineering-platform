# TASK-121 Review — AWS EKS

## 1. Review Header

- **Task ID:** TASK-121 — AWS EKS
- **Review date:** 2026-09-26
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:** `d710bd35c693bf6b50ef0c3be0995f58cddd37f0...06b27e0da6fa25e403cc42194c08b632008bbbbe` (three-dot; equivalently `d710bd35c693bf6b50ef0c3be0995f58cddd37f0..06b27e0da6fa25e403cc42194c08b632008bbbbe` because `d710bd3` is the direct parent of `06b27e0`)
- **Reviewed commits:**
  - `06b27e0da6fa25e403cc42194c08b632008bbbbe` — `feat(TASK-121): AWS EKS cluster with managed node groups and Strimzi Kafka`
- **Reviewed HEAD:** `06b27e0da6fa25e403cc42194c08b632008bbbbe` on `feature/TASK-121`
- **Scope:** The `eks` Terraform child module (EKS cluster, IAM cluster/node roles, CloudWatch log group, OIDC provider for IRSA, two managed node groups — general-purpose and Kafka-dedicated), the root `module "eks"` wiring and new root variables/outputs, the `tls` provider version pin, a Strimzi Kafka CR + namespace manifest, `docs/architecture/aws-eks-cluster.md`, and the deterministic structural test suite `tests/test_terraform_eks.py`.
- **Verdict:** APPROVED WITH NON-BLOCKING FINDINGS

---

## 2. Requirements Coverage

Task spec (`ai/tasks/TASK-121-aws-eks.md`) and its Terraform/AWS rules, cross-referenced with `ai/PROJECT.md` §2/§4/§11, `ai/SPECIFICATION.md` §25, and `ai/ROADMAP.md` §21:

| Requirement | Status | Implementation evidence |
|---|---|---|
| Terraform for AWS EKS cluster | **Met** | `aws_eks_cluster.this` in `terraform/modules/eks/main.tf` with IAM role, private subnets, control-plane SG, `endpoint_private_access = true`, and version `var.cluster_version` (default `1.31`). |
| Managed node groups | **Met** | `aws_eks_node_group.general` and `aws_eks_node_group.kafka`, each with `scaling_config`, `update_config`, and instance-type lists. |
| Node group sizing configurable | **Met** | Desired/min/max sizes and instance types exposed as root `eks_*` variables with documented defaults (general `t3.medium` 1–4, kafka `t3.large` 3–5). |
| Cluster networking | **Met (with caveat)** | Private-subnet placement, control-plane SG (`eks_cluster`) wired via `cluster_security_group_id`, service CIDR `172.20.0.0/16`. The dedicated `eks_nodes` security group is **not** attached to the node groups (Finding 1). |
| IRSA (IAM Roles for Service Accounts) | **Met (foundation)** | OIDC identity provider created from the cluster issuer (`aws_iam_openid_connect_provider.cluster`, thumbprint via `tls_certificate`); `oidc_provider_arn`/`oidc_provider_url` outputs exposed. Per-service IRSA roles are correctly deferred to the `iam` module (TASK-122), which already consumes `module.eks.oidc_provider_arn`. |
| Kafka deployed in EKS (Strimzi, not MSK) | **Partially met** | `kubernetes/deployments/strimzi-kafka-eks.yaml` defines a 3-broker / 3-ZooKeeper Strimzi `Kafka` CR with durable config (RF 3, `min.insync.replicas` 2, auto-create disabled, 168 h retention). The Strimzi **operator** is not provisioned anywhere (Finding 3), and broker PVs rely on an absent StorageClass (Finding 2). |
| Kafka reachable from ingestion and processor within the cluster | **Met (documented)** | Bootstrap FQDN `platform-cluster-kafka-bootstrap.strimzi.svc:9092` documented in `docs/architecture/aws-eks-cluster.md`. Actual service bootstrap wiring (`APP_KAFKA_BOOTSTRAP_SERVERS`) is TASK-123 scope (Non-Defect Observation 4). |
| EKS hosts all platform services and Kafka | **Met** | General node group for platform services; dedicated tainted Kafka node group (`role=kafka`, `dedicated=kafka:NoSchedule`) with matching tolerations in the Kafka CR. |
| Use IRSA for pod-level AWS permissions | **Met (foundation)** | OIDC provider is the IRSA prerequisite; role/trust-policy creation is TASK-122 (consistent with the TASK-118/119/120 deferral pattern). |
| Default to Strimzi or equivalent; do not introduce MSK | **Met** | Strimzi Kafka CR used; no MSK resource present. |
| Document cluster configuration and sizing | **Met (with caveat)** | `docs/architecture/aws-eks-cluster.md` documents cluster/networking/node-group/IRSA/Kafka configuration and sizing. `terraform/README.md` is left stale (`eks` still "Pending", no EKS section) and `kubernetes/README.md` omits the new Strimzi files (Finding 7). |
| Never commit credentials/access keys/secrets | **Met** | No `AKIA…`, `access_key`/`secret_key`, password, or token material in the diff or anywhere under `terraform/` (independently confirmed). |
| Add deterministic tests where applicable | **Met (with caveat)** | `tests/test_terraform_eks.py` — 23 deterministic structural tests, all passing. String-presence checks only; no HCL validation and the Strimzi YAML is untested (Finding 5). |
| No unrelated architecture changes or secrets | **Met** | Diff confined to the EKS module, root wiring, `docs/architecture/aws-eks-cluster.md`, the two Strimzi Kubernetes manifests, and the new test file. |

---

## 3. Git Diff Review

- **Range contents:** One commit (`06b27e0`). Task-specific diff: **11 files changed, +719 / −9**.
  - Added: `docs/architecture/aws-eks-cluster.md` (+96), `kubernetes/deployments/strimzi-kafka-eks.yaml` (+73), `kubernetes/namespaces/strimzi-namespace.yaml` (+7), `tests/test_terraform_eks.py` (+165).
  - Modified:
    - `terraform/modules/eks/main.tf` — stub `locals` → full module (cluster, IAM roles, CloudWatch log group, OIDC provider, two node groups).
    - `terraform/modules/eks/outputs.tf` — empty-string placeholders → real resource references (`cluster_name`, `cluster_endpoint`, `oidc_provider_arn`, `oidc_provider_url`, `node_role_arn`, `cluster_certificate_authority`); `cluster_security_group_id` is a pass-through echo of the input variable.
    - `terraform/modules/eks/variables.tf` — added cluster SG, public endpoint, service CIDR, log retention, and general/kafka node-group sizing variables.
    - `terraform/main.tf` — `module "eks"` block extended with all new inputs.
    - `terraform/variables.tf` — added root `eks_*` variables.
    - `terraform/outputs.tf` — added `eks_oidc_provider_arn`.
    - `terraform/versions.tf` — added `tls` provider (`hashicorp/tls ~> 4.0`).
- **Branch isolation:** Correct. `feature/TASK-121` contains exactly one TASK-121 commit on top of `d710bd3` (TASK-120). Working tree clean; no other task's changes present.
- **Scope correctness:** Correct. The change fills the EKS placeholder created by TASK-116 and adds the Kafka manifest set. The `module "iam"` wiring (`eks_cluster_name`, `eks_oidc_provider_arn`) was already present at the base commit and is now satisfied by real outputs.
- **Unrelated changes:** None. The `networking`/`ecr`/`s3`/`rds`/`iam` modules are untouched (the `iam` module remains a stub, which is TASK-122 scope).
- **Architectural changes:** None. No service boundaries, event contracts, or lake/warehouse ownership are affected. Strimzi-Kafka-in-EKS is the SPECIFICATION.md §25 default topology; the local kind Kafka (KRaft single-broker) is a separate, unaffected dev topology.
- **Dependency/configuration changes:** One new provider (`tls ~> 4.0`) — justified, it is required to compute the OIDC provider thumbprint. No Python/dependency/CI change.
- **Accidental changes:** None. No debugging code, temporary files, dead code (beyond the unused `vpc_id` variable, Finding 6), generated artifacts, or secrets.
- **Out-of-scope changes:** None introduced. Two forward-looking items are left to later tasks rather than pulled in here (correct scoping): the EBS CSI driver / Strimzi operator installation (TASK-123) and the actual per-service IRSA roles (TASK-122).

---

## 4. Test and Verification Review

- **Tests examined:** `tests/test_terraform_eks.py` (23 tests) — asserts presence of the EKS cluster, cluster/node IAM roles and policy attachments, the OIDC provider, the `tls_certificate` data source, the CloudWatch log group and log types, private/public endpoint settings, the cluster SG wiring, general/kafka scaling config, the kafka taint, real output references, required module variables, the root `module "eks"` wiring, the root EKS node-config variables, the root `eks_oidc_provider_arn` output, and the `tls` provider declaration.
- **Independently executed by reviewer (all passed):**
  - `python -m pytest tests/test_terraform_eks.py -q` → **23 passed in 0.20s**
  - `python -m pytest tests/test_terraform_*.py -q` → **79 passed in 0.77s** (eks + structure + s3 + networking + ecr + rds)
  - `python -m ruff check tests/test_terraform_eks.py` → **All checks passed!**
  - `python -m ruff format --check tests/test_terraform_eks.py` → **1 file already formatted**
  - `python -m mypy tests/test_terraform_eks.py` → **Success: no issues found in 1 source file**
- **Implementation evidence reviewed (not independently executed):**
  - `.github/workflows/ci.yml` runs ruff format/lint, mypy, pytest, an integration-migration step, and a repository-structure check — but has **no Terraform step** (no `terraform fmt`/`validate`/`plan`). The HCL surface has no automated safety net in CI (same gap noted in TASK-117/118/119/120 reviews).
- **Not independently executed (tooling unavailable):**
  - `terraform fmt -check` / `terraform validate` — the `terraform` binary is not installed in this environment (`terraform: command not found`). HCL syntax, formatting, and provider/resource-schema resolution were not verified by the reviewer, and the structural tests do not cover them. `terraform/main.tf`'s `module "eks"` block shows inconsistent `=` alignment, which is direct evidence that `terraform fmt` was not run (Finding 4).
- **Integration tests:** Not applicable. This task adds no runtime/cloud/Kafka/persistence *code* surface and does not require `-m integration`; the hermetic structural pytest is the only applicable verification. The Strimzi manifests and EKS HCL have no runtime integration path to exercise in this repository without an AWS account and `terraform apply`.
- **Verification status:**
  - Structural test suite — **Independently verified** (23/23; 79/79 including sibling Terraform tests).
  - Ruff lint + format — **Independently verified** (passed).
  - mypy — **Independently verified** (passed).
  - `terraform fmt` / `terraform validate` — **Unverified** (tool unavailable).

---

## 5. Findings

### Finding 1 — Moderate — The `eks_nodes` security group is never attached to the managed node groups, breaking RDS (and node-to-node/kubelet) connectivity

- **Severity:** Moderate (borders on High)
- **Affected file/reference:** `terraform/modules/eks/main.tf` (`aws_eks_node_group.general` / `.kafka` — no security-group reference and no `launch_template`); `terraform/modules/networking/outputs.tf` (`eks_nodes_security_group_id`, exported but never consumed); `terraform/modules/networking/main.tf` (`rds_from_eks` ingress references `aws_security_group.eks_nodes.id`).
- **Problem:** The networking module (TASK-117) creates a dedicated `eks_nodes` security group (self-referencing node-to-node, kubelet-from-cluster) and the RDS module (TASK-120) scopes its only ingress rule to `aws_security_group.eks_nodes.id`. The TASK-117 review explicitly recorded `eks_nodes_security_group_id` as "expected scaffolding for TASK-120/121." But the EKS module neither consumes `eks_nodes_security_group_id` nor declares a launch template. `aws_eks_node_group` has no direct `security_group_ids` argument; without a launch template, EKS applies only the EKS-managed cluster security group to the nodes. As a result the `eks_nodes` SG is orphaned — its node-to-node and kubelet rules have no effect, and the RDS ingress rule (port 5432, sourced from `eks_nodes`) will never match any worker-node traffic. PostgreSQL would be unreachable from the EKS-hosted warehouse-loader/API/agent.
- **Impact:** A silent connectivity break in the AWS topology. The cluster and node groups still provision and join correctly (nodes get the EKS-created cluster SG), and in-cluster Kafka is unaffected, but the warehouse/serving layer cannot reach RDS. `docs/architecture/aws-eks-cluster.md` compounds this by stating that "Node-to-node communication and kubelet access from the control plane are configured in the networking module" — true of the orphaned SG, but not of the actual node attachments.
- **Recommendation:** Attach the node security group by passing `eks_nodes_security_group_id` into the EKS module and referencing it in a `launch_template { ... }` block with `security_group_ids` on each node group (the only supported way to add custom SGs to a managed node group), or obtain explicit human sign-off that node-SG wiring is deferred to TASK-123 and track it as a blocking prerequisite. This must be resolved before the AWS deployment is exercised.

### Finding 2 — Moderate — Strimzi broker/ZooKeeper PVs rely on a default StorageClass that is not provisioned

- **Severity:** Moderate
- **Affected file/reference:** `kubernetes/deployments/strimzi-kafka-eks.yaml` (`spec.kafka.storage` 50Gi `persistent-claim`, `spec.zookeeper.storage` 20Gi `persistent-claim`, no `storageClassName`); `terraform/modules/eks/main.tf` (no `aws_eks_addon` for `aws-ebs-csi-driver`).
- **Problem:** The Kafka CR requests persistent-claim storage without an explicit `storageClassName`. EKS clusters at Kubernetes 1.31 have no default StorageClass unless the Amazon EBS CSI driver add-on is installed, and the Terraform does not provision that add-on (or any other StorageClass). Consequently the Kafka and ZooKeeper PVCs would remain `Pending` and the Strimzi cluster would never become ready.
- **Impact:** The "Kafka deployment in EKS" deliverable cannot actually acquire persistent storage as written. This is silent at plan time and would only surface as stuck PVCs after applying the CR.
- **Recommendation:** Provision the `aws-ebs-csi-driver` EKS add-on in the module (or document it as a TASK-123 prerequisite) and/or set an explicit `storageClassName` in the Kafka CR once a class exists.

### Finding 3 — Moderate — Strimzi operator is not provisioned; the Kafka CR alone is not a deployable Kafka

- **Severity:** Moderate
- **Affected file/reference:** `kubernetes/deployments/strimzi-kafka-eks.yaml` (header comment: "Apply after installing the Strimzi operator in the strimzi namespace"); no operator manifest/Helm release exists anywhere in the repository.
- **Problem:** The task objective is "Kafka deployment (Strimzi or equivalent) reachable from ingestion and processor services." The deliverable is a `Kafka` custom resource, which is inert without the Strimzi cluster operator installed in the `strimzi` namespace. Nothing in the Terraform or Kubernetes manifests installs that operator (no `helm_release`, no operator Deployment/CRDs).
- **Impact:** The Kafka deployment is declarative-only; applying the current manifests produces a namespace and an un-reconciled CR. The operator install is a manual, undocumented prerequisite.
- **Recommendation:** Add the Strimzi operator installation (Helm chart or manifest set) to Terraform, or explicitly document it as a TASK-123 step with the exact operator version pinned.

### Finding 4 — Minor — `terraform fmt` was not run (inconsistent `=` alignment in the root `module "eks"` block)

- **Severity:** Minor
- **Affected file/reference:** `terraform/main.tf` (`module "eks"` block).
- **Problem:** The `module "eks"` arguments are not aligned to a common `=` column — short keys (`project_name`, `environment`, `cluster_version`, `tags`) are padded to one width while the longer keys (`cluster_security_group_id`, `general_node_instance_types`, etc.) are single-spaced. `terraform fmt` would align all consecutive assignments to the longest key.
- **Impact:** Cosmetic only, but it is direct evidence that the repository's formatting discipline (ruff format for Python; `terraform fmt` for HCL) was not applied to the HCL, and it would produce a noisy diff on the next `terraform fmt` run.
- **Recommendation:** Run `terraform fmt -recursive terraform/` and re-commit.

### Finding 5 — Minor — Tests are structural string checks only; the Strimzi manifests are entirely untested, and there is no HCL validation anywhere

- **Severity:** Minor
- **Affected file/reference:** `tests/test_terraform_eks.py` (all 23 tests); `.github/workflows/ci.yml` (no Terraform step).
- **Problem:** Every test asserts the presence of a resource block or substring in the `.tf` text. They do not validate HCL syntax, `terraform fmt` compliance, provider/resource-schema correctness, or semantic values. The actual "Kafka deployment" deliverable (`kubernetes/deployments/strimzi-kafka-eks.yaml`, `kubernetes/namespaces/strimzi-namespace.yaml`) has **zero** tests: no assertion of the replication factor, `min.insync.replicas`, the taint/toleration match between the node group and the Kafka CR, the listener ports, or the bootstrap-service reachability the task requires. No test asserts the node group attaches the node SG (Finding 1) or that IRSA/OIDC is wired to the `iam` module. Some assertions are near-tautological (e.g. `test_eks_node_group_general_exists` asserts `'"general"' in content`).
- **Impact:** The suite gives a false sense of validation: it would still pass if the HCL were malformed, the taint/toleration drifted out of sync, the storage or replication config regressed, or the OIDC wiring broke. No CI job closes the gap (consistent with TASK-116..120).
- **Recommendation:** Add `terraform fmt -check -recursive terraform` (and eventually `terraform validate`) to CI. Add tests that parse the Strimzi YAML (e.g. via `yaml.safe_load`) and assert the durability parameters and that the toleration `dedicated=kafka:NoSchedule` matches the node group taint `dedicated=kafka:NO_SCHEDULE`.

### Finding 6 — Minor — `vpc_id` is declared and root-wired into the EKS module but never used

- **Severity:** Minor
- **Affected file/reference:** `terraform/modules/eks/variables.tf` (`variable "vpc_id"`); `terraform/modules/eks/main.tf` (no `var.vpc_id` reference); root `terraform/main.tf` (`vpc_id = module.networking.vpc_id`).
- **Problem:** The module declares `vpc_id` and the root passes it in, but `main.tf` never consumes it (the cluster uses `var.private_subnet_ids` and `var.cluster_security_group_id`). This is the same dead-variable pattern flagged in the TASK-120 review (RDS `vpc_id`).
- **Impact:** No functional defect (Terraform permits unused input variables), but it is dead configuration that implies placement derives from the VPC ID when it does not.
- **Recommendation:** Remove the unused `variable "vpc_id"` from the module and the `vpc_id` argument from the root `module "eks"` block, or actually use it.

### Finding 7 — Minor — Documentation drift: `terraform/README.md` and `kubernetes/README.md` were not updated

- **Severity:** Minor
- **Affected file/reference:** `terraform/README.md` (§Implementation Progress still lists `eks | TASK-121 | Pending`; no EKS section); `kubernetes/README.md` (directory listing omits `strimzi-kafka-eks.yaml` and `strimzi-namespace.yaml`).
- **Problem:** The task's Definition of Done requires documentation to be "updated where needed," and every prior AWS task (TASK-117..120) added a section to `terraform/README.md` and flipped the progress row to `Complete`. TASK-121 instead added a standalone `docs/architecture/aws-eks-cluster.md` (good and sufficient for the "document cluster configuration and sizing" rule) but left the `terraform/README.md` progress table stale and added no EKS section there, and left the `kubernetes/README.md` directory tree stale relative to the two new Strimzi files.
- **Impact:** Readers consulting the canonical per-module README are told EKS is still pending; the `kubernetes/README.md` tree no longer reflects the files on disk. Low functional impact, but inconsistent with the established documentation convention.
- **Recommendation:** Flip the progress row to `Complete`, add a short EKS section (or a cross-link to `docs/architecture/aws-eks-cluster.md`), and add the two Strimzi manifests to the `kubernetes/README.md` directory listing.

---

## 6. Non-Defect Observations

1. **IRSA foundation is correct and thoughtfully scoped.** The OIDC provider is created with the standard `tls_certificate` thumbprint pattern, and the module exposes both `oidc_provider_arn` (consumed by the `iam` module, which is already wired in root `main.tf`) and `oidc_provider_url` (the issuer with `https://` stripped, exactly what TASK-122 will need for IRSA trust policies). Deferring the actual per-service roles to TASK-122 is architecturally sound and consistent with the TASK-118/119/120 deferral pattern.
2. **Kafka durability configuration is sound.** RF 3, `min.insync.replicas = 2`, `offsets.topic.replication.factor = 3`, `transaction.state.log.*` set, `auto.create.topics.enable = "false"`, and `log.retention.hours = 168` all align with ADR-001 (auto-create disabled; 7-day product-topic retention). The dedicated tainted node group with matching tolerations correctly isolates Kafka from general workloads.
3. **Security defaults are good.** `endpoint_private_access = true` with public endpoint opt-in (`false` by default), no hardcoded credentials, and the OIDC provider's `client_id_list = ["sts.amazonaws.com"]` are all correct least-privilege defaults.
4. **Cross-namespace reachability is correctly specified, but service wiring is deferred.** The bootstrap FQDN `platform-cluster-kafka-bootstrap.strimzi.svc:9092` is the correct cross-namespace form. However, the platform services' `APP_KAFKA_BOOTSTRAP_SERVERS` (currently `kafka:29092` for kind) and the `kafka-topics-job` are not pointed at the Strimzi bootstrap in this task — that wiring belongs to TASK-123 (AWS deployment) and should be tracked.
5. **ZooKeeper-based Strimzi vs. local KRaft Kafka is a deliberate topology difference, not a defect.** The kind deployment uses a single-broker KRaft Kafka (no ZooKeeper) for local dev; the EKS deployment uses 3-broker Strimzi with 3 ZooKeeper nodes. Both are valid; the difference is expected (dev single-node vs. prod multi-node) but worth a one-line note for readers.
6. **Rolling-update availability tradeoff on the Kafka node group.** `update_config.max_unavailable = 1` with `min_size = desired_size = 3` means a rolling node update transiently leaves only 2 Kafka-capable nodes for 3 brokers + 3 ZooKeeper pods. Acceptable for dev/staging; consider `max_unavailable`/surge tuning or a 4th node for production.
7. **`cluster_security_group_id` is echoed as an output.** `output "cluster_security_group_id" { value = var.cluster_security_group_id }` re-exports an input. Harmless and not consumed downstream, but a pass-through output with no added value; could be dropped.
8. **No secrets introduced.** Independent scan of `terraform/` for `AKIA…`, `access_key`/`secret_key`, `password = "..."`, and token material returned nothing; `rds_password`/`rds_username` remain `sensitive` root variables.
9. **Scope discipline respected.** The diff completes only the EKS placeholder plus the Strimzi manifests and leaves the `iam` module stub and the deployment-wiring concerns to TASK-122/123, consistent with the one-task-per-execution rule.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The EKS module correctly provisions the cluster, cluster/node IAM roles and policy attachments, CloudWatch control-plane logging, the IRSA OIDC provider, and two configurable managed node groups (a general pool and a tainted Kafka pool with matching Strimzi tolerations). It is correctly isolated on `feature/TASK-121`, introduces no secrets or unrelated changes, adds the `tls` provider only where required, and is documented with a deterministic test suite that I independently verified passing (23/23 structural tests; 79/79 across all Terraform tests, plus ruff and mypy clean). The Strimzi Kafka CR embodies the correct durability settings and the SPECIFICATION.md §25 default (Strimzi in EKS, not MSK).

The findings are non-blocking but must be tracked before the AWS milestone is actually deployed. The single most important item is **Finding 1**: the dedicated `eks_nodes` security group — which the RDS module's only ingress rule depends on, and which the TASK-117 review anticipated would be consumed here — is never attached to the managed node groups, so RDS PostgreSQL is currently unreachable from EKS. Findings 2 and 3 (no EBS CSI/StorageClass and no Strimzi operator) mean the Kafka CR cannot actually run as written; both are prerequisites that TASK-123 must supply or that should be automated now. The remaining findings (terraform fmt, structurally shallow tests with no Strimzi coverage, the unused `vpc_id` variable, and stale READMEs) are minor and consistent with the sibling AWS tasks. None of these prevent acceptance of the declarative EKS/Kafka work itself, but Finding 1 in particular should be confirmed as "fix now" versus "explicitly tracked for TASK-123" before the AWS deployment is exercised.
