"""Structured result report for load-test runs (TASK-108).

Produces a JSON-serializable report containing test configuration,
summary metrics, and environment information.  The report format is
stable and machine-readable for downstream analysis.
"""

from __future__ import annotations

import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path


def build_report(
    settings_dict: dict,
    metrics_summary: dict,
    run_id: str,
) -> dict:
    """Assemble a structured load-test result report.

    Parameters
    ----------
    settings_dict:
        The load-test configuration as a plain dict (from settings.model_dump()).
    metrics_summary:
        The metrics summary from ``MetricsCollector.get_summary()``.
    run_id:
        Unique identifier for this run.

    Returns
    -------
    dict
        A JSON-serializable report.
    """
    return {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "configuration": settings_dict,
        "results": metrics_summary,
    }


def write_report(report: dict, output_path: str) -> Path:
    """Write a report to disk as formatted JSON.

    Returns the resolved path for logging.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path.resolve()
