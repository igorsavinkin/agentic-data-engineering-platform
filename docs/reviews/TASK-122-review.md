# TASK-122 Qwen Review — Round 1

**Reviewer:** Qwen Code CLI
**Date:** 2026-09-26
**Verdict:** CHANGES REQUIRED (all findings addressed in fix commit)

## Summary

Sound, idiomatic implementation. The IRSA trust policy and root-module wiring are correct. Main issues were least-privilege gaps that contradicted the module's own documentation.

## Findings

### HIGH

1. **CloudWatch Logs and Secrets Manager ARNs wildcard region AND account** — `arn:aws:logs:*:*:...` and `arn:aws:secretsmanager:*:*:...` left both account and region unscoped.
   - **Fix:** Added `aws_region` variable and `data.aws_caller_identity.current` data source. ARNs now scoped to `arn:aws:logs:${var.aws_region}:${local.account_id}:...`.

2. **ECR pull policy grants more than "pull"** — `GetRepositoryPolicy`, `DescribeRepositories`, `ListImages` are not needed for `docker pull`.
   - **Fix:** Trimmed to `BatchCheckLayerAvailability`, `GetDownloadUrlForLayer`, `BatchGetImage`.

### MEDIUM

3. **Unnecessary ACL grants on S3** — `s3:PutObjectAcl` and `s3:GetObjectAcl` not needed since bucket has `block_public_acls = true`.
   - **Fix:** Removed both ACL actions.

4. **S3 statements conflate ListBucket with object actions** — ListBucket is a bucket-level action but was grouped with object-level actions on mixed resources.
   - **Fix:** Split into separate statements: ListBucket on bucket ARN with prefix condition, PutObject/GetObject on object ARN only.

### LOW

5. Hardcoded service sets decoupled from `var.service_accounts` — accepted as-is since the default covers all services.
6. `ecr_repository_arns` empty default — accepted as latent; root wiring always passes non-empty map.
7. `secretsmanager:DescribeSecret` broader than needed — **Fix:** Removed, kept only `GetSecretValue`.
8. `logs:CreateLogGroup` ARN pattern — accepted; separate mechanism pre-creates groups.
9. Tests substring-only — **Fix:** Added `test_no_wildcard_region_or_account_in_arns` and region/account scoping tests.

## Post-Fix Verification

- 26/26 IAM tests pass (5 new tests added)
- 105/105 all Terraform structural tests pass
- ruff check: All checks passed
- ruff format: 1 file already formatted
