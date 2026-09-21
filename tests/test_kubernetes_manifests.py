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

    def test_raw_writer_deployment_uses_shared_minio_secret(self) -> None:
        manifest = _load_yaml(RAW_WRITER_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        secret_envs = [
            e for e in container["env"] if "valueFrom" in e and "secretKeyRef" in e["valueFrom"]
        ]
        for env in secret_envs:
            ref = env["valueFrom"]["secretKeyRef"]
            assert ref["name"] == "minio-credentials"
            assert ref.get("optional") is not True

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

    def test_lake_writer_deployment_uses_shared_minio_secret(self) -> None:
        manifest = _load_yaml(LAKE_WRITER_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        secret_envs = [
            e for e in container["env"] if "valueFrom" in e and "secretKeyRef" in e["valueFrom"]
        ]
        for env in secret_envs:
            ref = env["valueFrom"]["secretKeyRef"]
            assert ref["name"] == "minio-credentials"
            assert ref.get("optional") is not True

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

    def test_warehouse_loader_deployment_uses_shared_secrets(self) -> None:
        manifest = _load_yaml(WAREHOUSE_LOADER_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        secret_envs = [
            e for e in container["env"] if "valueFrom" in e and "secretKeyRef" in e["valueFrom"]
        ]
        secret_names = {e["valueFrom"]["secretKeyRef"]["name"] for e in secret_envs}
        assert "minio-credentials" in secret_names
        assert "database-credentials" in secret_names
        for env in secret_envs:
            assert env["valueFrom"]["secretKeyRef"].get("optional") is not True

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

    def test_api_deployment_uses_shared_database_secret(self) -> None:
        manifest = _load_yaml(API_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        secret_envs = [
            e for e in container["env"] if "valueFrom" in e and "secretKeyRef" in e["valueFrom"]
        ]
        for env in secret_envs:
            ref = env["valueFrom"]["secretKeyRef"]
            assert ref["name"] == "database-credentials"
            assert ref.get("optional") is not True

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


PLATFORM_CONFIG = REPO_ROOT / "kubernetes" / "config" / "platform-config.yaml"
DATABASE_CONFIG = REPO_ROOT / "kubernetes" / "config" / "database-config.yaml"


class TestPlatformConfigMap:
    def test_platform_config_exists(self) -> None:
        assert PLATFORM_CONFIG.exists(), f"platform config not found at {PLATFORM_CONFIG}"

    def test_platform_config_is_configmap(self) -> None:
        manifest = _load_yaml(PLATFORM_CONFIG)
        assert manifest["apiVersion"] == "v1"
        assert manifest["kind"] == "ConfigMap"

    def test_platform_config_namespace(self) -> None:
        manifest = _load_yaml(PLATFORM_CONFIG)
        assert manifest["metadata"]["namespace"] == "ai-data-platform"

    def test_platform_config_has_required_keys(self) -> None:
        manifest = _load_yaml(PLATFORM_CONFIG)
        data = manifest["data"]
        assert "APP_ENVIRONMENT" in data
        assert "APP_KAFKA_BOOTSTRAP_SERVERS" in data
        assert "APP_MINIO_ENDPOINT" in data

    def test_platform_config_kafka_endpoint(self) -> None:
        manifest = _load_yaml(PLATFORM_CONFIG)
        assert manifest["data"]["APP_KAFKA_BOOTSTRAP_SERVERS"] == "kafka:29092"

    def test_platform_config_minio_endpoint(self) -> None:
        manifest = _load_yaml(PLATFORM_CONFIG)
        assert manifest["data"]["APP_MINIO_ENDPOINT"] == "http://minio:9000"

    def test_platform_config_labels(self) -> None:
        manifest = _load_yaml(PLATFORM_CONFIG)
        labels = manifest["metadata"]["labels"]
        assert labels["app.kubernetes.io/part-of"] == "ai-data-platform"


class TestDatabaseConfigMap:
    def test_database_config_exists(self) -> None:
        assert DATABASE_CONFIG.exists(), f"database config not found at {DATABASE_CONFIG}"

    def test_database_config_is_configmap(self) -> None:
        manifest = _load_yaml(DATABASE_CONFIG)
        assert manifest["apiVersion"] == "v1"
        assert manifest["kind"] == "ConfigMap"

    def test_database_config_namespace(self) -> None:
        manifest = _load_yaml(DATABASE_CONFIG)
        assert manifest["metadata"]["namespace"] == "ai-data-platform"

    def test_database_config_has_required_keys(self) -> None:
        manifest = _load_yaml(DATABASE_CONFIG)
        data = manifest["data"]
        assert "WAREHOUSE_DB_HOST" in data
        assert "WAREHOUSE_DB_PORT" in data
        assert "WAREHOUSE_DB_NAME" in data
        assert "WAREHOUSE_DB_USER" in data

    def test_database_config_host_matches_service_name(self) -> None:
        manifest = _load_yaml(DATABASE_CONFIG)
        assert manifest["data"]["WAREHOUSE_DB_HOST"] == "postgresql"


MINIO_SECRET = REPO_ROOT / "kubernetes" / "secrets" / "minio-credentials.yaml"
DATABASE_SECRET = REPO_ROOT / "kubernetes" / "secrets" / "database-credentials.yaml"
INGESTION_SECRET = REPO_ROOT / "kubernetes" / "secrets" / "ingestion-api-keys.yaml"


class TestMinioCredentialsSecret:
    def test_minio_secret_exists(self) -> None:
        assert MINIO_SECRET.exists(), f"minio secret not found at {MINIO_SECRET}"

    def test_minio_secret_is_secret_resource(self) -> None:
        manifest = _load_yaml(MINIO_SECRET)
        assert manifest["apiVersion"] == "v1"
        assert manifest["kind"] == "Secret"

    def test_minio_secret_namespace(self) -> None:
        manifest = _load_yaml(MINIO_SECRET)
        assert manifest["metadata"]["namespace"] == "ai-data-platform"

    def test_minio_secret_has_required_keys(self) -> None:
        manifest = _load_yaml(MINIO_SECRET)
        assert "minio-access-key" in manifest["data"]
        assert "minio-secret-key" in manifest["data"]

    def test_minio_secret_is_opaque(self) -> None:
        manifest = _load_yaml(MINIO_SECRET)
        assert manifest["type"] == "Opaque"


class TestDatabaseCredentialsSecret:
    def test_database_secret_exists(self) -> None:
        assert DATABASE_SECRET.exists(), f"database secret not found at {DATABASE_SECRET}"

    def test_database_secret_is_secret_resource(self) -> None:
        manifest = _load_yaml(DATABASE_SECRET)
        assert manifest["apiVersion"] == "v1"
        assert manifest["kind"] == "Secret"

    def test_database_secret_namespace(self) -> None:
        manifest = _load_yaml(DATABASE_SECRET)
        assert manifest["metadata"]["namespace"] == "ai-data-platform"

    def test_database_secret_has_db_password_key(self) -> None:
        manifest = _load_yaml(DATABASE_SECRET)
        assert "db-password" in manifest["data"]


class TestIngestionApiKeysSecret:
    def test_ingestion_secret_exists(self) -> None:
        assert INGESTION_SECRET.exists(), f"ingestion secret not found at {INGESTION_SECRET}"

    def test_ingestion_secret_is_secret_resource(self) -> None:
        manifest = _load_yaml(INGESTION_SECRET)
        assert manifest["apiVersion"] == "v1"
        assert manifest["kind"] == "Secret"

    def test_ingestion_secret_has_bestbuy_key(self) -> None:
        manifest = _load_yaml(INGESTION_SECRET)
        assert "bestbuy-api-key" in manifest["data"]


MINIO_SERVICE = REPO_ROOT / "kubernetes" / "deployments" / "minio-service.yaml"
POSTGRESQL_SERVICE = REPO_ROOT / "kubernetes" / "deployments" / "postgresql-service.yaml"


class TestMinioService:
    def test_minio_service_exists(self) -> None:
        assert MINIO_SERVICE.exists(), f"minio service not found at {MINIO_SERVICE}"

    def test_minio_service_is_service_resource(self) -> None:
        manifest = _load_yaml(MINIO_SERVICE)
        assert manifest["apiVersion"] == "v1"
        assert manifest["kind"] == "Service"

    def test_minio_service_namespace(self) -> None:
        manifest = _load_yaml(MINIO_SERVICE)
        assert manifest["metadata"]["namespace"] == "ai-data-platform"

    def test_minio_service_is_clusterip(self) -> None:
        manifest = _load_yaml(MINIO_SERVICE)
        assert manifest["spec"]["type"] == "ClusterIP"

    def test_minio_service_exposes_api_port(self) -> None:
        manifest = _load_yaml(MINIO_SERVICE)
        ports = manifest["spec"]["ports"]
        assert any(p["port"] == 9000 for p in ports)

    def test_minio_service_labels(self) -> None:
        manifest = _load_yaml(MINIO_SERVICE)
        labels = manifest["metadata"]["labels"]
        assert labels["app.kubernetes.io/name"] == "minio"
        assert labels["app.kubernetes.io/part-of"] == "ai-data-platform"


class TestPostgreSQLService:
    def test_postgresql_service_exists(self) -> None:
        assert POSTGRESQL_SERVICE.exists(), f"postgresql service not found at {POSTGRESQL_SERVICE}"

    def test_postgresql_service_is_service_resource(self) -> None:
        manifest = _load_yaml(POSTGRESQL_SERVICE)
        assert manifest["apiVersion"] == "v1"
        assert manifest["kind"] == "Service"

    def test_postgresql_service_namespace(self) -> None:
        manifest = _load_yaml(POSTGRESQL_SERVICE)
        assert manifest["metadata"]["namespace"] == "ai-data-platform"

    def test_postgresql_service_is_clusterip(self) -> None:
        manifest = _load_yaml(POSTGRESQL_SERVICE)
        assert manifest["spec"]["type"] == "ClusterIP"

    def test_postgresql_service_exposes_port_5432(self) -> None:
        manifest = _load_yaml(POSTGRESQL_SERVICE)
        ports = manifest["spec"]["ports"]
        assert any(p["port"] == 5432 for p in ports)

    def test_postgresql_service_labels(self) -> None:
        manifest = _load_yaml(POSTGRESQL_SERVICE)
        labels = manifest["metadata"]["labels"]
        assert labels["app.kubernetes.io/name"] == "postgresql"
        assert labels["app.kubernetes.io/part-of"] == "ai-data-platform"


class TestDeploymentsUseConfigMaps:
    def test_ingestion_uses_platform_config(self) -> None:
        manifest = _load_yaml(INGESTION_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        configmap_envs = [
            e
            for e in container["env"]
            if "valueFrom" in e and "configMapKeyRef" in e.get("valueFrom", {})
        ]
        configmap_names = {e["valueFrom"]["configMapKeyRef"]["name"] for e in configmap_envs}
        assert "platform-config" in configmap_names

    def test_processor_uses_platform_config(self) -> None:
        manifest = _load_yaml(PROCESSOR_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        configmap_envs = [
            e
            for e in container["env"]
            if "valueFrom" in e and "configMapKeyRef" in e.get("valueFrom", {})
        ]
        configmap_names = {e["valueFrom"]["configMapKeyRef"]["name"] for e in configmap_envs}
        assert "platform-config" in configmap_names

    def test_warehouse_loader_uses_database_config(self) -> None:
        manifest = _load_yaml(WAREHOUSE_LOADER_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        configmap_envs = [
            e
            for e in container["env"]
            if "valueFrom" in e and "configMapKeyRef" in e.get("valueFrom", {})
        ]
        configmap_names = {e["valueFrom"]["configMapKeyRef"]["name"] for e in configmap_envs}
        assert "database-config" in configmap_names
        assert "platform-config" in configmap_names

    def test_api_uses_database_config(self) -> None:
        manifest = _load_yaml(API_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        configmap_envs = [
            e
            for e in container["env"]
            if "valueFrom" in e and "configMapKeyRef" in e.get("valueFrom", {})
        ]
        configmap_names = {e["valueFrom"]["configMapKeyRef"]["name"] for e in configmap_envs}
        assert "database-config" in configmap_names


class TestSecretCreationScript:
    SCRIPT = REPO_ROOT / "scripts" / "create-local-secrets.sh"

    def test_script_exists(self) -> None:
        assert self.SCRIPT.exists(), f"secret creation script not found at {self.SCRIPT}"

    def test_script_creates_all_secrets(self) -> None:
        content = self.SCRIPT.read_text(encoding="utf-8")
        assert "minio-credentials" in content
        assert "database-credentials" in content
        assert "ingestion-api-keys" in content


ALL_DEPLOYMENTS = {
    "ingestion": INGESTION_DEPLOYMENT,
    "processor": PROCESSOR_DEPLOYMENT,
    "raw-writer": RAW_WRITER_DEPLOYMENT,
    "lake-writer": LAKE_WRITER_DEPLOYMENT,
    "warehouse-loader": WAREHOUSE_LOADER_DEPLOYMENT,
    "api": API_DEPLOYMENT,
    "kafka": KAFKA_DEPLOYMENT,
}

MINIO_STATEFULSET = REPO_ROOT / "kubernetes" / "deployments" / "minio-statefulset.yaml"
POSTGRESQL_STATEFULSET = REPO_ROOT / "kubernetes" / "deployments" / "postgresql-statefulset.yaml"
DOCKER_COMPOSE = REPO_ROOT / "docker-compose.yml"

ALL_STATEFULSETS = {
    "minio": MINIO_STATEFULSET,
    "postgresql": POSTGRESQL_STATEFULSET,
}

KAFKA_DEPENDENT_DEPLOYMENTS = {
    "ingestion": INGESTION_DEPLOYMENT,
    "processor": PROCESSOR_DEPLOYMENT,
    "raw-writer": RAW_WRITER_DEPLOYMENT,
    "lake-writer": LAKE_WRITER_DEPLOYMENT,
}


class TestAllDeploymentsHaveHealthProbes:
    def test_every_deployment_has_liveness_probe(self) -> None:
        for name, path in ALL_DEPLOYMENTS.items():
            manifest = _load_yaml(path)
            container = manifest["spec"]["template"]["spec"]["containers"][0]
            assert "livenessProbe" in container, f"{name} deployment missing livenessProbe"

    def test_every_deployment_has_readiness_probe(self) -> None:
        for name, path in ALL_DEPLOYMENTS.items():
            manifest = _load_yaml(path)
            container = manifest["spec"]["template"]["spec"]["containers"][0]
            assert "readinessProbe" in container, f"{name} deployment missing readinessProbe"

    def test_liveness_probes_have_timing(self) -> None:
        for name, path in ALL_DEPLOYMENTS.items():
            manifest = _load_yaml(path)
            container = manifest["spec"]["template"]["spec"]["containers"][0]
            probe = container["livenessProbe"]
            assert "initialDelaySeconds" in probe, (
                f"{name} livenessProbe missing initialDelaySeconds"
            )
            assert "periodSeconds" in probe, f"{name} livenessProbe missing periodSeconds"

    def test_readiness_probes_have_timing(self) -> None:
        for name, path in ALL_DEPLOYMENTS.items():
            manifest = _load_yaml(path)
            container = manifest["spec"]["template"]["spec"]["containers"][0]
            probe = container["readinessProbe"]
            assert "initialDelaySeconds" in probe, (
                f"{name} readinessProbe missing initialDelaySeconds"
            )
            assert "periodSeconds" in probe, f"{name} readinessProbe missing periodSeconds"


class TestKafkaDeploymentProbes:
    def test_kafka_liveness_is_tcp_socket(self) -> None:
        manifest = _load_yaml(KAFKA_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        probe = container["livenessProbe"]
        assert "tcpSocket" in probe
        assert probe["tcpSocket"]["port"] == 29092

    def test_kafka_readiness_is_tcp_socket(self) -> None:
        manifest = _load_yaml(KAFKA_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        probe = container["readinessProbe"]
        assert "tcpSocket" in probe
        assert probe["tcpSocket"]["port"] == 29092


class TestWorkerServiceProbes:
    def test_kafka_consumers_have_exec_liveness(self) -> None:
        for name, path in KAFKA_DEPENDENT_DEPLOYMENTS.items():
            manifest = _load_yaml(path)
            container = manifest["spec"]["template"]["spec"]["containers"][0]
            probe = container["livenessProbe"]
            assert "exec" in probe, f"{name} livenessProbe should use exec"

    def test_kafka_consumers_have_exec_readiness(self) -> None:
        for name, path in KAFKA_DEPENDENT_DEPLOYMENTS.items():
            manifest = _load_yaml(path)
            container = manifest["spec"]["template"]["spec"]["containers"][0]
            probe = container["readinessProbe"]
            assert "exec" in probe, f"{name} readinessProbe should use exec"

    def test_kafka_consumer_readiness_checks_kafka_connectivity(self) -> None:
        for name, path in KAFKA_DEPENDENT_DEPLOYMENTS.items():
            manifest = _load_yaml(path)
            container = manifest["spec"]["template"]["spec"]["containers"][0]
            probe = container["readinessProbe"]
            command = " ".join(probe["exec"]["command"])
            assert "kafka" in command, f"{name} readiness probe should check Kafka connectivity"
            assert "29092" in command, f"{name} readiness probe should connect to port 29092"

    def test_warehouse_loader_readiness_checks_postgresql(self) -> None:
        manifest = _load_yaml(WAREHOUSE_LOADER_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        probe = container["readinessProbe"]
        command = " ".join(probe["exec"]["command"])
        assert "postgresql" in command
        assert "5432" in command


class TestAPIDeploymentProbes:
    def test_api_liveness_is_http_get(self) -> None:
        manifest = _load_yaml(API_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        probe = container["livenessProbe"]
        assert "httpGet" in probe
        assert probe["httpGet"]["path"] == "/api/v1/health"

    def test_api_readiness_is_http_get(self) -> None:
        manifest = _load_yaml(API_DEPLOYMENT)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        probe = container["readinessProbe"]
        assert "httpGet" in probe
        assert probe["httpGet"]["path"] == "/api/v1/ready"


class TestAllDeploymentsHaveResourceLimits:
    def test_every_deployment_has_resources(self) -> None:
        for name, path in ALL_DEPLOYMENTS.items():
            manifest = _load_yaml(path)
            container = manifest["spec"]["template"]["spec"]["containers"][0]
            assert "resources" in container, f"{name} deployment missing resources"

    def test_every_deployment_has_cpu_and_memory_requests(self) -> None:
        for name, path in ALL_DEPLOYMENTS.items():
            manifest = _load_yaml(path)
            container = manifest["spec"]["template"]["spec"]["containers"][0]
            resources = container["resources"]
            assert "requests" in resources, f"{name} missing resource requests"
            assert "cpu" in resources["requests"], f"{name} missing cpu request"
            assert "memory" in resources["requests"], f"{name} missing memory request"

    def test_every_deployment_has_cpu_and_memory_limits(self) -> None:
        for name, path in ALL_DEPLOYMENTS.items():
            manifest = _load_yaml(path)
            container = manifest["spec"]["template"]["spec"]["containers"][0]
            resources = container["resources"]
            assert "limits" in resources, f"{name} missing resource limits"
            assert "cpu" in resources["limits"], f"{name} missing cpu limit"
            assert "memory" in resources["limits"], f"{name} missing memory limit"

    def test_requests_do_not_exceed_limits(self) -> None:
        def _parse_cpu(val: str) -> int:
            s = str(val)
            if s.endswith("m"):
                return int(s[:-1])
            return int(float(s) * 1000)

        def _parse_mem(val: str) -> int:
            s = str(val)
            if s.endswith("Gi"):
                return int(float(s[:-2]) * 1024)
            if s.endswith("Mi"):
                return int(s[:-2])
            return int(s)

        for name, path in ALL_DEPLOYMENTS.items():
            manifest = _load_yaml(path)
            container = manifest["spec"]["template"]["spec"]["containers"][0]
            res = container["resources"]
            assert _parse_cpu(res["requests"]["cpu"]) <= _parse_cpu(res["limits"]["cpu"]), (
                f"{name} cpu request exceeds limit"
            )
            assert _parse_mem(res["requests"]["memory"]) <= _parse_mem(res["limits"]["memory"]), (
                f"{name} memory request exceeds limit"
            )


TROUBLESHOOTING_GUIDE = REPO_ROOT / "docs" / "kubernetes-troubleshooting.md"


class TestTroubleshootingGuide:
    def test_guide_exists(self) -> None:
        assert TROUBLESHOOTING_GUIDE.exists(), (
            f"troubleshooting guide not found at {TROUBLESHOOTING_GUIDE}"
        )

    def test_guide_covers_crash_loop(self) -> None:
        content = TROUBLESHOOTING_GUIDE.read_text(encoding="utf-8")
        assert "CrashLoopBackOff" in content

    def test_guide_covers_image_pull(self) -> None:
        content = TROUBLESHOOTING_GUIDE.read_text(encoding="utf-8")
        assert "ImagePullBackOff" in content

    def test_guide_covers_readiness_failure(self) -> None:
        content = TROUBLESHOOTING_GUIDE.read_text(encoding="utf-8")
        assert "Readiness" in content or "readiness" in content

    def test_guide_covers_oomkilled(self) -> None:
        content = TROUBLESHOOTING_GUIDE.read_text(encoding="utf-8")
        assert "OOMKilled" in content

    def test_guide_covers_missing_configuration(self) -> None:
        content = TROUBLESHOOTING_GUIDE.read_text(encoding="utf-8")
        assert "ConfigMap" in content or "configmap" in content
        assert "Secret" in content or "secret" in content


class TestMinioStatefulSet:
    def test_minio_statefulset_exists(self) -> None:
        assert MINIO_STATEFULSET.exists(), f"minio statefulset not found at {MINIO_STATEFULSET}"

    def test_minio_statefulset_is_statefulset_resource(self) -> None:
        manifest = _load_yaml(MINIO_STATEFULSET)
        assert manifest["apiVersion"] == "apps/v1"
        assert manifest["kind"] == "StatefulSet"

    def test_minio_statefulset_namespace(self) -> None:
        manifest = _load_yaml(MINIO_STATEFULSET)
        assert manifest["metadata"]["namespace"] == "ai-data-platform"

    def test_minio_statefulset_labels(self) -> None:
        manifest = _load_yaml(MINIO_STATEFULSET)
        labels = manifest["metadata"]["labels"]
        assert labels["app.kubernetes.io/name"] == "minio"
        assert labels["app.kubernetes.io/part-of"] == "ai-data-platform"

    def test_minio_pod_labels_match_service_selector(self) -> None:
        manifest = _load_yaml(MINIO_STATEFULSET)
        service = _load_yaml(MINIO_SERVICE)
        selector = service["spec"]["selector"]
        pod_labels = manifest["spec"]["template"]["metadata"]["labels"]
        for key, value in selector.items():
            assert pod_labels.get(key) == value, (
                f"MinIO pod label {key}={pod_labels.get(key)} does not match "
                f"service selector {key}={value}"
            )

    def test_minio_statefulset_selector_matches_template(self) -> None:
        manifest = _load_yaml(MINIO_STATEFULSET)
        selector = manifest["spec"]["selector"]["matchLabels"]
        template_labels = manifest["spec"]["template"]["metadata"]["labels"]
        for key, value in selector.items():
            assert template_labels.get(key) == value

    def test_minio_exposes_api_and_console_ports(self) -> None:
        manifest = _load_yaml(MINIO_STATEFULSET)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        ports = container["ports"]
        assert any(p["containerPort"] == 9000 for p in ports)
        assert any(p["containerPort"] == 9001 for p in ports)

    def test_minio_uses_secret_for_credentials(self) -> None:
        manifest = _load_yaml(MINIO_STATEFULSET)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        secret_envs = [
            e for e in container["env"] if "valueFrom" in e and "secretKeyRef" in e["valueFrom"]
        ]
        secret_names = {e["valueFrom"]["secretKeyRef"]["name"] for e in secret_envs}
        assert "minio-credentials" in secret_names

    def test_minio_has_liveness_probe(self) -> None:
        manifest = _load_yaml(MINIO_STATEFULSET)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert "livenessProbe" in container
        probe = container["livenessProbe"]
        assert "initialDelaySeconds" in probe
        assert "periodSeconds" in probe

    def test_minio_has_readiness_probe(self) -> None:
        manifest = _load_yaml(MINIO_STATEFULSET)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert "readinessProbe" in container
        probe = container["readinessProbe"]
        assert "initialDelaySeconds" in probe
        assert "periodSeconds" in probe

    def test_minio_has_resource_requests_and_limits(self) -> None:
        manifest = _load_yaml(MINIO_STATEFULSET)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        resources = container["resources"]
        assert "requests" in resources
        assert "cpu" in resources["requests"]
        assert "memory" in resources["requests"]
        assert "limits" in resources
        assert "cpu" in resources["limits"]
        assert "memory" in resources["limits"]

    def test_minio_has_volume_mount(self) -> None:
        manifest = _load_yaml(MINIO_STATEFULSET)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert "volumeMounts" in container
        mount_paths = [vm["mountPath"] for vm in container["volumeMounts"]]
        assert "/data" in mount_paths

    def test_minio_has_volume_claim_templates(self) -> None:
        manifest = _load_yaml(MINIO_STATEFULSET)
        vcts = manifest["spec"]["volumeClaimTemplates"]
        assert len(vcts) >= 1
        names = [v["metadata"]["name"] for v in vcts]
        assert "minio-data" in names
        spec = vcts[0]["spec"]
        assert "ReadWriteOnce" in spec["accessModes"]
        assert "storage" in spec["resources"]["requests"]

    def test_minio_has_security_context(self) -> None:
        manifest = _load_yaml(MINIO_STATEFULSET)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert "securityContext" in container
        sc = container["securityContext"]
        assert sc.get("allowPrivilegeEscalation") is False

    def test_minio_image_matches_docker_compose(self) -> None:
        import yaml

        manifest = _load_yaml(MINIO_STATEFULSET)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        k8s_image = container["image"]

        with open(DOCKER_COMPOSE, encoding="utf-8") as f:
            compose = yaml.safe_load(f)
        compose_image = compose["services"]["minio"]["image"]

        assert k8s_image == compose_image, (
            f"MinIO image mismatch: K8s={k8s_image}, docker-compose={compose_image}"
        )


class TestPostgreSQLStatefulSet:
    def test_postgresql_statefulset_exists(self) -> None:
        assert POSTGRESQL_STATEFULSET.exists(), (
            f"postgresql statefulset not found at {POSTGRESQL_STATEFULSET}"
        )

    def test_postgresql_statefulset_is_statefulset_resource(self) -> None:
        manifest = _load_yaml(POSTGRESQL_STATEFULSET)
        assert manifest["apiVersion"] == "apps/v1"
        assert manifest["kind"] == "StatefulSet"

    def test_postgresql_statefulset_namespace(self) -> None:
        manifest = _load_yaml(POSTGRESQL_STATEFULSET)
        assert manifest["metadata"]["namespace"] == "ai-data-platform"

    def test_postgresql_statefulset_labels(self) -> None:
        manifest = _load_yaml(POSTGRESQL_STATEFULSET)
        labels = manifest["metadata"]["labels"]
        assert labels["app.kubernetes.io/name"] == "postgresql"
        assert labels["app.kubernetes.io/part-of"] == "ai-data-platform"

    def test_postgresql_pod_labels_match_service_selector(self) -> None:
        manifest = _load_yaml(POSTGRESQL_STATEFULSET)
        service = _load_yaml(POSTGRESQL_SERVICE)
        selector = service["spec"]["selector"]
        pod_labels = manifest["spec"]["template"]["metadata"]["labels"]
        for key, value in selector.items():
            assert pod_labels.get(key) == value, (
                f"PostgreSQL pod label {key}={pod_labels.get(key)} does not match "
                f"service selector {key}={value}"
            )

    def test_postgresql_statefulset_selector_matches_template(self) -> None:
        manifest = _load_yaml(POSTGRESQL_STATEFULSET)
        selector = manifest["spec"]["selector"]["matchLabels"]
        template_labels = manifest["spec"]["template"]["metadata"]["labels"]
        for key, value in selector.items():
            assert template_labels.get(key) == value

    def test_postgresql_exposes_port_5432(self) -> None:
        manifest = _load_yaml(POSTGRESQL_STATEFULSET)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        ports = container["ports"]
        assert any(p["containerPort"] == 5432 for p in ports)

    def test_postgresql_uses_secret_for_password(self) -> None:
        manifest = _load_yaml(POSTGRESQL_STATEFULSET)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        secret_envs = [
            e for e in container["env"] if "valueFrom" in e and "secretKeyRef" in e["valueFrom"]
        ]
        secret_names = {e["valueFrom"]["secretKeyRef"]["name"] for e in secret_envs}
        assert "database-credentials" in secret_names

    def test_postgresql_has_liveness_probe(self) -> None:
        manifest = _load_yaml(POSTGRESQL_STATEFULSET)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert "livenessProbe" in container
        probe = container["livenessProbe"]
        assert "initialDelaySeconds" in probe
        assert "periodSeconds" in probe

    def test_postgresql_has_readiness_probe(self) -> None:
        manifest = _load_yaml(POSTGRESQL_STATEFULSET)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert "readinessProbe" in container
        probe = container["readinessProbe"]
        assert "initialDelaySeconds" in probe
        assert "periodSeconds" in probe

    def test_postgresql_has_resource_requests_and_limits(self) -> None:
        manifest = _load_yaml(POSTGRESQL_STATEFULSET)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        resources = container["resources"]
        assert "requests" in resources
        assert "cpu" in resources["requests"]
        assert "memory" in resources["requests"]
        assert "limits" in resources
        assert "cpu" in resources["limits"]
        assert "memory" in resources["limits"]

    def test_postgresql_has_volume_mount(self) -> None:
        manifest = _load_yaml(POSTGRESQL_STATEFULSET)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert "volumeMounts" in container
        mount_paths = [vm["mountPath"] for vm in container["volumeMounts"]]
        assert "/var/lib/postgresql/data" in mount_paths

    def test_postgresql_has_volume_claim_templates(self) -> None:
        manifest = _load_yaml(POSTGRESQL_STATEFULSET)
        vcts = manifest["spec"]["volumeClaimTemplates"]
        assert len(vcts) >= 1
        names = [v["metadata"]["name"] for v in vcts]
        assert "postgresql-data" in names
        spec = vcts[0]["spec"]
        assert "ReadWriteOnce" in spec["accessModes"]
        assert "storage" in spec["resources"]["requests"]

    def test_postgresql_has_security_context(self) -> None:
        manifest = _load_yaml(POSTGRESQL_STATEFULSET)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        assert "securityContext" in container
        sc = container["securityContext"]
        assert sc.get("allowPrivilegeEscalation") is False


class TestStatefulSetVolumeMountPVCConsistency:
    """Regression: every persistent volumeMount must resolve to a volumeClaimTemplate."""

    def _persistent_volume_mount_names(self, manifest: dict) -> set[str]:
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        pod_volumes = {
            v["name"]: v for v in manifest["spec"]["template"]["spec"].get("volumes", [])
        }
        vct_names = {
            v["metadata"]["name"] for v in manifest["spec"].get("volumeClaimTemplates", [])
        }
        mount_names: set[str] = set()
        for vm in container.get("volumeMounts", []):
            name = vm["name"]
            if name in vct_names:
                mount_names.add(name)
            elif name in pod_volumes and pod_volumes[name].get("emptyDir") is not None:
                continue
            else:
                mount_names.add(name)
        return mount_names

    def _vct_names(self, manifest: dict) -> set[str]:
        return {v["metadata"]["name"] for v in manifest["spec"].get("volumeClaimTemplates", [])}

    def test_minio_volume_mounts_resolve_to_vct(self) -> None:
        manifest = _load_yaml(MINIO_STATEFULSET)
        mount_names = self._persistent_volume_mount_names(manifest)
        vct_names = self._vct_names(manifest)
        unresolved = mount_names - vct_names
        assert not unresolved, (
            f"MinIO volumeMounts {unresolved} have no matching volumeClaimTemplate"
        )

    def test_postgresql_volume_mounts_resolve_to_vct(self) -> None:
        manifest = _load_yaml(POSTGRESQL_STATEFULSET)
        mount_names = self._persistent_volume_mount_names(manifest)
        vct_names = self._vct_names(manifest)
        unresolved = mount_names - vct_names
        assert not unresolved, (
            f"PostgreSQL volumeMounts {unresolved} have no matching volumeClaimTemplate"
        )

    def test_minio_vct_names_match_volume_mounts(self) -> None:
        manifest = _load_yaml(MINIO_STATEFULSET)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        mount_names = {vm["name"] for vm in container.get("volumeMounts", [])}
        vct_names = self._vct_names(manifest)
        assert vct_names == mount_names, (
            f"VCT names mismatch: mounts={mount_names}, vcts={vct_names}"
        )

    def test_postgresql_vct_names_match_volume_mounts(self) -> None:
        manifest = _load_yaml(POSTGRESQL_STATEFULSET)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        mount_names = {vm["name"] for vm in container.get("volumeMounts", [])}
        vct_names = self._vct_names(manifest)
        assert vct_names == mount_names, (
            f"VCT name mismatch: mounts={mount_names}, vcts={vct_names}"
        )


class TestStatefulSetServiceCompatibility:
    def test_minio_service_still_clusterip(self) -> None:
        manifest = _load_yaml(MINIO_SERVICE)
        assert manifest["spec"]["type"] == "ClusterIP"

    def test_postgresql_service_still_clusterip(self) -> None:
        manifest = _load_yaml(POSTGRESQL_SERVICE)
        assert manifest["spec"]["type"] == "ClusterIP"

    def test_minio_service_ports_unchanged(self) -> None:
        manifest = _load_yaml(MINIO_SERVICE)
        ports = {p["name"]: p["port"] for p in manifest["spec"]["ports"]}
        assert ports["api"] == 9000
        assert ports["console"] == 9001

    def test_postgresql_service_port_unchanged(self) -> None:
        manifest = _load_yaml(POSTGRESQL_SERVICE)
        ports = {p["name"]: p["port"] for p in manifest["spec"]["ports"]}
        assert ports["postgres"] == 5432

    def test_service_names_stable(self) -> None:
        minio_svc = _load_yaml(MINIO_SERVICE)
        pg_svc = _load_yaml(POSTGRESQL_SERVICE)
        assert minio_svc["metadata"]["name"] == "minio"
        assert pg_svc["metadata"]["name"] == "postgresql"
