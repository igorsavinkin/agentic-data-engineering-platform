"""Reusable data-quality checks, result models, and persistence.

Provides typed, deterministic quality checks that operate on Polars
DataFrames (TASK-056), plus PostgreSQL persistence with replay-safe
identity and query APIs (TASK-057).

Public API:
    - ``QualityResult``, ``QualitySuiteResult`` — result models.
    - ``CheckSeverity``, ``CheckStatus`` — enums.
    - ``QualityCheck`` — structural protocol.
    - ``QualitySuite``, ``run_checks`` — suite runner.
    - ``RequiredFieldsCheck``, ``PriceValidityCheck``, ``AllowedValuesCheck``,
      ``DuplicateCheck``, ``FreshnessCheck`` — concrete checks.
    - ``QualityPersistenceConfig``, ``QualityResultWriter``,
      ``QualityResultReader``, ``make_replay_key`` — persistence (TASK-057).
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

_PERSISTENCE_NAMES = frozenset(
    {
        "QualityPersistenceConfig",
        "QualityResultReader",
        "QualityResultRow",
        "QualityResultWriter",
        "WriteResult",
        "make_replay_key",
    }
)


def __getattr__(name: str) -> object:
    if name in _PERSISTENCE_NAMES:
        from libs.quality import persistence

        attr = getattr(persistence, name)
        globals()[name] = attr
        return attr
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AllowedValuesCheck",
    "CheckSeverity",
    "CheckStatus",
    "DuplicateCheck",
    "FreshnessCheck",
    "PriceValidityCheck",
    "QualityCheck",
    "QualityPersistenceConfig",
    "QualityResult",
    "QualityResultReader",
    "QualityResultRow",
    "QualityResultWriter",
    "QualitySuite",
    "QualitySuiteResult",
    "RequiredFieldsCheck",
    "WriteResult",
    "make_replay_key",
    "run_checks",
]
