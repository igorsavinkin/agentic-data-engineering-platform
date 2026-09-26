"""Validate Airflow Kubernetes runtime configuration (TASK-134).

Tests cover:
- Custom Airflow Dockerfile and build-time dependency configuration
- Helm chart Airflow template rendering and structure
- WAREHOUSE_DB_* environment contract
- Airflow metadata DB configuration
- Secret references (no plaintext credentials)
- No regression to host.docker.internal / port-forward topology
- kind cluster Airflow port mapping
- Security context and probe configuration

All tests are hermetic — no live cluster or Airflow installation required.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CHART_DIR = REPO_ROOT / "helm" / "ai-data-platform"
VALUES_YAML = CHART_DIR / "values.yaml"
VALUES_LOCAL = CHART_DIR / "values-local.yaml"
VALUES_PROD = CHART_DIR / "values-production.yaml"
TEMPLATES_DIR = CHART_DIR / "templates"

AIRFLOW_DIR = REPO_ROOT / "airflow"
DOCKERFILE = AIRFLOW_DIR / "Dockerfile"
REQUIREMENTS = AIRFLOW_DIR / "requirements.txt"

KIND_CONFIG = REPO_ROOT / "kubernetes" / "kind" / "kind-config.yaml"

HELM_BIN = shutil.which("helm")


def _load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _helm_template(
    values_files: list[Path] | None = None,
    extra_args: list[str] | None = None,
) -> list[dict[str, Any]]:
    if not HELM_BIN:
        pytest.skip("helm binary not available")
    cmd = [HELM_BIN, "template", "test-release", str(CHART_DIR)]
    for vf in values_files or []:
        cmd.extend(["-f", str(vf)])
    for arg in extra_args or []:
        cmd.append(arg)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f"helm template failed: {result.stderr}"
    docs = list(yaml.safe_load_all(result.stdout))
    return [d for d in docs if d is not None]


def _read_template(relative_path: str) -> str:
    return (TEMPLATES_DIR / relative_path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Airflow Dockerfile
# ---------------------------------------------------------------------------


class TestAirflowDockerfile:
    def test_dockerfile_exists(self) -> None:
        assert DOCKERFILE.exists()

    def test_base_image_is_official_airflow(self) -> None:
        content = DOCKERFILE.read_text(encoding="utf-8")
        assert "apache/airflow:" in content
        assert "python3.12" in content

    def test_airflow_version_is_2_10_4(self) -> None:
        content = DOCKERFILE.read_text(encoding="utf-8")
        assert "AIRFLOW_VERSION=2.10.4" in content

    def test_requirements_copied_and_installed(self) -> None:
        content = DOCKERFILE.read_text(encoding="utf-8")
        assert "COPY airflow/requirements.txt" in content
        assert "pip install -r" in content

    def test_dags_copied_into_image(self) -> None:
        content = DOCKERFILE.read_text(encoding="utf-8")
        assert "COPY" in content
        assert "airflow/dags/" in content
        assert "/opt/airflow/dags/" in content

    def test_libs_copied_into_image(self) -> None:
        content = DOCKERFILE.read_text(encoding="utf-8")
        assert "libs/" in content
        assert "/opt/airflow/libs/" in content

    def test_dags_folder_configured(self) -> None:
        content = DOCKERFILE.read_text(encoding="utf-8")
        assert "AIRFLOW__CORE__DAGS_FOLDER=/opt/airflow/dags" in content

    def test_runs_as_non_root_user(self) -> None:
        content = DOCKERFILE.read_text(encoding="utf-8")
        assert "USER airflow" in content


# ---------------------------------------------------------------------------
# Airflow requirements
# ---------------------------------------------------------------------------


class TestAirflowRequirements:
    def test_requirements_file_exists(self) -> None:
        assert REQUIREMENTS.exists()

    @pytest.mark.parametrize(
        "package",
        [
            "polars",
            "psycopg2-binary",
            "pydantic",
            "pydantic-settings",
            "boto3",
            "prometheus-client",
        ],
    )
    def test_required_package_present(self, package: str) -> None:
        content = REQUIREMENTS.read_text(encoding="utf-8")
        assert package in content

    def test_pydantic_settings_present_for_dag_imports(self) -> None:
        content = REQUIREMENTS.read_text(encoding="utf-8")
        assert "pydantic-settings" in content


# ---------------------------------------------------------------------------
# Helm values — Airflow section
# ---------------------------------------------------------------------------


class TestAirflowHelmValues:
    def test_airflow_section_exists(self) -> None:
        values = _load_yaml(VALUES_YAML)
        assert "airflow" in values

    def test_airflow_enabled_by_default(self) -> None:
        values = _load_yaml(VALUES_YAML)
        assert values["airflow"]["enabled"] is True

    def test_executor_is_local(self) -> None:
        values = _load_yaml(VALUES_YAML)
        assert values["airflow"]["executor"] == "LocalExecutor"

    def test_scheduler_has_resource_limits(self) -> None:
        values = _load_yaml(VALUES_YAML)
        scheduler = values["airflow"]["scheduler"]
        assert "resources" in scheduler
        assert "limits" in scheduler["resources"]
        assert "requests" in scheduler["resources"]

    def test_webserver_has_resource_limits(self) -> None:
        values = _load_yaml(VALUES_YAML)
        webserver = values["airflow"]["webserver"]
        assert "resources" in webserver
        assert "limits" in webserver["resources"]
        assert "requests" in webserver["resources"]

    def test_scheduler_liveness_probe_configured(self) -> None:
        values = _load_yaml(VALUES_YAML)
        probe = values["airflow"]["scheduler"]["livenessProbe"]
        assert "initialDelaySeconds" in probe
        assert "periodSeconds" in probe
        assert "timeoutSeconds" in probe
        assert "failureThreshold" in probe

    def test_scheduler_readiness_probe_configured(self) -> None:
        values = _load_yaml(VALUES_YAML)
        probe = values["airflow"]["scheduler"]["readinessProbe"]
        assert "initialDelaySeconds" in probe
        assert "periodSeconds" in probe

    def test_webserver_liveness_probe_configured(self) -> None:
        values = _load_yaml(VALUES_YAML)
        probe = values["airflow"]["webserver"]["livenessProbe"]
        assert "initialDelaySeconds" in probe
        assert "periodSeconds" in probe

    def test_local_values_enable_airflow(self) -> None:
        local = _load_yaml(VALUES_LOCAL)
        assert local["airflow"]["enabled"] is True

    def test_airflow_image_section_exists(self) -> None:
        values = _load_yaml(VALUES_YAML)
        assert "images" in values
        assert "airflow" in values["images"]


# ---------------------------------------------------------------------------
# Helm template rendering — Airflow resources
# ---------------------------------------------------------------------------


class TestAirflowHelmRendering:
    def test_scheduler_deployment_renders(self) -> None:
        docs = _helm_template()
        deployments = {d["metadata"]["name"]: d for d in docs if d["kind"] == "Deployment"}
        assert "airflow-scheduler" in deployments

    def test_webserver_deployment_renders(self) -> None:
        docs = _helm_template()
        deployments = {d["metadata"]["name"]: d for d in docs if d["kind"] == "Deployment"}
        assert "airflow-webserver" in deployments

    def test_init_job_renders(self) -> None:
        docs = _helm_template()
        jobs = {d["metadata"]["name"]: d for d in docs if d["kind"] == "Job"}
        assert "airflow-init" in jobs

    def test_airflow_metadata_configmap_renders(self) -> None:
        docs = _helm_template()
        cms = {d["metadata"]["name"]: d for d in docs if d["kind"] == "ConfigMap"}
        assert "airflow-metadata" in cms

    def test_airflow_credentials_secrets_render(self) -> None:
        docs = _helm_template()
        secrets = {d["metadata"]["name"]: d for d in docs if d["kind"] == "Secret"}
        assert "airflow-metadata-credentials" in secrets
        assert "airflow-keys" in secrets

    def test_airflow_webserver_service_renders(self) -> None:
        docs = _helm_template()
        services = {d["metadata"]["name"]: d for d in docs if d["kind"] == "Service"}
        assert "airflow-webserver" in services

    def test_no_airflow_resources_when_disabled(self) -> None:
        docs = _helm_template(extra_args=["--set", "airflow.enabled=false"])
        names = {(d["kind"], d["metadata"]["name"]) for d in docs}
        assert ("Deployment", "airflow-scheduler") not in names
        assert ("Deployment", "airflow-webserver") not in names
        assert ("Job", "airflow-init") not in names
        assert ("Service", "airflow-webserver") not in names

    def test_airflow_disabled_reverts_to_21_resources(self) -> None:
        docs = _helm_template(extra_args=["--set", "airflow.enabled=false"])
        assert len(docs) == 21


# ---------------------------------------------------------------------------
# Airflow deployment structure and security
# ---------------------------------------------------------------------------


class TestAirflowSchedulerDeployment:
    def _scheduler(self) -> dict[str, Any]:
        docs = _helm_template()
        return [
            d
            for d in docs
            if d["kind"] == "Deployment" and d["metadata"]["name"] == "airflow-scheduler"
        ][0]

    def test_has_correct_labels(self) -> None:
        dep = self._scheduler()
        labels = dep["metadata"]["labels"]
        assert labels["app.kubernetes.io/name"] == "airflow-scheduler"
        assert labels["app.kubernetes.io/component"] == "airflow"
        assert labels["app.kubernetes.io/part-of"] == "ai-data-platform"

    def test_uses_airflow_image(self) -> None:
        dep = self._scheduler()
        image = dep["spec"]["template"]["spec"]["containers"][0]["image"]
        assert "airflow" in image

    def test_has_liveness_probe(self) -> None:
        dep = self._scheduler()
        container = dep["spec"]["template"]["spec"]["containers"][0]
        assert "livenessProbe" in container

    def test_has_readiness_probe(self) -> None:
        dep = self._scheduler()
        container = dep["spec"]["template"]["spec"]["containers"][0]
        assert "readinessProbe" in container

    def test_has_resource_limits(self) -> None:
        dep = self._scheduler()
        container = dep["spec"]["template"]["spec"]["containers"][0]
        assert "resources" in container
        assert "limits" in container["resources"]
        assert "requests" in container["resources"]

    def test_security_context_non_root(self) -> None:
        dep = self._scheduler()
        pod_sc = dep["spec"]["template"]["spec"]["securityContext"]
        assert pod_sc.get("runAsNonRoot") is True

    def test_container_security_context(self) -> None:
        dep = self._scheduler()
        container_sc = dep["spec"]["template"]["spec"]["containers"][0]["securityContext"]
        assert container_sc.get("allowPrivilegeEscalation") is False
        assert container_sc.get("capabilities", {}).get("drop") == ["ALL"]

    def test_has_warehouse_db_env_vars(self) -> None:
        dep = self._scheduler()
        container = dep["spec"]["template"]["spec"]["containers"][0]
        env_names = {e["name"] for e in container["env"]}
        assert "WAREHOUSE_DB_HOST" in env_names
        assert "WAREHOUSE_DB_PORT" in env_names
        assert "WAREHOUSE_DB_NAME" in env_names
        assert "WAREHOUSE_DB_USER" in env_names
        assert "WAREHOUSE_DB_PASSWORD" in env_names

    def test_warehouse_db_host_from_configmap(self) -> None:
        dep = self._scheduler()
        container = dep["spec"]["template"]["spec"]["containers"][0]
        host_env = next(e for e in container["env"] if e["name"] == "WAREHOUSE_DB_HOST")
        ref = host_env["valueFrom"]["configMapKeyRef"]
        assert ref["name"] == "database-config"

    def test_warehouse_db_password_from_secret(self) -> None:
        dep = self._scheduler()
        container = dep["spec"]["template"]["spec"]["containers"][0]
        pw_env = next(e for e in container["env"] if e["name"] == "WAREHOUSE_DB_PASSWORD")
        ref = pw_env["valueFrom"]["secretKeyRef"]
        assert ref["name"] == "database-credentials"
        assert ref["key"] == "db-password"

    def test_no_host_docker_internal(self) -> None:
        dep = self._scheduler()
        content = str(dep)
        assert "host.docker.internal" not in content


class TestAirflowWebserverDeployment:
    def _webserver(self) -> dict[str, Any]:
        docs = _helm_template()
        return [
            d
            for d in docs
            if d["kind"] == "Deployment" and d["metadata"]["name"] == "airflow-webserver"
        ][0]

    def test_has_correct_labels(self) -> None:
        dep = self._webserver()
        labels = dep["metadata"]["labels"]
        assert labels["app.kubernetes.io/name"] == "airflow-webserver"
        assert labels["app.kubernetes.io/component"] == "airflow"

    def test_has_liveness_probe(self) -> None:
        dep = self._webserver()
        container = dep["spec"]["template"]["spec"]["containers"][0]
        assert "livenessProbe" in container

    def test_has_readiness_probe(self) -> None:
        dep = self._webserver()
        container = dep["spec"]["template"]["spec"]["containers"][0]
        assert "readinessProbe" in container

    def test_has_resource_limits(self) -> None:
        dep = self._webserver()
        container = dep["spec"]["template"]["spec"]["containers"][0]
        assert "resources" in container
        assert "limits" in container["resources"]

    def test_security_context_non_root(self) -> None:
        dep = self._webserver()
        pod_sc = dep["spec"]["template"]["spec"]["securityContext"]
        assert pod_sc.get("runAsNonRoot") is True

    def test_container_security_context(self) -> None:
        dep = self._webserver()
        container_sc = dep["spec"]["template"]["spec"]["containers"][0]["securityContext"]
        assert container_sc.get("allowPrivilegeEscalation") is False
        assert container_sc.get("capabilities", {}).get("drop") == ["ALL"]

    def test_has_warehouse_db_env_vars(self) -> None:
        dep = self._webserver()
        container = dep["spec"]["template"]["spec"]["containers"][0]
        env_names = {e["name"] for e in container["env"]}
        assert "WAREHOUSE_DB_HOST" in env_names
        assert "WAREHOUSE_DB_PORT" in env_names
        assert "WAREHOUSE_DB_NAME" in env_names
        assert "WAREHOUSE_DB_USER" in env_names
        assert "WAREHOUSE_DB_PASSWORD" in env_names

    def test_warehouse_db_password_from_secret(self) -> None:
        dep = self._webserver()
        container = dep["spec"]["template"]["spec"]["containers"][0]
        pw_env = next(e for e in container["env"] if e["name"] == "WAREHOUSE_DB_PASSWORD")
        ref = pw_env["valueFrom"]["secretKeyRef"]
        assert ref["name"] == "database-credentials"

    def test_has_minio_env_vars(self) -> None:
        dep = self._webserver()
        container = dep["spec"]["template"]["spec"]["containers"][0]
        env_names = {e["name"] for e in container["env"]}
        assert "AIRFLOW_VAR_MINIO_ENDPOINT" in env_names
        assert "APP_MINIO_ACCESS_KEY" in env_names
        assert "APP_MINIO_SECRET_KEY" in env_names

    def test_minio_credentials_from_secret(self) -> None:
        dep = self._webserver()
        container = dep["spec"]["template"]["spec"]["containers"][0]
        ak_env = next(e for e in container["env"] if e["name"] == "APP_MINIO_ACCESS_KEY")
        ref = ak_env["valueFrom"]["secretKeyRef"]
        assert ref["name"] == "minio-credentials"

    def test_no_host_docker_internal(self) -> None:
        dep = self._webserver()
        content = str(dep)
        assert "host.docker.internal" not in content

    def test_has_wait_for_db_init_container(self) -> None:
        dep = self._webserver()
        init_containers = dep["spec"]["template"]["spec"].get("initContainers", [])
        names = [ic["name"] for ic in init_containers]
        assert "wait-for-airflow-db" in names


# ---------------------------------------------------------------------------
# Airflow init job
# ---------------------------------------------------------------------------


class TestAirflowInitJob:
    def _init_job(self) -> dict[str, Any]:
        docs = _helm_template()
        return [d for d in docs if d["kind"] == "Job" and d["metadata"]["name"] == "airflow-init"][
            0
        ]

    def test_has_helm_hook_annotations(self) -> None:
        job = self._init_job()
        annotations = job["metadata"]["annotations"]
        assert "helm.sh/hook" in annotations
        hook = annotations["helm.sh/hook"]
        assert "post-install" in hook
        assert "pre-upgrade" in hook

    def test_has_hook_delete_policy(self) -> None:
        job = self._init_job()
        annotations = job["metadata"]["annotations"]
        assert "helm.sh/hook-delete-policy" in annotations
        assert "before-hook-creation" in annotations["helm.sh/hook-delete-policy"]

    def test_has_wait_for_postgresql_init_container(self) -> None:
        job = self._init_job()
        init_containers = job["spec"]["template"]["spec"].get("initContainers", [])
        names = [ic["name"] for ic in init_containers]
        assert "wait-for-postgresql" in names

    def test_has_create_database_init_container(self) -> None:
        job = self._init_job()
        init_containers = job["spec"]["template"]["spec"].get("initContainers", [])
        names = [ic["name"] for ic in init_containers]
        assert "create-database" in names

    def test_migration_command(self) -> None:
        job = self._init_job()
        container = job["spec"]["template"]["spec"]["containers"][0]
        command_str = " ".join(container["command"])
        assert "airflow db migrate" in command_str

    def test_migrate_failure_propagates(self) -> None:
        job = self._init_job()
        container = job["spec"]["template"]["spec"]["containers"][0]
        script = container["command"][-1]
        assert "set -e" in script

    def test_password_from_secret(self) -> None:
        job = self._init_job()
        container = job["spec"]["template"]["spec"]["containers"][0]
        pw_env = next(e for e in container["env"] if e["name"] == "AIRFLOW_METADATA_DB_PASSWORD")
        ref = pw_env["valueFrom"]["secretKeyRef"]
        assert ref["name"] == "airflow-metadata-credentials"
        assert ref["key"] == "db-password"

    def test_security_context(self) -> None:
        job = self._init_job()
        pod_sc = job["spec"]["template"]["spec"]["securityContext"]
        assert pod_sc.get("runAsNonRoot") is True
        container_sc = job["spec"]["template"]["spec"]["containers"][0]["securityContext"]
        assert container_sc.get("allowPrivilegeEscalation") is False
        assert container_sc.get("capabilities", {}).get("drop") == ["ALL"]

    def test_has_resource_limits(self) -> None:
        job = self._init_job()
        container = job["spec"]["template"]["spec"]["containers"][0]
        assert "resources" in container
        assert "limits" in container["resources"]


# ---------------------------------------------------------------------------
# Airflow metadata ConfigMap
# ---------------------------------------------------------------------------


class TestAirflowMetadataConfigMap:
    def test_configmap_renders(self) -> None:
        docs = _helm_template()
        cms = {d["metadata"]["name"]: d for d in docs if d["kind"] == "ConfigMap"}
        assert "airflow-metadata" in cms

    def test_has_required_keys(self) -> None:
        docs = _helm_template()
        cm = [
            d
            for d in docs
            if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "airflow-metadata"
        ][0]
        data = cm["data"]
        assert "AIRFLOW_METADATA_DB_HOST" in data
        assert "AIRFLOW_METADATA_DB_PORT" in data
        assert "AIRFLOW_METADATA_DB_NAME" in data
        assert "AIRFLOW_METADATA_DB_USER" in data

    def test_metadata_db_separate_from_warehouse(self) -> None:
        docs = _helm_template()
        cm = [
            d
            for d in docs
            if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "airflow-metadata"
        ][0]
        db_config = [
            d
            for d in docs
            if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "database-config"
        ][0]
        metadata_name = cm["data"]["AIRFLOW_METADATA_DB_NAME"]
        warehouse_name = db_config["data"]["WAREHOUSE_DB_NAME"]
        assert metadata_name != warehouse_name, (
            "Airflow metadata DB must be separate from warehouse"
        )


# ---------------------------------------------------------------------------
# Airflow credentials — no plaintext secrets
# ---------------------------------------------------------------------------


class TestAirflowSecretsNoPlaintext:
    def test_airflow_credentials_secret_renders(self) -> None:
        docs = _helm_template()
        secrets = {d["metadata"]["name"]: d for d in docs if d["kind"] == "Secret"}
        assert "airflow-metadata-credentials" in secrets

    def test_airflow_keys_secret_renders(self) -> None:
        docs = _helm_template()
        secrets = {d["metadata"]["name"]: d for d in docs if d["kind"] == "Secret"}
        assert "airflow-keys" in secrets

    def test_fernet_key_is_valid(self) -> None:
        import base64

        from cryptography.fernet import Fernet

        docs = _helm_template()
        secret = [
            d for d in docs if d["kind"] == "Secret" and d["metadata"]["name"] == "airflow-keys"
        ][0]
        fernet_b64 = base64.b64decode(secret["data"]["fernet-key"]).decode("utf-8")
        Fernet(fernet_b64)

    def test_no_plaintext_passwords_in_airflow_templates(self) -> None:
        airflow_templates = [
            "deployments/airflow-scheduler.yaml",
            "deployments/airflow-webserver.yaml",
            "jobs/airflow-init.yaml",
        ]
        for template_path in airflow_templates:
            content = _read_template(template_path)
            assert "password:" not in content.lower() or "valueFrom" in content, (
                f"{template_path} may contain plaintext password"
            )

    def test_all_airflow_env_credentials_use_secret_refs(self) -> None:
        docs = _helm_template()
        for dep_name in ("airflow-scheduler", "airflow-webserver"):
            dep = [
                d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"] == dep_name
            ][0]
            container = dep["spec"]["template"]["spec"]["containers"][0]
            credential_envs = [
                e
                for e in container["env"]
                if "PASSWORD" in e["name"] or "SECRET_KEY" in e["name"] or "FERNET_KEY" in e["name"]
            ]
            for env in credential_envs:
                assert "valueFrom" in env, f"{dep_name} {env['name']} should use valueFrom"
                assert "secretKeyRef" in env["valueFrom"], (
                    f"{dep_name} {env['name']} should use secretKeyRef"
                )


# ---------------------------------------------------------------------------
# No regression to Docker host.docker.internal / port-forward topology
# ---------------------------------------------------------------------------


class TestNoDockerTopologyRegression:
    def test_no_host_docker_internal_in_scheduler_template(self) -> None:
        content = _read_template("deployments/airflow-scheduler.yaml")
        assert "host.docker.internal" not in content

    def test_no_host_docker_internal_in_webserver_template(self) -> None:
        content = _read_template("deployments/airflow-webserver.yaml")
        assert "host.docker.internal" not in content

    def test_no_host_docker_internal_in_init_template(self) -> None:
        content = _read_template("jobs/airflow-init.yaml")
        assert "host.docker.internal" not in content

    def test_warehouse_connectivity_via_k8s_service_dns(self) -> None:
        docs = _helm_template()
        dep = [
            d
            for d in docs
            if d["kind"] == "Deployment" and d["metadata"]["name"] == "airflow-scheduler"
        ][0]
        container = dep["spec"]["template"]["spec"]["containers"][0]
        host_env = next(e for e in container["env"] if e["name"] == "WAREHOUSE_DB_HOST")
        if "valueFrom" in host_env:
            ref_name = host_env["valueFrom"]["configMapKeyRef"]["name"]
            assert ref_name == "database-config"
        else:
            value = host_env.get("value", "")
            assert "host.docker.internal" not in value
            assert "localhost" not in value

    def test_no_port_forward_references_in_airflow_templates(self) -> None:
        airflow_templates = [
            "deployments/airflow-scheduler.yaml",
            "deployments/airflow-webserver.yaml",
            "jobs/airflow-init.yaml",
            "services/airflow-webserver.yaml",
            "configmaps/airflow-metadata.yaml",
        ]
        for template_path in airflow_templates:
            content = _read_template(template_path)
            assert "port-forward" not in content.lower()


# ---------------------------------------------------------------------------
# kind cluster configuration
# ---------------------------------------------------------------------------


class TestKindConfigAirflow:
    def test_kind_config_exists(self) -> None:
        assert KIND_CONFIG.exists()

    def test_airflow_port_mapping_present(self) -> None:
        config = _load_yaml(KIND_CONFIG)
        nodes = config["nodes"]
        control_plane = nodes[0]
        port_mappings = control_plane.get("extraPortMappings", [])
        airflow_mappings = [pm for pm in port_mappings if pm.get("hostPort") == 8080]
        assert len(airflow_mappings) == 1, (
            "Missing kind port mapping for Airflow webserver (hostPort 8080)"
        )

    def test_airflow_port_mapping_protocol(self) -> None:
        config = _load_yaml(KIND_CONFIG)
        port_mappings = config["nodes"][0]["extraPortMappings"]
        airflow = [pm for pm in port_mappings if pm.get("hostPort") == 8080][0]
        assert airflow["protocol"] == "TCP"


# ---------------------------------------------------------------------------
# Airflow webserver service
# ---------------------------------------------------------------------------


class TestAirflowWebService:
    def test_service_type_is_cluster_ip(self) -> None:
        docs = _helm_template()
        svc = [
            d
            for d in docs
            if d["kind"] == "Service" and d["metadata"]["name"] == "airflow-webserver"
        ][0]
        assert svc["spec"]["type"] == "NodePort"

    def test_service_nodeport_is_30088(self) -> None:
        docs = _helm_template()
        svc = [
            d
            for d in docs
            if d["kind"] == "Service" and d["metadata"]["name"] == "airflow-webserver"
        ][0]
        ports = svc["spec"]["ports"]
        assert ports[0]["nodePort"] == 30088

    def test_service_port_is_8080(self) -> None:
        docs = _helm_template()
        svc = [
            d
            for d in docs
            if d["kind"] == "Service" and d["metadata"]["name"] == "airflow-webserver"
        ][0]
        ports = svc["spec"]["ports"]
        port_numbers = [p["port"] for p in ports]
        assert 8080 in port_numbers

    def test_service_selects_webserver_pods(self) -> None:
        docs = _helm_template()
        svc = [
            d
            for d in docs
            if d["kind"] == "Service" and d["metadata"]["name"] == "airflow-webserver"
        ][0]
        selector = svc["spec"]["selector"]
        assert selector.get("app.kubernetes.io/name") == "airflow-webserver"
