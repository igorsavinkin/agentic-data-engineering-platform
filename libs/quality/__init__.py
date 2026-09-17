"""Reusable data-quality checks and result models.

Provides typed, deterministic quality checks that operate on Polars
DataFrames without persistence or Airflow dependencies (TASK-056).

Public API:
    - ``QualityResult``, ``QualitySuiteResult`` — result models.
    - ``CheckSeverity``, ``CheckStatus`` — enums.
    - ``QualityCheck`` — structural protocol.
    - ``QualitySuite``, ``run_checks`` — suite runner.
    - ``RequiredFieldsCheck``, ``PriceValidityCheck``, ``AllowedValuesCheck``,
      ``DuplicateCheck``, ``FreshnessCheck`` — concrete checks.
"""

from __future__ import annotations

from libs.quality.checks import (
    AllowedValuesCheck,
    DuplicateCheck,
    FreshnessCheck,
    PriceValidityCheck,
    RequiredFieldsCheck,
)
from libs.quality.models import (
    CheckSeverity,
    CheckStatus,
    QualityCheck,
    QualityResult,
    QualitySuiteResult,
)
from libs.quality.runner import QualitySuite, run_checks

__all__ = [
    "AllowedValuesCheck",
    "CheckSeverity",
    "CheckStatus",
    "DuplicateCheck",
    "FreshnessCheck",
    "PriceValidityCheck",
    "QualityCheck",
    "QualityResult",
    "QualitySuite",
    "QualitySuiteResult",
    "RequiredFieldsCheck",
    "run_checks",
]
