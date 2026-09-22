"""Regression tests for application container image build definitions (TASK-K8S-FIX-002).

Catches the class of regression where Kubernetes references an application
image that the repository has no reproducible way to build.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

DOCKERFILE = REPO_ROOT / "Dockerfile"
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build-local-images.sh"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"

DEPLOYMENTS_DIR = REPO_ROOT / "kubernetes" / "deployments"
HELM_VALUES = REPO_ROOT / "helm" / "ai-data-platform" / "values.yaml"

APPLICATION_SERVICES = [
    "ingestion",
    "processor",
    "raw-writer",
    "lake-writer",
    "warehouse-loader",
    "api",
]

EXPECTED_ENTRYPOINTS: dict[str, list[str]] = {
    "ingestion": ["python", "-m", "services.ingestion"],
    "processor": ["python", "-m", "services.processor"],
    "raw-writer": ["python", "-m", "services.raw-writer.consumer"],
    "lake-writer": ["python", "-m", "services.lake-writer.consumer"],
    "warehouse-loader": ["python", "-m", "services.warehouse-loader.runner"],
    "api": ["python", "-m", "services.api"],
}

IMAGE_REGISTRY = "ai-data-platform"
IMAGE_TAG = "dev"


def _load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _k8s_image(service_name: str) -> str:
    return f"{IMAGE_REGISTRY}/{service_name}:{IMAGE_TAG}"


class TestDockerfileExists:
    def test_dockerfile_exists(self) -> None:
        assert DOCKERFILE.exists(), "Dockerfile not found at repository root"

    def test_dockerfile_uses_build_arg(self) -> None:
        content = DOCKERFILE.read_text(encoding="utf-8")
        assert "SERVICE_MODULE" in content, (
            "Dockerfile must use SERVICE_MODULE build arg for multi-service support"
        )

    def test_dockerfile_copies_source_tree(self) -> None:
        content = DOCKERFILE.read_text(encoding="utf-8")
        for directory in ["services/", "libs/", "warehouse/"]:
            assert directory in content, f"Dockerfile must copy {directory} for imports to resolve"

    def test_dockerfile_installs_requirements(self) -> None:
        content = DOCKERFILE.read_text(encoding="utf-8")
        assert "requirements.txt" in content, "Dockerfile must install root requirements.txt"


class TestBuildScriptExists:
    def test_build_script_exists(self) -> None:
        assert BUILD_SCRIPT.exists(), f"build script not found at {BUILD_SCRIPT}"

    def test_build_script_references_all_services(self) -> None:
        content = BUILD_SCRIPT.read_text(encoding="utf-8")
        for service in APPLICATION_SERVICES:
            assert service in content, f"build script missing service: {service}"

    def test_build_script_references_dockerfile(self) -> None:
        content = BUILD_SCRIPT.read_text(encoding="utf-8")
        assert "Dockerfile" in content

    def test_build_script_uses_correct_registry(self) -> None:
        content = BUILD_SCRIPT.read_text(encoding="utf-8")
        assert IMAGE_REGISTRY in content, f"build script must use image registry '{IMAGE_REGISTRY}'"


class TestDockerignoreExists:
    def test_dockerignore_exists(self) -> None:
        assert DOCKERIGNORE.exists(), ".dockerignore not found at repository root"

    def test_dockerignore_excludes_tests(self) -> None:
        content = DOCKERIGNORE.read_text(encoding="utf-8")
        assert "tests" in content, ".dockerignore should exclude tests/"


class TestBuildDefinitionsCoverAllK8sImages:
    """Every application image referenced by K8s must have a build definition."""

    def _k8s_application_images(self) -> dict[str, str]:
        images = {}
        for deployment_file in DEPLOYMENTS_DIR.glob("*-deployment.yaml"):
            manifest = _load_yaml(deployment_file)
            if manifest is None:
                continue
            containers = (
                manifest.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
            )
            for container in containers:
                image = container.get("image", "")
                if image.startswith(f"{IMAGE_REGISTRY}/"):
                    service_name = image.split("/")[1].split(":")[0]
                    images[service_name] = image
        return images

    def test_all_k8s_images_have_build_definitions(self) -> None:
        k8s_images = self._k8s_application_images()
        for service in APPLICATION_SERVICES:
            assert service in k8s_images, f"Service '{service}' not found in K8s deployments"

        build_content = BUILD_SCRIPT.read_text(encoding="utf-8")
        for service, image in k8s_images.items():
            assert service in build_content, (
                f"K8s references image '{image}' but build script has no "
                f"build definition for service '{service}'"
            )

    def test_no_orphan_build_definitions(self) -> None:
        k8s_images = self._k8s_application_images()
        for service in APPLICATION_SERVICES:
            assert service in k8s_images, (
                f"Build script defines '{service}' but no K8s deployment uses it"
            )


class TestImageNameAlignment:
    """Image names must be consistent across build config, K8s, and Helm."""

    def test_k8s_deployment_images_match_expected(self) -> None:
        for service in APPLICATION_SERVICES:
            deployment_file = DEPLOYMENTS_DIR / f"{service}-deployment.yaml"
            manifest = _load_yaml(deployment_file)
            container = manifest["spec"]["template"]["spec"]["containers"][0]
            actual = container["image"]
            expected = _k8s_image(service)
            assert actual == expected, f"K8s {service} image '{actual}' != expected '{expected}'"

    def test_helm_values_images_match_expected(self) -> None:
        values = _load_yaml(HELM_VALUES)
        images = values["images"]

        helm_service_keys = {
            "ingestion": "ingestion",
            "processor": "processor",
            "raw-writer": "rawWriter",
            "lake-writer": "lakeWriter",
            "warehouse-loader": "warehouseLoader",
            "api": "api",
        }

        for service, helm_key in helm_service_keys.items():
            entry = images[helm_key]
            actual_repo = entry["repository"]
            actual_tag = entry["tag"]
            expected_repo = f"{IMAGE_REGISTRY}/{service}"
            assert actual_repo == expected_repo, (
                f"Helm {helm_key} repository '{actual_repo}' != '{expected_repo}'"
            )
            assert actual_tag == IMAGE_TAG, f"Helm {helm_key} tag '{actual_tag}' != '{IMAGE_TAG}'"

    def test_build_script_image_names_match_k8s(self) -> None:
        content = BUILD_SCRIPT.read_text(encoding="utf-8")
        assert IMAGE_REGISTRY in content, f"Build script must reference registry '{IMAGE_REGISTRY}'"
        assert "IMAGE_REGISTRY" in content, "Build script must use IMAGE_REGISTRY variable"
        for service in APPLICATION_SERVICES:
            assert service in content, (
                f"Build script missing service '{service}' needed to produce "
                f"image matching K8s: {_k8s_image(service)}"
            )


class TestServiceEntrypoints:
    """K8s commands must correspond to actual Python modules in the source tree."""

    def test_k8s_commands_match_expected_entrypoints(self) -> None:
        for service in APPLICATION_SERVICES:
            deployment_file = DEPLOYMENTS_DIR / f"{service}-deployment.yaml"
            manifest = _load_yaml(deployment_file)
            container = manifest["spec"]["template"]["spec"]["containers"][0]
            actual_command = container["command"]
            expected = EXPECTED_ENTRYPOINTS[service]
            assert actual_command == expected, (
                f"{service} K8s command {actual_command} != expected {expected}"
            )

    def test_entrypoint_modules_exist_in_source_tree(self) -> None:
        for service, command in EXPECTED_ENTRYPOINTS.items():
            module_path = command[2]
            parts = module_path.split(".")
            package_dir = REPO_ROOT / "/".join(parts[:-1])
            assert package_dir.is_dir(), (
                f"Service '{service}' entrypoint module directory '{package_dir}' does not exist"
            )

    def test_build_script_modules_match_k8s_commands(self) -> None:
        content = BUILD_SCRIPT.read_text(encoding="utf-8")
        for service, command in EXPECTED_ENTRYPOINTS.items():
            module = command[2]
            assert module in content, (
                f"Build script missing module '{module}' for service '{service}'"
            )


class TestBuildWorkflowDocumentation:
    """The documented workflow must reference building images before loading."""

    K8S_README = REPO_ROOT / "kubernetes" / "README.md"

    def test_k8s_readme_references_build_script(self) -> None:
        content = self.K8S_README.read_text(encoding="utf-8")
        assert "build-local-images" in content, (
            "kubernetes/README.md must reference scripts/build-local-images.sh"
        )

    def test_k8s_readme_documents_build_before_load(self) -> None:
        content = self.K8S_README.read_text(encoding="utf-8")
        build_pos = content.find("build-local-images")
        load_pos = content.find("kind-cluster.sh load")
        assert build_pos >= 0, "README must document image building"
        assert load_pos >= 0, "README must document kind image loading"
        assert build_pos < load_pos, "README must document building images BEFORE loading into kind"

    def test_k8s_readme_lists_all_application_images(self) -> None:
        content = self.K8S_README.read_text(encoding="utf-8")
        for service in APPLICATION_SERVICES:
            assert f"{IMAGE_REGISTRY}/{service}" in content, (
                f"README missing image reference for {service}"
            )


class TestRuntimeImportChains:
    """Verify that services can import their dependencies at runtime.

    Catches the class of failure where a service crashes at startup due to
    missing dependencies or unnecessary import coupling (e.g., ingestion
    failing because libs.observability eagerly imports psycopg2).
    """

    def test_ingestion_can_import_observability_without_psycopg2(self) -> None:
        """Ingestion should not require psycopg2 to import observability modules.

        Regression: libs.observability.__init__ used to eagerly import
        health_persistence which requires psycopg2, causing ingestion to
        crash with ModuleNotFoundError even though ingestion doesn't use
        health persistence.
        """
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; "
                "sys.modules['psycopg2'] = None; "
                "sys.modules['psycopg2.extras'] = None; "
                "from libs.observability import SourceHealthTracker, create_prometheus_registry, setup_opentelemetry; "
                "assert SourceHealthTracker is not None; "
                "assert create_prometheus_registry is not None; "
                "assert setup_opentelemetry is not None; "
                "print('OK')",
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Import failed without psycopg2:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_health_persistence_not_in_observability_init(self) -> None:
        """health_persistence symbols should not be in libs.observability.__all__.

        This prevents accidental eager imports that force all services to
        have psycopg2 even if they only need Kafka metrics.
        """
        import libs.observability

        all_symbols = libs.observability.__all__
        health_persistence_symbols = [
            "HealthPersistenceConfig",
            "HealthWriteResult",
            "IngestionHealthResultReader",
            "IngestionHealthResultRow",
            "IngestionHealthResultWriter",
        ]
        for symbol in health_persistence_symbols:
            assert symbol not in all_symbols, (
                f"{symbol} should not be in libs.observability.__all__ — "
                "import directly from libs.observability.health_persistence"
            )
