"""Validate Terraform ECR module structure (TASK-118)."""

from __future__ import annotations

from pathlib import Path

TERRAFORM_ROOT = Path(__file__).resolve().parents[1] / "terraform"
ECR_MODULE = TERRAFORM_ROOT / "modules" / "ecr"


def _read(name: str) -> str:
    return (ECR_MODULE / name).read_text(encoding="utf-8")


def test_ecr_creates_repositories() -> None:
    content = _read("main.tf")
    assert 'resource "aws_ecr_repository"' in content, "Must create ECR repositories"


def test_ecr_repositories_are_immutable() -> None:
    content = _read("main.tf")
    assert "IMMUTABLE" in content, "Image tag mutability must be IMMUTABLE"


def test_ecr_has_lifecycle_policy() -> None:
    content = _read("main.tf")
    assert 'resource "aws_ecr_lifecycle_policy"' in content, "Must configure lifecycle policies"


def test_ecr_lifecycle_expires_untagged() -> None:
    content = _read("main.tf")
    assert "untagged" in content, "Lifecycle must handle untagged images"


def test_ecr_has_repository_policy() -> None:
    content = _read("main.tf")
    assert 'resource "aws_ecr_repository_policy"' in content, "Must set repository policy"


def test_ecr_scan_on_push_enabled() -> None:
    content = _read("main.tf")
    assert "scan_on_push" in content, "Image scanning on push must be enabled"


def test_ecr_encryption_configured() -> None:
    content = _read("main.tf")
    assert "encryption_configuration" in content, "Encryption must be configured"


def test_ecr_outputs_expose_urls() -> None:
    content = _read("outputs.tf")
    assert 'output "repository_urls"' in content, "Must output repository URLs"


def test_ecr_outputs_expose_arns() -> None:
    content = _read("outputs.tf")
    assert 'output "repository_arns"' in content, "Must output repository ARNs"


def test_ecr_no_credentials() -> None:
    import re

    sensitive = re.compile(r"(?i)(access_key|secret_key)\s*=\s*\"[A-Za-z0-9/+=]+\"")
    for filename in ["main.tf", "variables.tf", "outputs.tf"]:
        content = _read(filename)
        assert not sensitive.search(content), f"Potential credential in {filename}"


def test_ecr_uses_service_names_variable() -> None:
    content = _read("main.tf")
    assert "var.service_names" in content, "Must iterate over service_names variable"
