"""Validate Terraform S3 data-lake module (TASK-119)."""

from __future__ import annotations

from pathlib import Path

TERRAFORM_ROOT = Path(__file__).resolve().parents[1] / "terraform"
S3_MODULE = TERRAFORM_ROOT / "modules" / "s3"


def _read(filename: str) -> str:
    return (S3_MODULE / filename).read_text(encoding="utf-8")


def test_s3_bucket_resource_exists() -> None:
    content = _read("main.tf")
    assert 'resource "aws_s3_bucket"' in content


def test_s3_versioning_enabled() -> None:
    content = _read("main.tf")
    assert 'resource "aws_s3_bucket_versioning"' in content
    assert '"Enabled"' in content


def test_s3_encryption_configured() -> None:
    content = _read("main.tf")
    assert 'resource "aws_s3_bucket_server_side_encryption_configuration"' in content
    assert "AES256" in content


def test_s3_public_access_blocked() -> None:
    content = _read("main.tf")
    assert 'resource "aws_s3_bucket_public_access_block"' in content
    assert "block_public_acls" in content
    assert "block_public_policy" in content
    assert "ignore_public_acls" in content
    assert "restrict_public_buckets" in content


def test_s3_lifecycle_rules_present() -> None:
    content = _read("main.tf")
    assert 'resource "aws_s3_bucket_lifecycle_configuration"' in content
    assert "bronze-layer" in content
    assert "silver-layer" in content
    assert "gold-layer" in content
    assert "abort-incomplete-uploads" in content


def test_s3_lifecycle_bronze_expires() -> None:
    content = _read("main.tf")
    assert 'prefix = "bronze/"' in content
    assert "STANDARD_IA" in content


def test_s3_lifecycle_silver_expires() -> None:
    content = _read("main.tf")
    assert 'prefix = "silver/"' in content


def test_s3_lifecycle_gold_no_expiration() -> None:
    content = _read("main.tf")
    assert 'prefix = "gold/"' in content


def test_s3_outputs_reference_real_resources() -> None:
    content = _read("outputs.tf")
    assert "aws_s3_bucket.data_lake" in content
    assert "data_bucket_name" in content
    assert "data_bucket_arn" in content


def test_s3_module_has_required_variables() -> None:
    content = _read("variables.tf")
    assert 'variable "project_name"' in content
    assert 'variable "environment"' in content
    assert 'variable "tags"' in content


def test_root_main_references_s3_module() -> None:
    main_tf = (TERRAFORM_ROOT / "main.tf").read_text(encoding="utf-8")
    assert 'module "s3"' in main_tf
    assert "./modules/s3" in main_tf


def test_root_outputs_include_s3_bucket() -> None:
    outputs = (TERRAFORM_ROOT / "outputs.tf").read_text(encoding="utf-8")
    assert "s3_data_bucket" in outputs
    assert "module.s3.data_bucket_name" in outputs
