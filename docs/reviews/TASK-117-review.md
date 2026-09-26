# TASK-117 Review — AWS Networking

## 1. Review Header

- **Task ID:** TASK-117 — AWS Networking
- **Review date:** 2026-09-26
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:** `928bcb815f56cec6adfeab64446de6e8c15fd488...9a1b8058d46e3ae2fd53b5a81310f0464d499a95`
- **Reviewed commits:**
  - `ced6b8a57dbb68d87092ec62ee6b0ed7ef5135e0` — `feat(TASK-117): AWS networking — VPC, subnets, gateways, security groups`
  - `9a1b8058d46e3ae2fd53b5a81310f0464d499a95` — `fix(TASK-117): address Qwen review findings — self-ref SG, NAT comment, description`
- **Reviewed HEAD:** `9a1b8058d46e3ae2fd53b5a81310f0464d499a95` on `feature/TASK-117`
- **Scope:** The `networking` Terraform child module — VPC, public/private subnets, internet gateway, NAT gateway, route tables, and three security groups (`eks_cluster`, `eks_nodes`, `rds`) — plus the corresponding `terraform/README.md` topology documentation and a deterministic structural test suite (`tests/test_terraform_networking.py`).
- **Verdict:** APPROVED WITH NON-BLOCKING FINDINGS

---

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
|---|---|---|
| Provision a VPC | **Met** | `aws_vpc.this` with `enable_dns_support` and `enable_dns_hostnames = true`. |
| Public and private subnets | **Met** | `aws_subnet.public` and `aws_subnet.private`, one per AZ via `cidrsubnet(var.vpc_cidr, 8, …)`; public subnets use indices `0..n-1`, private subnets use `n..2n-1` (no overlap). |
| Internet gateway | **Met** | `aws_internet_gateway.this` attached to the VPC; `aws_route.public_internet` routes `0.0.0.0/0` to it. |
| NAT gateway | **Met** | `aws_nat_gateway.this` + `aws_eip.nat` in `public[0]`; private route table routes `0.0.0.0/0` to it. Single-AZ NAT is now explicitly documented as a dev/staging tradeoff. |
| Route tables (public and private) | **Met** | Separate `aws_route_table.public`/`private`, routes, and per-AZ `aws_route_table_association` for both tiers. |
| Security groups | **Met** | `eks_cluster`, `eks_nodes`, `rds` security groups with ingress/egress rules. |
| Support EKS, RDS, and internal communication | **Met** | Private subnets for compute/database; ELB tags for public/internal load balancers; dedicated EKS cluster/node SGs and an RDS SG; outputs expose `vpc_id`, subnet ids, and SG ids for downstream TASK-120/121 modules. |
| Use private subnets for compute/database; public only for LB/NAT | **Met** | NAT in `public[0]`; public subnets tagged `kubernetes.io/role/elb`, private tagged `kubernetes.io/role/internal-elb`. |
| Security groups follow least-privilege | **Met (with caveat)** | Node-to-node, kubelet, and RDS rules now all use SG references (`referenced_security_group_id`). Only the EKS cluster API rule (TCP 443) remains VPC-CIDR-scoped, and its description now honestly states that scope (Finding 3). |
| Document network topology | **Met (with caveat)** | `terraform/README.md` §Network Topology has an ASCII diagram, ELB-tag notes, and per-SG ingress scoping. One topology line is stale after the node self-reference fix (Finding 1). |
| Follow AWS networking best practices | **Met (with caveat)** | Multi-AZ subnets, dedicated route tables, DNS hostnames, `create_before_destroy` on SGs, self-referencing node SG. Single-AZ NAT remains an acknowledged availability tradeoff (Non-Defect Observation 2). |
| Never commit credentials/access keys/secrets | **Met** | No `AKIA…`, `access_key`, `secret_key`, or token material in the diff. `rds_password=CHANGE_ME` in README is a placeholder; `var.rds_password` is a TASK-116 variable, not part of this diff. |
| Add deterministic tests where applicable | **Met (with caveat)** | `tests/test_terraform_networking.py` — 12 deterministic structural tests, all passing. Tests are string-presence checks only; no HCL syntax/plan validation (Finding 2). |
| No unrelated architecture changes or secrets | **Met** | Diff is confined to `terraform/modules/networking/`, `terraform/README.md`, and the new test file. |

---

## 3. Git Diff Review

- **Range contents:** Two commits. Combined diff: 4 files, **+379 / −4**.
  - Modified: `terraform/modules/networking/main.tf` (stub → full module), `terraform/modules/networking/outputs.tf` (placeholders → real refs), `terraform/README.md` (§Network Topology + progress table).
  - Added: `tests/test_terraform_networking.py` (+83).
  - The fix commit `9a1b805` touches only `main.tf` (+10/−8): converts `eks_nodes_self` from `cidr_ipv4 = var.vpc_cidr` to `referenced_security_group_id = aws_security_group.eks_nodes.id`, adds the single-NAT tradeoff comment, and changes the `eks_cluster_api` description to `"EKS API from VPC"`.
- **Branch isolation:** Correct. `feature/TASK-117` contains exactly the two TASK-117 commits on top of `928bcb8` (TASK-116). No other task's changes are present.
- **Scope correctness:** Correct. The change is exactly the networking module the task describes, completing the placeholder created by TASK-116.
- **Unrelated changes:** None. The `ecr`/`s3`/`rds`/`eks`/`iam` modules are untouched (remaining placeholder state is TASK-118..122 scope).
- **Architectural changes:** None. No service boundaries, event contracts, or repository layout outside the `networking` module are affected.
- **Dependency/configuration changes:** None. No `pyproject.toml`, `requirements*.txt`, or CI change.
- **Accidental changes:** None. No debugging code, temporary files, dead code, generated artifacts, or secrets.
- **Out-of-scope changes:** None. The four forward-looking outputs (`eks_cluster_security_group_id`, `eks_nodes_security_group_id`, `rds_security_group_id`, `nat_gateway_id`) are expected scaffolding for TASK-120/121 and are currently unconsumed.

---

## 4. Test and Verification Review

- **Tests examined:** `tests/test_terraform_networking.py` (12 tests) — asserts the presence of the VPC, public/private subnets, internet/NAT gateways, route tables, and the three security groups; verifies required outputs are declared; checks the RDS SG uses `referenced_security_group_id`; checks subnets use `var.availability_zones`; checks private subnets do not set `map_public_ip_on_launch`; and checks the Kubernetes ELB tags are present.
- **Independently executed by reviewer (all passed):**
  - `python -m pytest tests/test_terraform_networking.py -q` → **12 passed in 0.08s**
  - `python -m ruff check tests/test_terraform_networking.py` → **All checks passed!**
  - `python -m ruff format --check tests/test_terraform_networking.py` → **1 file already formatted**
  - `python -m mypy tests/test_terraform_networking.py` → **Success: no issues found in 1 source file**
- **Not independently executed (tooling unavailable in this environment):**
  - `terraform fmt -check` / `terraform validate` — the `terraform` binary is not installed (`terraform: command not found`). HCL syntax, formatting, and provider resolution were not verified by the reviewer, and the structural tests do not cover them (Finding 2).
- **CI coverage reviewed:** No Terraform step exists in CI, so HCL syntax/format/validation has no automated safety net anywhere in the repository today.
- **Integration tests:** Not applicable. This task adds no runtime/cloud/Kafka/persistence surface and does not require `-m integration`; the structural pytest is hermetic and is the only applicable verification.
- **Verification status:**
  - Structural test suite — **Independently verified** (12/12 passed).
  - Ruff lint + format — **Independently verified** (passed).
  - mypy — **Independently verified** (passed).
  - `terraform fmt` / `terraform validate` — **Unverified** (tool unavailable).

---

## 5. Findings

### Finding 1 — Minor — README topology line is stale after the node self-reference fix

- **Severity:** Minor
- **Affected file/reference:** `terraform/README.md`, §Network Topology diagram, line 84 (`├── eks-nodes — node-to-node within VPC, kubelet from cluster SG`)
- **Problem:** The fix commit changed `eks_nodes_self` from a VPC-CIDR-scoped rule to a self-referenced SG rule, but the README still describes node-to-node traffic as "within VPC". The documentation now understates the tighter scoping that the code actually enforces.
- **Impact:** Documentation/code drift. Low functional impact, but a reader relying on the topology diagram would believe node-to-node access is broader than it is.
- **Recommendation:** Update the line to reflect the self-reference, e.g. `eks-nodes — node-to-node (self-referenced SG), kubelet from cluster SG`.

### Finding 2 — Minor — Tests are structural string checks; no HCL syntax/format/plan validation

- **Severity:** Minor
- **Affected file/reference:** `tests/test_terraform_networking.py` (all 12 tests); `.github/workflows/ci.yml` (no Terraform step)
- **Problem:** Every test asserts the *presence* of a resource block or substring in the `.tf` text. They do not validate HCL syntax, `terraform fmt` compliance, `cidrsubnet` arithmetic, route-table → subnet/gateway wiring, or the actual source of each security-group rule. `test_networking_rds_sg_restricts_to_eks_nodes` only checks that `referenced_security_group_id` appears anywhere in `main.tf`; after the fix there are now **three** occurrences (node self, kubelet-from-cluster, RDS-from-EKS), so the test would still pass even if the RDS rule were changed to a VPC CIDR. `test_networking_no_public_ip_on_private_subnets` relies on a brittle `split('resource "aws_subnet" "private"')[1]...` slice.
- **Impact:** The suite gives a false sense of validation: it can pass even if a future edit introduces an HCL syntax error, a broken subnet CIDR, or a widened RDS rule, because no check asks Terraform to parse the configuration. No CI job covers this gap.
- **Recommendation:** Add a `terraform fmt -check -recursive terraform` (and, once `terraform init` can run, a `terraform validate`) step to CI. Tighten the RDS test to assert the reference appears on the `rds_from_eks` rule specifically, and make the private-subnet assertion more robust.

### Finding 3 — Minor — EKS cluster API rule (TCP 443) remains VPC-wide, now honestly documented

- **Severity:** Minor
- **Affected file/reference:** `terraform/modules/networking/main.tf`, `aws_vpc_security_group_ingress_rule "eks_cluster_api"` (`cidr_ipv4 = var.vpc_cidr`); description now `"EKS API from VPC"`.
- **Problem:** The prior round's description/scope mismatch is resolved (the description now matches the actual scope), but the rule still permits TCP 443 from the entire VPC CIDR rather than restricting to the node SG plus an explicit operator/admin CIDR. Least-privilege would scope the control-plane endpoint more tightly.
- **Impact:** Low — the EKS API endpoint enforces IAM/RBAC authentication, so a VPC-wide 443 allow is a modest surface, not a bypass. It remains a missed least-privilege opportunity for a production-oriented platform (`PROJECT.md` §11).
- **Recommendation:** For production, scope worker traffic to `referenced_security_group_id = aws_security_group.eks_nodes.id` and add a separate, explicitly-named ingress for operator `kubectl` access from a specific admin/VPN CIDR. Acceptable as-is for dev/staging.

---

## 6. Non-Defect Observations

1. **Prior blocking finding is resolved.** The previous review's High finding — `eks_nodes_self` scoped to the entire VPC on all ports/protocols — is fixed: the rule now uses `referenced_security_group_id = aws_security_group.eks_nodes.id`, matching the least-privilege pattern already used by the RDS rule. The self-reference pattern is the correct AWS provider 5.x idiom and does not create a Terraform dependency cycle.
2. **Single NAT gateway is now an explicitly documented tradeoff.** The code comment states single-AZ NAT is a deliberate cost tradeoff for dev/staging and that production should add one NAT per AZ. This satisfies the prior Moderate finding's minimum requirement. It should be revisited (per-AZ NATs) before a production `prod` environment is applied.
3. **Subnet CIDR scheme is correct.** For a `/16` VPC and three AZs, public subnets occupy `10.0.0.0/24`–`10.0.2.0/24` and private subnets `10.0.3.0/24`–`10.0.5.0/24`, with no overlap; `length(var.availability_zones) + count.index` cleanly avoids collision for any realistic AZ count.
4. **RDS ingress is the best-constructed rule in the module:** PostgreSQL 5432 restricted to `referenced_security_group_id = aws_security_group.eks_nodes.id` with no VPC-CIDR fallback.
5. **Correct SG replacement pattern:** `name_prefix` + `create_before_destroy = true` on all three security groups avoids name-collision churn when SGs referenced by other resources are replaced.
6. **Provider idioms are current:** the separate-rule resources (`aws_vpc_security_group_ingress_rule`/`_egress_rule`, AWS provider 5.x) and `aws_eip.nat.domain = "vpc"` are the non-deprecated forms.
7. **No secrets introduced.** The `tags`/`default_tags` scheme from TASK-116 is preserved without collision; `rds_password` remains an unset, `sensitive` root variable passed at plan/apply time.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The networking module is functionally complete and correctly structured: VPC, multi-AZ public/private subnets with a correct CIDR scheme, internet and NAT gateways, dedicated public/private route tables, and three purpose-scoped security groups, all documented and covered by a passing deterministic test suite (12/12 independently verified, plus ruff and mypy clean). No secrets, unrelated changes, or architectural drift were introduced, and the diff is correctly isolated to `feature/TASK-117`.

The prior round's blocking High finding (VPC-wide node-to-node ingress) is resolved via a self-referencing security-group rule, and the Moderate single-NAT and Minor cluster-API description findings were addressed. The three remaining findings are all Minor and non-blocking: a stale README topology line, structurally shallow HCL test coverage with no `terraform` validation in CI, and a residual VPC-wide EKS API (443) allow that is now honestly documented. None of these prevent acceptance; they should be addressed opportunistically before the AWS milestone reaches a production environment.
