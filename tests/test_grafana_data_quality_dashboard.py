"""Validate Grafana data-quality dashboard JSON (TASK-087).

Tests verify the dashboard JSON structure, panel definitions, and that
PromQL queries reference real metrics exposed by the platform.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_JSON = REPO_ROOT / "monitoring" / "grafana" / "dashboards" / "data-quality.json"
HELM_DASHBOARD_JSON = REPO_ROOT / "helm" / "ai-data-platform" / "dashboards" / "data-quality.json"

KNOWN_METRICS = {
    "processor_events_valid_total",
    "processor_events_invalid_total",
    "processor_events_duplicate_total",
    "processor_events_failed_total",
    "events_invalid_total",
    "kafka_processing_errors_total",
    "kafka_dead_letter_events_total",
    "source_freshness_age_seconds",
    "source_fetch_attempts_total",
    "source_fetch_success_total",
    "source_fetch_failure_total",
    "source_malformed_records_total",
    "source_zero_record_fetches_total",
    "source_partial_failures_total",
    "source_retry_attempts_total",
    "source_records_collected_total",
    "source_records_emitted_total",
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
        assert dashboard["uid"] == "ai-data-platform-data-quality"

    def test_title_contains_data_quality(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        assert "Data Quality" in dashboard["title"]

    def test_has_minimum_panel_count(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        assert len(dashboard["panels"]) >= 10

    def test_not_editable(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        assert dashboard["editable"] is False

    def test_has_data_quality_tag(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        assert "data-quality" in dashboard.get("tags", [])


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
            assert len(panel["targets"]) >= 1, f"Panel '{panel['title']}' has no targets"

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

    def test_no_overlapping_panels(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        occupied: dict[tuple[int, int], str] = {}
        for panel in dashboard["panels"]:
            gp = panel["gridPos"]
            for dx in range(gp["w"]):
                for dy in range(gp["h"]):
                    pos = (gp["x"] + dx, gp["y"] + dy)
                    assert pos not in occupied, (
                        f"Panel '{panel['title']}' overlaps with "
                        f"'{occupied[pos]}' at grid position {pos}"
                    )
                    occupied[pos] = panel["title"]


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


class TestDashboardCoversQualityDimensions:
    def test_covers_validation(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        titles = [p["title"].lower() for p in dashboard["panels"]]
        assert any("valid" in t for t in titles)

    def test_covers_freshness(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        titles = [p["title"].lower() for p in dashboard["panels"]]
        assert any("freshness" in t for t in titles)

    def test_covers_deduplication(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        titles = [p["title"].lower() for p in dashboard["panels"]]
        assert any("dedup" in t or "duplicate" in t for t in titles)

    def test_covers_failures(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        titles = [p["title"].lower() for p in dashboard["panels"]]
        assert any("failure" in t or "failed" in t for t in titles)

    def test_covers_dead_letter_queue(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        titles = [p["title"].lower() for p in dashboard["panels"]]
        assert any("dead letter" in t or "dlq" in t for t in titles)

    def test_covers_source_quality(self) -> None:
        dashboard = _load_dashboard(DASHBOARD_JSON)
        titles = [p["title"].lower() for p in dashboard["panels"]]
        assert any("malformed" in t or "zero-record" in t for t in titles)
