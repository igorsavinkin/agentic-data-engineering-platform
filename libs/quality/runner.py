"""Quality-check suite runner.

Executes a sequence of quality checks against a Polars DataFrame and
produces an aggregated ``QualitySuiteResult``.

Design decisions (TASK-056):
    - The runner is deterministic: checks execute in order, no parallelism.
    - Each check receives the same DataFrame — the runner does not mutate it.
    - A failing check does not prevent subsequent checks from running.
    - No Airflow or persistence dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

import polars as pl

from libs.quality.models import QualityCheck, QualityResult, QualitySuiteResult


@dataclass(frozen=True)
class QualitySuite:
    """An ordered collection of quality checks to run together.

    Attributes
    ----------
    name:
        Suite identifier for logging and persistence.
    checks:
        Ordered sequence of checks to execute.
    """

    name: str
    checks: Sequence[QualityCheck]

    def run(self, df: pl.DataFrame) -> QualitySuiteResult:
        """Execute all checks against the DataFrame and return aggregated results."""
        started_at = datetime.now(timezone.utc)
        results: list[QualityResult] = []
        for check in self.checks:
            result = check.run(df)
            results.append(result)
        finished_at = datetime.now(timezone.utc)
        return QualitySuiteResult(
            results=tuple(results),
            started_at=started_at,
            finished_at=finished_at,
        )


def run_checks(
    df: pl.DataFrame,
    checks: Sequence[QualityCheck],
    *,
    suite_name: str = "default",
) -> QualitySuiteResult:
    """Convenience function to run a sequence of checks without building a suite.

    Parameters
    ----------
    df:
        Polars DataFrame to check.
    checks:
        Quality checks to execute in order.
    suite_name:
        Optional suite identifier.

    Returns
    -------
    QualitySuiteResult
        Aggregated results from all checks.
    """
    suite = QualitySuite(name=suite_name, checks=checks)
    return suite.run(df)
