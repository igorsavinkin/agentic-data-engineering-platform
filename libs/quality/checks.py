"""Concrete quality-check implementations.

Each check operates on a Polars DataFrame and returns a ``QualityResult``.
Checks are deterministic, stateless, and independent of Airflow or
persistence (TASK-056).

Available checks:
    - ``RequiredFieldsCheck``: verifies required columns are non-null.
    - ``PriceValidityCheck``: verifies price is non-negative when present.
    - ``AllowedValuesCheck``: verifies a column's values are within an
      allowed set.
    - ``DuplicateCheck``: detects duplicate records by key columns.
    - ``FreshnessCheck``: verifies data freshness against a threshold.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

import polars as pl

from libs.quality.models import CheckSeverity, CheckStatus, QualityResult


@dataclass(frozen=True)
class RequiredFieldsCheck:
    """Check that required columns have no null values.

    Attributes
    ----------
    columns:
        Column names that must be non-null.
    severity:
        Severity when the check fails.
    name:
        Check identifier.
    """

    columns: Sequence[str]
    severity: CheckSeverity = CheckSeverity.ERROR
    name: str = "required_fields"

    def run(self, df: pl.DataFrame) -> QualityResult:
        now = datetime.now(timezone.utc)
        if df.height == 0:
            return QualityResult(
                check_name=self.name,
                severity=self.severity,
                status=CheckStatus.PASSED,
                records_checked=0,
                message="empty DataFrame — nothing to check",
                checked_at=now,
            )

        missing_columns = [c for c in self.columns if c not in df.columns]
        if missing_columns:
            return QualityResult(
                check_name=self.name,
                severity=self.severity,
                status=CheckStatus.FAILED,
                records_checked=df.height,
                failed_records=df.height,
                details={"missing_columns": missing_columns},
                message=f"columns not found in DataFrame: {missing_columns}",
                checked_at=now,
            )

        null_counts: dict[str, int] = {}
        for col in self.columns:
            count = df.filter(pl.col(col).is_null()).height
            if count > 0:
                null_counts[col] = count

        total_failed = sum(null_counts.values()) if null_counts else 0

        if null_counts:
            return QualityResult(
                check_name=self.name,
                severity=self.severity,
                status=CheckStatus.FAILED,
                records_checked=df.height,
                failed_records=total_failed,
                details={"null_counts_by_column": null_counts},
                message=f"null values found in {len(null_counts)} column(s)",
                checked_at=now,
            )

        return QualityResult(
            check_name=self.name,
            severity=self.severity,
            status=CheckStatus.PASSED,
            records_checked=df.height,
            failed_records=0,
            details={"null_counts_by_column": {}},
            message="all required fields present",
            checked_at=now,
        )


@dataclass(frozen=True)
class PriceValidityCheck:
    """Check that price values are non-negative when present.

    Attributes
    ----------
    price_column:
        Name of the price column.
    min_price:
        Minimum allowed price (inclusive). Defaults to 0.0.
    max_price:
        Maximum allowed price (inclusive). ``None`` means no upper bound.
    severity:
        Severity when the check fails.
    name:
        Check identifier.
    """

    price_column: str = "price"
    min_price: float = 0.0
    max_price: float | None = None
    severity: CheckSeverity = CheckSeverity.ERROR
    name: str = "price_validity"

    def run(self, df: pl.DataFrame) -> QualityResult:
        now = datetime.now(timezone.utc)
        if df.height == 0:
            return QualityResult(
                check_name=self.name,
                severity=self.severity,
                status=CheckStatus.PASSED,
                records_checked=0,
                message="empty DataFrame — nothing to check",
                checked_at=now,
            )

        if self.price_column not in df.columns:
            return QualityResult(
                check_name=self.name,
                severity=self.severity,
                status=CheckStatus.FAILED,
                records_checked=df.height,
                failed_records=df.height,
                details={"missing_column": self.price_column},
                message=f"price column '{self.price_column}' not found",
                checked_at=now,
            )

        col = pl.col(self.price_column)
        below_min = df.filter(col.is_not_null() & (col < self.min_price)).height

        above_max = 0
        if self.max_price is not None:
            above_max = df.filter(col.is_not_null() & (col > self.max_price)).height

        total_failed = below_min + above_max
        details: dict[str, Any] = {
            "below_min_count": below_min,
            "min_price": self.min_price,
        }
        if self.max_price is not None:
            details["above_max_count"] = above_max
            details["max_price"] = self.max_price

        if total_failed > 0:
            return QualityResult(
                check_name=self.name,
                severity=self.severity,
                status=CheckStatus.FAILED,
                records_checked=df.height,
                failed_records=total_failed,
                details=details,
                message=f"{total_failed} record(s) with invalid price",
                checked_at=now,
            )

        return QualityResult(
            check_name=self.name,
            severity=self.severity,
            status=CheckStatus.PASSED,
            records_checked=df.height,
            failed_records=0,
            details=details,
            message="all prices valid",
            checked_at=now,
        )


@dataclass(frozen=True)
class AllowedValuesCheck:
    """Check that a column's values are within an allowed set.

    Attributes
    ----------
    column:
        Column name to validate.
    allowed_values:
        Set of permitted values.
    severity:
        Severity when the check fails.
    name:
        Check identifier.
    """

    column: str
    allowed_values: frozenset[str]
    severity: CheckSeverity = CheckSeverity.ERROR
    name: str = "allowed_values"

    def run(self, df: pl.DataFrame) -> QualityResult:
        now = datetime.now(timezone.utc)
        if df.height == 0:
            return QualityResult(
                check_name=self.name,
                severity=self.severity,
                status=CheckStatus.PASSED,
                records_checked=0,
                message="empty DataFrame — nothing to check",
                checked_at=now,
            )

        if self.column not in df.columns:
            return QualityResult(
                check_name=self.name,
                severity=self.severity,
                status=CheckStatus.FAILED,
                records_checked=df.height,
                failed_records=df.height,
                details={"missing_column": self.column},
                message=f"column '{self.column}' not found",
                checked_at=now,
            )

        invalid = df.filter(~pl.col(self.column).is_in(sorted(self.allowed_values)))
        invalid_count = invalid.height

        if invalid_count > 0:
            found_values = invalid[self.column].unique().to_list()
            return QualityResult(
                check_name=self.name,
                severity=self.severity,
                status=CheckStatus.FAILED,
                records_checked=df.height,
                failed_records=invalid_count,
                details={
                    "column": self.column,
                    "disallowed_values_found": sorted(found_values),
                    "allowed_values": sorted(self.allowed_values),
                },
                message=f"{invalid_count} record(s) with disallowed values in '{self.column}'",
                checked_at=now,
            )

        return QualityResult(
            check_name=self.name,
            severity=self.severity,
            status=CheckStatus.PASSED,
            records_checked=df.height,
            failed_records=0,
            details={
                "column": self.column,
                "allowed_values": sorted(self.allowed_values),
            },
            message=f"all values in '{self.column}' are allowed",
            checked_at=now,
        )


@dataclass(frozen=True)
class DuplicateCheck:
    """Check for duplicate records by key columns.

    Reports the duplicate rate and the number of unique keys that have
    duplicates. Does not remove duplicates — it only measures them.

    Attributes
    ----------
    key_columns:
        Columns that define record identity.
    max_duplicate_rate:
        Maximum acceptable duplicate rate (0.0 to 1.0). Defaults to 0.0
        (any duplicates fail the check).
    severity:
        Severity when the check fails.
    name:
        Check identifier.
    """

    key_columns: Sequence[str]
    max_duplicate_rate: float = 0.0
    severity: CheckSeverity = CheckSeverity.WARNING
    name: str = "duplicates"

    def run(self, df: pl.DataFrame) -> QualityResult:
        now = datetime.now(timezone.utc)
        if df.height == 0:
            return QualityResult(
                check_name=self.name,
                severity=self.severity,
                status=CheckStatus.PASSED,
                records_checked=0,
                message="empty DataFrame — nothing to check",
                checked_at=now,
            )

        missing = [c for c in self.key_columns if c not in df.columns]
        if missing:
            return QualityResult(
                check_name=self.name,
                severity=self.severity,
                status=CheckStatus.FAILED,
                records_checked=df.height,
                failed_records=df.height,
                details={"missing_columns": missing},
                message=f"key columns not found: {missing}",
                checked_at=now,
            )

        total = df.height
        unique_keys = df.select(self.key_columns).unique().height
        duplicate_rows = total - unique_keys
        duplicate_rate = duplicate_rows / total if total > 0 else 0.0

        keys_with_dups = df.group_by(self.key_columns).len().filter(pl.col("len") > 1).height

        details: dict[str, Any] = {
            "total_records": total,
            "unique_keys": unique_keys,
            "duplicate_rows": duplicate_rows,
            "duplicate_rate": round(duplicate_rate, 6),
            "keys_with_duplicates": keys_with_dups,
        }

        if duplicate_rate > self.max_duplicate_rate:
            return QualityResult(
                check_name=self.name,
                severity=self.severity,
                status=CheckStatus.FAILED,
                records_checked=total,
                failed_records=duplicate_rows,
                details=details,
                message=(
                    f"duplicate rate {duplicate_rate:.4f} exceeds threshold "
                    f"{self.max_duplicate_rate}"
                ),
                checked_at=now,
            )

        return QualityResult(
            check_name=self.name,
            severity=self.severity,
            status=CheckStatus.PASSED,
            records_checked=total,
            failed_records=duplicate_rows,
            details=details,
            message="duplicate rate within threshold",
            checked_at=now,
        )


@dataclass(frozen=True)
class FreshnessCheck:
    """Check data freshness against a configurable threshold.

    Evaluates whether the most recent ``timestamp_column`` value is within
    ``max_age_seconds`` of the reference time. Compatible with the existing
    ``SourceHealthTracker`` freshness semantics from
    ``libs/observability/health_assessment.py``.

    Attributes
    ----------
    timestamp_column:
        Column containing observation timestamps.
    max_age_seconds:
        Maximum acceptable age of the most recent record.
    source:
        Source identifier for scoping the check.
    reference_time:
        Time to compare against. Defaults to current UTC time.
    severity:
        Severity when the check fails.
    name:
        Check identifier.
    """

    timestamp_column: str = "collected_at"
    max_age_seconds: float = 3600.0
    source: str | None = None
    reference_time: datetime | None = None
    severity: CheckSeverity = CheckSeverity.WARNING
    name: str = "freshness"

    def run(self, df: pl.DataFrame) -> QualityResult:
        ref_time = self.reference_time or datetime.now(timezone.utc)
        if df.height == 0:
            return QualityResult(
                check_name=self.name,
                severity=self.severity,
                status=CheckStatus.FAILED,
                source=self.source,
                records_checked=0,
                failed_records=0,
                details={"reason": "no_records"},
                message="no records to evaluate freshness",
                checked_at=ref_time,
            )

        if self.timestamp_column not in df.columns:
            return QualityResult(
                check_name=self.name,
                severity=self.severity,
                status=CheckStatus.FAILED,
                source=self.source,
                records_checked=df.height,
                failed_records=df.height,
                details={"missing_column": self.timestamp_column},
                message=f"timestamp column '{self.timestamp_column}' not found",
                checked_at=ref_time,
            )

        non_null = df.filter(pl.col(self.timestamp_column).is_not_null())
        if non_null.height == 0:
            return QualityResult(
                check_name=self.name,
                severity=self.severity,
                status=CheckStatus.FAILED,
                source=self.source,
                records_checked=df.height,
                failed_records=df.height,
                details={"reason": "all_null_timestamps"},
                message="all timestamp values are null",
                checked_at=ref_time,
            )

        latest_raw = non_null[self.timestamp_column].max()
        if latest_raw is None or not isinstance(latest_raw, datetime):
            return QualityResult(
                check_name=self.name,
                severity=self.severity,
                status=CheckStatus.FAILED,
                source=self.source,
                records_checked=df.height,
                failed_records=df.height,
                details={"reason": "no_valid_timestamp"},
                message="could not determine latest timestamp",
                checked_at=ref_time,
            )

        latest: datetime = latest_raw
        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=timezone.utc)

        age_seconds = (ref_time - latest).total_seconds()

        details: dict[str, Any] = {
            "latest_timestamp": latest.isoformat(),
            "reference_time": ref_time.isoformat(),
            "age_seconds": round(age_seconds, 2),
            "max_age_seconds": self.max_age_seconds,
            "records_with_timestamps": non_null.height,
        }

        if age_seconds > self.max_age_seconds:
            return QualityResult(
                check_name=self.name,
                severity=self.severity,
                status=CheckStatus.FAILED,
                source=self.source,
                records_checked=df.height,
                failed_records=df.height,
                details=details,
                message=(
                    f"freshness age {age_seconds:.0f}s exceeds threshold "
                    f"{self.max_age_seconds:.0f}s"
                ),
                checked_at=ref_time,
            )

        return QualityResult(
            check_name=self.name,
            severity=self.severity,
            status=CheckStatus.PASSED,
            source=self.source,
            records_checked=df.height,
            failed_records=0,
            details=details,
            message=f"freshness age {age_seconds:.0f}s within threshold",
            checked_at=ref_time,
        )
