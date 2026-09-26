"""Validate Terraform EKS cluster module (TASK-121)."""

from __future__ import annotations

from pathlib import Path

TERRAFORM_ROOT = Path(__file__).resolve().parents[1] / "terraform"
EKS_MODULE = TERRAFORM_ROOT / "modules" / "eks"


def _read(filename: str) -> str:
    return (EKS_MODULE / filename).read_text(encoding="utf-8")


def test_eks_cluster_resource_exists() -> None:
    content = _read("main.tf")
    assert 'resource "aws_eks_cluster"' in content


def test_eks_cluster_iam_role_exists() -> None:
    content = _read("main.tf")
    assert 'resource "aws_iam_role" "cluster"' in content
    assert "eks.amazonaws.com" in content


def test_eks_cluster_policy_attached() -> None:
    content = _read("main.tf")
    assert "AmazonEKSClusterPolicy" in content
    assert "AmazonEKSVPCResourceController" in content


def test_eks_node_group_general_exists() -> None:
    content = _read("main.tf")
    assert 'resource "aws_eks_node_group" "general"' in content
    assert '"general"' in content


def test_eks_node_group_kafka_exists() -> None:
    content = _read("main.tf")
    assert 'resource "aws_eks_node_group" "kafka"' in content
    assert '"kafka"' in content


def test_eks_kafka_node_taint() -> None:
    content = _read("main.tf")
    assert "taint {" in content
    assert "dedicated" in content
    assert "NO_SCHEDULE" in content


def test_eks_node_iam_role_exists() -> None:
    content = _read("main.tf")
    assert 'resource "aws_iam_role" "nodes"' in content
    assert "ec2.amazonaws.com" in content


def test_eks_node_policy_attachments() -> None:
    content = _read("main.tf")
    assert "AmazonEKSWorkerNodePolicy" in content
    assert "AmazonEKS_CNI_Policy" in content
    assert "AmazonEC2ContainerRegistryReadOnly" in content


def test_eks_oidc_provider_exists() -> None:
    content = _read("main.tf")
    assert 'resource "aws_iam_openid_connect_provider" "cluster"' in content
    assert "sts.amazonaws.com" in content


def test_eks_tls_certificate_data_source() -> None:
    content = _read("main.tf")
    assert 'data "tls_certificate" "cluster"' in content


def test_eks_cloudwatch_log_group() -> None:
    content = _read("main.tf")
    assert 'resource "aws_cloudwatch_log_group" "cluster"' in content
    assert "/aws/eks/" in content


def test_eks_cluster_log_types() -> None:
    content = _read("main.tf")
    assert "enabled_cluster_log_types" in content
    assert '"api"' in content
    assert '"audit"' in content
    assert '"authenticator"' in content


def test_eks_cluster_private_endpoint() -> None:
    content = _read("main.tf")
    assert "endpoint_private_access = true" in content
    assert "endpoint_public_access" in content


def test_eks_cluster_security_group_ids() -> None:
    content = _read("main.tf")
    assert "security_group_ids" in content
    assert "var.cluster_security_group_id" in content


def test_eks_scaling_config_general() -> None:
    content = _read("main.tf")
    assert "var.general_node_desired_size" in content
    assert "var.general_node_min_size" in content
    assert "var.general_node_max_size" in content


def test_eks_scaling_config_kafka() -> None:
    content = _read("main.tf")
    assert "var.kafka_node_desired_size" in content
    assert "var.kafka_node_min_size" in content
    assert "var.kafka_node_max_size" in content


def test_eks_outputs_reference_real_resources() -> None:
    content = _read("outputs.tf")
    assert "aws_eks_cluster.this.name" in content
    assert "aws_eks_cluster.this.endpoint" in content
    assert "aws_iam_openid_connect_provider.cluster.arn" in content
    assert "aws_iam_role.nodes.arn" in content


def test_eks_module_has_required_variables() -> None:
    content = _read("variables.tf")
    assert 'variable "project_name"' in content
    assert 'variable "environment"' in content
    assert 'variable "vpc_id"' in content
    assert 'variable "private_subnet_ids"' in content
    assert 'variable "cluster_security_group_id"' in content
    assert 'variable "cluster_version"' in content
    assert 'variable "tags"' in content


def test_eks_node_group_variables() -> None:
    content = _read("variables.tf")
    assert 'variable "general_node_instance_types"' in content
    assert 'variable "kafka_node_instance_types"' in content
    assert 'variable "general_node_desired_size"' in content
    assert 'variable "kafka_node_desired_size"' in content


def test_root_main_references_eks_module() -> None:
    main_tf = (TERRAFORM_ROOT / "main.tf").read_text(encoding="utf-8")
    assert 'module "eks"' in main_tf
    assert "./modules/eks" in main_tf
    assert "cluster_security_group_id" in main_tf


def test_root_variables_include_eks_node_config() -> None:
    variables = (TERRAFORM_ROOT / "variables.tf").read_text(encoding="utf-8")
    assert 'variable "eks_general_node_instance_types"' in variables
    assert 'variable "eks_kafka_node_instance_types"' in variables
    assert 'variable "eks_cluster_public_endpoint"' in variables
    assert 'variable "eks_service_cidr"' in variables


def test_root_outputs_include_oidc() -> None:
    outputs = (TERRAFORM_ROOT / "outputs.tf").read_text(encoding="utf-8")
    assert "eks_oidc_provider_arn" in outputs
    assert "module.eks.oidc_provider_arn" in outputs


def test_tls_provider_declared() -> None:
    versions = (TERRAFORM_ROOT / "versions.tf").read_text(encoding="utf-8")
    assert "hashicorp/tls" in versions
