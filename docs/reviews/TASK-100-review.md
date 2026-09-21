# TASK-100 Review — Agent Tests

## 1. Review Header

| Field | Value |
|---|---|
| Task ID | TASK-100 — Agent Tests |
| Review date | 2026-09-21 |
| Reviewer | Qwen Code (independent review, no code modified) |
| Reviewed change set / Git range | `7d0430b71d475abfcba24f1fbcf8f706989923c1...39da69a3f6100730531e9e01eaf6d75566613eef` |
| Reviewed commit | `39da69a3f6100730531e9e01eaf6d75566613eef` — `feat(TASK-100): add comprehensive end-to-end agent tests` |
| Commits in range | `39da69a` (single commit; parent is `7d0430b`, the TASK-099 Agent API commit) |
| Reviewed HEAD | `39da69a3f6100730531e9e01eaf6d75566613eef` on `feature/TASK-100` |
| Scope | `tests/agent/test_agent_e2e.py` (new, 423 insertions, 0 deletions) |
| Diff stat | 1 file changed, 423 insertions(+), 0 deletions(-) |
| Verdict | **APPROVED WITH NON-BLOCKING FINDINGS** |

**Authorities consulted:** `ai/tasks/TASK-100-agent-tests.md`, `ai/PROJECT.md` (§2, §4, §11, §12), `ai/SPECIFICATION.md` (§16 FastAPI, §17 LangGraph Data Engineer Agent, §18 Agent State), `ai/ROADMAP.md` (Milestone 11 — LangGraph Agent, acceptance list), `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, `ai/REVIEWER.md`; the surrounding agent implementation (`services/agent/graph.py`, `classifier.py`, `tools.py`, `state.py`, `intents.py`, `services/api/routes/v1/agent.py`) and the existing agent test suite (`tests/agent/test_*.py`, `tests/api/routes/v1/test_agent.py`). The sole ADR (`docs/adr/ADR-001-kafka-topic-configuration.md`) concerns Kafka and is not applicable.

**Sequencing note:** TASK-092 through TASK-099 each shipped their own unit tests alongside implementation (classifier, tools, adapters, graph, endpoint). TASK-100 is the final Milestone-11 item and contributes the graph-level end-to-end layer that ties those pieces together. This review evaluates the TASK-100 delta (the single new e2e file) against the milestone's overall test-coverage objective.

---

## 2. Requirements Coverage

Requirements are taken from `ai/tasks/TASK-100-agent-tests.md` and corroborated by `ai/ROADMAP.md` (Milestone 11 acceptance) and `ai/PROJECT.md` (§11 read-only agent, §12 testing).

| # | Requirement | Status | Implementation evidence |
|---|---|---|---|
| R1 | Comprehensive tests covering **intent classification** | ✅ Met (indirectly) | Every e2e test asserts `state.response.intent == IntentType.X` through the full `classify → route → tool → compose` pipeline; classification is exercised end-to-end, while dedicated classifier unit tests remain in `tests/agent/test_classifier.py` (TASK-093) |
| R2 | Comprehensive tests covering **tool invocation** | ✅ Met | `test_*_uses_tool` asserts `tool_calls[0].tool_name == "get_<tool>"` and `tool_results[0].success is True` for pipeline, quality, source, and price/metadata intents |
| R3 | Comprehensive tests covering **routing logic** | ✅ Met | `test_full_context_routes_correctly` and `test_each_intent_invokes_exactly_one_tool` assert the correct single tool for each of the four routed intents |
| R4 | Comprehensive tests covering **API endpoint** | ⚠️ Partially (not in this commit) | The TASK-100 commit adds **no** HTTP-level tests. Endpoint coverage lives in TASK-099's `tests/api/routes/v1/test_agent.py` (9 tests). See F1 |
| R5 | Comprehensive tests covering **end-to-end question answering** | ✅ Met | 20 graph-level e2e tests run `build_agent_graph(ctx).run(question)` end to end with mocked providers |
| R6 | Verify the agent **uses tools rather than hallucinating state** | ✅ Met | `TestAgentUsesToolsNotHallucination` (3 tests) proves the graph still issues the tool call and returns a "not available"/error answer when a provider is absent; `TestAgentReadOnlyGuarantee` proves no raw SQL path |
| R7 | Cover edge case: **unrecognized intents** | ✅ Met | `TestEndToEndUnrecognizedIntents` (random question, empty, greeting → `IntentType.GENERAL`, zero tool calls) |
| R8 | Cover edge case: **tool failures** | ✅ Met | `TestEndToEndToolFailures` (provider exception, missing DB for SQL intent, all-tools-fail → error answers) |
| R9 | Verify example questions ("largest price increases", "freshness problems", "observations drop") are answered using tools | ⚠️ Partially | "Which products had the largest price increases?" (`test_price_question_routes_to_sql`) and "Which sources have freshness problems?" (`test_source_freshness_question_uses_tool`) are covered. "Why did observations drop yesterday?" is **not** exercised e2e — only at the classifier level (`test_classifier.py`). See F2 |
| R10 | Agent must not have write access to PostgreSQL | ✅ Met (graph-level) | `test_agent_graph_has_no_write_capability` whitelists tool names; `test_execute_sql_node_calls_metadata_not_raw_sql` asserts `db.execute.assert_not_called()` and `db.list_tables.assert_called()` |
| R11 | Tests must be **deterministic**; mock LLM calls and external dependencies | ✅ Met | No LLM, network, or DB IO; providers are `MagicMock`/in-memory fakes; classifier is keyword-deterministic |

---

## 3. Git Diff Review

Full-range diff (`git diff --stat 7d0430b...39da69a`):

```
 tests/agent/test_agent_e2e.py | 423 ++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 423 insertions(+)
```

- **Scope correctness:** The single file belongs to TASK-100. The commit is purely additive (a new test module); no production code is touched.
- **Unrelated changes:** None. No files from other tasks are modified.
- **Architectural changes:** None. No service boundary, contract, or dependency altered.
- **Accidental changes / debugging code / dead artifacts / secrets:** None. No debug prints, temporary files, generated artifacts, or secrets. `git diff --check` reports no whitespace errors.
- **Dependency/configuration changes:** None. `pyproject.toml`, `requirements*.txt`, and `docker-compose.yml` are untouched. The test file uses only `unittest.mock.MagicMock` and existing `services.agent` imports.
- **Branch/task isolation:** Clean. Branch is `feature/TASK-100`; the range contains exactly one TASK-100 commit whose parent is the TASK-099 commit (`7d0430b`). No cross-task leakage. The working tree is clean apart from this review file.

---

## 4. Test and Verification Review

### Tests examined

- `tests/agent/test_agent_e2e.py` (20 tests, the reviewed change): end-to-end pipeline/quality/source/price routing, tool-failure handling, unrecognized-intent fallback, "uses tools not hallucination", read-only guarantee, and full-context routing.
- `tests/agent/test_classifier.py`, `test_graph.py`, `test_tools.py` (pre-existing): reviewed to determine whether TASK-100's e2e layer duplicates or fills a gap — it fills the graph-integration gap; the unit layers remain the primary coverage for classification, individual tools, and `_format_tool_answer`/`_compose_response_node`.
- `tests/api/routes/v1/test_agent.py` (pre-existing, TASK-099): reviewed because the objective names "API endpoint" as a coverage area.

### Tests independently executed (reviewer)

| Command | Result |
|---|---|
| `python -m pytest tests/agent/test_agent_e2e.py -q` | **20 passed** |
| `python -m pytest tests/agent -q` | **209 passed** |
| `python -m pytest tests/api/routes/v1/test_agent.py -q` | **9 passed** (1 third-party deprecation warning) |
| `python -m ruff check tests/agent/test_agent_e2e.py` | **All checks passed** |
| `python -m ruff format --check tests/agent/test_agent_e2e.py` | **1 file already formatted** |
| `python -m mypy tests/agent/test_agent_e2e.py` | **Success: no issues found in 1 source file** |
| `git diff --check 7d0430b...39da69a` | clean (no output) |

### Verification classification

- Unit/e2e tests (agent suite, 209): **Independently verified** — executed by reviewer.
- Lint/format: **Independently verified**.
- Type check (single-file mypy): **Independently verified**.
- Integration tests (`python -m pytest -m integration`): **Unverified** — not executed (requires Docker/PostgreSQL, unavailable in this environment). This is acceptable for a test-only change that is entirely graph-level and mocked, but note the read-only guarantee against a real PostgreSQL database remains unverified (carried forward from TASK-099 Finding F2).

---

## 5. Findings

### F1 — Minor — Objective names "API endpoint", but TASK-100 adds no endpoint tests

- **File / line:** `tests/agent/test_agent_e2e.py` (entire file); gap relative to `ai/tasks/TASK-100-agent-tests.md` objective
- **Problem:** The objective explicitly lists "API endpoint" among the areas to cover, yet the TASK-100 commit adds only graph-level tests. The endpoint is tested only in TASK-099's `tests/api/routes/v1/test_agent.py`.
- **Impact:** Low — the endpoint coverage already exists and passes (9 tests independently executed). The gap is one of milestone scope clarity, not missing coverage.
- **Recommendation:** Either leave as-is (the milestone's coverage is complete across TASK-092..100) or, if TASK-100 was intended as the consolidating test milestone, add an explicit note/pointer in the task or commit documenting that endpoint coverage is owned by TASK-099.

### F2 — Minor — "Why did observations drop yesterday?" example is not exercised end-to-end

- **File / line:** `tests/agent/test_agent_e2e.py` (`TestEndToEndSourceHealth`)
- **Problem:** The ROADMAP/objective lists three example questions; the e2e file covers "largest price increases" and "freshness problems", but the "observations drop" phrasing (which the classifier maps to `SOURCE_HEALTH` via the `"observations drop"` keyword) is only tested at the classifier level in `test_classifier.py`.
- **Impact:** Low — the classifier already proves the phrasing routes to `SOURCE_HEALTH`, and the e2e `SOURCE_HEALTH` path is exercised with equivalent questions. One of the three named examples is simply not covered graph-level.
- **Recommendation:** Add a graph-level case for `"Why did observations drop yesterday?"` asserting `SOURCE_HEALTH` intent and a `get_source_health` tool call.

### F3 — Minor — Several "answer contains tool data" assertions are weak/loose

- **File / line:** `tests/agent/test_agent_e2e.py:85-101` (`test_pipeline_status_answer_contains_tool_data`), `:188-206` (`test_price_answer_uses_metadata_not_hallucination`)
- **Problem:** `test_pipeline_status_answer_contains_tool_data` only asserts `state.response.answer` is truthy and `tool_results[0].success is True` — it does **not** assert the answer actually incorporates the run's data (e.g. `"records_loaded"`/`"500"`). `test_price_answer_uses_metadata_not_hallucination` falls back to `"result" in state.response.answer.lower()`, which is trivially satisfied by the "Result with keys: tables" formatting regardless of content.
- **Impact:** Low — the core "uses tools, not hallucination" guarantee is still meaningfully covered by `TestAgentUsesToolsNotHallucination`, `test_source_health_answer_references_tool_data` (asserts `healthy_count`), and `test_execute_sql_node_calls_metadata_not_raw_sql`. These two tests just overpromise relative to their names/assertions.
- **Recommendation:** Tighten the assertions to check for a specific data-derived token (e.g. `"records_loaded"`/`"500"` for the pipeline test, `"tables"` for the metadata test).

### F4 — Minor — PRODUCT_HISTORY intent is not covered end-to-end

- **File / line:** `tests/agent/test_agent_e2e.py` (no `product_history` case)
- **Problem:** The classifier defines `PRODUCT_HISTORY` (routed to `execute_sql`), but no e2e test exercises it; only `pipeline_status`, `data_quality`, `source_health`, `price_analytics`, and `general` are covered. Routing for `PRODUCT_HISTORY` is only unit-tested in `test_graph.py::test_product_history_routes_to_sql`.
- **Impact:** Low — the routing is unit-tested, and the objective's named examples do not include product-history questions. This is a completeness observation.
- **Recommendation:** Optionally add an e2e case asserting a product-history question routes to `get_dataset_metadata`.

---

## 6. Non-Defect Observations

- **N1 — The change is a clean, deterministic, pure-test addition.** It mocks all providers, performs no IO, uses the deterministic keyword classifier, and adds no dependencies. This matches the task's "deterministic; mock LLM calls and external dependencies" rule exactly.
- **N2 — The read-only guarantee is verified at the right layer for a unit test.** `test_execute_sql_node_calls_metadata_not_raw_sql` asserts `db.execute.assert_not_called()` while `db.list_tables` is called, proving the graph's SQL/price path uses metadata only, not arbitrary SQL. This complements the query-level `validate_read_only` unit tests in `test_tools.py`.
- **N3 — The graph's "SQL" path returns dataset metadata, not query results.** `_execute_sql_node_fn` calls `get_dataset_metadata`, never `execute_read_only_sql`, so a price question yields table/column/row-count metadata rather than a ranked price list. The e2e tests correctly reflect this ("routes to `get_dataset_metadata`"). This is a pre-existing TASK-098/099 design choice, not a TASK-100 defect, but it bounds what "answers questions" currently means for analytics-style questions.
- **N4 — No secrets, credentials, or keys introduced.**
- **N5 — Commit hygiene is good.** The commit message enumerates the coverage (intents, tool invocation, failure handling, fallback, read-only, full-context routing) and the claimed "20 new tests" count is accurate (I counted and executed exactly 20).

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The TASK-100 change is a single, clean, purely additive end-to-end test module that correctly ties the graph pipeline together and satisfies the milestone's core acceptance criterion: the agent is shown to route each intent to exactly one controlled tool and to fall back to an error answer (rather than hallucinate) when a provider is missing. Determinism and read-only behavior are asserted directly. All 20 new tests, the full 209-test agent suite, the 9 API-endpoint tests, ruff lint/format, single-file mypy, and `git diff --check` pass under independent execution; the range is correctly isolated to `feature/TASK-100` with no cross-task or architectural leakage.

The four findings (F1–F4) are **Minor** and non-blocking: the objective's "API endpoint" coverage is owned by TASK-099 rather than this commit (F1); one of the three named example questions ("observations drop") is not exercised graph-level (F2); two "answer contains tool data" tests have loose assertions (F3); and the `PRODUCT_HISTORY` intent lacks an e2e case (F4).

**Verification note:** unit/e2e/endpoint tests, lint, format, and type-check were independently executed and passed. Integration tests (`python -m pytest -m integration`) were **not** run (Docker/PostgreSQL unavailable), which is acceptable for this mocked graph-level test-only change; the read-only guarantee against a real PostgreSQL database remains unverified and is carried forward from TASK-099's Finding F2.
