"""Validate Helm chart structure and rendering (TASK-083).

Tests run without a live cluster or Helm binary — they validate chart
files, rendered YAML structure, and value semantics using PyYAML.
Helm CLI tests are included but skipped gracefully when helm is absent.
"""

from __future__ import annotations

import base64
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CHART_DIR = REPO_ROOT / "helm" / "ai-data-platform"
CHART_YAML = CHART_DIR / "Chart.yaml"
VALUES_YAML = CHART_DIR / "values.yaml"
VALUES_LOCAL = CHART_DIR / "values-local.yaml"
VALUES_PROD = CHART_DIR / "values-production.yaml"
TEMPLATES_DIR = CHART_DIR / "templates"
README = CHART_DIR / "README.md"

HELM_BIN = shutil.which("helm")


def _load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _helm_template(
    values_files: list[Path] | None = None, extra_args: list[str] | None = None
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


def _helm_lint(values_files: list[Path] | None = None) -> str:
    if not HELM_BIN:
        pytest.skip("helm binary not available")
    cmd = [HELM_BIN, "lint", str(CHART_DIR)]
    for vf in values_files or []:
        cmd.extend(["-f", str(vf)])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return result.stdout + result.stderr


class TestChartStructure:
    def test_chart_yaml_exists(self) -> None:
        assert CHART_YAML.exists()

    def test_chart_yaml_required_fields(self) -> None:
        chart = _load_yaml(CHART_YAML)
        assert chart["apiVersion"] == "v2"
        assert chart["name"] == "ai-data-platform"
        assert chart["type"] == "application"
        assert "version" in chart
        assert "appVersion" in chart

    def test_values_yaml_exists(self) -> None:
        assert VALUES_YAML.exists()

    def test_values_yaml_required_sections(self) -> None:
        values = _load_yaml(VALUES_YAML)
        for section in [
            "global",
            "images",
            "platform",
            "database",
            "secrets",
            "ingestion",
            "processor",
            "rawWriter",
            "lakeWriter",
            "warehouseLoader",
            "warehouse",
            "api",
            "kafka",
            "minio",
            "postgresql",
            "airflow",
            "ingress",
            "hpa",
            "networkPolicy",
            "prometheus",
            "grafana",
        ]:
            assert section in values, f"Missing values section: {section}"

    def test_templates_directory_exists(self) -> None:
        assert TEMPLATES_DIR.is_dir()

    def test_helpers_template_exists(self) -> None:
        assert (TEMPLATES_DIR / "_helpers.tpl").exists()

    def test_expected_template_files_exist(self) -> None:
        expected = [
            "namespace.yaml",
            "ingress.yaml",
            "hpa.yaml",
            "networkpolicy.yaml",
            "configmaps/platform-config.yaml",
            "configmaps/database-config.yaml",
            "configmaps/airflow-metadata.yaml",
            "secrets/minio-credentials.yaml",
            "secrets/database-credentials.yaml",
            "secrets/ingestion-api-keys.yaml",
            "secrets/airflow-credentials.yaml",
            "deployments/ingestion.yaml",
            "deployments/processor.yaml",
            "deployments/raw-writer.yaml",
            "deployments/lake-writer.yaml",
            "deployments/warehouse-loader.yaml",
            "deployments/api.yaml",
            "deployments/kafka.yaml",
            "deployments/airflow-scheduler.yaml",
            "deployments/airflow-webserver.yaml",
            "services/api.yaml",
            "services/kafka.yaml",
            "services/minio.yaml",
            "services/postgresql.yaml",
            "services/airflow-webserver.yaml",
            "statefulsets/minio.yaml",
            "statefulsets/postgresql.yaml",
            "jobs/kafka-topics.yaml",
            "jobs/warehouse-migration.yaml",
            "jobs/airflow-init.yaml",
            "monitoring/prometheus-configmap.yaml",
            "monitoring/prometheus-deployment.yaml",
            "monitoring/prometheus-service.yaml",
            "monitoring/grafana-deployment.yaml",
            "monitoring/grafana-service.yaml",
            "monitoring/grafana-configmap.yaml",
            "monitoring/grafana-secret.yaml",
            "monitoring/grafana-dashboards-configmap.yaml",
        ]
        for template in expected:
            path = TEMPLATES_DIR / template
            assert path.exists(), f"Missing template: {template}"

    def test_helmignore_exists(self) -> None:
        assert (CHART_DIR / ".helmignore").exists()

    def test_readme_exists(self) -> None:
        assert README.exists()


class TestEnvironmentValues:
    def test_local_values_exist(self) -> None:
        assert VALUES_LOCAL.exists()

    def test_production_values_exist(self) -> None:
        assert VALUES_PROD.exists()

    def test_local_values_set_environment(self) -> None:
        local = _load_yaml(VALUES_LOCAL)
        assert local["platform"]["environment"] == "development"

    def test_production_values_set_environment(self) -> None:
        prod = _load_yaml(VALUES_PROD)
        assert prod["platform"]["environment"] == "production"

    def test_local_values_have_reduced_resources(self) -> None:
        base = _load_yaml(VALUES_YAML)
        local = _load_yaml(VALUES_LOCAL)
        base_cpu = base["processor"]["resources"]["requests"]["cpu"]
        local_cpu = local["processor"]["resources"]["requests"]["cpu"]
        assert int(local_cpu.replace("m", "")) <= int(base_cpu.replace("m", ""))

    def test_production_enables_optional_resources(self) -> None:
        prod = _load_yaml(VALUES_PROD)
        assert prod["ingress"]["enabled"] is True
        assert prod["hpa"]["enabled"] is True
        assert prod["networkPolicy"]["enabled"] is True

    def test_production_has_higher_replicas(self) -> None:
        base = _load_yaml(VALUES_YAML)
        prod = _load_yaml(VALUES_PROD)
        assert prod["api"]["replicas"] >= base["api"]["replicas"]
        assert prod["processor"]["replicas"] >= base["processor"]["replicas"]


class TestDefaultSecretsArePlaceholders:
    def test_secrets_are_base64_placeholders(self) -> None:
        values = _load_yaml(VALUES_YAML)
        secrets = values["secrets"]
        placeholder_values = [
            secrets["minio"]["accessKey"],
            secrets["minio"]["secretKey"],
            secrets["database"]["password"],
            secrets["ingestion"]["bestbuyApiKey"],
        ]
        for encoded in placeholder_values:
            decoded = base64.b64decode(encoded).decode("utf-8")
            assert len(decoded) < 30, f"Secret looks too long to be a placeholder: {decoded[:5]}..."
            assert not decoded.startswith("prod-"), "Production secret in default values"
            assert not decoded.startswith("real-"), "Real secret in default values"

    def test_no_plaintext_passwords_in_values(self) -> None:
        content = VALUES_YAML.read_text(encoding="utf-8")
        suspicious = ["password:", "secret:", "api_key:", "apikey:"]
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern in suspicious:
                if pattern in stripped.lower():
                    value_part = stripped.split(":", 1)[1].strip()
                    try:
                        base64.b64decode(value_part)
                    except Exception:
                        pytest.fail(f"Possible plaintext secret in values.yaml: {stripped}")


class TestOptionalResourcesDisabledByDefault:
    def test_ingress_disabled(self) -> None:
        values = _load_yaml(VALUES_YAML)
        assert values["ingress"]["enabled"] is False

    def test_hpa_disabled(self) -> None:
        values = _load_yaml(VALUES_YAML)
        assert values["hpa"]["enabled"] is False

    def test_network_policy_disabled(self) -> None:
        values = _load_yaml(VALUES_YAML)
        assert values["networkPolicy"]["enabled"] is False

    def test_prometheus_disabled(self) -> None:
        values = _load_yaml(VALUES_YAML)
        assert values["prometheus"]["enabled"] is False

    def test_grafana_disabled(self) -> None:
        values = _load_yaml(VALUES_YAML)
        assert values["grafana"]["enabled"] is False


class TestHelmLint:
    def test_lint_default_values(self) -> None:
        output = _helm_lint()
        assert "0 chart(s) failed" in output

    def test_lint_local_values(self) -> None:
        output = _helm_lint([VALUES_LOCAL])
        assert "0 chart(s) failed" in output

    def test_lint_production_values(self) -> None:
        output = _helm_lint([VALUES_PROD])
        assert "0 chart(s) failed" in output


class TestHelmTemplate:
    def test_default_renders_27_resources(self) -> None:
        docs = _helm_template()
        assert len(docs) == 27

    def test_local_renders_27_resources(self) -> None:
        docs = _helm_template([VALUES_LOCAL])
        assert len(docs) == 27

    def test_production_renders_28_resources(self) -> None:
        docs = _helm_template([VALUES_PROD])
        assert len(docs) == 28

    def test_default_has_no_ing(self) -> None:
        docs = _helm_template()
        kinds = [d["kind"] for d in docs]
        assert "Ingress" not in kinds

    def test_default_has_no_hpa(self) -> None:
        docs = _helm_template()
        kinds = [d["kind"] for d in docs]
        assert "HorizontalPodAutoscaler" not in kinds

    def test_default_has_no_network_policy(self) -> None:
        docs = _helm_template()
        kinds = [d["kind"] for d in docs]
        assert "NetworkPolicy" not in kinds

    def test_production_has_ingress(self) -> None:
        docs = _helm_template([VALUES_PROD])
        kinds = [d["kind"] for d in docs]
        assert "Ingress" in kinds

    def test_production_has_hpa(self) -> None:
        docs = _helm_template([VALUES_PROD])
        kinds = [d["kind"] for d in docs]
        assert "HorizontalPodAutoscaler" in kinds

    def test_production_has_network_policy(self) -> None:
        docs = _helm_template([VALUES_PROD])
        kinds = [d["kind"] for d in docs]
        assert "NetworkPolicy" in kinds

    def test_all_deployments_have_resources(self) -> None:
        docs = _helm_template()
        deployments = [d for d in docs if d["kind"] == "Deployment"]
        assert len(deployments) == 9
        for dep in deployments:
            containers = dep["spec"]["template"]["spec"]["containers"]
            for container in containers:
                assert "resources" in container
                assert "requests" in container["resources"]
                assert "limits" in container["resources"]

    def test_all_deployments_have_probes(self) -> None:
        docs = _helm_template()
        deployments = [d for d in docs if d["kind"] == "Deployment"]
        for dep in deployments:
            containers = dep["spec"]["template"]["spec"]["containers"]
            for container in containers:
                assert "livenessProbe" in container
                assert "readinessProbe" in container

    def test_namespace_is_correct(self) -> None:
        docs = _helm_template()
        ns = [d for d in docs if d["kind"] == "Namespace"][0]
        assert ns["metadata"]["name"] == "ai-data-platform"

    def test_configmaps_present(self) -> None:
        docs = _helm_template()
        cms = [d for d in docs if d["kind"] == "ConfigMap"]
        names = {cm["metadata"]["name"] for cm in cms}
        assert "platform-config" in names
        assert "database-config" in names

    def test_secrets_present(self) -> None:
        docs = _helm_template()
        secrets = [d for d in docs if d["kind"] == "Secret"]
        assert len(secrets) == 4

    def test_hpa_targets_api_deployment(self) -> None:
        docs = _helm_template([VALUES_PROD])
        hpa = [d for d in docs if d["kind"] == "HorizontalPodAutoscaler"][0]
        assert hpa["spec"]["scaleTargetRef"]["name"] == "api"

    def test_ingress_routes_to_api_service(self) -> None:
        docs = _helm_template([VALUES_PROD])
        ingress = [d for d in docs if d["kind"] == "Ingress"][0]
        rules = ingress["spec"]["rules"]
        backend_service = rules[0]["http"]["paths"][0]["backend"]["service"]["name"]
        assert backend_service == "api"

    def test_local_environment_overrides_platform_value(self) -> None:
        docs = _helm_template([VALUES_LOCAL])
        cm = [
            d
            for d in docs
            if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "platform-config"
        ][0]
        assert cm["data"]["APP_ENVIRONMENT"] == "development"

    def test_production_environment_overrides_platform_value(self) -> None:
        docs = _helm_template([VALUES_PROD])
        cm = [
            d
            for d in docs
            if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "platform-config"
        ][0]
        assert cm["data"]["APP_ENVIRONMENT"] == "production"

    def test_default_has_no_grafana(self) -> None:
        docs = _helm_template()
        kinds_names = {(d["kind"], d["metadata"]["name"]) for d in docs}
        assert ("Deployment", "grafana") not in kinds_names
        assert ("Service", "grafana") not in kinds_names

    def test_grafana_renders_when_enabled(self) -> None:
        docs = _helm_template(extra_args=["--set", "grafana.enabled=true"])
        kinds = {d["kind"] for d in docs}
        assert "Deployment" in kinds
        grafana_deps = [
            d
            for d in docs
            if d["metadata"]["name"]
            in ("grafana", "grafana-provisioning", "grafana-credentials", "grafana-dashboards")
        ]
        names = {d["metadata"]["name"] for d in grafana_deps}
        assert "grafana" in names
        assert "grafana-provisioning" in names
        assert "grafana-credentials" in names
        assert "grafana-dashboards" in names

    def test_grafana_deployment_has_probes_and_resources(self) -> None:
        docs = _helm_template(extra_args=["--set", "grafana.enabled=true"])
        dep = [d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"] == "grafana"][
            0
        ]
        container = dep["spec"]["template"]["spec"]["containers"][0]
        assert "livenessProbe" in container
        assert "readinessProbe" in container
        assert "resources" in container
        assert container["image"].startswith("grafana/grafana:")

    def test_grafana_secret_contains_admin_credentials(self) -> None:
        docs = _helm_template(extra_args=["--set", "grafana.enabled=true"])
        secret = [
            d
            for d in docs
            if d["kind"] == "Secret" and d["metadata"]["name"] == "grafana-credentials"
        ][0]
        data = secret["data"]
        assert "admin-user" in data
        assert "admin-password" in data
        decoded_user = base64.b64decode(data["admin-user"]).decode("utf-8")
        assert decoded_user == "admin"

    def test_grafana_configmap_has_datasource(self) -> None:
        docs = _helm_template(extra_args=["--set", "grafana.enabled=true"])
        cm = [
            d
            for d in docs
            if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "grafana-provisioning"
        ][0]
        datasources = yaml.safe_load(cm["data"]["datasources.yml"])
        assert datasources["datasources"][0]["type"] == "prometheus"
        assert datasources["datasources"][0]["url"] == "http://prometheus:9090"
        assert datasources["datasources"][0]["uid"] == "prometheus"

    def test_grafana_dashboards_configmap_contains_dashboard_json(self) -> None:
        docs = _helm_template(extra_args=["--set", "grafana.enabled=true"])
        cm = [
            d
            for d in docs
            if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "grafana-dashboards"
        ][0]
        assert "platform-overview.json" in cm["data"]
        assert "data-quality.json" in cm["data"]
        assert "kafka-processing.json" in cm["data"]
        import json

        overview = json.loads(cm["data"]["platform-overview.json"])
        assert overview["uid"] == "ai-data-platform-overview"
        assert len(overview["panels"]) >= 1

        quality = json.loads(cm["data"]["data-quality.json"])
        assert quality["uid"] == "ai-data-platform-data-quality"
        assert len(quality["panels"]) >= 1

        kafka = json.loads(cm["data"]["kafka-processing.json"])
        assert kafka["uid"] == "ai-data-platform-kafka"
        assert len(kafka["panels"]) >= 1

    def test_grafana_deployment_mounts_dashboard_volume(self) -> None:
        docs = _helm_template(extra_args=["--set", "grafana.enabled=true"])
        dep = [d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"] == "grafana"][
            0
        ]
        spec = dep["spec"]["template"]["spec"]
        mount_names = [vm["name"] for vm in spec["containers"][0]["volumeMounts"]]
        volume_names = [v["name"] for v in spec["volumes"]]
        assert "dashboards" in mount_names
        assert "dashboards" in volume_names
        dash_vol = [v for v in spec["volumes"] if v["name"] == "dashboards"][0]
        assert dash_vol["configMap"]["name"] == "grafana-dashboards"


class TestHelmStatefulSets:
    def test_default_renders_minio_statefulset(self) -> None:
        docs = _helm_template()
        statefulsets = [d for d in docs if d["kind"] == "StatefulSet"]
        names = {ss["metadata"]["name"] for ss in statefulsets}
        assert "minio" in names

    def test_default_renders_postgresql_statefulset(self) -> None:
        docs = _helm_template()
        statefulsets = [d for d in docs if d["kind"] == "StatefulSet"]
        names = {ss["metadata"]["name"] for ss in statefulsets}
        assert "postgresql" in names

    def test_production_disables_statefulsets(self) -> None:
        docs = _helm_template([VALUES_PROD])
        statefulsets = [d for d in docs if d["kind"] == "StatefulSet"]
        assert len(statefulsets) == 0

    def test_minio_statefulset_has_correct_labels(self) -> None:
        docs = _helm_template()
        minio_ss = [
            d for d in docs if d["kind"] == "StatefulSet" and d["metadata"]["name"] == "minio"
        ][0]
        labels = minio_ss["metadata"]["labels"]
        assert labels["app.kubernetes.io/name"] == "minio"
        assert labels["app.kubernetes.io/part-of"] == "ai-data-platform"

    def test_postgresql_statefulset_has_correct_labels(self) -> None:
        docs = _helm_template()
        pg_ss = [
            d for d in docs if d["kind"] == "StatefulSet" and d["metadata"]["name"] == "postgresql"
        ][0]
        labels = pg_ss["metadata"]["labels"]
        assert labels["app.kubernetes.io/name"] == "postgresql"
        assert labels["app.kubernetes.io/part-of"] == "ai-data-platform"

    def test_statefulset_pod_labels_match_service_selectors(self) -> None:
        docs = _helm_template()
        services = {
            d["metadata"]["name"]: d
            for d in docs
            if d["kind"] == "Service" and d["metadata"]["name"] in ("minio", "postgresql")
        }
        statefulsets = {d["metadata"]["name"]: d for d in docs if d["kind"] == "StatefulSet"}
        for svc_name in ("minio", "postgresql"):
            selector = services[svc_name]["spec"]["selector"]
            pod_labels = statefulsets[svc_name]["spec"]["template"]["metadata"]["labels"]
            for key, value in selector.items():
                assert pod_labels.get(key) == value, f"{svc_name} pod label mismatch for {key}"

    def test_statefulsets_have_probes_and_resources(self) -> None:
        docs = _helm_template()
        statefulsets = [d for d in docs if d["kind"] == "StatefulSet"]
        for ss in statefulsets:
            container = ss["spec"]["template"]["spec"]["containers"][0]
            assert "livenessProbe" in container, f"{ss['metadata']['name']} missing livenessProbe"
            assert "readinessProbe" in container, f"{ss['metadata']['name']} missing readinessProbe"
            assert "resources" in container, f"{ss['metadata']['name']} missing resources"

    def test_statefulsets_use_secrets_not_plaintext(self) -> None:
        docs = _helm_template()
        statefulsets = [d for d in docs if d["kind"] == "StatefulSet"]
        for ss in statefulsets:
            container = ss["spec"]["template"]["spec"]["containers"][0]
            secret_envs = [
                e for e in container["env"] if "valueFrom" in e and "secretKeyRef" in e["valueFrom"]
            ]
            assert len(secret_envs) > 0, (
                f"{ss['metadata']['name']} should reference Secrets for credentials"
            )

    def test_statefulsets_have_volume_claim_templates(self) -> None:
        docs = _helm_template()
        statefulsets = {d["metadata"]["name"]: d for d in docs if d["kind"] == "StatefulSet"}
        for name in ("minio", "postgresql"):
            vcts = statefulsets[name]["spec"]["volumeClaimTemplates"]
            assert len(vcts) >= 1, f"{name} missing volumeClaimTemplates"
            assert "storage" in vcts[0]["spec"]["resources"]["requests"]

    def test_statefulsets_volume_mounts_match_vct_names(self) -> None:
        docs = _helm_template()
        statefulsets = {d["metadata"]["name"]: d for d in docs if d["kind"] == "StatefulSet"}
        for name in ("minio", "postgresql"):
            ss = statefulsets[name]
            container = ss["spec"]["template"]["spec"]["containers"][0]
            mount_names = {vm["name"] for vm in container.get("volumeMounts", [])}
            vct_names = {v["metadata"]["name"] for v in ss["spec"]["volumeClaimTemplates"]}
            assert mount_names == vct_names, (
                f"{name}: volumeMount names {mount_names} != volumeClaimTemplate names {vct_names}"
            )


class TestHelmWarehouseMigrationJob:
    def test_migration_job_renders(self) -> None:
        docs = _helm_template()
        jobs = [d for d in docs if d["kind"] == "Job"]
        job_names = {j["metadata"]["name"] for j in jobs}
        assert "warehouse-migration" in job_names

    def test_migration_job_command(self) -> None:
        docs = _helm_template()
        job = [
            d for d in docs if d["kind"] == "Job" and d["metadata"]["name"] == "warehouse-migration"
        ][0]
        container = job["spec"]["template"]["spec"]["containers"][0]
        assert container["command"] == ["python", "-m", "warehouse.migrations", "upgrade", "head"]

    def test_migration_job_image(self) -> None:
        docs = _helm_template()
        job = [
            d for d in docs if d["kind"] == "Job" and d["metadata"]["name"] == "warehouse-migration"
        ][0]
        container = job["spec"]["template"]["spec"]["containers"][0]
        assert container["image"] == "ai-data-platform/warehouse-migrations:dev"

    def test_migration_job_security_context(self) -> None:
        docs = _helm_template()
        job = [
            d for d in docs if d["kind"] == "Job" and d["metadata"]["name"] == "warehouse-migration"
        ][0]
        pod_sc = job["spec"]["template"]["spec"]["securityContext"]
        container_sc = job["spec"]["template"]["spec"]["containers"][0]["securityContext"]
        assert pod_sc.get("runAsNonRoot") is True
        assert pod_sc.get("seccompProfile", {}).get("type") == "RuntimeDefault"
        assert container_sc.get("allowPrivilegeEscalation") is False
        assert container_sc.get("capabilities", {}).get("drop") == ["ALL"]

    def test_migration_job_uses_database_config(self) -> None:
        docs = _helm_template()
        job = [
            d for d in docs if d["kind"] == "Job" and d["metadata"]["name"] == "warehouse-migration"
        ][0]
        container = job["spec"]["template"]["spec"]["containers"][0]
        configmap_envs = [
            e
            for e in container["env"]
            if "valueFrom" in e and "configMapKeyRef" in e.get("valueFrom", {})
        ]
        configmap_names = {e["valueFrom"]["configMapKeyRef"]["name"] for e in configmap_envs}
        assert "database-config" in configmap_names

    def test_migration_job_password_from_secret(self) -> None:
        docs = _helm_template()
        job = [
            d for d in docs if d["kind"] == "Job" and d["metadata"]["name"] == "warehouse-migration"
        ][0]
        container = job["spec"]["template"]["spec"]["containers"][0]
        pw_env = next(e for e in container["env"] if e["name"] == "WAREHOUSE_DB_PASSWORD")
        ref = pw_env["valueFrom"]["secretKeyRef"]
        assert ref["name"] == "database-credentials"
        assert ref["key"] == "db-password"

    def test_migration_job_has_resources(self) -> None:
        docs = _helm_template()
        job = [
            d for d in docs if d["kind"] == "Job" and d["metadata"]["name"] == "warehouse-migration"
        ][0]
        container = job["spec"]["template"]["spec"]["containers"][0]
        assert "resources" in container
        assert "requests" in container["resources"]
        assert "limits" in container["resources"]

    def test_migration_job_has_helm_hook_annotations(self) -> None:
        docs = _helm_template()
        job = [
            d for d in docs if d["kind"] == "Job" and d["metadata"]["name"] == "warehouse-migration"
        ][0]
        annotations = job["metadata"]["annotations"]
        assert "helm.sh/hook" in annotations
        hook = annotations["helm.sh/hook"]
        assert "post-install" in hook
        assert "pre-upgrade" in hook
        assert "pre-install" not in hook
        assert "helm.sh/hook-delete-policy" in annotations
        assert "before-hook-creation" in annotations["helm.sh/hook-delete-policy"]

    def test_migration_job_has_postgresql_readiness_initcontainer(self) -> None:
        docs = _helm_template()
        job = [
            d for d in docs if d["kind"] == "Job" and d["metadata"]["name"] == "warehouse-migration"
        ][0]
        init_containers = job["spec"]["template"]["spec"].get("initContainers", [])
        assert len(init_containers) >= 1
        wait = init_containers[0]
        assert wait["name"] == "wait-for-postgresql"
        assert "socket" in wait["command"][2]

    def test_migration_job_initcontainer_security_context(self) -> None:
        docs = _helm_template()
        job = [
            d for d in docs if d["kind"] == "Job" and d["metadata"]["name"] == "warehouse-migration"
        ][0]
        wait = job["spec"]["template"]["spec"]["initContainers"][0]
        sc = wait["securityContext"]
        assert sc.get("allowPrivilegeEscalation") is False
        assert sc.get("capabilities", {}).get("drop") == ["ALL"]

    def test_production_migration_image_not_dev(self) -> None:
        docs = _helm_template([VALUES_PROD])
        job = [
            d for d in docs if d["kind"] == "Job" and d["metadata"]["name"] == "warehouse-migration"
        ][0]
        container = job["spec"]["template"]["spec"]["containers"][0]
        assert not container["image"].endswith(":dev"), (
            f"production migration image should not use :dev tag, got {container['image']}"
        )
        assert "warehouse-migrations" in container["image"]
