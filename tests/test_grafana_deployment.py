"""Validate Grafana deployment configuration (TASK-085).

Tests verify Docker Compose service definition, provisioning files,
and monitoring documentation without requiring a running Docker daemon.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
MONITORING_DIR = REPO_ROOT / "monitoring"
GRAFANA_DATASOURCES = MONITORING_DIR / "grafana" / "datasources"
GRAFANA_DASHBOARDS = MONITORING_DIR / "grafana" / "dashboards"


def _load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_compose() -> dict[str, Any]:
    return _load_yaml(COMPOSE_FILE)  # type: ignore[no-any-return]


class TestGrafanaComposeService:
    def test_grafana_service_defined(self) -> None:
        compose = _load_compose()
        assert "grafana" in compose["services"]

    def test_grafana_uses_official_image(self) -> None:
        compose = _load_compose()
        image = compose["services"]["grafana"]["image"]
        assert image.startswith("grafana/grafana:")

    def test_grafana_exposes_port_3000(self) -> None:
        compose = _load_compose()
        ports = compose["services"]["grafana"]["ports"]
        assert any("3000" in str(p) for p in ports)

    def test_grafana_has_admin_env_vars(self) -> None:
        compose = _load_compose()
        env = compose["services"]["grafana"]["environment"]
        assert "GF_SECURITY_ADMIN_USER" in env
        assert "GF_SECURITY_ADMIN_PASSWORD" in env

    def test_grafana_mounts_provisioning_volumes(self) -> None:
        compose = _load_compose()
        volumes = compose["services"]["grafana"]["volumes"]
        volume_str = " ".join(str(v) for v in volumes)
        assert "datasources" in volume_str
        assert "dashboards" in volume_str

    def test_grafana_depends_on_prometheus(self) -> None:
        compose = _load_compose()
        deps = compose["services"]["grafana"]["depends_on"]
        assert "prometheus" in deps

    def test_grafana_has_healthcheck(self) -> None:
        compose = _load_compose()
        assert "healthcheck" in compose["services"]["grafana"]

    def test_grafana_on_platform_network(self) -> None:
        compose = _load_compose()
        networks = compose["services"]["grafana"]["networks"]
        assert "platform" in networks

    def test_grafana_data_volume_declared(self) -> None:
        compose = _load_compose()
        assert "grafana_data" in compose["volumes"]


class TestGrafanaProvisioningFiles:
    def test_datasource_file_exists(self) -> None:
        assert (GRAFANA_DATASOURCES / "prometheus.yml").exists()

    def test_dashboard_provisioning_exists(self) -> None:
        assert (GRAFANA_DASHBOARDS / "dashboard.yml").exists()

    def test_datasource_points_to_prometheus(self) -> None:
        ds = _load_yaml(GRAFANA_DATASOURCES / "prometheus.yml")
        sources = ds["datasources"]
        assert len(sources) >= 1
        prom = sources[0]
        assert prom["type"] == "prometheus"
        assert prom["url"] == "http://prometheus:9090"
        assert prom["isDefault"] is True
        assert prom["uid"] == "prometheus"

    def test_dashboard_provider_points_to_correct_path(self) -> None:
        dash = _load_yaml(GRAFANA_DASHBOARDS / "dashboard.yml")
        providers = dash["providers"]
        assert len(providers) >= 1
        assert "/etc/grafana/provisioning/dashboards" in providers[0]["options"]["path"]


class TestMonitoringDocumentation:
    def test_readme_mentions_grafana(self) -> None:
        readme = (MONITORING_DIR / "README.md").read_text(encoding="utf-8")
        assert "Grafana" in readme
        assert "TASK-085" in readme

    def test_readme_documents_local_access(self) -> None:
        readme = (MONITORING_DIR / "README.md").read_text(encoding="utf-8")
        assert "localhost:3000" in readme
