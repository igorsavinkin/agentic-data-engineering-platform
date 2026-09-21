# TASK-099 Review — Agent API (Final)

## 1. Review Header

| Field | Value |
|---|---|
| Task ID | TASK-099 — Agent API |
| Review date | 2026-09-21 |
| Reviewer | Qwen Code (independent review, no code modified) |
| Review round | Final — re-review after `f6ce36a` addressed the round-2 blocking findings |
| Reviewed change set / Git range | `7a22c5a6be54824d1b257ea5039a506da56a76f0...f6ce36ab770dcc95d7842cc317cb2b07f675623f` |
| Reviewed commit | `f6ce36ab770dcc95d7842cc317cb2b07f675623f` — `fix(TASK-099): add connection-level read-only and fix mypy regression` |
| Commits in range | `2c3bd0e` (feat: `/agent/ask` endpoint), `666293e` (fix: round-2 findings), `f6ce36a` (fix: connection-level read-only + mypy) |
| Reviewed HEAD | `f6ce36ab770dcc95d7842cc317cb2b07f675623f` on `feature/TASK-099` |
| Scope | `services/agent/db_adapter.py`, `services/api/routes/v1/agent.py`, `services/api/routes/v1/router.py`, `services/api/schemas.py`, `tests/agent/test_db_adapter.py`, `tests/api/routes/v1/test_agent.py` |
| Diff stat | 6 files changed, 487 insertions(+), 0 deletions(-) |
| Verdict | **APPROVED WITH NON-BLOCKING FINDINGS** |

**Authorities consulted:** `ai/tasks/TASK-099-agent-api.md`, `ai/PROJECT.md` (§2, §4, §11), `ai/SPECIFICATION.md` (§16 API endpoints, §17 LangGraph Data Engineer Agent, §18 Agent State), `ai/ROADMAP.md` (Milestone 11 — LangGraph Agent), `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, `ai/REVIEWER.md`; the surrounding agent implementation (`services/agent/*`, `services/api/*`) and the round-2 review of this task. The sole ADR (`docs/adr/ADR-001-kafka-topic-configuration.md`) concerns Kafka and is not applicable.

**Sequencing note:** TASK-098 introduced the real LangGraph `StateGraph` (verified present in `services/agent/graph.py`: `StateGraph`, `START`, `END`, `add_conditional_edges`, `compile()`), so TASK-099 builds on a genuine LangGraph graph. This review focuses on the API exposure and the database-adapter read-only enforcement added by TASK-099.

---

## 2. Requirements Coverage

Requirements are taken from `ai/tasks/TASK-099-agent-api.md` and corroborated by `ai/PROJECT.md` and `ai/SPECIFICATION.md` (§16, §17).

| # | Requirement | Status | Implementation evidence |
|---|---|---|---|
| R1 | Expose the LangGraph agent through a FastAPI endpoint accepting natural-language questions | ✅ Met | `services/api/routes/v1/agent.py` defines `POST /api/v1/agent/ask` (`AgentAskRequest.question`), builds a `GraphContext`, calls `build_agent_graph(context).run(body.question)` |
| R2 | Return structured agent responses | ✅ Met | `AgentAskResponse` (`answer`, `intent`, `confidence`, `sources`) in `services/api/schemas.py`, inheriting the `APIResponse` envelope |
| R3 | Integrate with the existing API service | ✅ Met | Router registered in `router.py`; uses `get_db`, `APIError`, existing repositories (`PipelineStatusRepository`, `DataQualityRepository`) and agent adapters |
| R4 | Support streaming or synchronous response | ✅ Met (synchronous) | `graph.run()` invoked synchronously; streaming not chosen, which the task permits ("or") |
| R5 | Handle timeouts gracefully | ✅ Met (by design) | Graph is deterministic and in-process (keyword classifier, no LLM/network calls); DB queries carry engine-level timeouts. No explicit timeout wrapper is warranted yet (see N1) |
| R6 | Handle errors gracefully | ✅ Met | Broad `except Exception` around `graph.run()` → structured `APIError(500, "AGENT_ERROR")`; `state.response is None` → `APIError(500, "AGENT_NO_RESPONSE")` |
| R7 | Agent uses controlled tools and read-only SQL; never write to PostgreSQL | ✅ Met | Query-level guard (`validate_read_only` in `db_adapter.execute`) plus connection/transaction-level guard (`SET TRANSACTION READ ONLY` for PostgreSQL in `SQLAlchemyDatabaseConnection.__init__`) |
| R8 | Keep the API surface minimal | ✅ Met | One endpoint, two small schema models |
| R9 | Deterministic tests added | ✅ Met | 9 endpoint tests + 9 adapter tests, all deterministic and passing (18 total) |

---

## 3. Git Diff Review

Full-range diff (`git diff --stat 7a22c5a...f6ce36a`):

```
 services/agent/db_adapter.py      | 105 ++++++++++++++++++++
 services/api/routes/v1/agent.py   |  74 ++++++++++++++
 services/api/routes/v1/router.py  |   2 +
 services/api/schemas.py           |  15 +++
 tests/agent/test_db_adapter.py    |  92 ++++++++++++++++++
 tests/api/routes/v1/test_agent.py | 199 ++++++++++++++++++++++++++++++++++++++
 6 files changed, 487 insertions(+)
```

- **Scope correctness:** All six files belong to TASK-099. No files from other tasks are touched.
- **Unrelated changes:** None. The diff is purely additive.
- **Architectural changes:** None. The route composes the existing agent graph/adapters and API repositories; no service boundary is altered. PostgreSQL remains the read-only serving/analytical store; the agent gains no write path.
- **Accidental changes / debugging code / dead artifacts / secrets:** None. No debug prints, temporary files, generated artifacts, or secrets. `git diff --check` reports no whitespace errors.
- **Dependency/configuration changes:** None. No new third-party dependencies; `pyproject.toml`, `requirements*.txt`, and `docker-compose.yml` are untouched (`langgraph` was already added in TASK-098).
- **Branch/task isolation:** Clean. Branch is `feature/TASK-099`; all three commits in range are TASK-099. No cross-task leakage. The working tree contains only the untracked review file being written here.

---

## 4. Test and Verification Review

### Tests examined

- `tests/api/routes/v1/test_agent.py` (9 tests): pipeline-status, data-quality, source-health, general fallback, empty/missing/whitespace question (422), `sources` list, and no-data behavior.
- `tests/agent/test_db_adapter.py` (9 tests): `execute` read-only enforcement (insert/delete/drop/update/empty/multi-statement rejected, CTE allowed) plus `get_row_count`.

### Tests independently executed (reviewer)

| Command | Result |
|---|---|
| `python -m pytest tests/agent/test_db_adapter.py tests/api/routes/v1/test_agent.py -q` | **18 passed** |
| `python -m pytest tests/agent tests/api -q` | **346 passed** |
| `python -m ruff check <6 changed files>` | **All checks passed** |
| `python -m ruff format --check <6 changed files>` | **6 files already formatted** |
| `python -m mypy` (full project config: `scripts`, `tests`, `libs`) | **Success: no issues found in 192 source files** |
| `git diff --check <range>` | clean (no output) |

### Verification classification

- Unit/endpoint tests: **Independently verified** (executed by reviewer — 346 passed).
- Lint/format: **Independently verified**.
- Type check (mypy): **Independently verified — PASSES** (round-2 Finding 1 resolved; previously failing with 1 error).
- Integration tests (`python -m pytest -m integration`): **Unverified** — not executed (requires Docker/PostgreSQL, unavailable in this environment). This is material because `db_adapter.py` issues PostgreSQL-specific `information_schema.*` / `information_schema.key_column_usage` queries and `SET TRANSACTION READ ONLY` semantics that are not exercised by the SQLite-backed unit tests, and the endpoint tests never route to the `execute_sql` node (no price-analytics/product-history question).

---

## 5. Findings

Round-2's two blocking findings are resolved. The following findings remain, all **Minor** (non-blocking).

### F1 — Minor — `execute`'s `params` parameter is still silently ignored

- **File / line:** `services/agent/db_adapter.py:51` (signature) and `:56` (`self._session.execute(text(query))`)
- **Problem:** The `params: tuple[Any, ...] | None = None` parameter remains in the signature and is never used. Any caller passing `params` would have them silently dropped; a query with `:name` or `?` placeholders would then fail at the SQLAlchemy/DB layer or produce wrong behavior. This is the `DatabaseConnection` protocol's public method.
- **Impact:** Latent — no current code path calls `execute` with parameters (the graph uses `get_dataset_metadata`, not `execute`). It is a footgun for the next consumer.
- **Recommendation:** Remove the unused parameter (simplest, since no caller uses it) or implement correct binding (positional sequence for `?`/`:%s`-style, or a dict for `:name`-style) with a unit test.

### F2 — Minor — PostgreSQL-specific metadata methods and connection-level read-only remain untested

- **File / line:** `services/agent/db_adapter.py:32-76` (`get_columns`, `list_tables`, `_primary_key_columns`) and `:42-58` (`_enforce_connection_read_only`); `tests/agent/test_db_adapter.py` (no coverage of those methods)
- **Problem:** The new test file covers `execute` and `get_row_count` only (both SQLite-portable). `list_tables`, `get_columns`, and `_primary_key_columns` issue PostgreSQL `information_schema` SQL and are never exercised; the connection-level `SET TRANSACTION READ ONLY` path is likewise never exercised (the SQLite test session has dialect `sqlite`, so `_enforce_connection_read_only` is a no-op). Integration tests (`-m integration`) were not run.
- **Impact:** The metadata path and the database-layer read-only guard — the two genuinely PostgreSQL-specific pieces of this task — are unverified against a real database.
- **Recommendation:** Add an integration test (marked `integration`) that exercises `get_columns`/`list_tables`/`_primary_key_columns`/`get_dataset_metadata` against real PostgreSQL and proves a write attempt fails at the database, not only at the Python `validate_read_only` layer. Optionally add an endpoint test that routes a price-analytics question through `execute_sql`.

### F3 — Minor — Endpoint path differs from the SPECIFICATION example

- **File / line:** `services/api/routes/v1/agent.py:23` (`@router.post("/ask")`, `prefix="/agent"`)
- **Problem:** `ai/SPECIFICATION.md` §16 lists the initial endpoint as `POST /agent/query`; the implementation exposes `POST /api/v1/agent/ask`.
- **Impact:** The spec's list is illustrative ("Initial endpoints:"), and the task text does not mandate a path, so this is not a functional defect — but it is an undocumented deviation from a documented example.
- **Recommendation:** Either align the path with the spec or record the deliberate rename in task/docs.

### F4 — Minor — `get_row_count` still interpolates identifiers (mitigated)

- **File / line:** `services/agent/db_adapter.py:62-67`
- **Problem:** `get_row_count` builds `SELECT COUNT(*) FROM "{schema}"."{table}"` via f-string. The round-2 fix added `schema.replace('"', "")` / `table.replace('"', "")`, which removes embedded double-quotes before re-quoting and thereby neutralizes the identifier-injection vector (a value like `products" WHERE …` is reduced to a single invalid identifier rather than breaking out).
- **Impact:** Low — `schema` defaults to `"public"` and `table` comes from `information_schema.tables` (not user input), so it was never directly injectable. Remaining concern is code quality adjacent to a read-only SQL boundary.
- **Recommendation:** Prefer SQLAlchemy identifier quoting (e.g. `sqlalchemy.sql.quoted_name`) for robustness rather than ad-hoc quote-stripping.

---

## Round-2 Findings — Disposition

| Round-2 finding | Severity (R2) | Disposition in `f6ce36a` |
|---|---|---|
| Finding 1 — mypy regression in `tests/agent/test_db_adapter.py` (generator fixture `-> Session`) | Moderate | **Resolved** — fixture now annotated `-> Generator[Session, None, None]`; `python -m mypy` is clean (192 files) |
| Finding 2 — connection-level read-only not enforced | Moderate | **Resolved (transaction-level)** — `_enforce_connection_read_only` issues `SET TRANSACTION READ ONLY` for PostgreSQL in `__init__`; query-level `validate_read_only` retained. Integration proof still absent → F2 |
| Finding 3 — `execute` `params` silently ignored | Minor | **Unaddressed** → F1 |
| Finding 4 — PostgreSQL metadata methods untested | Minor | **Unaddressed** → F2 |
| Finding 5 — `/agent/ask` vs spec `/agent/query` | Minor | **Unaddressed** → F3 |
| Finding 6 — `get_row_count` identifier interpolation | Minor | **Unaddressed** → F4 |

---

## 6. Non-Defect Observations

- **N1 — "Handle timeouts gracefully" is effectively satisfied by design.** The graph is fully deterministic (keyword classifier, no LLM, no network, no IO other than the DB session), so `graph.run()` cannot realistically hang; the only blocking call is DB queries, which carry engine-level timeouts. No explicit timeout wrapper is warranted until a genuinely long-running (e.g. LLM) step is added.
- **N2 — Read-only is now enforced at two layers.** Query-level `validate_read_only` (tested) is the primary guard; `SET TRANSACTION READ ONLY` is defense-in-depth for PostgreSQL. The endpoint never reaches `execute` (it only calls `get_dataset_metadata`, which issues hard-coded read-only `information_schema` queries), so there is no live write path today.
- **N3 — The connection-level guard is transaction-scoped and fail-open.** `_enforce_connection_read_only` sets read-only for the *current* transaction and swallows exceptions (`except Exception: return`). It is effective within the single-request scope (no commit occurs in the agent path), but a failure to set it (e.g. a future reordering that begins a transaction first) would degrade silently to query-level-only enforcement. The docstring is honest about this and correctly defers a dedicated read-only PostgreSQL role to production. This is acceptable defense-in-depth, not a defect.
- **N4 — Clean reuse of existing layers.** The route composes `RepositoryPipelineStatusProvider`, `RepositoryDataQualityProvider`, `RepositorySourceHealthProvider`, and the read-only repositories rather than duplicating business logic — consistent with the agent package's established adapter pattern.
- **N5 — Deterministic and read-only by construction.** All data access is through injected providers and validated read-only queries; no LLM inference, so the "never hallucinate platform state" rule is honored. The read-only tests cover insert/delete/drop/update/empty/multi-statement and allow CTEs, giving good coverage of the security-critical validation.
- **N6 — Response mapping is type-correct.** `intent=response.intent.value`, bounded `confidence`, and `sources` flow into a typed `AgentAskResponse` inheriting the `APIResponse` envelope, consistent with the project's response conventions.
- **N7 — No secrets, credentials, or keys introduced.**

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The round-2 blocking findings are resolved: the mypy regression is fixed (full `python -m mypy` is clean at 192 files), and connection/transaction-level read-only enforcement is now implemented via `SET TRANSACTION READ ONLY` alongside the retained query-level `validate_read_only` guard. The endpoint, adapter, and schema are correctly scoped, minimal, and well tested; 346 unit/endpoint tests, `ruff check`, `ruff format --check`, and `git diff --check` all pass under independent execution.

The four remaining findings (F1–F4) are **Minor** and non-blocking: the unused `execute` `params` parameter, the untested PostgreSQL-specific metadata methods and connection-level read-only (no integration test evidence), the `/agent/ask` vs `/agent/query` path deviation, and the remaining identifier-interpolation smell in `get_row_count`.

**Verification note:** unit/endpoint tests (346), lint, format, and the full type check were independently executed and passed. Integration tests (`python -m pytest -m integration`) were **not** run (Docker/PostgreSQL unavailable in this environment), leaving the PostgreSQL-specific `information_schema` queries and the `SET TRANSACTION READ ONLY` semantics unverified against a real database — the single most valuable remaining verification step, tracked as F2.
