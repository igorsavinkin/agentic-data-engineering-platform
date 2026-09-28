"""Validate Terraform bootstrap configuration for remote backend provisioning."""

from __future__ import annotations

import re
from pathlib import Path

BOOTSTRAP_ROOT = Path(__file__).resolve().parents[1] / "terraform" / "bootstrap"

EXPECTED_FILES = [
    "main.tf",
    "variables.tf",
    "outputs.tf",
    "versions.tf",
    "providers.tf",
    "README.md",
]

SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(access_key|secret_key)\s*=\s*\"[A-Za-z0-9/+=]+\""),
    re.compile(r"(?i)AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)(password|secret)\s*=\s*\"[^\"]+\""),
]


def test_bootstrap_files_exist() -> None:
    for filename in EXPECTED_FILES:
        path = BOOTSTRAP_ROOT / filename
        assert path.exists(), f"Missing bootstrap file: terraform/bootstrap/{filename}"


def test_bootstrap_creates_s3_bucket() -> None:
    content = (BOOTSTRAP_ROOT / "main.tf").read_text(encoding="utf-8")
    assert 'resource "aws_s3_bucket"' in content, "Must create an S3 bucket"


def test_bootstrap_enables_versioning() -> None:
    content = (BOOTSTRAP_ROOT / "main.tf").read_text(encoding="utf-8")
    assert "aws_s3_bucket_versioning" in content, "Must enable bucket versioning"
    assert '"Enabled"' in content, "Versioning status must be Enabled"


def test_bootstrap_enables_encryption() -> None:
    content = (BOOTSTRAP_ROOT / "main.tf").read_text(encoding="utf-8")
    assert "server_side_encryption" in content, "Must enable server-side encryption"
    assert "AES256" in content, "Must use AES256 encryption"


def test_bootstrap_blocks_public_access() -> None:
    content = (BOOTSTRAP_ROOT / "main.tf").read_text(encoding="utf-8")
    assert "public_access_block" in content, "Must block public access"
    assert "block_public_acls" in content
    assert "block_public_policy" in content
    assert "ignore_public_acls" in content
    assert "restrict_public_buckets" in content


def test_bootstrap_creates_dynamodb_table() -> None:
    content = (BOOTSTRAP_ROOT / "main.tf").read_text(encoding="utf-8")
    assert 'resource "aws_dynamodb_table"' in content, "Must create a DynamoDB table"
    assert "LockID" in content, "DynamoDB hash key must be LockID"
    assert "PAY_PER_REQUEST" in content, "Must use on-demand billing"


def test_bootstrap_bucket_name_is_variable() -> None:
    content = (BOOTSTRAP_ROOT / "main.tf").read_text(encoding="utf-8")
    assert "var.bucket_name" in content, "Bucket name must come from a variable"


def test_bootstrap_default_region_is_eu_north_1() -> None:
    content = (BOOTSTRAP_ROOT / "variables.tf").read_text(encoding="utf-8")
    assert "eu-north-1" in content, "Default region must be eu-north-1"


def test_bootstrap_bucket_name_has_validation() -> None:
    content = (BOOTSTRAP_ROOT / "variables.tf").read_text(encoding="utf-8")
    assert 'variable "bucket_name"' in content
    assert "validation" in content, "Bucket name variable must have validation"


def test_bootstrap_outputs_bucket_name() -> None:
    content = (BOOTSTRAP_ROOT / "outputs.tf").read_text(encoding="utf-8")
    assert "state_bucket_name" in content
    assert "locks_table_name" in content
    assert "backend_config_snippet" in content


def test_bootstrap_has_prevent_destroy() -> None:
    content = (BOOTSTRAP_ROOT / "main.tf").read_text(encoding="utf-8")
    assert content.count("prevent_destroy = true") >= 2, (
        "Both bucket and DynamoDB table must have prevent_destroy"
    )


def test_bootstrap_no_credentials() -> None:
    tf_files = list(BOOTSTRAP_ROOT.rglob("*.tf"))
    tf_files += list(BOOTSTRAP_ROOT.rglob("*.tfvars*"))
    for tf_file in tf_files:
        content = tf_file.read_text(encoding="utf-8")
        for pattern in SENSITIVE_PATTERNS:
            assert not pattern.search(content), f"Potential credential found in {tf_file.name}"


def test_bootstrap_terraform_version_constrained() -> None:
    content = (BOOTSTRAP_ROOT / "versions.tf").read_text(encoding="utf-8")
    assert "required_version" in content
    assert "hashicorp/aws" in content


def test_main_backend_uses_backend_config() -> None:
    terraform_root = BOOTSTRAP_ROOT.parent
    content = (terraform_root / "backend.tf").read_text(encoding="utf-8")
    assert 'backend "s3"' in content
    assert "encrypt" in content
    assert "eu-west-1" not in content, "Backend must not hardcode eu-west-1"


def test_main_backend_no_hardcoded_bucket() -> None:
    terraform_root = BOOTSTRAP_ROOT.parent
    content = (terraform_root / "backend.tf").read_text(encoding="utf-8")
    assert "ai-data-platform-terraform" not in content, "Backend must not hardcode a bucket name"
