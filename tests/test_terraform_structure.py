"""Validate Terraform project structure (TASK-116)."""

from __future__ import annotations

import re
from pathlib import Path

TERRAFORM_ROOT = Path(__file__).resolve().parents[1] / "terraform"

EXPECTED_ROOT_FILES = [
    "main.tf",
    "variables.tf",
    "outputs.tf",
    "versions.tf",
    "providers.tf",
    "backend.tf",
    "README.md",
    ".gitignore",
]

EXPECTED_MODULES = [
    "networking",
    "ecr",
    "s3",
    "rds",
    "eks",
    "iam",
]

MODULE_FILES = ["main.tf", "variables.tf", "outputs.tf"]

EXPECTED_ENV_FILES = ["dev.tfvars", "staging.tfvars"]

SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(access_key|secret_key)\s*=\s*\"[A-Za-z0-9/+=]+\""),
    re.compile(r"(?i)AKIA[0-9A-Z]{16}"),
]


def test_terraform_root_files_exist() -> None:
    for filename in EXPECTED_ROOT_FILES:
        path = TERRAFORM_ROOT / filename
        assert path.exists(), f"Missing root file: terraform/{filename}"


def test_terraform_modules_exist() -> None:
    for module_name in EXPECTED_MODULES:
        module_dir = TERRAFORM_ROOT / "modules" / module_name
        assert module_dir.is_dir(), f"Missing module directory: modules/{module_name}"
        for filename in MODULE_FILES:
            path = module_dir / filename
            assert path.exists(), f"Missing file in module {module_name}: {filename}"


def test_terraform_env_files_exist() -> None:
    envs_dir = TERRAFORM_ROOT / "envs"
    assert envs_dir.is_dir(), "Missing envs/ directory"
    for filename in EXPECTED_ENV_FILES:
        path = envs_dir / filename
        assert path.exists(), f"Missing env file: envs/{filename}"


def test_backend_uses_s3() -> None:
    backend_file = TERRAFORM_ROOT / "backend.tf"
    content = backend_file.read_text(encoding="utf-8")
    assert 'backend "s3"' in content, "Backend must use S3 for remote state"
    assert "encrypt" in content, "State must be encrypted at rest"
    assert "dynamodb_table" in content, "State locking must use DynamoDB"


def test_provider_version_constrained() -> None:
    versions_file = TERRAFORM_ROOT / "versions.tf"
    content = versions_file.read_text(encoding="utf-8")
    assert "required_version" in content, "Terraform version must be constrained"
    assert "hashicorp/aws" in content, "AWS provider must be declared"


def test_no_credentials_in_terraform_files() -> None:
    tf_files = list(TERRAFORM_ROOT.rglob("*.tf"))
    tf_files += list(TERRAFORM_ROOT.rglob("*.tfvars"))
    for tf_file in tf_files:
        content = tf_file.read_text(encoding="utf-8")
        for pattern in SENSITIVE_PATTERNS:
            assert not pattern.search(content), (
                f"Potential credential found in {tf_file.relative_to(TERRAFORM_ROOT)}"
            )


def test_gitignore_excludes_state() -> None:
    gitignore = (TERRAFORM_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".terraform/" in gitignore
    assert "*.tfstate" in gitignore


def test_environment_variable_files_set_environment() -> None:
    for env_file in EXPECTED_ENV_FILES:
        path = TERRAFORM_ROOT / "envs" / env_file
        content = path.read_text(encoding="utf-8")
        assert "environment" in content, f"{env_file} must set the environment variable"


def test_root_main_references_all_modules() -> None:
    main_tf = (TERRAFORM_ROOT / "main.tf").read_text(encoding="utf-8")
    for module_name in EXPECTED_MODULES:
        assert f'module "{module_name}"' in main_tf, (
            f"Root main.tf must reference module {module_name}"
        )


def test_environment_separation_in_variables() -> None:
    variables_tf = (TERRAFORM_ROOT / "variables.tf").read_text(encoding="utf-8")
    assert 'variable "environment"' in variables_tf
    assert "dev" in variables_tf and "staging" in variables_tf and "prod" in variables_tf
