"""Validate Kubernetes manifest structure (TASK-070).

Ensures the kind cluster config and namespace manifest are well-formed
YAML with the expected Kubernetes/kind fields. These tests run without
a live cluster — they validate file content, not cluster state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
KIND_CONFIG = REPO_ROOT / "kubernetes" / "kind" / "kind-config.yaml"
NAMESPACE_MANIFEST = REPO_ROOT / "kubernetes" / "namespaces" / "platform-namespace.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    with open(path, encoding="utf-8") as f:
        result: dict[str, Any] = yaml.safe_load(f)
    return result


class TestKindConfig:
    def test_kind_config_exists(self) -> None:
        assert KIND_CONFIG.exists(), f"kind config not found at {KIND_CONFIG}"

    def test_kind_config_has_required_fields(self) -> None:
        config = _load_yaml(KIND_CONFIG)
        assert config["kind"] == "Cluster"
        assert config["apiVersion"] == "kind.x-k8s.io/v1alpha4"
        assert "nodes" in config
        assert len(config["nodes"]) >= 1

    def test_kind_config_control_plane_node(self) -> None:
        config = _load_yaml(KIND_CONFIG)
        control_plane = config["nodes"][0]
        assert control_plane["role"] == "control-plane"
        assert "extraPortMappings" in control_plane
        assert len(control_plane["extraPortMappings"]) >= 1

    def test_kind_config_port_mappings_have_required_fields(self) -> None:
        config = _load_yaml(KIND_CONFIG)
        for mapping in config["nodes"][0]["extraPortMappings"]:
            assert "containerPort" in mapping
            assert "hostPort" in mapping
            assert "protocol" in mapping
            assert mapping["protocol"] in ("TCP", "UDP")


class TestNamespaceManifest:
    def test_namespace_manifest_exists(self) -> None:
        assert NAMESPACE_MANIFEST.exists(), f"namespace manifest not found at {NAMESPACE_MANIFEST}"

    def test_namespace_manifest_is_namespace_resource(self) -> None:
        manifest = _load_yaml(NAMESPACE_MANIFEST)
        assert manifest["apiVersion"] == "v1"
        assert manifest["kind"] == "Namespace"

    def test_namespace_name(self) -> None:
        manifest = _load_yaml(NAMESPACE_MANIFEST)
        assert manifest["metadata"]["name"] == "ai-data-platform"

    def test_namespace_has_platform_label(self) -> None:
        manifest = _load_yaml(NAMESPACE_MANIFEST)
        labels = manifest["metadata"]["labels"]
        assert labels["app.kubernetes.io/part-of"] == "ai-data-platform"


INGESTION_DEPLOYMENT = REPO_ROOT / "kubernetes" / "deployments" / "ingestion-deployment.yaml"


class TestIngestionDeployment:
    def test_ingestion_deployment_exists(self) -> None:
        assert INGESTION_DEPLOYMENT.exists(), (
            f"ingestion deployment not found at {INGESTION_DEPLOYMENT}"
        )

    def test_ingestion_deployment_is_deployment_resource(self) -> None:
        manifest = _load_yaml(INGESTION_DEPLOYMENT)
        assert manifest["apiVersion"] == "apps/v1"
        assert manifest["kind"] == "Deployment"

    def test_ingestion_deployment_namespace(self) -> None:
        manifest = _load_yaml(INGESTION_DEPLOYMENT)
        assert manifest["metadata"]["namespace"] == "ai-data-platform"

    def test_ingestion_deployment_labels(self) -> None:
        manifest = _load_yaml(INGESTION_DEPLOYMENT)
        labels = manifest["metadata"]["labels"]
        assert labels["app.kubernetes.io/name"] == "ingestion"
        assert labels["app.kubernetes.io/part-of"] == "ai-data-platform"

    def test_ingestion_deployment_selector_matches_template(self) -> None:
        manifest = _load_yaml(INGESTION_DEPLOYMENT)
        selector = manifest["spec"]["selector"]["matchLabels"]
        template_labels = manifest["spec"]["template"]["metadata"]["labels"]
        for key, value in selector.items():
            assert template_labels.get(key) == value

    def test_ingestion_deployment_has_kafka_env(self) -> None:
        manifest = _load_yaml(INGESTION_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        env_names = [e["name"] for e in container["env"]]
        assert "KAFKA_BOOTSTRAP_SERVERS" in env_names

    def test_ingestion_deployment_no_inbound_ports(self) -> None:
        manifest = _load_yaml(INGESTION_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert "ports" not in container, "ingestion should not expose inbound ports"
