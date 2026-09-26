"""Validate Terraform networking module structure (TASK-117)."""

from __future__ import annotations

from pathlib import Path

TERRAFORM_ROOT = Path(__file__).resolve().parents[1] / "terraform"
NETWORKING_MODULE = TERRAFORM_ROOT / "modules" / "networking"


def _read(name: str) -> str:
    return (NETWORKING_MODULE / name).read_text(encoding="utf-8")


def test_networking_main_has_vpc() -> None:
    content = _read("main.tf")
    assert 'resource "aws_vpc"' in content, "Networking module must create a VPC"


def test_networking_main_has_public_subnets() -> None:
    content = _read("main.tf")
    assert 'resource "aws_subnet" "public"' in content, "Must create public subnets"


def test_networking_main_has_private_subnets() -> None:
    content = _read("main.tf")
    assert 'resource "aws_subnet" "private"' in content, "Must create private subnets"


def test_networking_main_has_internet_gateway() -> None:
    content = _read("main.tf")
    assert 'resource "aws_internet_gateway"' in content, "Must create an internet gateway"


def test_networking_main_has_nat_gateway() -> None:
    content = _read("main.tf")
    assert 'resource "aws_nat_gateway"' in content, "Must create a NAT gateway"


def test_networking_main_has_route_tables() -> None:
    content = _read("main.tf")
    assert 'resource "aws_route_table" "public"' in content, "Must create a public route table"
    assert 'resource "aws_route_table" "private"' in content, "Must create a private route table"


def test_networking_main_has_security_groups() -> None:
    content = _read("main.tf")
    assert 'resource "aws_security_group" "eks_cluster"' in content
    assert 'resource "aws_security_group" "eks_nodes"' in content
    assert 'resource "aws_security_group" "rds"' in content


def test_networking_outputs_expose_required_values() -> None:
    content = _read("outputs.tf")
    assert 'output "vpc_id"' in content
    assert 'output "private_subnet_ids"' in content
    assert 'output "public_subnet_ids"' in content


def test_networking_rds_sg_restricts_to_eks_nodes() -> None:
    content = _read("main.tf")
    assert "referenced_security_group_id" in content, (
        "RDS security group must use security group references, not CIDR"
    )


def test_networking_subnets_use_availability_zones() -> None:
    content = _read("main.tf")
    assert "var.availability_zones" in content, "Subnets must be distributed across AZs"


def test_networking_no_public_ip_on_private_subnets() -> None:
    content = _read("main.tf")
    private_section = content.split('resource "aws_subnet" "private"')[1].split("resource")[0]
    assert "map_public_ip_on_launch" not in private_section, (
        "Private subnets must not auto-assign public IPs"
    )


def test_networking_kubernetes_tags_present() -> None:
    content = _read("main.tf")
    assert "kubernetes.io/role/elb" in content, "Public subnets need ELB tag for Kubernetes"
    assert "kubernetes.io/role/internal-elb" in content, "Private subnets need internal ELB tag"
