"""Validate Terraform RDS PostgreSQL module (TASK-120)."""

from __future__ import annotations

from pathlib import Path

TERRAFORM_ROOT = Path(__file__).resolve().parents[1] / "terraform"
RDS_MODULE = TERRAFORM_ROOT / "modules" / "rds"


def _read(filename: str) -> str:
    return (RDS_MODULE / filename).read_text(encoding="utf-8")


def test_rds_instance_resource_exists() -> None:
    content = _read("main.tf")
    assert 'resource "aws_db_instance"' in content


def test_rds_postgres_engine() -> None:
    content = _read("main.tf")
    assert 'engine         = "postgres"' in content
    assert "engine_version" in content


def test_rds_db_subnet_group() -> None:
    content = _read("main.tf")
    assert 'resource "aws_db_subnet_group"' in content
    assert "var.private_subnet_ids" in content


def test_rds_storage_encrypted() -> None:
    content = _read("main.tf")
    assert "storage_encrypted" in content
    assert "true" in content


def test_rds_gp3_storage() -> None:
    content = _read("main.tf")
    assert 'storage_type          = "gp3"' in content
    assert "max_allocated_storage" in content


def test_rds_backup_configured() -> None:
    content = _read("main.tf")
    assert "backup_retention_period" in content
    assert "backup_window" in content
    assert "maintenance_window" in content


def test_rds_deletion_protection() -> None:
    content = _read("main.tf")
    assert "deletion_protection" in content
    assert "final_snapshot_identifier" in content


def test_rds_security_group_variable() -> None:
    content = _read("variables.tf")
    assert 'variable "security_group_id"' in content


def test_rds_sensitive_credentials() -> None:
    content = _read("variables.tf")
    assert 'variable "username"' in content
    assert 'variable "password"' in content
    assert "sensitive" in content


def test_rds_outputs_reference_real_resources() -> None:
    content = _read("outputs.tf")
    assert "aws_db_instance.this" in content
    assert "endpoint" in content
    assert "port" in content


def test_root_main_passes_security_group() -> None:
    main_tf = (TERRAFORM_ROOT / "main.tf").read_text(encoding="utf-8")
    assert 'module "rds"' in main_tf
    assert "security_group_id" in main_tf
    assert "module.networking.rds_security_group_id" in main_tf


def test_root_outputs_include_rds_endpoint() -> None:
    outputs = (TERRAFORM_ROOT / "outputs.tf").read_text(encoding="utf-8")
    assert "rds_endpoint" in outputs
    assert "module.rds.endpoint" in outputs
