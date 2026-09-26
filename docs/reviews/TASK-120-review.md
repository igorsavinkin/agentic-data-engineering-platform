# TASK-120 Review — AWS RDS PostgreSQL

## 1. Review Header

- **Task ID:** TASK-120 — AWS RDS PostgreSQL
- **Review date:** 2026-09-26
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:** `6adf7b4f0ed2f206212267dc19d8afdedb5420c7...3095404ccc4ef6f16054d8f5bdb745859537ceb5` (three-dot; equivalent to the two-dot range `6adf7b4f0ed2f206212267dc19d8afdedb5420c7..3095404ccc4ef6f16054d8f5bdb745859537ceb5` because `6adf7b4` is the direct parent of `3095404`)
- **Reviewed commits:**
  - `3095404ccc4ef6f16054d8f5bdb745859537ceb5` — `feat(TASK-120): AWS RDS PostgreSQL warehouse with encrypted storage and backups`
- **Reviewed HEAD:** `3095404ccc4ef6f16054d8f5bdb745859537ceb5` on `feature/TASK-120`
- **Scope:** The `rds` Terraform child module (PostgreSQL 16.4 on gp3 storage with auto-scaling, DB subnet group in private subnets, EKS-node-only ingress via the networking module, automated backups, encrypted storage, deletion protection), the root `module "rds"` wiring in `terraform/main.tf`, `terraform/README.md` documentation, and the deterministic structural test suite `tests/test_terraform_rds.py`.
- **Verdict:** APPROVED WITH NON-BLOCKING FINDINGS

---

## 2. Requirements Coverage

Task spec (`ai/tasks/TASK-120-aws-rds-postgresql.md`) and its Terraform/AWS rules:

| Requirement | Status | Implementation evidence |
|---|---|---|
| Implement Terraform for AWS RDS PostgreSQL replacing local PostgreSQL for the warehouse layer | **Met** | `aws_db_instance.this` with `engine = "postgres"`, `engine_version = "16.4"` in `terraform/modules/rds/main.tf`. |
| Configure instance size | **Met** | `instance_class = var.instance_class` (default `db.t3.medium` in root `terraform/variables.tf`); sizing rationale documented in a code comment and `terraform/README.md`. |
| Configure storage | **Met** | `allocated_storage = 20`, `max_allocated_storage = 100`, `storage_type = "gp3"`, `storage_encrypted = true`. |
| Configure backups | **Met** | `backup_retention_period = var.backup_retention_days` (default 7), `backup_window = "03:00-04:00"`, `maintenance_window = "Mon:04:00-Mon:05:00"`. |
| Configure security groups | **Met** | `vpc_security_group_ids = [var.security_group_id]` wired to `module.networking.rds_security_group_id` in root `terraform/main.tf`. |
| Connection from EKS | **Met** | The networking module's `rds` SG has a single ingress rule (`rds_from_eks`, port 5432, `referenced_security_group_id = aws_security_group.eks_nodes.id`). No public/VPC-CIDR ingress. |
| RDS must be in private subnets | **Met** | `aws_db_subnet_group.this` uses `subnet_ids = var.private_subnet_ids`; `publicly_accessible` is not set, so it defaults to `false` (see Non-Defect Observation 1). |
| Accessible only from EKS security group | **Met** | Ingress is restricted to the EKS node SG only (port 5432); verified in `terraform/modules/networking/main.tf`. |
| Enable automated backups and appropriate retention | **Met** | Automated backups with configurable 7-day retention (appropriate for dev/staging; see Finding 4 on root wiring). |
| Credentials must use AWS Secrets Manager or equivalent; never hardcoded | **Partially met** | "Never hardcoded" is satisfied: `password`/`username` are `sensitive = true`, `rds_password` has no default, and no password exists in Git (verified across `*.tf` and `*.tfvars`). "Secrets Manager or equivalent" is **not** met — the master password is supplied via a sensitive variable and stored in (encrypted) Terraform state; Secrets Manager integration is deferred to TASK-122. See Finding 1. |
| Never commit credentials, access keys, or secrets | **Met** | No `AKIA…`, `access_key`/`secret_key`, or password material anywhere in the diff or in `terraform/envs/*.tfvars` (which set `rds_username = "platform_admin"` but no password). |
| Instance sizing should be documented and justifiable | **Met** | `db.t3.medium` (2 vCPU, 4 GiB) documented with dev/staging-vs-production guidance in `terraform/modules/rds/main.tf` and `terraform/README.md`. |
| Implement this task only / no unrelated architecture changes | **Met** | Diff confined to the RDS module, root wiring, README, and the RDS test file. No changes to service boundaries, contracts, or other modules. |
| Add deterministic tests where applicable | **Met (with caveat)** | `tests/test_terraform_rds.py` — 12 deterministic structural tests, all passing. String-presence checks only; no HCL syntax/format/plan validation (Finding 3). |
| Documentation updated where needed | **Met** | `terraform/README.md` §PostgreSQL Warehouse added and progress table updated (`rds` → Complete). |
| Run repository quality checks | **Met (independently confirmed)** | ruff lint/format clean, mypy clean, pytest (all Terraform tests) passing. See §4. |

---

## 3. Git Diff Review

- **Range contents:** One commit (`3095404`). Task-specific diff: **6 files changed, 186 insertions(+), 3 deletions(-)**.
  - Modified:
    - `terraform/modules/rds/main.tf` — stub → DB subnet group + `aws_db_instance` (PostgreSQL 16.4, gp3, encryption, backups, deletion protection).
    - `terraform/modules/rds/outputs.tf` — empty-string/constant placeholders → real `aws_db_instance.this.endpoint` / `.port` / `.db_name` / `.id`.
    - `terraform/modules/rds/variables.tf` — added `security_group_id` and `backup_retention_days` variables.
    - `terraform/main.tf` — added `security_group_id = module.networking.rds_security_group_id` to the `module "rds"` block.
    - `terraform/README.md` — added §PostgreSQL Warehouse and flipped the progress table row to `Complete`.
  - Added: `tests/test_terraform_rds.py` (12 tests).
- **Branch isolation:** Correct. `feature/TASK-120` contains exactly one TASK-120 commit on top of `6adf7b4` (TASK-119). No other task's changes are present in the branch.
- **Scope correctness:** Correct. The change fills the RDS placeholder created by TASK-116. The root `module "rds"` block and `output "rds_endpoint"` were already present at the base commit (confirmed: `6adf7b4:terraform/outputs.tf` already referenced `module.rds.endpoint`), and are only minimally extended here.
- **Unrelated changes:** None. The `eks`/`iam` modules remain untouched stubs (their implementation is TASK-121..122 scope). No Python code, Docker, Helm, Kubernetes, or CI changes.
- **Architectural changes:** None. PostgreSQL remains the serving/analytical layer; Warehouse Loader's Gold-to-PostgreSQL ownership (`PROJECT.md` §4) is untouched. The module only provisions the AWS RDS resource that that boundary will eventually target.
- **Dependency/configuration changes:** None. No `pyproject.toml`, `requirements*.txt`, `.github/` workflow, or provider-version change.
- **Accidental changes:** None. No debugging code, temporary files, dead code (beyond the unused variable noted in Finding 2), generated artifacts, or secrets.

---

## 4. Test and Verification Review

- **Tests examined:** `tests/test_terraform_rds.py` (12 tests) — asserts presence of `aws_db_instance`, `aws_db_subnet_group`, the postgres engine, gp3 storage, `max_allocated_storage`, storage encryption, backup/maintenance windows, deletion protection, `final_snapshot_identifier`, the `security_group_id` variable, sensitive username/password variables, real output references, the root `module "rds"` wiring, and the root `rds_endpoint` output.
- **Independently executed by reviewer (all passed):**
  - `python -m pytest tests/test_terraform_rds.py -q` → **12 passed in 0.15s**
  - `python -m pytest tests/test_terraform_*.py -q` → **56 passed in 0.85s** (rds + structure + s3 + networking + ecr)
  - `python -m ruff check tests/test_terraform_rds.py` → **All checks passed!**
  - `python -m ruff format --check tests/test_terraform_rds.py` → **1 file already formatted**
  - `python -m mypy tests/test_terraform_rds.py` → **Success: no issues found in 1 source file**
- **Implementation evidence reviewed (not independently executed):**
  - `.github/workflows/ci.yml` runs ruff format/lint, mypy, pytest, an integration-migration step, and a repository-structure check — but has **no Terraform step** (no `terraform fmt`/`validate`/`plan`). The HCL surface has no automated safety net in CI (same gap noted in the TASK-119 review).
- **Not independently executed (tooling unavailable):**
  - `terraform fmt -check` / `terraform validate` — the `terraform` binary is not installed in this environment (`terraform: command not found`). HCL syntax, formatting, and provider/resource-schema resolution were not verified by the reviewer, and the structural tests do not cover them (Finding 3).
- **Integration tests:** Not applicable. This task adds no runtime/cloud/Kafka/persistence *code* surface and does not require `-m integration`; the hermetic structural pytest is the only applicable verification. (The task touches the RDS infrastructure boundary, but the declarative HCL has no runtime integration path to exercise in this repository yet — the RDS instance cannot be created without an AWS account and `terraform apply`.)
- **Verification status:**
  - Structural test suite — **Independently verified** (12/12; 56/56 including sibling Terraform tests).
  - Ruff lint + format — **Independently verified** (passed).
  - mypy — **Independently verified** (passed).
  - `terraform fmt` / `terraform validate` — **Unverified** (tool unavailable).

---

## 5. Findings

### Finding 1 — Moderate — "Credentials must use AWS Secrets Manager or equivalent" is not met; it is deferred to TASK-122

- **Severity:** Moderate
- **Affected file/reference:** `terraform/modules/rds/main.tf` (`password = var.password`, no `manage_master_user_password`); `terraform/README.md` §PostgreSQL Warehouse ("Secrets Manager integration for runtime credential injection is handled by the IAM module (TASK-122)").
- **Problem:** The task objective states "Credentials must be managed via AWS Secrets Manager or equivalent" and the Terraform/AWS rules state "Credentials must use AWS Secrets Manager or equivalent; never hardcoded." The implementation supplies the RDS master password through a plain `password = var.password` input and does not use Secrets Manager (nor the built-in `manage_master_user_password = true` / `manage_master_user_password_rotation`), SSM Parameter Store, or any equivalent managed-secret mechanism. The deferral is documented and assigned to TASK-122, but TASK-122 is the *IAM* task, and Secrets Manager is a distinct service — and, unlike the TASK-119 IAM deferral, there is no hard dependency (EKS OIDC ARN) preventing the master password from being Secrets Manager-managed within TASK-120 itself.
- **Impact:** No security breach: the "never hardcoded" half of the rule is genuinely satisfied (verified — no password in Git; `sensitive = true`; the value lives only in the encrypted S3 state). The risk is requirement non-compliance and a forgotten/ambiguous follow-up: the master password is not rotated, not discoverable via a secret store, and its provisioning depends on an operator manually supplying `-var="rds_password=..."`. The README's TASK-122 hand-off only addresses *runtime service credential injection*, not the *master password* created here.
- **Recommendation:** The lowest-cost fix is to set `manage_master_user_password = true` (optionally with `manage_master_user_password_rotation`) on `aws_db_instance.this`, which makes AWS provision and store the master password in Secrets Manager with zero additional resources — satisfying the rule inside TASK-120. Alternatively, obtain explicit human sign-off that the sensitive-variable approach is acceptable for dev/staging and that TASK-122 will close the gap (in which case this becomes a documented sequencing decision, not a defect). Given the explicit wording of the task's own rules, this borders on High; it is rated Moderate because the security-critical invariant (no secrets in Git) holds and the deferral is documented.

### Finding 2 — Minor — `vpc_id` input variable is declared and wired but never used by the RDS module

- **Severity:** Minor
- **Affected file/reference:** `terraform/modules/rds/variables.tf` (`variable "vpc_id"`); `terraform/modules/rds/main.tf` (no reference to `var.vpc_id`); root `terraform/main.tf` (`vpc_id = module.networking.vpc_id` in the `module "rds"` block).
- **Problem:** The RDS module declares `vpc_id` and the root module passes it in, but `main.tf` never consumes it. The DB subnet group uses `var.private_subnet_ids` and the instance uses `var.security_group_id`; nothing references `var.vpc_id`.
- **Impact:** No functional defect (Terraform permits unused input variables), but it is dead configuration that implies the module derives placement/security from the VPC ID when it does not.
- **Recommendation:** Remove the unused `variable "vpc_id"` from the module and the corresponding `vpc_id` argument from the root `module "rds"` block, or actually use it (e.g., the subnet group could accept the VPC for validation) — whichever matches intent.

### Finding 3 — Minor — Tests are structural string checks with several near-tautological assertions, and no HCL validation exists anywhere

- **Severity:** Minor
- **Affected file/reference:** `tests/test_terraform_rds.py` (all 12 tests); `.github/workflows/ci.yml` (no Terraform step).
- **Problem:** Every test asserts the *presence* of a resource block or substring. They do not validate HCL syntax, `terraform fmt` compliance, provider/resource-schema correctness, or semantic values. Several assertions are weaker than their names suggest: `test_rds_storage_encrypted` asserts `"true" in content` (would pass if the literal `true` appeared anywhere, e.g. in a comment), and `test_rds_sensitive_credentials` asserts `"sensitive" in content` (same). No test asserts the negative invariants that matter — e.g. `publicly_accessible` is absent/false, `storage_encrypted = true` is on the `aws_db_instance` specifically, or the default backup retention equals 7. There is also no per-module `no_credentials` test (the global `test_terraform_structure.py` credential regex only matches `access_key`/`secret_key` and `AKIA…`, so a hardcoded `password = "..."` in a `.tfvars` would not be caught by it).
- **Impact:** The suite can pass even if the HCL is malformed or a security-relevant attribute regresses, and no CI job closes the gap. This is consistent with the sibling Terraform tasks (TASK-116..119), but it remains a genuine coverage limitation for a security-sensitive module.
- **Recommendation:** Add a `terraform fmt -check -recursive terraform` step (and, once `terraform init` can run against a provider, a `terraform validate`) to CI. Strengthen tests to assert concrete attribute values in context (e.g. a regex matching `storage_encrypted\s*=\s*true` inside the `aws_db_instance` block) and add a per-module check that no `password\s*=\s*"..."` literal is committed.

### Finding 4 — Minor — `backup_retention_days` is configurable at the module level but not exposed at the root, contradicting the README

- **Severity:** Minor
- **Affected file/reference:** root `terraform/main.tf` (`module "rds"` block omits `backup_retention_days`); `terraform/README.md` §PostgreSQL Warehouse ("Backups: automated, 7-day retention (configurable)").
- **Problem:** The module declares `backup_retention_days` (default 7), but the root module does not pass it, so an operator applying via `terraform/main.tf` cannot change retention without editing the root file. The README's "(configurable)" is therefore misleading at the operator-facing level.
- **Impact:** No defect; a minor documentation/wiring inconsistency. Staging also uses the 7-day default despite `enable_deletion_protection = true`.
- **Recommendation:** Either pass `backup_retention_days = var.rds_backup_retention_days` (with a root variable and per-environment `.tfvars` value) or reword the README to "7-day retention (module default)".

---

## 6. Non-Defect Observations

1. **`publicly_accessible` is not set explicitly.** It defaults to `false`, and the DB subnet group uses private subnets, so RDS is not publicly reachable. Setting `publicly_accessible = false` explicitly would be clearer defense-in-depth, but the current posture is correct.
2. **`skip_final_snapshot` is coupled to `enable_deletion_protection`.** `skip_final_snapshot = !var.enable_deletion_protection` means `dev.tfvars` (deletion protection off) will destroy the warehouse *without* a final snapshot. This is acceptable for dev but worth a conscious human decision, since the warehouse holds historical analytical data. The two settings are conceptually independent; decoupling them (a separate `skip_final_snapshot`/`final_snapshot` variable) would be more flexible.
3. **`final_snapshot_identifier` uses a fixed name.** `${local.name_prefix}-final` will collide if the same instance is destroyed and recreated with a prior final snapshot still present (RDS requires unique snapshot identifiers). Cosmetic for dev; consider a timestamp suffix.
4. **EKS-only ingress is correctly wired via the networking module.** The `rds` SG (TASK-117) has a single inbound rule from the EKS node SG on 5432, and TASK-120 wires it via `security_group_id`. This satisfies "accessible only from EKS security group" without duplicating security-group logic in the RDS module.
5. **Instance sizing is documented and justifiable.** The `db.t3.medium` default (2 vCPU / 4 GiB) is explained with a production-scale-up note (`db.r6g.large` or larger) in both the code comment and README, satisfying the "documented and justifiable" rule and the Human Learning Rule.
6. **Multi-AZ is not configured.** Not a task requirement (TASK-120 does not mandate high availability), but the private DB subnet group spans three AZs, so a future `multi_az = true` + `db.m*`/`db.r*` instance class would be a straightforward follow-up for production.
7. **Scope discipline respected.** The diff completes only the RDS placeholder and leaves the `eks`/`iam` stubs untouched, consistent with the one-task-per-execution rule. No secrets were introduced.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The RDS module correctly provisions a managed PostgreSQL 16.4 instance on encrypted gp3 storage (20–100 GiB auto-scaling), placed in private subnets via a DB subnet group, with ingress restricted to the EKS node security group (port 5432), automated backups with configurable retention, and deletion protection with final-snapshot support. It is correctly isolated on `feature/TASK-120`, introduces no secrets or unrelated changes, and is documented with a deterministic test suite that I independently verified passing (12/12 structural tests, plus ruff and mypy clean; 56/56 across all Terraform tests).

The findings are non-blocking but should be tracked: the "Secrets Manager or equivalent" credential requirement is deferred to TASK-122 rather than met inside TASK-120 (Moderate — the "never hardcoded" invariant holds, but the managed-secret mechanism is absent, and the trivial `manage_master_user_password = true` fix is available); the `vpc_id` module variable is dead (Minor); the test suite is structural-only with no `terraform` validation in CI and no password-specific secret check (Minor); and `backup_retention_days` is module-configurable but not root-wired despite being described as configurable (Minor). None of these prevent acceptance of the declarative RDS work itself; Finding 1 is the one to confirm as a deliberate sequencing decision versus a gap to close now.
