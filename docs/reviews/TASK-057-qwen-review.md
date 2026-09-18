# TASK-057 Qwen Post-Merge Review Report

**Task:** TASK-057 — Quality Result Persistence
**Merge commit:** `f9b2f3c` (`Merge pull request #70 from igorsavinkin/feature/TASK-057`)
**Parent:** `9b3f10d` (first parent — the pre-merge `main` tip; reviewed diff is `9b3f10d..f9b2f3c`)
**Review method:** Post-merge diff review (Qwen)
**Verdict:** CHANGES_REQUIRED

## Scope

`9b3f10d..f9b2f3c` is 8 files, +980 / -4 lines:

| File | Kind | Lines |
|---|---|---|
| `libs/quality/persistence.py` | new | +370 |
| `libs/quality/__init__.py` | modified | +14 / -1 |
| `warehouse/migrations/versions/004_quality_result_persistence.py` | new | +61 |
| `warehouse/schema/init.sql` | modified | +9 / -1 |
| `tests/test_quality_persistence_integration.py` | new | +385 |
| `tests/test_quality_persistence_unit.py` | new | +56 |
| `tests/warehouse/test_migrations.py` | modified | +1 / -1 |
| `docs/reviews/TASK-057-review.md` | new (OCR review artifact) | +78 |

The feature branch contributes five commits: `e6bed9f` (the implementation the bundled OCR review reviewed), then three follow-up fixes — `eae24bf` (mypy import-untyped suppression), `f771c4b` (`sa.Column()` instead of non-existent `op.column()`), `bf667a6` (migration version assertion) — plus `e001573` (OCR report). The `op.column()`→`sa.Column()` fix and the `003`→`004` assertion fix are genuine correctness repairs that landed after the OCR review, which is a positive signal that the migration was actually exercised.

## Verification Performed

- `ruff check libs/quality/persistence.py tests/test_quality_persistence_*.py warehouse/migrations/versions/004_*.py` → **All checks passed.**
- `mypy libs/quality/persistence.py` → only `import-not-found` for `polars` (the local `.venv` does not have `polars` installed); no errors attributable to `persistence.py` itself.
- `pytest tests/test_quality_persistence_unit.py` → **could not run** in this environment: collection fails with `ModuleNotFoundError: No module named 'polars'` (a stale/incomplete `.venv`, not a code defect — `polars` is a declared dependency in `requirements.txt`).
- Integration tests (`test_quality_persistence_integration.py`) not run — they require a live PostgreSQL instance.

## Findings

### High

**H1 — Replay key collapses to `check_name` when context is omitted, causing silent data loss (`libs/quality/persistence.py:35-52, 122-197, 203`)**

`make_replay_key` maps a `None` `pipeline_run_id`, `observation_id`, or `source` to the literal `"_"` (lines 43-51). The public write APIs default these to `None` — `write_result(..., pipeline_run_id=None, observation_id=None)` and `write_suite_result(..., pipeline_run_id=None)` — and `QualityResult.source` also defaults to `None`. Consequently, the default call `writer.write_result(result)` produces the key `"<check_name>:_:_:_"`.

Because the INSERT uses `ON CONFLICT (replay_key) DO NOTHING` (line 197), a second, *distinct* execution of the same check (different `checked_at`, different data, different observation) with no context silently becomes a no-op. The module's own docstring defines replay safety as "two results with the same key represent the same logical check execution" — but two same-name results at different times with no context are *not* the same logical execution, and they still collide. `write_result.written = len(values)` (line 203) reports success, and the `skipped` counter is never incremented, so the caller receives no signal that rows were dropped. `write_suite_result` is also affected: it forwards `pipeline_run_id` but never `observation_id`, so a suite whose checks are scoped per-observation collides across observations.

Failure scenario: run `required_fields` twice in a row via `write_result(result)` (no context); the second write is discarded and `latest_status()` returns the stale first row indefinitely. This is the core deliverable — "replay-safe result identity" — and it fails in the default calling path.

Recommended fix: require `pipeline_run_id` (and `observation_id` for per-observation writes) rather than defaulting to `None`, or include an execution-scoped component in the key, or reject/populate-`skipped` when context is absent.

### Medium

**M1 — `ai/SPECIFICATION.md` §13 schema mismatch was not reconciled, and `source`/`status` are dropped from persistence (`libs/quality/persistence.py` vs `ai/SPECIFICATION.md:596` and `warehouse/schema/init.sql`)**

The higher-authority spec defines `data_quality_results` as `id, run_id, check_name, source, status, checked_at, records_checked, failed_records, details`, indexed by run/source/check. The actual table (created in TASK-027 and carried forward here) instead has `pipeline_run_id`, `observation_id`, `check_name`, `severity`, `passed`, `message`, and no `source` or `status` column. TASK-057 persists into the actual table and:

- drops `source` entirely — it is only embedded inside `replay_key`, never written to a column, never read back (`QualityResultRow` has no `source` field), and never indexed/queryable;
- collapses `status` (`passed`/`failed`/`skipped`) into the boolean `passed`, losing the `SKIPPED` distinction (moot today since no check emits `SKIPPED`, but a design smell);
- persists `severity`/`message`, which are not in the spec at all.

This is exactly the conflict flagged as **M1 in the TASK-056 Qwen review**, which stated it "must be reconciled before TASK-057 persistence." It was neither reconciled nor escalated nor documented. Per `AGENTS.md` §1, a conflict with a higher-authority document should have been escalated rather than silently resolved by picking the existing table schema.

**M2 — Migration/`init.sql` type drift for `details` (`warehouse/migrations/versions/004_quality_result_persistence.py:37` vs `warehouse/schema/init.sql`)**

Migration 004 declares `details` as `sa.JSON()` (renders to PostgreSQL `JSON`), while `init.sql` declares it `JSONB`, and migration 001's existing convention (e.g. `pipeline_runs.metadata`) uses `sa.dialects.postgresql.JSONB()`. A DB built by Alembic therefore has `details JSON`, while a fresh `init.sql` build has `details JSONB` — schema drift between the two bootstrap paths, and a break with the established migration convention. The reader/writer happen to tolerate both (`_map_row` has a `json.loads` fallback for the string form), so it is non-blocking, but it should be `JSONB` for consistency.

**M3 — `WriteResult.written` reports submitted rows, not inserted rows; `skipped` is never populated (`libs/quality/persistence.py:89, 203`)**

`written = len(values)` is set after `execute_batch` with `ON CONFLICT DO NOTHING`. On a replay/conflict, zero (or fewer) rows are actually inserted, but `written` still equals the input count and `success` is `True`. `WriteResult.skipped` exists but is never written. Combined with H1, the caller has no way to detect dropped rows. (Also flagged by the bundled OCR review.)

**M4 — `psycopg2` becomes a hard import-time dependency of the whole `libs.quality` package (`libs/quality/__init__.py:34-42`; `requirements.txt` vs `requirements-dev.txt`)**

`libs/quality/__init__.py` now unconditionally imports `persistence`, which imports `psycopg2` at module top level. But `psycopg2-binary` (and `sqlalchemy`/`alembic`) live only in `requirements-dev.txt`, not `requirements.txt`. The TASK-056 checks framework was explicitly "persistence-free" with no DB dependency; this change means `import libs.quality` now fails in any runtime that installs `requirements.txt` alone, even if the caller only wants the pure-Polars checks. The checks (`checks.py`, `runner.py`, `models.py`) should remain importable without a database driver — e.g. by lazy-importing `persistence`, or not re-exporting it from `__init__.py`.

### Low

**L1 — `replay_key` is `NOT NULL DEFAULT ''` under a UNIQUE constraint (`warehouse/migrations/versions/004_quality_result_persistence.py:41,43-47`; `init.sql`)**

Any insert that omits `replay_key` collides on `''` after the first row. During the migration itself, `server_default=''` backfills all pre-existing rows with `''`, so the `create_unique_constraint` would fail if `data_quality_results` already contained more than one row. Practically safe today (the table is empty), but fragile. (Also flagged by the bundled OCR review.)

**L2 — Empty `details` dict is round-tripped as `NULL`, not `{}` (`libs/quality/persistence.py:184`)**

`json.dumps(r.details) if r.details else None` converts the model's default `details={}` to SQL `NULL`. A result written with no details reads back as `None`, not `{}`. `test_read_preserves_details` only exercises a non-empty dict, so the lossy edge is untested.

**L3 — Integration tests break the hermetic-test convention (`tests/test_quality_persistence_integration.py:40,55,126`)**

This file uses `pytestmark = pytest.mark.skipif(not _db_available(), ...)` instead of the repo-wide `pytest.mark.integration` (used by every other integration file). Consequences: (a) `_db_available()` opens a live DB connection at module import/collection time on every plain `pytest` run; (b) when PostgreSQL is up, these tests run under a plain `pytest` rather than being opt-in via `-m integration`, contradicting `pyproject.toml`'s "plain test run stays fast and hermetic"; (c) they target the dev `platform` database (default `WAREHOUSE_DB_NAME="platform"`) rather than an isolated test DB like `warehouse_migration_test`/`warehouse_loader_test`.

**L4 — `latest_status` collapses contexts (`libs/quality/persistence.py:284-312`)**

`DISTINCT ON (check_name)` returns a single row per check name, but the replay key permits many rows per check name (distinct `source`/`observation_id`/`pipeline_run_id`). When context *is* provided, `latest_status` arbitrarily selects one context's latest row and cannot answer per-source or per-observation status — despite the spec's "indexed by run/source/check" intent. This is a direct consequence of M1's dropped `source`.

**L5 — `:` delimiter is unescaped in the replay key (`libs/quality/persistence.py:35-52`)**

A `check_name` or `source` containing `:` would produce ambiguous or colliding keys. Low risk today (check names are controlled), but worth a delimiter/escaping convention if the key format is ever opened up.

## Comparison Summary

The bundled OCR review (`docs/reviews/TASK-057-review.md`, reviewed commit `e6bed9f`) returned **APPROVED** with two Medium findings and no High. My review of the merge commit confirms:

- **OCR Medium #1 (`WriteResult.written` counts attempted vs actual inserts)** — confirmed, retained as **M3**.
- **OCR Medium #2 (UNIQUE constraint on `replay_key` with `server_default=''`)** — confirmed, retained as **L1** (practically safe today).
- The OCR review also noted that `skipped` exists but is never populated (folded into M3).

Findings the OCR review missed:

- **H1 (replay key collapse → silent data loss)** is the most consequential miss — it is the core deliverable and fails in the default path.
- **M1 (spec §13 schema mismatch unresolved, `source`/`status` dropped)** — this was a documented precondition from the TASK-056 Qwen review ("must be reconciled before TASK-057 persistence") and was not addressed.
- **M2 (JSON vs JSONB migration drift)**, **M4 (psycopg2 import-time coupling)**, and **L2–L5** are new.

A positive note the OCR review predates: the merge includes three follow-up fix commits (`eae24bf`, `f771c4b`, `bf667a6`) that corrected a real migration bug (`op.column()` → `sa.Column()`) and the migration-version assertion — evidence the migration path was validated after the initial review.

## Verdict

**CHANGES_REQUIRED.** The implementation is typed, deterministic, well-factored, and well-tested for the context-provided path (writer/reader round-trips, replay dedup with context, filters, details/counts preservation), and the follow-up commits show the migration was exercised. However:

- **H1** is a silent-data-loss defect in the exact deliverable the task names ("replay-safe result identity"), reachable through the default `write_result(result)` call, with no observability (the `skipped` counter is never populated).
- **M1** is an unresolved conflict with a higher-authority document (`ai/SPECIFICATION.md` §13) that the prior review explicitly required to be reconciled before persistence — it was neither reconciled nor escalated.

H1 and M1 should be resolved before this persistence layer is wired into the upcoming DAGs (TASK-059/060) and the FastAPI data-quality API (TASK-068); M2–M4 and the Low items are non-blocking follow-ups. No secrets were introduced, and no tests were weakened.
