"""Tests for libs.quality.models — core type definitions."""

from __future__ import annotations

from datetime import datetime, timezone

from libs.quality.models import (
    CheckSeverity,
    CheckStatus,
    QualityResult,
    QualitySuiteResult,
)


class TestQualityResult:
    def test_passed_property(self) -> None:
        result = QualityResult(
            check_name="test",
            severity=CheckSeverity.ERROR,
            status=CheckStatus.PASSED,
        )
        assert result.passed is True

    def test_failed_property(self) -> None:
        result = QualityResult(
            check_name="test",
            severity=CheckSeverity.ERROR,
            status=CheckStatus.FAILED,
        )
        assert result.passed is False

    def test_failure_rate_zero_records(self) -> None:
        result = QualityResult(
            check_name="test",
            severity=CheckSeverity.ERROR,
            status=CheckStatus.PASSED,
            records_checked=0,
        )
        assert result.failure_rate == 0.0

    def test_failure_rate_calculation(self) -> None:
        result = QualityResult(
            check_name="test",
            severity=CheckSeverity.ERROR,
            status=CheckStatus.FAILED,
            records_checked=100,
            failed_records=25,
        )
        assert result.failure_rate == 0.25

    def test_frozen(self) -> None:
        result = QualityResult(
            check_name="test",
            severity=CheckSeverity.ERROR,
            status=CheckStatus.PASSED,
        )
        try:
            result.check_name = "other"  # type: ignore[misc]
            raise AssertionError("expected FrozenInstanceError")
        except Exception:
            pass

    def test_default_checked_at(self) -> None:
        result = QualityResult(
            check_name="test",
            severity=CheckSeverity.INFO,
            status=CheckStatus.PASSED,
        )
        assert result.checked_at.tzinfo is not None

    def test_details_default_empty(self) -> None:
        result = QualityResult(
            check_name="test",
            severity=CheckSeverity.INFO,
            status=CheckStatus.PASSED,
        )
        assert result.details == {}


class TestQualitySuiteResult:
    def _make_result(
        self, passed: bool, severity: CheckSeverity = CheckSeverity.ERROR
    ) -> QualityResult:
        return QualityResult(
            check_name="test",
            severity=severity,
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
        )

    def test_total_checks(self) -> None:
        now = datetime.now(timezone.utc)
        suite = QualitySuiteResult(
            results=(self._make_result(True), self._make_result(False)),
            started_at=now,
            finished_at=now,
        )
        assert suite.total_checks == 2

    def test_passed_and_failed_counts(self) -> None:
        now = datetime.now(timezone.utc)
        suite = QualitySuiteResult(
            results=(
                self._make_result(True),
                self._make_result(False),
                self._make_result(True),
            ),
            started_at=now,
            finished_at=now,
        )
        assert suite.passed_checks == 2
        assert suite.failed_checks == 1

    def test_has_errors(self) -> None:
        now = datetime.now(timezone.utc)
        suite = QualitySuiteResult(
            results=(self._make_result(False, CheckSeverity.ERROR),),
            started_at=now,
            finished_at=now,
        )
        assert suite.has_errors is True

    def test_has_no_errors_when_only_warnings(self) -> None:
        now = datetime.now(timezone.utc)
        suite = QualitySuiteResult(
            results=(self._make_result(False, CheckSeverity.WARNING),),
            started_at=now,
            finished_at=now,
        )
        assert suite.has_errors is False
        assert suite.has_warnings is True

    def test_errors_and_warnings_filters(self) -> None:
        now = datetime.now(timezone.utc)
        err = QualityResult(
            check_name="err",
            severity=CheckSeverity.ERROR,
            status=CheckStatus.FAILED,
        )
        warn = QualityResult(
            check_name="warn",
            severity=CheckSeverity.WARNING,
            status=CheckStatus.FAILED,
        )
        ok = QualityResult(
            check_name="ok",
            severity=CheckSeverity.ERROR,
            status=CheckStatus.PASSED,
        )
        suite = QualitySuiteResult(
            results=(err, warn, ok),
            started_at=now,
            finished_at=now,
        )
        assert len(suite.errors()) == 1
        assert suite.errors()[0].check_name == "err"
        assert len(suite.warnings()) == 1
        assert suite.warnings()[0].check_name == "warn"

    def test_empty_suite(self) -> None:
        now = datetime.now(timezone.utc)
        suite = QualitySuiteResult(results=(), started_at=now, finished_at=now)
        assert suite.total_checks == 0
        assert suite.passed_checks == 0
        assert suite.failed_checks == 0
        assert suite.has_errors is False
        assert suite.has_warnings is False
