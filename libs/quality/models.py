"""Core type definitions for the data-quality framework.

Provides the result model, severity/status enums, check protocol, and
suite-result aggregation used by all concrete quality checks.

Design decisions (TASK-056):
    - Frozen dataclasses for immutable results.
    - ``QualityCheck`` is a ``Protocol`` — structural typing, no forced
      inheritance. Any callable object with ``name`` and ``run()`` qualifies.
    - Result fields align with the ``data_quality_results`` warehouse table
      (``check_name``, ``severity``, ``passed``, ``message``, ``checked_at``)
      plus analytical fields (``records_checked``, ``failed_records``,
      ``details``) from ``ai/SPECIFICATION.md`` §13.
    - No persistence or Airflow dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class CheckSeverity(StrEnum):
    """Severity classification for quality-check findings.

    Maps to the ``severity`` column of ``data_quality_results``.
    """

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class CheckStatus(StrEnum):
    """Outcome status of a quality check execution."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class QualityResult:
    """Outcome of a single quality check execution.

    Attributes
    ----------
    check_name:
        Unique identifier for the check (e.g. ``"required_fields"``).
    severity:
        Finding severity — ``error`` is blocking, ``warning`` is advisory,
        ``info`` is informational.
    status:
        Whether the check passed, failed, or was skipped.
    source:
        Source identifier the check was scoped to, if any.
    records_checked:
        Total number of records evaluated.
    failed_records:
        Number of records that failed the check.
    details:
        Check-specific diagnostic metadata (e.g. which fields had nulls,
        duplicate rate, freshness age).
    message:
        Human-readable summary of the result.
    checked_at:
        UTC timestamp of the check execution.
    """

    check_name: str
    severity: CheckSeverity
    status: CheckStatus
    source: str | None = None
    records_checked: int = 0
    failed_records: int = 0
    details: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def passed(self) -> bool:
        return self.status == CheckStatus.PASSED

    @property
    def failure_rate(self) -> float:
        if self.records_checked == 0:
            return 0.0
        return self.failed_records / self.records_checked


@dataclass(frozen=True)
class QualitySuiteResult:
    """Aggregated outcome of running multiple quality checks.

    Attributes
    ----------
    results:
        Individual check results in execution order.
    started_at:
        UTC timestamp when the suite started.
    finished_at:
        UTC timestamp when the suite finished.
    """

    results: tuple[QualityResult, ...]
    started_at: datetime
    finished_at: datetime

    @property
    def total_checks(self) -> int:
        return len(self.results)

    @property
    def passed_checks(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_checks(self) -> int:
        return sum(1 for r in self.results if not r.passed and r.status != CheckStatus.SKIPPED)

    @property
    def has_errors(self) -> bool:
        return any(r.severity == CheckSeverity.ERROR and not r.passed for r in self.results)

    @property
    def has_warnings(self) -> bool:
        return any(r.severity == CheckSeverity.WARNING and not r.passed for r in self.results)

    def errors(self) -> list[QualityResult]:
        return [r for r in self.results if r.severity == CheckSeverity.ERROR and not r.passed]

    def warnings(self) -> list[QualityResult]:
        return [r for r in self.results if r.severity == CheckSeverity.WARNING and not r.passed]


@runtime_checkable
class QualityCheck(Protocol):
    """Structural protocol for a quality check.

    Any object with a ``name`` attribute and a ``run()`` method that returns
    a ``QualityResult`` satisfies this protocol.
    """

    name: str

    def run(self, df: Any) -> QualityResult: ...
