# TASK-118 Review — AWS ECR

## 1. Review Header

- **Task ID:** TASK-118 — AWS ECR
- **Review date:** 2026-09-26
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:** `8b8af833a6c600308a0d52462fa028100c06d939...02147f18c707e305740c7d41c5858ce80963ff3e`
- **Reviewed commits:**
  - `e5ced7e1d1dfcd33cc0a8ad685abc2cd1676b339` — `feat(TASK-118): AWS ECR — container repositories with lifecycle and pull policies`
  - `02147f18c707e305740c7d41c5858ce80963ff3e` — `fix(TASK-118): remove ECS policy, fix lifecycle for immutable tags`
- **Reviewed HEAD:** `02147f18c707e305740c7d41c5858ce80963ff3e` on `feature/TASK-118`
- **Scope:** The `ecr` Terraform child module (one repository per platform service, lifecycle policy, outputs), `terraform/README.md` documentation, and the structural test suite `tests/test_terraform_ecr.py`.
- **Verdict:** APPROVED WITH NON-BLOCKING FINDINGS

---

## 2. Requirements Coverage

Task spec (`ai/tasks/TASK-118-aws-ecr.md`) and its Terraform/AWS rules:

| Requirement | Status | Implementation evidence |
|---|---|---|
| One ECR repository per service boundary | **Met** | `aws_ecr_repository.this` with `for_each = toset(var.service_names)`. Root `var.ecr_service_names` default (and both `dev.tfvars` / `staging.tfvars`) list exactly the seven required services: ingestion, processor, raw-writer, lake-writer, warehouse-loader, api, agent. |
| Configure image lifecycle policies to manage storage | **Met** | `aws_ecr_lifecycle_policy.this` (one per repository) expires untagged images after 7 days (`sinceImagePushed` / `days` / `7`). Correct for `IMMUTABLE` tag mutability. |
| IAM access for EKS nodes to pull images | **Deferred (documented)** | No IAM/pull resource exists in the ECR module. The earlier wrong ECS grant was removed in `02147f1`, and `terraform/README.md` §Container Registries states "EKS pull access — granted via node IAM role (TASK-122)". See Finding 1. |
| IAM access follows least-privilege | **N/A in this task** | No IAM resource is created here; the node role belongs to TASK-122 (`ai/tasks/TASK-122-aws-iam.md`). The deferral is least-privilege-correct in the sense that no broad or wrong-principal grant is left behind. |
| ECR reachable from EKS nodes | **Deferred** | Depends on the EKS node IAM role (TASK-122) plus private-subnet routing already provisioned by TASK-117. Not demonstrated in this task. |
| Never commit credentials / access keys / secrets | **Met** | No `AKIA…`, `access_key`, `secret_key`, or token material anywhere in the diff; `test_ecr_no_credentials` performs a smoke check. |
| Add deterministic tests where applicable | **Met (with caveat)** | `tests/test_terraform_ecr.py` — 10 deterministic structural tests, all passing. String-presence checks only; no HCL syntax/plan validation (Finding 3). |
| Documentation updated where needed | **Met** | `terraform/README.md` §Container Registries added and progress table updated (`ecr` → Complete). README is consistent with the final code. |
| No unrelated architecture changes or secrets | **Met** | Diff confined to `terraform/modules/ecr/`, `terraform/README.md`, and the new test file. No provider/dependency/CI changes. |

---

## 3. Git Diff Review

- **Range contents:** Two commits (`e5ced7e` + `02147f1`). Combined diff: **4 files changed, 135 insertions(+), 2 deletions(-)**.
  - Modified: `terraform/modules/ecr/main.tf` (stub → repository + lifecycle policy), `terraform/modules/ecr/outputs.tf` (placeholders → real `repository_urls`/`repository_arns`/`repository_names`), `terraform/README.md` (§Container Registries + progress table).
  - Added: `tests/test_terraform_ecr.py` (10 tests).
- **Branch isolation:** Correct. `feature/TASK-118` contains exactly two TASK-118 commits on top of `8b8af83` (TASK-117). No other task's changes are present.
- **Scope correctness:** Correct. The change fills the ECR placeholder created by TASK-116. The root `module "ecr"` block, `var.ecr_service_names`, and the `output "ecr_repositories"` wiring were already present at the base commit and are unchanged here.
- **Fix commit review:** `02147f1` is a clean, well-scoped correction. It removes the `aws_ecr_repository_policy` that trusted `ecs-tasks.amazonaws.com` (the wrong service principal for an EKS-only platform) and drops the "keep last 10 tagged images" lifecycle rule that is ineffective under `image_tag_mutability = "IMMUTABLE"`. It also removes the now-orphaned test for the repository policy and corrects the README. This addresses the two blocking findings from the earlier review round.
- **Unrelated changes:** None. The `s3`/`rds`/`eks`/`iam` modules remain untouched stubs (their implementation is TASK-119..122 scope).
- **Architectural changes:** None to service boundaries or contracts. The final state no longer introduces any ECS trust relationship.
- **Dependency/configuration changes:** None. No `pyproject.toml`, `requirements*.txt`, `.github/` workflow, or provider-version change.
- **Accidental changes:** None. No debugging code, temporary files, dead code, generated artifacts, or secrets. `force_delete = false` prevents accidental deletion of populated repositories.

---

## 4. Test and Verification Review

- **Tests examined:** `tests/test_terraform_ecr.py` (10 tests) — asserts presence of the ECR repository resource, `IMMUTABLE` mutability, lifecycle-policy resource, `untagged` handling, `scan_on_push`, `encryption_configuration`, the three outputs (`repository_urls`, `repository_arns`, `repository_names`), absence of a credential-looking pattern, and iteration over `var.service_names`.
- **Independently executed by reviewer (all passed):**
  - `python -m pytest tests/test_terraform_ecr.py -q` → **10 passed in 0.09s**
  - `python -m ruff check tests/test_terraform_ecr.py` → **All checks passed!**
  - `python -m ruff format --check tests/test_terraform_ecr.py` → **1 file already formatted**
  - `python -m mypy tests/test_terraform_ecr.py` → **Success: no issues found in 1 source file**
- **Implementation evidence reviewed (not independently executed):**
  - `.github/workflows/ci.yml` runs ruff format/lint, mypy, pytest, an integration-migration step, and a repository-structure check — but has **no Terraform step** (no `terraform fmt`/`validate`/`plan`). The HCL surface has no automated safety net in CI.
- **Not independently executed (tooling unavailable):**
  - `terraform fmt -check` / `terraform validate` — the `terraform` binary is not installed in this environment (`terraform: command not found`). HCL syntax, formatting, and provider/resource-schema resolution were not verified by the reviewer, and the structural tests do not cover them (Finding 3).
- **Integration tests:** Not applicable. This task adds no runtime/cloud/Kafka/persistence surface and does not require `-m integration`; the hermetic structural pytest is the only applicable verification.
- **Verification status:**
  - Structural test suite — **Independently verified** (10/10 passed).
  - Ruff lint + format — **Independently verified** (passed).
  - mypy — **Independently verified** (passed).
  - `terraform fmt` / `terraform validate` — **Unverified** (tool unavailable).

---

## 5. Findings

### Finding 1 — Moderate — "IAM access for EKS nodes to pull images" is deferred, not delivered

- **Severity:** Moderate
- **Affected file/reference:** `terraform/modules/ecr/main.tf` (no pull/IAM resource); `terraform/README.md` §Container Registries ("EKS pull access — granted via node IAM role (TASK-122)").
- **Problem:** The task objective explicitly lists "IAM access for EKS nodes to pull images" and "ECR must be reachable from EKS nodes." The final deliverable creates no EKS pull access; it removes the earlier (incorrect) ECS repository policy and defers the grant to TASK-122. The deferral is architecturally sound — the EKS node IAM role belongs to the `iam` module (TASK-122), which depends on the EKS cluster (TASK-121), both of which are currently empty stubs — and the wrong ECS principal was correctly removed rather than left in place. However, a stated TASK-118 objective is therefore not met inside this task, and the deferral is not recorded in `docs/reviews/FOLLOWUPS.md`.
- **Impact:** No functional defect in the repository/lifecycle work, and no security hazard (no wrong grant remains). The risk is a forgotten dependency: if TASK-122 does not explicitly wire the node role's ECR pull permissions (and, where pods need it, IRSA), EKS nodes will hit `ImagePullBackOff`. `TASK-122-aws-iam.md` mentions IRSA mappings and least-privilege roles but does not name ECR pull as an explicit deliverable.
- **Recommendation:** Record this deferral in `docs/reviews/FOLLOWUPS.md` with a revisit trigger tied to TASK-122 (e.g. "TASK-122 must grant the EKS node role `ecr:GetAuthorizationToken`, `ecr:BatchCheckLayerAvailability`, `ecr:GetDownloadUrlForLayer`, `ecr:BatchGetImage` — and IRSA roles where applicable — and the ECR module must remain reachable from the EKS node security group"). Non-blocking because the node role cannot be created before TASK-121/122 without out-of-scope and circular-dependency work.

### Finding 2 — Minor — Tests are structural string checks; no HCL syntax/format/validation anywhere

- **Severity:** Minor
- **Affected file/reference:** `tests/test_terraform_ecr.py` (all 10 tests); `.github/workflows/ci.yml` (no Terraform step)
- **Problem:** Every test asserts the *presence* of a resource block or substring in the `.tf` text. They do not validate HCL syntax, `terraform fmt` compliance, provider/resource-schema correctness, or semantic values (e.g. the lifecycle `countType`/`countUnit` combination). The prior review's point about the pull-policy principal is now moot (no policy exists), but the broader gap — that the module could be malformed or semantically wrong and the suite would still pass — remains. `test_ecr_no_credentials` uses a regex matching only `access_key = "…"` / `secret_key = "…"` literal assignments, a smoke check rather than a real secret scan.
- **Impact:** The suite can pass even if the HCL is malformed or a credential is introduced in a form the regex does not match, and no CI job closes the gap.
- **Recommendation:** Add a `terraform fmt -check -recursive terraform` step (and, once `terraform init` can run, a `terraform validate`) to CI. Optionally strengthen tests to assert semantic HCL values (e.g. `image_tag_mutability = "IMMUTABLE"`, `tagStatus = "untagged"`, `countType = "sinceImagePushed"`) rather than bare substrings.

### Finding 3 — Minor — `scan_on_push` is the legacy scanning toggle

- **Severity:** Minor
- **Affected file/reference:** `terraform/modules/ecr/main.tf:19-21` (`image_scanning_configuration { scan_on_push = true }`)
- **Problem:** `scan_on_push` is the legacy boolean basic-scanning flag; the current AWS provider v5 idiom for explicit scan configuration is `scan_type = "BASIC"` / `"ENHANCED"` (or the separate `aws_ecr_repository_scanning_configuration` resource). The value used here is still valid and enables basic scanning.
- **Impact:** None functional. Modernization/consistency point only.
- **Recommendation:** Optionally migrate to `scan_type = "ENHANCED"` for the more capable scanning, or leave as-is and accept basic scanning.

---

## 6. Non-Defect Observations

1. **Repository resource is well-formed.** `for_each = toset(var.service_names)`, `name = "${local.name_prefix}-${each.value}"`, `force_delete = false`, immutable tags, per-service `Name`/`Service` tags, and `merge(var.tags, …)` follow the TASK-116/117 conventions (project-name prefix, environment, default tags).
2. **Lifecycle policy is now correct for immutable tags.** The single `untagged` / `sinceImagePushed` / 7-day rule is the correct minimal lifecycle policy under `image_tag_mutability = "IMMUTABLE"`; the removed "keep last 10 tagged" rule would have been a no-op. README now accurately states "expire untagged images after 7 days".
3. **Outputs are complete and correctly shaped.** `repository_urls`, `repository_arns`, and `repository_names` are keyed by service name; the root `outputs.tf` already consumes `module.ecr.repository_urls` via `output "ecr_repositories"` (TASK-116 wiring), so the module integrates cleanly.
4. **No secrets introduced.** The module reads no credentials; naming, tags, and policy JSON contain no sensitive material, and the structural test performs a (limited) credential smoke check.
5. **Scope discipline respected.** The diff completes only the ECR placeholder and leaves the `s3`/`rds`/`eks`/`iam` stubs untouched, consistent with the one-task-per-execution rule.
6. **Tagged-image accumulation (operational note).** With immutable tags and unique version tags, tagged images will accumulate indefinitely because lifecycle policies cannot expire tagged images in an `IMMUTABLE` repository. This is inherent to the chosen design, not a defect. Worth a follow-up decision on the CI tagging scheme (e.g. push untagged build artifacts or a bounded set of mutable tags) if storage growth matters later.
7. **Explicit `encryption_type = "AES256"`.** This is already the default (and effectively only) value for private repositories, so the block adds no behavior, but it is a harmless explicit at-rest-encryption statement.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The ECR module correctly provisions one immutable-tag, scan-on-push, AES256-encrypted repository per service for all seven required services, applies a correct untagged-image lifecycle policy, exposes complete outputs, is correctly isolated on `feature/TASK-118`, introduces no secrets or unrelated changes, and is documented with a passing deterministic test suite (10/10 independently verified, plus ruff and mypy clean).

The two blocking findings from the prior review round are resolved: commit `02147f1` removed the incorrect ECS repository policy and the ineffective tagged-image lifecycle rule, and corrected the README accordingly. The remaining findings are non-blocking: the EKS pull-access requirement is deferred to TASK-122 (Moderate, must be tracked so it is not forgotten), the test suite is structural-only with no `terraform` validation in CI (Minor), and `scan_on_push` uses the legacy scanning toggle (Minor).
