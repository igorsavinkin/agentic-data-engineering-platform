"""Data-quality validation for normalized product-observation records.

This module provides an explicit validation layer that deterministically splits
a normalized DataFrame (output of ``schema_normalization.normalize()``) into
valid and invalid records. Every invalid record carries diagnosable reason(s)
so that downstream routing (TASK-017) can direct it to ``products.invalid.v1``
with full diagnostic context.

Validation rules (per TASK-015 and ``ai/SPECIFICATION.md``):
    1. Required fields must be non-null (all columns except ``price``).
    2. ``price`` must be non-negative when present.
    3. ``produced_at`` and ``collected_at`` must be non-null timestamps.
    4. ``availability`` must be one of the four canonical enum values.
    5. ``schema_version`` must be in ``SUPPORTED_SCHEMA_VERSIONS``.
    6. ``currency`` must match the ISO-4217 three-letter pattern.

Design decisions:
    - Uses pure Polars expressions (no pandera dependency) to stay consistent
      with the repository's existing Polars-centric processing.
    - Collects *all* violations per row rather than failing fast, so that
      diagnostics are maximally useful.
    - Never silently drops records — every input row appears in exactly one
      of ``valid`` or ``invalid``.
    - The ``ValidationResult`` interface is designed for TASK-017 routing:
      the invalid DataFrame carries an ``_validation_errors`` column with
      semicolon-separated reason strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import polars as pl

from libs.event_contracts import SUPPORTED_SCHEMA_VERSIONS
from libs.event_contracts.product_observation import Availability
from services.processor.schema_normalization import NORMALIZED_SCHEMA

_REQUIRED_COLUMNS: Sequence[str] = [
    "event_id",
    "event_type",
    "schema_version",
    "source",
    "produced_at",
    "external_id",
    "name",
    "url",
    "currency",
    "availability",
    "category",
    "collected_at",
]

_VALID_AVAILABILITY: frozenset[str] = frozenset(v.value for v in Availability)

_CURRENCY_PATTERN = r"^[A-Z]{3}$"

_ERRORS_COL = "_validation_errors"


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating a normalized product-observation DataFrame.

    Every input row appears in exactly one of ``valid`` or ``invalid``.
    The ``invalid`` DataFrame carries an ``_validation_errors`` column
    containing semicolon-separated diagnostic reason strings.
    """

    valid: pl.DataFrame
    invalid: pl.DataFrame
    valid_count: int = field(init=False)
    invalid_count: int = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "valid_count", self.valid.height)
        object.__setattr__(self, "invalid_count", self.invalid.height)

    @property
    def total_count(self) -> int:
        return self.valid_count + self.invalid_count


def validate(df: pl.DataFrame) -> ValidationResult:
    """Validate a normalized product-observation DataFrame.

    Parameters
    ----------
    df:
        A Polars DataFrame whose schema matches ``NORMALIZED_SCHEMA``
        (i.e., the output of ``schema_normalization.normalize()``).

    Returns
    -------
    ValidationResult
        Deterministic split into valid and invalid records. Every invalid
        row has an ``_validation_errors`` column with semicolon-separated
        diagnostic reasons.
    """
    if df.height == 0:
        empty_valid = pl.DataFrame(schema={**NORMALIZED_SCHEMA})
        empty_invalid = pl.DataFrame(schema={**NORMALIZED_SCHEMA, _ERRORS_COL: pl.Utf8})
        return ValidationResult(valid=empty_valid, invalid=empty_invalid)

    error_exprs = _build_error_expressions()

    annotated = df.with_columns(
        pl.concat_str(error_exprs, separator="; ", ignore_nulls=True).alias(_ERRORS_COL)
    )

    has_errors = pl.col(_ERRORS_COL).is_not_null() & (pl.col(_ERRORS_COL).str.len_chars() > 0)

    valid_df = annotated.filter(~has_errors).drop(_ERRORS_COL)
    invalid_df = annotated.filter(has_errors)

    return ValidationResult(valid=valid_df, invalid=invalid_df)


def _build_error_expressions() -> list[pl.Expr]:
    """Build one Polars expression per validation rule.

    Each expression returns a string describing the violation for the row,
    or ``null`` when the row passes that rule. ``concat_str`` with
    ``ignore_nulls=True`` joins only the non-null (failing) reasons.
    """
    exprs: list[pl.Expr] = []

    # 1. Required-field null checks (all except price).
    for col in _REQUIRED_COLUMNS:
        exprs.append(
            pl.when(pl.col(col).is_null()).then(pl.lit(f"null_required:{col}")).otherwise(None)
        )

    # 2. Price semantics: non-negative when present.
    exprs.append(
        pl.when(pl.col("price").is_not_null() & (pl.col("price") < 0))
        .then(pl.lit("negative_price"))
        .otherwise(None)
    )

    # 3. Timestamp null checks are already covered by required-field checks
    #    above (produced_at, collected_at are in _REQUIRED_COLUMNS).

    # 4. Availability enum check.
    valid_avails = sorted(_VALID_AVAILABILITY)
    exprs.append(
        pl.when(~pl.col("availability").is_in(valid_avails))
        .then(pl.lit(f"invalid_availability:allowed={{{','.join(valid_avails)}}}"))
        .otherwise(None)
    )

    # 5. Schema version compatibility.
    supported = sorted(SUPPORTED_SCHEMA_VERSIONS)
    exprs.append(
        pl.when(~pl.col("schema_version").is_in(supported))
        .then(
            pl.lit(f"unsupported_schema_version:allowed={{{','.join(str(v) for v in supported)}}}")
        )
        .otherwise(None)
    )

    # 6. Currency format: three uppercase ASCII letters.
    exprs.append(
        pl.when(
            pl.col("currency").is_not_null() & ~pl.col("currency").str.contains(_CURRENCY_PATTERN)
        )
        .then(pl.lit("invalid_currency_format"))
        .otherwise(None)
    )

    return exprs
