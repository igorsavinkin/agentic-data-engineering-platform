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
        assert "APP_KAFKA_BOOTSTRAP_SERVERS" in env_names

    def test_ingestion_deployment_no_inbound_ports(self) -> None:
        manifest = _load_yaml(INGESTION_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert "ports" not in container, "ingestion should not expose inbound ports"


PROCESSOR_DEPLOYMENT = REPO_ROOT / "kubernetes" / "deployments" / "processor-deployment.yaml"


class TestProcessorDeployment:
    def test_processor_deployment_exists(self) -> None:
        assert PROCESSOR_DEPLOYMENT.exists(), (
            f"processor deployment not found at {PROCESSOR_DEPLOYMENT}"
        )

    def test_processor_deployment_is_deployment_resource(self) -> None:
        manifest = _load_yaml(PROCESSOR_DEPLOYMENT)
        assert manifest["apiVersion"] == "apps/v1"
        assert manifest["kind"] == "Deployment"

    def test_processor_deployment_namespace(self) -> None:
        manifest = _load_yaml(PROCESSOR_DEPLOYMENT)
        assert manifest["metadata"]["namespace"] == "ai-data-platform"

    def test_processor_deployment_labels(self) -> None:
        manifest = _load_yaml(PROCESSOR_DEPLOYMENT)
        labels = manifest["metadata"]["labels"]
        assert labels["app.kubernetes.io/name"] == "processor"
        assert labels["app.kubernetes.io/part-of"] == "ai-data-platform"

    def test_processor_deployment_selector_matches_template(self) -> None:
        manifest = _load_yaml(PROCESSOR_DEPLOYMENT)
        selector = manifest["spec"]["selector"]["matchLabels"]
        template_labels = manifest["spec"]["template"]["metadata"]["labels"]
        for key, value in selector.items():
            assert template_labels.get(key) == value

    def test_processor_deployment_has_kafka_env(self) -> None:
        manifest = _load_yaml(PROCESSOR_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        env_names = [e["name"] for e in container["env"]]
        assert "APP_KAFKA_BOOTSTRAP_SERVERS" in env_names
        assert "APP_KAFKA_GROUP_ID" in env_names

    def test_processor_deployment_no_inbound_ports(self) -> None:
        manifest = _load_yaml(PROCESSOR_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert "ports" not in container, "processor should not expose inbound ports"


RAW_WRITER_DEPLOYMENT = REPO_ROOT / "kubernetes" / "deployments" / "raw-writer-deployment.yaml"


class TestRawWriterDeployment:
    def test_raw_writer_deployment_exists(self) -> None:
        assert RAW_WRITER_DEPLOYMENT.exists(), (
            f"raw-writer deployment not found at {RAW_WRITER_DEPLOYMENT}"
        )

    def test_raw_writer_deployment_is_deployment_resource(self) -> None:
        manifest = _load_yaml(RAW_WRITER_DEPLOYMENT)
        assert manifest["apiVersion"] == "apps/v1"
        assert manifest["kind"] == "Deployment"

    def test_raw_writer_deployment_namespace(self) -> None:
        manifest = _load_yaml(RAW_WRITER_DEPLOYMENT)
        assert manifest["metadata"]["namespace"] == "ai-data-platform"

    def test_raw_writer_deployment_labels(self) -> None:
        manifest = _load_yaml(RAW_WRITER_DEPLOYMENT)
        labels = manifest["metadata"]["labels"]
        assert labels["app.kubernetes.io/name"] == "raw-writer"
        assert labels["app.kubernetes.io/part-of"] == "ai-data-platform"

    def test_raw_writer_deployment_selector_matches_template(self) -> None:
        manifest = _load_yaml(RAW_WRITER_DEPLOYMENT)
        selector = manifest["spec"]["selector"]["matchLabels"]
        template_labels = manifest["spec"]["template"]["metadata"]["labels"]
        for key, value in selector.items():
            assert template_labels.get(key) == value

    def test_raw_writer_deployment_has_kafka_and_minio_env(self) -> None:
        manifest = _load_yaml(RAW_WRITER_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        env_names = [e["name"] for e in container["env"]]
        assert "APP_KAFKA_BOOTSTRAP_SERVERS" in env_names
        assert "APP_KAFKA_GROUP_ID" in env_names
        assert "APP_MINIO_ENDPOINT" in env_names

    def test_raw_writer_deployment_minio_secrets_are_optional(self) -> None:
        manifest = _load_yaml(RAW_WRITER_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        secret_envs = [
            e for e in container["env"] if "valueFrom" in e and "secretKeyRef" in e["valueFrom"]
        ]
        for env in secret_envs:
            assert env["valueFrom"]["secretKeyRef"].get("optional") is True

    def test_raw_writer_deployment_no_inbound_ports(self) -> None:
        manifest = _load_yaml(RAW_WRITER_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert "ports" not in container, "raw-writer should not expose inbound ports"

    def test_raw_writer_deployment_command_uses_module_invocation(self) -> None:
        manifest = _load_yaml(RAW_WRITER_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert container["command"] == ["python", "-m", "services.raw-writer.consumer"]


LAKE_WRITER_DEPLOYMENT = REPO_ROOT / "kubernetes" / "deployments" / "lake-writer-deployment.yaml"


class TestLakeWriterDeployment:
    def test_lake_writer_deployment_exists(self) -> None:
        assert LAKE_WRITER_DEPLOYMENT.exists(), (
            f"lake-writer deployment not found at {LAKE_WRITER_DEPLOYMENT}"
        )

    def test_lake_writer_deployment_is_deployment_resource(self) -> None:
        manifest = _load_yaml(LAKE_WRITER_DEPLOYMENT)
        assert manifest["apiVersion"] == "apps/v1"
        assert manifest["kind"] == "Deployment"

    def test_lake_writer_deployment_namespace(self) -> None:
        manifest = _load_yaml(LAKE_WRITER_DEPLOYMENT)
        assert manifest["metadata"]["namespace"] == "ai-data-platform"

    def test_lake_writer_deployment_labels(self) -> None:
        manifest = _load_yaml(LAKE_WRITER_DEPLOYMENT)
        labels = manifest["metadata"]["labels"]
        assert labels["app.kubernetes.io/name"] == "lake-writer"
        assert labels["app.kubernetes.io/part-of"] == "ai-data-platform"

    def test_lake_writer_deployment_selector_matches_template(self) -> None:
        manifest = _load_yaml(LAKE_WRITER_DEPLOYMENT)
        selector = manifest["spec"]["selector"]["matchLabels"]
        template_labels = manifest["spec"]["template"]["metadata"]["labels"]
        for key, value in selector.items():
            assert template_labels.get(key) == value

    def test_lake_writer_deployment_has_kafka_and_minio_env(self) -> None:
        manifest = _load_yaml(LAKE_WRITER_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        env_names = [e["name"] for e in container["env"]]
        assert "APP_KAFKA_BOOTSTRAP_SERVERS" in env_names
        assert "APP_KAFKA_GROUP_ID" in env_names
        assert "APP_MINIO_ENDPOINT" in env_names

    def test_lake_writer_deployment_minio_secrets_are_optional(self) -> None:
        manifest = _load_yaml(LAKE_WRITER_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        secret_envs = [
            e for e in container["env"] if "valueFrom" in e and "secretKeyRef" in e["valueFrom"]
        ]
        for env in secret_envs:
            assert env["valueFrom"]["secretKeyRef"].get("optional") is True

    def test_lake_writer_deployment_no_inbound_ports(self) -> None:
        manifest = _load_yaml(LAKE_WRITER_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert "ports" not in container, "lake-writer should not expose inbound ports"

    def test_lake_writer_deployment_command_uses_module_invocation(self) -> None:
        manifest = _load_yaml(LAKE_WRITER_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert container["command"] == ["python", "-m", "services.lake-writer.consumer"]


WAREHOUSE_LOADER_DEPLOYMENT = (
    REPO_ROOT / "kubernetes" / "deployments" / "warehouse-loader-deployment.yaml"
)


class TestWarehouseLoaderDeployment:
    def test_warehouse_loader_deployment_exists(self) -> None:
        assert WAREHOUSE_LOADER_DEPLOYMENT.exists(), (
            f"warehouse-loader deployment not found at {WAREHOUSE_LOADER_DEPLOYMENT}"
        )

    def test_warehouse_loader_deployment_is_deployment_resource(self) -> None:
        manifest = _load_yaml(WAREHOUSE_LOADER_DEPLOYMENT)
        assert manifest["apiVersion"] == "apps/v1"
        assert manifest["kind"] == "Deployment"

    def test_warehouse_loader_deployment_namespace(self) -> None:
        manifest = _load_yaml(WAREHOUSE_LOADER_DEPLOYMENT)
        assert manifest["metadata"]["namespace"] == "ai-data-platform"

    def test_warehouse_loader_deployment_labels(self) -> None:
        manifest = _load_yaml(WAREHOUSE_LOADER_DEPLOYMENT)
        labels = manifest["metadata"]["labels"]
        assert labels["app.kubernetes.io/name"] == "warehouse-loader"
        assert labels["app.kubernetes.io/part-of"] == "ai-data-platform"

    def test_warehouse_loader_deployment_selector_matches_template(self) -> None:
        manifest = _load_yaml(WAREHOUSE_LOADER_DEPLOYMENT)
        selector = manifest["spec"]["selector"]["matchLabels"]
        template_labels = manifest["spec"]["template"]["metadata"]["labels"]
        for key, value in selector.items():
            assert template_labels.get(key) == value

    def test_warehouse_loader_deployment_has_db_and_minio_env(self) -> None:
        manifest = _load_yaml(WAREHOUSE_LOADER_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        env_names = [e["name"] for e in container["env"]]
        assert "WAREHOUSE_DB_HOST" in env_names
        assert "WAREHOUSE_DB_PORT" in env_names
        assert "WAREHOUSE_DB_NAME" in env_names
        assert "APP_MINIO_ENDPOINT" in env_names

    def test_warehouse_loader_deployment_has_no_kafka_env(self) -> None:
        manifest = _load_yaml(WAREHOUSE_LOADER_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        env_names = [e["name"] for e in container["env"]]
        assert "APP_KAFKA_BOOTSTRAP_SERVERS" not in env_names
        assert "APP_KAFKA_GROUP_ID" not in env_names

    def test_warehouse_loader_deployment_secrets_are_optional(self) -> None:
        manifest = _load_yaml(WAREHOUSE_LOADER_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        secret_envs = [
            e for e in container["env"] if "valueFrom" in e and "secretKeyRef" in e["valueFrom"]
        ]
        for env in secret_envs:
            assert env["valueFrom"]["secretKeyRef"].get("optional") is True

    def test_warehouse_loader_deployment_no_inbound_ports(self) -> None:
        manifest = _load_yaml(WAREHOUSE_LOADER_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert "ports" not in container, "warehouse-loader should not expose inbound ports"

    def test_warehouse_loader_deployment_command_uses_module_invocation(self) -> None:
        manifest = _load_yaml(WAREHOUSE_LOADER_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert container["command"] == ["python", "-m", "services.warehouse-loader.runner"]
