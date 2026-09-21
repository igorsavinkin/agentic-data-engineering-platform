# TASK-094 Review — Read-Only SQL and Dataset Metadata Tools

## 1. Review Header

- **Task ID:** TASK-094 — Read-Only SQL and Dataset Metadata Tools
- **Review date:** 2026-09-21
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:** `81b6897c5bd57c5014b41ecc201aa6e14e5c2ba5...88fc61b38821b29660d525bb58b3c3d5b5c7c066`
- **Reviewed HEAD (commit):** `88fc61b38821b29660d525bb58b3c3d5b5c7c066` on `feature/TASK-094`
- **Merge base / prior HEAD:** `85ad147cce64ce4a38a79ecddd6526467d078fc3` ("Implement TASK-093: Intent Classifier (#106)")
- **Commits reviewed:**
  - `88fc61b` — `feat(TASK-094): Add read-only SQL and dataset metadata agent tools`
- **Scope:** Two agent tools — `execute_read_only_sql` (read-only SQL with query-level validation) and `get_dataset_metadata` (table schemas, column info, row counts) — built on a `DatabaseConnection` Protocol, plus 36 deterministic unit tests. No runtime component, no live database connection, no infrastructure, no new dependencies.
- **Verdict:** `CHANGES REQUIRED`

Sources of authority consulted: `ai/tasks/TASK-094-read-only-sql-and-dataset-metadata-tools.md`; `ai/PROJECT.md`; `ai/SPECIFICATION.md` §5, §17, §18, §21; `ai/ROADMAP.md` Milestone 11; `ai/AGENTS.md` §3/§6/§7/§10/§14; `ai/REVIEWER.md`; the TASK-092/093 implementations (`services/agent/state.py`, `services/agent/intents.py`, `services/agent/classifier.py`) and the prior TASK-093 review (`docs/reviews/TASK-093-review.md`). The sole ADR (`docs/adr/ADR-001-kafka-topic-configuration.md`) concerns Kafka topic configuration and is not applicable.

## 2. Requirements Coverage

| Requirement | Status | Evidence |
|---|---|---|
| Execute read-only SQL queries against PostgreSQL | ✅ Met (interface) | `execute_read_only_sql(query, db)` executes via the `DatabaseConnection` Protocol (`services/agent/tools.py:92`). No concrete PostgreSQL connection exists yet; connection is injected. |
| Enforce read-only at the connection and query level | ⚠️ Partially met | Query level: `validate_read_only` (`tools.py:73`) enforces a `SELECT`/`WITH` prefix plus a keyword blocklist. Connection level: **not implemented** — `DatabaseConnection` is only a Protocol; no read-only connection exists anywhere in the repo. See F2. |
| Reject DDL, DML, and any non-SELECT statement | ⚠️ Partially met | Blocklist catches `INSERT/UPDATE/DELETE/DROP/CREATE/ALTER/TRUNCATE/GRANT/REVOKE/EXEC/EXECUTE/CALL/MERGE/REPLACE/LOAD` and the prefix check rejects non-`SELECT`/`WITH`. Bypassable via `SELECT ... INTO` (creates a table in PostgreSQL) and side-effecting functions. See F2. |
| Retrieve dataset metadata — table schemas | ✅ Met | `get_dataset_metadata` + `TableMetadata`/`ColumnMetadata` model schema name, columns (name, data type, nullability, PK flag). |
| Retrieve dataset metadata — row counts | ✅ Met | `TableMetadata.row_count` populated via `db.get_row_count`. |
| Retrieve dataset metadata — partition info | ❌ Not met | No partition metadata is modeled or retrieved (`TableMetadata` has no partition fields; `DatabaseConnection` has no partition method). See F4. |
| Return structured results suitable for agent reasoning | ✅ Met | Pydantic models (`SQLResult`, `ToolResponse`, `ColumnMetadata`, `TableMetadata`, `DatasetMetadataResult`) serialized via `model_dump()`. |
| Agent must not have write access to PostgreSQL | ⚠️ Partially met | No write path exists today (tool is unwired), but the query-level gate is bypassable and connection-level read-only is absent. See F2. |
| Deterministic tests with fakes/mocks | ✅ Met | `FakeDatabaseConnection`; 36 tests, all hermetic (no DB/network/LLM). |
| Implement only this task; no unrelated changes or secrets | ✅ Met | Three-dot (merge-base) diff is two new files (+457 lines), purely additive. No secrets, no config/dependency changes. See §3 for the branch-topology note. |

## 3. Git Diff Review

**Merge-base (three-dot) diff `85ad147...88fc61b`:** 1 commit, 2 files, +457 lines (all additive).

Files changed:

- `services/agent/tools.py` (+142) — read-only SQL and dataset metadata tools, Pydantic result models, `DatabaseConnection` Protocol.
- `tests/agent/test_tools.py` (+315) — 36 deterministic unit tests.

**Scope correctness:** All changes belong to TASK-094. The tools build on the TASK-092 `ToolCallResult`/state vocabulary (though not yet wired) and do not drift into routing (TASK-098), the other tools (TASK-095–097), or the API (TASK-099), matching Milestone 11 sequencing.

**Unrelated/accidental changes:** None in the task-specific (merge-base) diff. No existing tracked file was modified by the TASK-094 commit.

**Branch-topology note (important for interpreting the requested range):** The specified base `81b6897` ("tech debt for TASK 129") is a commit on `main`, not an ancestor of `feature/TASK-094`. `main` and `feature/TASK-094` diverged from `85ad147`; `main` later gained `81b6897` (adding five "technical debt" lines to `ai/tasks/TASK-129-security-review.md`), which the feature branch does not contain. Consequently:

- `git diff 81b6897...88fc61b` (three-dot, merge-base → HEAD) → 2 files, clean (the correct task-specific diff).
- `git diff 81b6897..88fc61b` (two-dot, tree-to-tree) → additionally shows `ai/tasks/TASK-129-security-review.md | 5 -`. Those five deletions are **not** part of TASK-094; they are a phantom caused by comparing against `main`'s side commit. TASK-094 did not modify `ai/tasks/TASK-129-security-review.md`.

This is not a defect in the TASK-094 change, but the branch is one commit behind `main`; a normal rebase/merge before integration is expected.

**Architectural changes:** None. The change adds functions inside the normative `services/agent/` boundary (`ai/SPECIFICATION.md` §5) and preserves the agent's read-only posture in intent, though the enforcement itself is incomplete (see F2).

**Dependency/config changes:** None. `pyproject.toml`, `requirements*.txt`, and `docker-compose.yml` are untouched. Only `re`, `typing.Protocol`, and `pydantic` (already present) are used.

**Debug/temp/dead code/secrets:** No debug prints, temp files, generated artifacts, dead code, or secrets. No `__pycache__` committed.

**Branch and task isolation:** Reviewed HEAD is on `feature/TASK-094`; the range contains exactly one TASK-094 commit. Working tree is clean (`git status` → nothing to commit).

## 4. Test and Verification Review

**Tests added:** `tests/agent/test_tools.py` — 36 tests covering:

- `validate_read_only`: SELECT/WITH allowed (incl. lowercase, leading whitespace, CTE), empty/whitespace rejected, each blocked keyword rejected, non-SELECT prefix rejected, blocked keywords inside string literals rejected.
- `execute_read_only_sql`: success path, empty result, validation failure, database exception, query forwarding.
- `get_dataset_metadata`: explicit table names, auto-discovery, default schema, column defaults, database exception, multiple tables.
- Model serialization and optional `row_count`.

**Independently verified (executed by reviewer):**

- `python -m pytest tests/agent/test_tools.py -v` → **36 passed** in 0.38s.
- `python -m pytest tests/agent/ -q` → **71 passed** (TASK-092/093/094 suites) in 0.40s.
- `python -m ruff check services/agent/tools.py tests/agent/test_tools.py` → **All checks passed**.
- `python -m ruff format --check services/agent/tools.py tests/agent/test_tools.py` → **2 files already formatted**.
- `python -m mypy tests/agent` → **FAILED — 3 errors** in `tests/agent/test_tools.py` (see F1).
- `python -m mypy` (full configured gate: `files = ["scripts", "tests", "libs"]`) → **FAILED — 3 errors** in `tests/agent/test_tools.py` (the only failing file among 186 checked).

**Implementation evidence reviewed (not rerun):** The commit message reports "36 deterministic tests" but contains no evidence that `mypy` or `ruff` were run; the independent execution above is the authoritative verification for this review.

**Unverified / not rerun:**

- The full repository pytest suite was **not rerun** (the change is purely additive, and the full `tests/agent/` suite plus lint/format/type checks were run instead).
- No integration tests are relevant: the task touches no Kafka, persistence, MinIO/S3, or infrastructure boundary (the tools are wired to no live DB). The default `addopts = "-m 'not integration'"` has no bearing here.

## 5. Findings

### F1 — High — New test file fails the repository `mypy` gate (3 errors)

- **File:** `tests/agent/test_tools.py` (lines 194, 261, 266).
- **Problem:** `python -m mypy` (the configured gate, `files = ["scripts", "tests", "libs"]`) reports three errors, all in the newly committed test file:
  - `tests\agent\test_tools.py:194: Unsupported right operand type for in ("str | None")` — `assert "connection lost" in response.error` uses `in` on `response.error`, which is `str | None`.
  - `tests\agent\test_tools.py:266: Unsupported right operand type for in ("str | None")` — `assert "db down" in response.error`, same cause.
  - `tests\agent\test_tools.py:261: Unused "type: ignore" comment, use narrower [method-assign] instead of [assignment]` — the `# type: ignore[assignment]` is unnecessary/wrongly scoped.
- **Impact:** The committed change does **not** pass the repository's type-check gate. This directly violates `ai/AGENTS.md` §7 ("run lint/format/type checks") and the task's Definition of Done ("checks pass"). The failure is confined to the test file (production `services/agent/tools.py` is outside the configured mypy `files` scope), but it is still a green-build blocker.
- **Recommendation:** Narrow the type before the `in` checks (e.g. assert `response.error is not None` first, or use `response.error == "connection lost"`), and remove or correct the `# type: ignore[assignment]` comment at line 261. Re-run `python -m mypy`.

### F2 — High — Read-only enforcement is incomplete: no connection-level read-only and a query-level DDL bypass

- **File:** `services/agent/tools.py` (lines 55–59 `_BLOCKED_KEYWORDS`, 62–70 `DatabaseConnection`, 73–89 `validate_read_only`).
- **Problem:** The task requires "SQL tools must enforce read-only access at the connection and query level" and "reject DDL, DML, and any non-SELECT statements."
  - **Connection level:** `DatabaseConnection` is only a `Protocol`; the tool delegates all connection behavior to the caller. No read-only PostgreSQL connection exists anywhere in the repository (all existing `psycopg2` connections in `libs/quality/persistence.py`, `warehouse/loader/batch_loader.py`, and Airflow DAGs are read-write). The "connection level" half of the requirement is therefore unimplemented.
  - **Query level:** the validator is a keyword blocklist + `SELECT`/`WITH` prefix check. This is bypassable. Independently verified: `validate_read_only("SELECT * INTO new_table FROM products")` returns `None` (allowed), yet `SELECT ... INTO` **creates a table** in PostgreSQL — a DDL/write operation that violates "reject DDL". Side-effecting functions reachable from `SELECT` (e.g. `setval`, `nextval`, `lo_from_bytea`, and `dblink_exec` if the extension is installed) also pass the blocklist.
- **Impact:** The core security property (agent has no write access to PostgreSQL; `ai/AGENTS.md` §10, `ai/SPECIFICATION.md` §17 "The SQL tool must be read-only" and §21 "read-only SQL agent") is not robustly enforced. There is no live exploit today because no database connection is wired yet (deferred to TASK-099), but the enforcement design does not satisfy the explicit requirement and the module docstring's claim that "DDL, DML, and any non-SELECT statements are rejected" is false.
- **Recommendation:** Before the tool is wired to PostgreSQL, (a) implement a concrete read-only connection (`default_transaction_read_only=on` or a least-privilege read-only role) and make the transaction read-only the primary enforcement; and (b) harden the query-level check — at minimum reject `SELECT ... INTO`, and prefer tokenization/parsing (e.g. `sqlparse`/`pglast`) over a keyword blocklist for the "reject DDL/DML" goal.

### F3 — Moderate — Keyword blocklist over-blocks legitimate SELECTs (false positives codified by tests)

- **File:** `services/agent/tools.py` (lines 55–59, 85–87); `tests/agent/test_tools.py` (`test_blocked_keyword_inside_select`, `test_select_with_insert_keyword_in_string`, `test_select_with_drop_keyword_in_string`).
- **Problem:** `_BLOCKED_KEYWORDS.search(stripped)` scans the entire query text, including string literals and quoted identifiers, so a read-only query such as `SELECT * FROM t WHERE action = 'INSERT'` is rejected as "Blocked keyword found: INSERT". The tests explicitly assert this incorrect behavior, locking in the false positive.
- **Impact:** Legitimate analytical queries containing these words in string literals will be refused, reducing the tool's usefulness for exactly the analytical work it is meant to serve. This is a functional defect, not a security hole.
- **Recommendation:** Do not match blocked keywords inside single-quoted strings, double-quoted identifiers, or `--`/`/* */` comments. Tokenize the query, or drop the keyword scan in favor of connection-level read-only plus a stricter prefix/`INTO` check.

### F4 — Moderate — "Partition info" from the objective is not implemented

- **File:** `services/agent/tools.py` (`TableMetadata` lines 40–46, `DatasetMetadataResult` lines 49–52, `get_dataset_metadata` lines 107–141); `ai/tasks/TASK-094-read-only-sql-and-dataset-metadata-tools.md` Objective.
- **Problem:** The objective explicitly lists "partition info" among the dataset metadata to retrieve ("table schemas, row counts, partition info"). The implementation returns schema name, columns, and row count, but has no partition model, no `DatabaseConnection` method, and no retrieval path for partition metadata.
- **Impact:** The delivered `dataset_metadata` tool is missing a stated requirement. Downstream consumers that expect partition information (e.g. partitioned Gold tables or the Parquet/dataset layer) will find it unavailable.
- **Recommendation:** Clarify the intended meaning of "partition info" (PostgreSQL declarative partitions vs. data-lake Parquet partitions) and add a corresponding field/method, or explicitly document and defer it with a follow-up task if it belongs to a later milestone.

### F5 — Minor — Raw exception text returned to the agent

- **File:** `services/agent/tools.py` (lines 103–104, 141–142).
- **Problem:** Both tools catch `Exception` and return `str(e)` verbatim in `ToolResponse.error`. Database exceptions can include connection strings, schema/table names, and internal SQL fragments.
- **Impact:** Low-risk information disclosure once wired; the error text is also not stable/structured for agent reasoning.
- **Recommendation:** Return a sanitized/generic message and log the full exception server-side.

### F6 — Minor — No guardrails on result size, query cost, or multi-statement execution

- **File:** `services/agent/tools.py` (`execute_read_only_sql` lines 92–104).
- **Problem:** There is no row limit, statement timeout, or rejection of multiple statements (`SELECT 1; SELECT 2` passes validation and would be forwarded to the driver). An agent-generated query could materialize a very large result or run long enough to degrade the serving DB.
- **Impact:** Operational risk once the tool is wired to a live PostgreSQL instance.
- **Recommendation:** Add a configurable row cap and statement timeout, and consider rejecting multiple statements (the tool is meant for single read-only analytical queries).

## 6. Non-Defect Observations

- **N1 — Standalone, correctly deferred integration.** The tools are intentionally not wired into routing or the agent graph. Per `ai/ROADMAP.md` Milestone 11, routing is TASK-098 and the API is TASK-099; keeping the tools as pure, isolated functions over a `Protocol` is the right scope for TASK-094.
- **N2 — `services/agent/` is outside the configured mypy gate.** `pyproject.toml` sets `[tool.mypy] files = ["scripts", "tests", "libs"]`, so `services/agent/tools.py` is not type-checked by the repository gate (it is still lint/format-checked and fully exercised by tests). This is consistent with TASK-092/093 and pre-existing; note that the *test* file is inside the gate and does fail it (F1).
- **N3 — Strong, focused test coverage.** The 36 tests exercise the full requirement surface (validation allow/block matrix, success/empty/error paths, metadata discovery/defaults, model serialization). Coverage is more than the minimum.
- **N4 — `services/agent/README.md` not updated; not required.** The task's Definition of Done says "documentation updated where needed". The README already states the agent uses "explicit read-only tools over platform state", so no additional documentation is warranted.
- **N5 — Result serialization uses `model_dump()`.** `ToolResponse.data` is a plain dict rather than a nested typed model. This is a reasonable serialization choice for an agent-facing tool and does not affect correctness.
- **N6 — Clean scope and hygiene.** No secrets, no debug artifacts, no dependency or config churn; the branch is clean and correctly named `feature/TASK-094`.

## 7. Verdict

**`CHANGES REQUIRED`**

The TASK-094 implementation is well-structured, cleanly scoped, and thoroughly unit-tested: two in-scope new files, 36 deterministic tests that all pass, and clean `ruff check` / `ruff format --check`. The structured Pydantic results and the `DatabaseConnection` Protocol are idiomatic and consistent with the preceding TASK-092/093 work.

However, the change does not yet meet the task's core requirements or the repository's quality gate, and should not be accepted as-is:

1. **F1 (High):** The committed `tests/agent/test_tools.py` fails the repository `mypy` gate with 3 errors (`python -m mypy` → "Found 3 errors in 1 file"). This is an independently verified, unambiguous violation of `ai/AGENTS.md` §7 and the Definition of Done ("checks pass").
2. **F2 (High):** Read-only enforcement is incomplete. There is no connection-level read-only (the task requires "at the connection and query level"), and the query-level validator has a concrete DDL bypass — `SELECT ... INTO` passes validation yet creates a table in PostgreSQL, plus side-effecting functions reachable from `SELECT`. The task's central "reject DDL/DML, read-only" property is not robustly met.
3. **F3/F4 (Moderate):** The blocklist over-blocks legitimate queries (keywords in string literals, codified by tests), and the objective's "partition info" metadata is not implemented.

F1 and F2 are blocking. The remaining findings (F3–F6) are non-blocking but should be addressed alongside. None of the blocking issues requires an architecture decision; both are localized fixes (type narrowing in tests; a read-only connection plus a hardened `SELECT ... INTO`/tokenized validation) that can be completed without leaving TASK-094's scope.
