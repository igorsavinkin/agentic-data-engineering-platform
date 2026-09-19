"""Validate Grafana Kafka & Processing dashboard JSON (TASK-088).

Tests verify the dashboard JSON structure, panel definitions, and that
PromQL queries reference real metrics exposed by the platform.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_JSON = REPO_ROOT / "monitoring" / "grafana" / "dashboards" / "kafka-processing.json"
HELM_DASHBOARD_JSON = (
    REPO_ROOT / "helm" / "ai-data-platform" / "dashboards" / "kafka-processing.json"
)

KNOWN_METRICS = {
    "kafka_events_consumed_total",
    "kafka_events_processed_total",
    "events_invalid_total",
    "kafka_consumer_errors_total",
    "kafka_processing_errors_total",
    "kafka_dead_letter_events_total",
    "kafka_lag_errors_total",
    "ingestion_events_total",
    "ingestion_errors_total",
    "processor_events_processed_total",
    "processor_events_valid_total",
    "processor_events_invalid_total",
    "processor_processing_seconds",
    "processor_batches_total",
    "processor_batch_records_total",
}

PANEL_TYPES = {
    "timeseries",
    "stat",
    "gauge",
    "graph",
    "table",
    "bargauge",
    "heatmap",
    "histogram",
    "piechart",
    "status-history",
    "text",
}

PROMQL_FUNCTIONS = {
    "rate",
    "sum",
    "avg",
    "min",
    "max",
    "count",
    "histogram_quantile",
    "increase",
    "irate",
    "delta",
    "deriv",
    "predict_linear",
    "label_replace",
    "label_join",
    "abs",
    "ceil",
    "floor",
    "round",
    "clamp_min",
    "clamp_max",
    "by",
    "without",
    "on",
    "ignoring",
    "group_left",
    "group_right",
    "bool",
    "offset",
}


def _load_dashboard(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)  # type: ignore[no-any-return]


def _extract_metric_names(expr: str) -> set[str]:
    raw = set(re.findall(r"[a-zA-Z_:][a-zA-Z0-9_:]*(?=\s*[\[{(])", expr))
    return raw - PROMQL_FUNCTIONS


class TestDashboardFileExists:
    def test_compose_dashboard_exists(self) -> None:
        assert DASHBOARD_JSON.exists()

    def test_helm_dashboard_exists(self) -> None:
        assert HELM_DASHBOARD_JSON.exists()

    def test_both_dashboards_are_identical(self) -> None:
        compose = DASHBOARD_JSON.read_text(encoding="utf-8")
        helm = HELM_DASHBOARD_JSON.read_text(encoding="utf-8")
        assert compose == helm


class TestDashboardStructure:
    def test_valid_json(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        assert isinstance(dashboard, dict)

    def test_required_top_level_fields(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        assert "schemaVersion" in dashboard
        assert "panels" in dashboard
        assert "title" in dashboard
        assert "uid" in dashboard

    def test_schema_version(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        assert dashboard["schemaVersion"] == 39

    def test_uid_is_set(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        assert dashboard["uid"] == "ai-data-platform-kafka"

    def test_title_contains_kafka(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        assert "Kafka" in dashboard["title"]

    def test_has_minimum_panel_count(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        assert len(dashboard["panels"]) >= 10

    def test_not_editable(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        assert dashboard["editable"] is False

    def test_has_kafka_tag(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        assert "kafka" in dashboard.get("tags", [])


class TestPanelDefinitions:
    def test_every_panel_has_title(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        for panel in dashboard["panels"]:
            assert "title" in panel, f"Panel missing title: {panel}"

    def test_every_panel_has_valid_type(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        for panel in dashboard["panels"]:
            assert panel["type"] in PANEL_TYPES, f"Unknown panel type: {panel['type']}"

    def test_every_panel_has_targets(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        for panel in dashboard["panels"]:
            assert "targets" in panel, f"Panel '{panel['title']}' missing targets"
            assert len(panel["targets"]) >= 1

    def test_every_panel_has_datasource(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        for panel in dashboard["panels"]:
            assert "datasource" in panel, f"Panel '{panel['title']}' missing datasource"
            ds = panel["datasource"]
            assert ds["type"] == "prometheus"
            assert ds["uid"] == "prometheus"

    def test_every_target_has_expr(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        for panel in dashboard["panels"]:
            for target in panel["targets"]:
                assert "expr" in target, f"Panel '{panel['title']}' target missing expr"
                assert len(target["expr"]) > 0

    def test_panels_have_grid_positions(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        for panel in dashboard["panels"]:
            assert "gridPos" in panel, f"Panel '{panel['title']}' missing gridPos"
            gp = panel["gridPos"]
            assert all(k in gp for k in ("h", "w", "x", "y"))


class TestPromQLReferencesRealMetrics:
    def test_all_metric_names_are_known(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        for panel in dashboard["panels"]:
            for target in panel["targets"]:
                expr = target["expr"]
                referenced = _extract_metric_names(expr)
                for metric in referenced:
                    base = metric.replace("_bucket", "").replace("_count", "").replace("_sum", "")
                    assert base in KNOWN_METRICS, (
                        f"Panel '{panel['title']}' references unknown metric "
                        f"'{metric}' in expr: {expr}"
                    )

    def test_no_histogram_quantile_queries(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        for panel in dashboard["panels"]:
            for target in panel["targets"]:
                assert "histogram_quantile" not in target["expr"], (
                    f"Panel '{panel['title']}' uses histogram_quantile but all "
                    f"platform latency metrics are summaries (no _bucket series)"
                )


class TestDashboardCoversKafkaDimensions:
    def test_covers_consumer_throughput(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        titles = [p["title"].lower() for p in dashboard["panels"]]
        assert any("consumer" in t and "throughput" in t for t in titles)

    def test_covers_lag(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        titles = [p["title"].lower() for p in dashboard["panels"]]
        assert any("lag" in t for t in titles)

    def test_covers_errors(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        titles = [p["title"].lower() for p in dashboard["panels"]]
        assert any("error" in t for t in titles)

    def test_covers_latency(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        titles = [p["title"].lower() for p in dashboard["panels"]]
        assert any("latency" in t for t in titles)

    def test_covers_dead_letter_queue(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        titles = [p["title"].lower() for p in dashboard["panels"]]
        assert any("dead letter" in t or "dlq" in t for t in titles)

    def test_covers_ingestion(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        titles = [p["title"].lower() for p in dashboard["panels"]]
        assert any("ingestion" in t for t in titles)
