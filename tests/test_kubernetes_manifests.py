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


API_DEPLOYMENT = REPO_ROOT / "kubernetes" / "deployments" / "api-deployment.yaml"
API_SERVICE = REPO_ROOT / "kubernetes" / "deployments" / "api-service.yaml"


class TestAPIDeployment:
    def test_api_deployment_exists(self) -> None:
        assert API_DEPLOYMENT.exists(), f"api deployment not found at {API_DEPLOYMENT}"

    def test_api_deployment_is_deployment_resource(self) -> None:
        manifest = _load_yaml(API_DEPLOYMENT)
        assert manifest["apiVersion"] == "apps/v1"
        assert manifest["kind"] == "Deployment"

    def test_api_deployment_namespace(self) -> None:
        manifest = _load_yaml(API_DEPLOYMENT)
        assert manifest["metadata"]["namespace"] == "ai-data-platform"

    def test_api_deployment_labels(self) -> None:
        manifest = _load_yaml(API_DEPLOYMENT)
        labels = manifest["metadata"]["labels"]
        assert labels["app.kubernetes.io/name"] == "api"
        assert labels["app.kubernetes.io/part-of"] == "ai-data-platform"

    def test_api_deployment_selector_matches_template(self) -> None:
        manifest = _load_yaml(API_DEPLOYMENT)
        selector = manifest["spec"]["selector"]["matchLabels"]
        template_labels = manifest["spec"]["template"]["metadata"]["labels"]
        for key, value in selector.items():
            assert template_labels.get(key) == value

    def test_api_deployment_has_db_env(self) -> None:
        manifest = _load_yaml(API_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        env_names = [e["name"] for e in container["env"]]
        assert "WAREHOUSE_DB_HOST" in env_names
        assert "WAREHOUSE_DB_PORT" in env_names
        assert "WAREHOUSE_DB_NAME" in env_names

    def test_api_deployment_exposes_port(self) -> None:
        manifest = _load_yaml(API_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert "ports" in container
        ports = container["ports"]
        assert any(p["containerPort"] == 8000 for p in ports)

    def test_api_deployment_has_liveness_probe(self) -> None:
        manifest = _load_yaml(API_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert "livenessProbe" in container
        probe = container["livenessProbe"]
        assert probe["httpGet"]["path"] == "/api/v1/health"
        assert probe["httpGet"]["port"] == 8000

    def test_api_deployment_has_readiness_probe(self) -> None:
        manifest = _load_yaml(API_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert "readinessProbe" in container
        probe = container["readinessProbe"]
        assert probe["httpGet"]["path"] == "/api/v1/ready"
        assert probe["httpGet"]["port"] == 8000

    def test_api_deployment_secrets_are_optional(self) -> None:
        manifest = _load_yaml(API_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        secret_envs = [
            e for e in container["env"] if "valueFrom" in e and "secretKeyRef" in e["valueFrom"]
        ]
        for env in secret_envs:
            assert env["valueFrom"]["secretKeyRef"].get("optional") is True

    def test_api_deployment_command_uses_module_invocation(self) -> None:
        manifest = _load_yaml(API_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert container["command"] == ["python", "-m", "services.api"]


class TestAPIService:
    def test_api_service_exists(self) -> None:
        assert API_SERVICE.exists(), f"api service not found at {API_SERVICE}"

    def test_api_service_is_service_resource(self) -> None:
        manifest = _load_yaml(API_SERVICE)
        assert manifest["apiVersion"] == "v1"
        assert manifest["kind"] == "Service"

    def test_api_service_namespace(self) -> None:
        manifest = _load_yaml(API_SERVICE)
        assert manifest["metadata"]["namespace"] == "ai-data-platform"

    def test_api_service_labels(self) -> None:
        manifest = _load_yaml(API_SERVICE)
        labels = manifest["metadata"]["labels"]
        assert labels["app.kubernetes.io/name"] == "api"
        assert labels["app.kubernetes.io/part-of"] == "ai-data-platform"

    def test_api_service_selector_matches_deployment(self) -> None:
        manifest = _load_yaml(API_SERVICE)
        selector = manifest["spec"]["selector"]
        deployment = _load_yaml(API_DEPLOYMENT)
        template_labels = deployment["spec"]["template"]["metadata"]["labels"]
        for key, value in selector.items():
            assert template_labels.get(key) == value

    def test_api_service_exposes_port_8000(self) -> None:
        manifest = _load_yaml(API_SERVICE)
        ports = manifest["spec"]["ports"]
        assert any(p["port"] == 8000 for p in ports)


KAFKA_DEPLOYMENT = REPO_ROOT / "kubernetes" / "deployments" / "kafka-deployment.yaml"
KAFKA_SERVICE = REPO_ROOT / "kubernetes" / "deployments" / "kafka-service.yaml"
KAFKA_TOPICS_JOB = REPO_ROOT / "kubernetes" / "deployments" / "kafka-topics-job.yaml"


class TestKafkaDeployment:
    def test_kafka_deployment_exists(self) -> None:
        assert KAFKA_DEPLOYMENT.exists(), f"kafka deployment not found at {KAFKA_DEPLOYMENT}"

    def test_kafka_deployment_is_deployment_resource(self) -> None:
        manifest = _load_yaml(KAFKA_DEPLOYMENT)
        assert manifest["apiVersion"] == "apps/v1"
        assert manifest["kind"] == "Deployment"

    def test_kafka_deployment_namespace(self) -> None:
        manifest = _load_yaml(KAFKA_DEPLOYMENT)
        assert manifest["metadata"]["namespace"] == "ai-data-platform"

    def test_kafka_deployment_labels(self) -> None:
        manifest = _load_yaml(KAFKA_DEPLOYMENT)
        labels = manifest["metadata"]["labels"]
        assert labels["app.kubernetes.io/name"] == "kafka"
        assert labels["app.kubernetes.io/part-of"] == "ai-data-platform"

    def test_kafka_deployment_selector_matches_template(self) -> None:
        manifest = _load_yaml(KAFKA_DEPLOYMENT)
        selector = manifest["spec"]["selector"]["matchLabels"]
        template_labels = manifest["spec"]["template"]["metadata"]["labels"]
        for key, value in selector.items():
            assert template_labels.get(key) == value

    def test_kafka_deployment_uses_kraft_mode(self) -> None:
        manifest = _load_yaml(KAFKA_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        env_names = [e["name"] for e in container["env"]]
        assert "KAFKA_PROCESS_ROLES" in env_names
        assert "KAFKA_NODE_ID" in env_names
        roles = next(e["value"] for e in container["env"] if e["name"] == "KAFKA_PROCESS_ROLES")
        assert "broker" in roles and "controller" in roles

    def test_kafka_deployment_auto_create_disabled(self) -> None:
        manifest = _load_yaml(KAFKA_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        auto_create = next(
            (
                e["value"]
                for e in container["env"]
                if e["name"] == "KAFKA_AUTO_CREATE_TOPICS_ENABLE"
            ),
            None,
        )
        assert auto_create == "false"

    def test_kafka_deployment_exposes_ports(self) -> None:
        manifest = _load_yaml(KAFKA_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert "ports" in container
        ports = container["ports"]
        assert any(p["containerPort"] == 29092 for p in ports)
        assert any(p["containerPort"] == 9092 for p in ports)


class TestKafkaService:
    def test_kafka_service_exists(self) -> None:
        assert KAFKA_SERVICE.exists(), f"kafka service not found at {KAFKA_SERVICE}"

    def test_kafka_service_is_service_resource(self) -> None:
        manifest = _load_yaml(KAFKA_SERVICE)
        assert manifest["apiVersion"] == "v1"
        assert manifest["kind"] == "Service"

    def test_kafka_service_namespace(self) -> None:
        manifest = _load_yaml(KAFKA_SERVICE)
        assert manifest["metadata"]["namespace"] == "ai-data-platform"

    def test_kafka_service_labels(self) -> None:
        manifest = _load_yaml(KAFKA_SERVICE)
        labels = manifest["metadata"]["labels"]
        assert labels["app.kubernetes.io/name"] == "kafka"
        assert labels["app.kubernetes.io/part-of"] == "ai-data-platform"

    def test_kafka_service_selector_matches_deployment(self) -> None:
        manifest = _load_yaml(KAFKA_SERVICE)
        selector = manifest["spec"]["selector"]
        deployment = _load_yaml(KAFKA_DEPLOYMENT)
        template_labels = deployment["spec"]["template"]["metadata"]["labels"]
        for key, value in selector.items():
            assert template_labels.get(key) == value

    def test_kafka_service_is_nodeport(self) -> None:
        manifest = _load_yaml(KAFKA_SERVICE)
        assert manifest["spec"]["type"] == "NodePort"

    def test_kafka_service_exposes_internal_port_with_nodeport(self) -> None:
        manifest = _load_yaml(KAFKA_SERVICE)
        ports = manifest["spec"]["ports"]
        external_port = next((p for p in ports if p["port"] == 9092), None)
        assert external_port is not None
        assert external_port["nodePort"] == 30092


class TestKafkaTopicsJob:
    def test_kafka_topics_job_exists(self) -> None:
        assert KAFKA_TOPICS_JOB.exists(), f"kafka topics job not found at {KAFKA_TOPICS_JOB}"

    def test_kafka_topics_job_is_job_resource(self) -> None:
        manifest = _load_yaml(KAFKA_TOPICS_JOB)
        assert manifest["apiVersion"] == "batch/v1"
        assert manifest["kind"] == "Job"

    def test_kafka_topics_job_namespace(self) -> None:
        manifest = _load_yaml(KAFKA_TOPICS_JOB)
        assert manifest["metadata"]["namespace"] == "ai-data-platform"

    def test_kafka_topics_job_creates_all_topics(self) -> None:
        manifest = _load_yaml(KAFKA_TOPICS_JOB)
        command = manifest["spec"]["template"]["spec"]["containers"][0]["command"]
        script = " ".join(command)
        expected_topics = [
            "products.raw.v1",
            "products.validated.v1",
            "products.invalid.v1",
            "pipeline.events.v1",
            "data-quality.events.v1",
        ]
        for topic in expected_topics:
            assert topic in script, f"topic {topic} not found in kafka-topics-job script"
