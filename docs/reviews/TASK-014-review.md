# TASK-014 Review — Schema Normalization

## 1. Review Header

- **Task ID:** TASK-014 — Schema Normalization
- **Review date:** 2026-09-10
- **Reviewed commit:** `c06ace19f77d7a5d2d881c048a97c07b4509821b` (`feat(TASK-014): Add deterministic schema normalization for product observations`)
- **Reviewed change set / Git range:** `9c460ab5f275b04665cda2f1b66834521a203291...c06ace19f77d7a5d2d881c048a97c07b4509821b` (single commit `c06ace1`), branch `feature/TASK-014`
- **Scope:** New `services/processor/schema_normalization.py` (133 lines) and new unit tests `tests/test_schema_normalization.py` (496 lines, 42 tests). No other files changed.
- **Verdict:** **APPROVED WITH NON-BLOCKING FINDINGS**

---

## 2. Requirements Coverage

Sources: `ai/tasks/TASK-014-schema-normalization.md`, `ai/SPECIFICATION.md` §7 (Event Contract) and §11 (Processing Layer), `ai/PROJECT.md` §5 (Event Semantics).

| Requirement | Status | Implementation evidence |
| --- | --- | --- |
| 1. Define the normalized analytical schema in one reusable place | ✅ Met | `NORMALIZED_SCHEMA` dict in `schema_normalization.py` is the single source of truth for column names, order, and dtypes; consumed by both `normalize()` and the tests. |
| 2. Normalize types without silently corrupting invalid values | ✅ Met | All coercions use `strict=False`; invalid numeric values become `null` (never zero-filled); invalid enum values are preserved verbatim rather than coerced. |
| 3. Normalize timestamps to the project convention | ✅ Met | `_normalize_timestamps()` converts aware timestamps to UTC and stamps naive timestamps as UTC, producing `Datetime("us", "UTC")`. |
| 4. Preserve event ID, source ID, external product ID, schema version, and distinct producer/collection timestamps | ✅ Met | `event_id`/`external_id` are cast to `Utf8` but never whitespace-stripped; `schema_version` cast to `Int64`; `produced_at`/`collected_at` remain distinct columns. (See Finding F4 for a `source`-stripping nuance.) |
| 5. Normalize availability only to allowed values | ✅ Met | Availability is whitespace-stripped and lowercased so canonical forms (`IN_STOCK` → `in_stock`) normalize to allowed values; invalid values (`discontinued`) are preserved as-is for TASK-015 to flag. |
| 6. Predictable string/null handling without changing semantic IDs/URLs unless specified | ✅ Met | `event_id`, `external_id`, and `url` are explicitly excluded from `_STRIP_WHITESPACE_COLS`; `name`, `category`, `currency`, `source`, `event_type` are stripped. Nulls propagate through every expression. |
| 7. Prefer Polars expressions | ✅ Met | All transformations use `with_columns` + `pl.col(...)` expressions; no Python row-level loops after DataFrame construction. |
| 8. Invalid/unparseable values must remain detectable by TASK-015 | ✅ Met | Non-numeric `price` → `null`; invalid `availability` preserved as string; unparseable timestamps → `null`. No value is silently coerced into a valid-looking value. |
| 9. No silent row dropping | ✅ Met | Only `with_columns`/`select` are used; no `filter`/`drop_nulls`/`unique`. Row count is preserved (`result.height == df.height`); empty input returns 0 rows. |
| 10. Document schema invariants | ✅ Met | Module docstring lists guaranteed invariants and explicitly separates out TASK-015 responsibilities. |

### Acceptance Criteria

| Criterion | Status | Evidence |
| --- | --- | --- |
| Valid inputs normalize into one stable analytical schema | ✅ Met | `TestValidTypeNormalization`, `TestStableSchemaRegardlessOfRowOrder` verify dtype/order stability. |
| Failures are explicit and available for validation | ✅ Met | `TestMalformedValuesDetectable`, `TestAvailabilityEnumHandling.test_invalid_availability_preserved_for_validation`. |
| No records silently disappear | ✅ Met | `TestRowCountPreservation` (empty/single/multi/null-price rows). |
| Tests and quality checks pass | ✅ Met | See §4; independently verified. |

---

## 3. Git Diff Review

- **Scope correctness:** ✅ Both files are TASK-014-scoped: the normalization module and its unit tests. 629 insertions, 0 deletions; no existing file modified.
- **Branch/task isolation:** ✅ All changes on `feature/TASK-014`; single commit `c06ace1` contains only this task's work. No TASK-013 or other task changes mixed in.
- **Unrelated changes:** None.
- **Architectural changes:** None. New module sits inside the existing `services/processor/` boundary and consumes the TASK-013 `events_to_polars()` output; no service boundaries altered, no ADR impact.
- **Accidental changes / debug / secrets:** None. No credentials, debug prints, TODOs, dead code, or generated artifacts.
- **Dependencies/configuration:** None. No `requirements.txt`, `pyproject.toml`, or CI changes; Polars was already a dependency from TASK-013.
- **Test weakening:** None. Existing tests untouched; the new tests are additive and assert strict invariants.

---

## 4. Test and Verification Review

- **Tests examined:** `tests/test_schema_normalization.py` — 42 tests across 12 classes.

### Independently verified (reviewer-executed)

| Command | Result |
| --- | --- |
| `pytest tests/test_schema_normalization.py -v` | **42 passed** |
| `pytest -q` (full suite) | **282 passed, 29 deselected** (integration correctly excluded) |
| `ruff check services/processor/schema_normalization.py tests/test_schema_normalization.py` | **All checks passed** |
| `ruff format --check services/processor/schema_normalization.py tests/test_schema_normalization.py` | **2 files already formatted** |
| `mypy libs services` | **Success: no issues found in 13 source files** |

### Test coverage vs. required scenarios

| Required test scenario (task spec) | Covered by |
| --- | --- |
| valid type normalization | `TestValidTypeNormalization` (4 tests) |
| timestamp normalization | `TestTimestampNormalization` (3 tests) |
| nullable fields | `TestNullableFields` (4 tests) |
| malformed values remain detectable | `TestMalformedValuesDetectable` (3 tests) |
| availability enum handling | `TestAvailabilityEnumHandling` (4 tests) |
| exact ID preservation | `TestExactIDPreservation` (5 tests) |
| stable schema regardless of row order | `TestStableSchemaRegardlessOfRowOrder` (2 tests) |

Additional coverage beyond the required list: whitespace stripping (5 tests), row-count preservation (4 tests), schema-version preservation (2 tests), empty input (2 tests).

- **Implementation results inspected but not rerun:** None — all checks were independently executed.
- **Unverified checks:** None.

**Note on mypy scope:** The project's default mypy config (`pyproject.toml`) is `files = ["scripts", "tests", "libs"]`, so `services/` is not type-checked by the default CI run (the tests file is covered). My independent run overrode this to include `services/` and passed cleanly. See Non-Defect Observation N1.

---

## 5. Findings

### F1 — Non-datetime timestamps are nulled rather than parsed, using deprecated Polars behavior — **Moderate**

- **File:** `services/processor/schema_normalization.py`, `_normalize_timestamps()` else-branch (lines ~120–130).
- **Problem:** The non-datetime branch does `col.cast(UTC_DATETIME, strict=False)`. For a string column this produces `null` for every value and emits a `DeprecationWarning` ("Casting from String to DateTime is deprecated and will be removed in Polars 2.0"). A parseable ISO-8601 timestamp string (a plausible raw representation) is therefore lost rather than normalized to UTC, and the code path is untested and relies on deprecated behavior.
- **Impact:** If `normalize()` is ever applied to a DataFrame whose timestamp columns are strings (e.g., read directly from Bronze Parquet rather than via `events_to_polars()`), valid timestamps silently become `null`. The null is detectable by TASK-015, so this is not silent data *loss*, but it degrades a parseable value into an invalid one.
- **Recommendation:** Either (a) document that `normalize()` requires datetime-typed timestamp columns and reject/`null` other types explicitly, or (b) parse ISO strings via `pl.col(...).str.to_datetime(...)` before the UTC cast. Add a test covering string timestamp input. Not blocking because the documented primary input (`events_to_polars()` output) always yields timezone-aware `datetime` objects, and the `polars>=1.0,<2` pin bounds the deprecation for now.

### F2 — `currency` is whitespace-stripped but not uppercased — **Minor**

- **File:** `services/processor/schema_normalization.py`, `_STRIP_WHITESPACE_COLS` / `normalize()`.
- **Problem:** Availability is lowercased (`in_stock` canonical form), but currency is only stripped, not uppercased, despite the contract requiring `^[A-Z]{3}$` (ISO-4217). A raw value like `"eur"` would survive normalization and be rejected by TASK-015, which is acceptable but asymmetric with availability handling.
- **Impact:** Cosmetic/consistency; a downstream validation failure for lowercase currency is arguably intended (normalization should not hide source issues), but the asymmetry is worth an explicit decision.
- **Recommendation:** Either uppercase currency during normalization (symmetric with availability), or document that currency case is intentionally left to validation. Low priority.

### F3 — `services/processor/README.md` not updated for the new module — **Minor**

- **File:** `services/processor/README.md`.
- **Problem:** TASK-013 established a module-index convention in this README; `schema_normalization.py` was added but the README's "Module Structure" and "Downstream" sections were not updated to document the new `normalize()` entry point.
- **Impact:** Documentation drift; the invariant documentation exists only in the module docstring, so the README now under-represents the processor's capabilities.
- **Recommendation:** Add a `schema_normalization.py` (TASK-014) subsection to the README. Not blocking.

### F4 — "source ID" preservation vs. whitespace-stripping of `source` — **Minor**

- **File:** `services/processor/schema_normalization.py`, `_STRIP_WHITESPACE_COLS` includes `"source"`.
- **Problem:** Requirement 4 says to preserve the "source ID," while the implementation whitespace-strips `source` (and does not include it in the verbatim-preserved `event_id`/`external_id`/`url` set). This is defensible because the event contract's Pydantic model already strips all strings (`str_strip_whitespace=True`) and `source` is a source *name*, not a globally-unique identifier — but the terminology is ambiguous.
- **Impact:** No behavioral impact through the normal path (Pydantic already strips `source`); the semantic source value is preserved. Purely a spec-interpretation ambiguity.
- **Recommendation:** Confirm/clarify whether `source` should be treated as a verbatim ID like `event_id`/`external_id` or as a normalized name. Low priority.

---

## 6. Non-Defect Observations

1. **`services/` not in default mypy scope (continuing from TASK-013).** `pyproject.toml` mypy `files = ["scripts", "tests", "libs"]` still excludes `services/`, so the production module is not type-checked by the default CI run. My explicit `mypy libs services` run passed cleanly, but the config should be updated to include `services` as the layer grows.

2. **Float64 price representation (continuing from TASK-013).** `price` is normalized to `Float64`; the upstream `Decimal`→`float` conversion at the `events_to_polars()` boundary means potential precision loss for price arithmetic. Consistent with the schema and task intent ("numeric price representation"), but downstream Silver/Gold stages should remain aware.

3. **Availability handled as lowercased string, not enum.** Type safety is intentionally lost at the Polars boundary; validation of the allowed set is correctly deferred to TASK-015. This matches requirement 8.

4. **Defensive non-datetime/naive-timestamp handling.** `_normalize_timestamps()` correctly handles timezone-aware, timezone-naive, and non-datetime inputs, which is good defensive design even though the Pydantic contract already requires aware timestamps.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The TASK-014 deliverable satisfies all requirements and acceptance criteria:

- ✅ Canonical schema defined in one reusable place (`NORMALIZED_SCHEMA`)
- ✅ Deterministic type normalization with no silent corruption (invalid → `null`, not coerced)
- ✅ Timestamps normalized to `Datetime("us", "UTC")`
- ✅ `event_id`, `external_id`, `url`, `schema_version`, and distinct `produced_at`/`collected_at` preserved
- ✅ Availability normalized to canonical lowercase form without inventing new values
- ✅ Invalid/unparseable values remain detectable for TASK-015
- ✅ No silent row dropping (row count preserved)
- ✅ Schema invariants documented in the module docstring
- ✅ All required test scenarios covered (42 tests) and passing
- ✅ Full suite green (282 passed), ruff check/format clean, mypy clean on `libs services`

The four findings (one Moderate, three Minor) are non-blocking: none violates a task requirement or acceptance criterion, and none introduces a correctness defect on the documented input path (`events_to_polars()` output). The Moderate finding (F1) should be addressed before the module is fed non-`events_to_polars` input (e.g., direct Bronze Parquet reads). Ready to merge to `main`.
