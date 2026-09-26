"""Validate Terraform IAM module (TASK-122)."""

from __future__ import annotations

from pathlib import Path

TERRAFORM_ROOT = Path(__file__).resolve().parents[1] / "terraform"
IAM_MODULE = TERRAFORM_ROOT / "modules" / "iam"


def _read(filename: str) -> str:
    return (IAM_MODULE / filename).read_text(encoding="utf-8")


def _read_root(filename: str) -> str:
    return (TERRAFORM_ROOT / filename).read_text(encoding="utf-8")


# --- IRSA roles ---


def test_service_roles_created_for_all_services() -> None:
    content = _read("main.tf")
    assert 'resource "aws_iam_role" "service"' in content
    assert "for_each = var.service_accounts" in content


def test_irsa_trust_policy_uses_oidc_provider() -> None:
    content = _read("main.tf")
    assert "Federated = var.eks_oidc_provider_arn" in content
    assert "sts:AssumeRoleWithWebIdentity" in content


def test_irsa_trust_condition_scopes_to_service_account() -> None:
    content = _read("main.tf")
    assert ":sub" in content
    assert "system:serviceaccount:" in content
    assert ":aud" in content
    assert "sts.amazonaws.com" in content


# --- CloudWatch Logs ---


def test_cloudwatch_logs_policy_exists() -> None:
    content = _read("main.tf")
    assert 'resource "aws_iam_policy" "cloudwatch_logs"' in content
    assert "logs:CreateLogStream" in content
    assert "logs:PutLogEvents" in content


def test_cloudwatch_logs_attached_to_all_services() -> None:
    content = _read("main.tf")
    assert 'resource "aws_iam_role_policy_attachment" "cloudwatch_logs"' in content


# --- ECR pull ---


def test_ecr_pull_policy_exists() -> None:
    content = _read("main.tf")
    assert 'resource "aws_iam_policy" "ecr_pull"' in content
    assert "ecr:BatchGetImage" in content
    assert "ecr:GetDownloadUrlForLayer" in content


def test_ecr_get_auth_token_uses_wildcard() -> None:
    content = _read("main.tf")
    assert "ecr:GetAuthorizationToken" in content


def test_ecr_pull_attached_to_all_services() -> None:
    content = _read("main.tf")
    assert 'resource "aws_iam_role_policy_attachment" "ecr_pull"' in content


# --- S3 write ---


def test_s3_write_policy_for_raw_writer_and_lake_writer() -> None:
    content = _read("main.tf")
    assert 'resource "aws_iam_policy" "s3_write"' in content
    assert "s3:PutObject" in content
    assert "bronze" in content
    assert "silver" in content


def test_s3_write_attached() -> None:
    content = _read("main.tf")
    assert 'resource "aws_iam_role_policy_attachment" "s3_write"' in content


# --- S3 read ---


def test_s3_read_policy_for_warehouse_loader() -> None:
    content = _read("main.tf")
    assert 'resource "aws_iam_policy" "s3_read"' in content
    assert "s3:GetObject" in content


def test_s3_read_attached() -> None:
    content = _read("main.tf")
    assert 'resource "aws_iam_role_policy_attachment" "s3_read"' in content


# --- Secrets Manager ---


def test_secrets_read_policy_exists() -> None:
    content = _read("main.tf")
    assert 'resource "aws_iam_policy" "secrets_read"' in content
    assert "secretsmanager:GetSecretValue" in content
    assert "secretsmanager:DescribeSecret" in content


def test_secrets_read_attached_to_db_services() -> None:
    content = _read("main.tf")
    assert 'resource "aws_iam_role_policy_attachment" "secrets_read"' in content


# --- Variables ---


def test_required_variables_declared() -> None:
    content = _read("variables.tf")
    assert 'variable "project_name"' in content
    assert 'variable "environment"' in content
    assert 'variable "eks_cluster_name"' in content
    assert 'variable "eks_oidc_provider_arn"' in content
    assert 'variable "eks_oidc_provider_url"' in content
    assert 'variable "data_bucket_arn"' in content
    assert 'variable "ecr_repository_arns"' in content
    assert 'variable "service_accounts"' in content
    assert 'variable "tags"' in content


# --- Outputs ---


def test_service_role_arns_output() -> None:
    content = _read("outputs.tf")
    assert 'output "service_role_arns"' in content
    assert "aws_iam_role.service" in content


# --- Root module wiring ---


def test_root_module_passes_oidc_url() -> None:
    content = _read_root("main.tf")
    assert "eks_oidc_provider_url" in content
    assert "module.eks.oidc_provider_url" in content


def test_root_module_passes_data_bucket_arn() -> None:
    content = _read_root("main.tf")
    assert "data_bucket_arn" in content
    assert "module.s3.data_bucket_arn" in content


def test_root_module_passes_ecr_arns() -> None:
    content = _read_root("main.tf")
    assert "ecr_repository_arns" in content
    assert "module.ecr.repository_arns" in content


def test_root_outputs_iam_role_arns() -> None:
    content = _read_root("outputs.tf")
    assert "iam_service_role_arns" in content
    assert "module.iam.service_role_arns" in content


# --- No wildcards except where required ---


def test_no_wildcard_actions_except_ecr_auth_token() -> None:
    content = _read("main.tf")
    lines = content.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == '"*",':
            context = "\n".join(lines[max(0, i - 5) : i + 1])
            assert "ecr:GetAuthorizationToken" in context, (
                f"Wildcard resource found outside ECR auth token at line {i + 1}"
            )
