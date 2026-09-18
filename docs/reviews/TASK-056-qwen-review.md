# TASK-056 Qwen Post-Merge Review Report

**Task:** TASK-056 — Data Quality Framework
**Merge commit:** `9b3f10d` (`feat(TASK-056): Add data-quality framework (#69)`)
**Parent:** `6ed2bfc` (single parent — GitHub squash-merge; reviewed diff is `6ed2bfc..9b3f10d`)
**Review method:** Post-merge diff review (Qwen)
**Verdict:** APPROVED

## Scope

`6ed2bfc..9b3f10d` is 8 files, +1475 lines:

| File | Kind | Lines |
|---|---|---|
| `libs/quality/__init__.py` | new | +46 |
| `libs/quality/models.py` | new | +149 |
| `libs/quality/checks.py` | new | +492 |
| `libs/quality/runner.py` | new | +77 |
| `tests/test_quality_checks.py` | new | +342 |
| `tests/test_quality_models.py` | new | +166 |
| `tests/test_quality_runner.py` | new | +142 |
| `docs/reviews/TASK-056-review.md` | new (OCR review artifact) | +61 |

The seven code/test files are the review target. `libs/quality/persistence.py` is **not** part of this commit (it arrives later with TASK-057), and the committed `__init__.py` correctly imports only `checks`, `models`, and `runner` — the package is importable at this commit.

## Verification Performed

- `python -m pytest tests/test_quality_checks.py tests/test_quality_models.py tests/test_quality_runner.py -q` → **53 passed**
- `python -m ruff check libs/quality/ tests/test_quality_*.py` → **All checks passed**
- `python -m ruff format --check ...` → **8 files already formatted**
- `python -m mypy libs/quality/` → **Success: no issues found**
- Targeted runtime probes for null / NaN / naive-datetime edge cases (results cited in findings below).

## Findings

### High

None.

### Medium

**M1 — `QualityResult` docstring misrepresents alignment with the `data_quality_results` schema (`libs/quality/models.py:10-13`)**

The module docstring states the result fields align with the `data_quality_results` warehouse table as `check_name`, `severity`, `passed`, `message`, `checked_at`. `ai/SPECIFICATION.md` §13 (PostgreSQL entities table) defines that table as:

```
data_quality_results | id, run_id, check_name, source, status, checked_at, records_checked, failed_records, details
```

The spec table has a single `status` column and **no** `severity`, `passed`, or `message` columns. The model does carry `status` (so it is partially aligned), but `severity` and `message` are additions, and `passed` is a derived boolean property — none of which exist in the spec. This is a documentation/design mismatch against a higher-authority document. It is non-blocking for TASK-056 (no persistence), but it must be reconciled when TASK-057 persists results: either the spec table gains `severity`/`message` (a schema change requiring an ADR/spec update) or persistence must drop them. **Recommend resolving before TASK-057 persistence work proceeds.**

**M2 — NaN values are invisible to the framework (`libs/quality/checks.py:153,157` and the null-count path)**

`PriceValidityCheck` computes `below_min`/`above_max` with `col.is_not_null() & (col < min)` / `(col > max)`. Polars `is_not_null()` returns `True` for `NaN`, and both `NaN < 0.0` and `NaN > 0.0` are `False`, so a `NaN` price passes as "valid". The same blind spot affects `RequiredFieldsCheck`: `pl.col(...).is_null()` is `False` for `NaN`, so `NaN` in a required column is not flagged. Verified at runtime:

```
price NaN status: passed failed: 0
RequiredFields NaN status: passed failed: 0   (polars is_null(NaN) -> [False])
```

For a data-quality framework whose purpose is to catch bad values, silently accepting `NaN` in price/required fields is a correctness gap. The ingestion path is partially protected upstream (`libs/event_contracts/product_observation.py` validates via `Decimal`, which cannot be `NaN`), but the framework is documented as generic over Polars DataFrames and will be reused on lake/warehouse frames where `Float64` `NaN` is plausible.

**M3 — `AllowedValuesCheck` silently ignores nulls (`libs/quality/checks.py:237`)**

`invalid = df.filter(~pl.col(self.column).is_in(sorted(self.allowed_values)))`. For a `null` value, `is_in` yields `null`, `~null` is `null`, and Polars `filter` drops null-mask rows — so `null` is neither "allowed" nor flagged as "disallowed". Verified: a column value of `[in_stock, null, preorder]` returns `passed` with `failed_records=0`. The `availability` field is a non-nullable enum per the event contract, so a null availability would escape this check (only `RequiredFieldsCheck`, if explicitly configured for that column, would catch it). The check should decide and document whether nulls are invalid or out-of-scope, and ideally expose a `disallowed_values_found` that accounts for them.

### Low

**L1 — `FreshnessCheck` crashes on a naive `reference_time` (`libs/quality/checks.py:397,454`)**

If a caller passes a naive `reference_time` while the timestamp column is tz-aware (the default), `ref_time - latest` raises `TypeError: can't subtract offset-naive and offset-aware datetimes` instead of returning a `QualityResult`. The default (`datetime.now(timezone.utc)`) is safe, and tests use aware datetimes, but the public `reference_time` parameter accepts naive values without normalization.

**L2 — Empty-DataFrame semantics are inconsistent across checks**

`RequiredFieldsCheck`, `PriceValidityCheck`, `AllowedValuesCheck`, and `DuplicateCheck` return `PASSED` on an empty DataFrame (`checks.py:47,130,215,299`), whereas `FreshnessCheck` returns `FAILED` (`checks.py:398`). Freshness failing on no data is defensible and matches `SourceHealthTracker.NEVER_COLLECTED`, but the divergence should be documented. Additionally, the four "pass on empty" checks short-circuit before validating column presence, so an empty frame with a missing required column is reported as `PASSED` rather than surfacing the schema problem.

**L3 — `FreshnessCheck` conflates a dataset-level metric with record-level counters (`checks.py:418,432,446,473`)**

On any freshness failure (no records, missing column, all-null timestamps, stale data), the check sets `failed_records = df.height`. Freshness is a dataset-level property; "all N records failed" misrepresents a stale/freshness failure as per-record failure. Same convention is used for missing-column failures across all checks, which is acceptable for schema errors but misleading for freshness.

**L4 — `QualityCheck` Protocol types the DataFrame as `Any` (`models.py:149`)**

`def run(self, df: Any) -> QualityResult` defeats type checking on the one argument every check consumes. The concrete checks correctly type `df: pl.DataFrame`, but a caller typing against the protocol gets no enforcement. Previously noted by the OCR review as an accepted trade-off for structural typing; retaining as Low.

**L5 — Overlap with existing validation is undocumented**

`PriceValidityCheck` (non-negative price) duplicates the rule already enforced in `libs/event_contracts/product_observation.py` (`_validate_price_non_negative`), and the framework overlaps conceptually with `libs/schema/parquet_schemas.py` (`validate_row_against_schema`). There is no doc clarifying whether the quality framework should eventually delegate to, or supersede, these event/schema-level checks. (The prior OCR review referenced a processor `data_validation.py`, which does not exist in the tree; the actual overlap is the event-contract and parquet-schema layers.)

**L6 — Speculative surface not exercised**

`CheckStatus.SKIPPED` is defined (`models.py:41`) and `QualitySuiteResult` accounts for it, but no check ever emits it. `severity` (INFO/WARNING/ERROR) is a model addition absent from `ai/SPECIFICATION.md` §13/§14. Neither is harmful, but both are unused/un-spec'd surface added ahead of need.

## Comparison Summary

The bundled OCR review (`docs/reviews/TASK-056-review.md`, reviewed commit `272f58f` on the feature branch) found one High finding — `RequiredFieldsCheck.failed_records` summed per-column nulls instead of counting rows — plus two Medium findings. My review of the merged commit confirms:

- **High finding is fixed.** `checks.py` now uses `pl.any_horizontal(...)` to count rows with at least one null, and `tests/test_quality_checks.py::test_failed_records_counts_rows_not_nulls` guards it. Verified passing.
- **OCR Medium #2 (`Protocol` uses `Any`)** — confirmed and retained as L4.
- **OCR Medium #3 (relationship to processor `data_validation.py`)** — the referenced module does not exist; the real overlap is with the event-contract and parquet-schema validation layers (L5).

New findings not caught by the OCR review: the `data_quality_results` schema misalignment (M1), the NaN blind spot (M2), nulls ignored by `AllowedValuesCheck` (M3), the naive-`reference_time` crash (L1), empty-frame semantic inconsistency (L2), and freshness `failed_records` conflation (L3).

## Verdict

**APPROVED.** The implementation satisfies the TASK-056 objective (typed, deterministic, Airflow-independent, persistence-free checks for required fields, price validity, allowed values, duplicates, and freshness) and is well-tested (53 passing tests) with clean lint/format/type checks. No High-severity issues. M1 must be reconciled before TASK-057 persistence; M2/M3 are real data-quality gaps that should be closed when the framework is wired into live pipelines, and the Low items are polish/robustness follow-ups.
