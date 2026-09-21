# TASK-098 Review — LangGraph Routing

## 1. Review Header

- **Task ID:** TASK-098 — LangGraph Routing
- **Review date:** 2026-09-21
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:** `2d33347c13d689d69ae60dde0b1c36928d347662...610d761d041746a745863dae6feebe718d3134f8`
- **Reviewed commit:** `610d761d041746a745863dae6feebe718d3134f8` — `feat(TASK-098): Add LangGraph routing and graph construction`
- **Reviewed HEAD:** `610d761d041746a745863dae6feebe718d3134f8` on `feature/TASK-098`
- **Scope:** `services/agent/graph.py` (new, +339), `tests/agent/test_graph.py` (new, +358)
- **Diff stat:** 2 files changed, 697 insertions(+), 0 deletions(-)
- **Verdict:** `CHANGES REQUIRED`

**Authorities consulted:** `ai/tasks/TASK-098-langgraph-routing.md`, `ai/PROJECT.md` (§1, §2 Technology Baseline, §4 LangGraph Agent), `ai/SPECIFICATION.md` (§17 LangGraph Data Engineer Agent, §18 Agent State), `ai/ROADMAP.md` (Milestone 11 — LangGraph Agent), `ai/AGENTS.md`, `ai/REVIEWER.md`; the TASK-092–097 implementation (`services/agent/{state,intents,classifier,tools}.py`) and prior reviews (`docs/reviews/TASK-092-review.md` … `TASK-097-review.md`). The sole ADR (`docs/adr/ADR-001-kafka-topic-configuration.md`) concerns Kafka configuration and is not applicable.

**Note on sequencing:** Prior reviews (TASK-092 … TASK-097) explicitly deferred the LangGraph framework itself to this task. TASK-092's review states: *"LangGraph is correctly **not** introduced here (routing is TASK-098), keeping the state model framework-independent."* TASK-097's review records the same expectation (*"Tool binding/routing is deferred to TASK-098"*). TASK-098 is therefore the milestone point at which the named LangGraph technology was expected to be introduced.

---

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
|---|---|---|
| Implement LangGraph graph construction (the named framework) | ❌ Not met — see F1 | `services/agent/graph.py` hand-rolls a graph via a `AgentGraph` dataclass, a `_NODE_MAP` dict, a `NodeFunction` callable alias, and a linear `run()` method. There is **no** `langgraph` (or `langchain`) import anywhere in the diff or the repository, and `requirements*.txt` has no such dependency. The `__init__.py`/`README.md`/module docstrings claim "LangGraph-based" but nothing uses LangGraph. |
| Connect intent classification → tool selection → response generation | ✅ Met | `AgentGraph.run()` executes `_classify_node → _route_intent → tool node → _compose_response_node`; routing is a pure `_INTENT_TOOL_MAP` lookup keyed by `IntentType`. |
| Route based on classified intent | ✅ Met | `_route_intent()` maps `PRICE_ANALYTICS`/`PRODUCT_HISTORY` → `execute_sql`, `PIPELINE_STATUS`/`DATA_QUALITY`/`SOURCE_HEALTH` → their tool nodes, and `GENERAL`/unknown → `fallback`. |
| Invoke the appropriate tools | ⚠️ Partially met — see F2 | Pipeline/data-quality/source-health intents invoke `get_pipeline_status`/`get_data_quality`/`get_source_health`. The two SQL-routed intents (`PRICE_ANALYTICS`, `PRODUCT_HISTORY`) invoke only `get_dataset_metadata`, not any SQL/analytics execution. |
| Compose a final response from tool results | ✅ Met | `_compose_response_node()` builds an `AgentResponse` from `tool_results` (success → summarized answer + `sources`; all-fail → error text; no results → "No data available"). |
| Routing deterministic for test inputs | ✅ Met | No randomness, no IO, no LLM; verified by `TestGraphDeterminism` and independently reproduced. |
| Handle unrecognized intents gracefully (fallback) | ✅ Met | `GENERAL` routes to `_fallback_node`; unknown `IntentType` falls back via `_INTENT_TOOL_MAP.get(..., "fallback")`; `_compose_response_node` also guards `classified_intent is None`. |
| Agent must not have write access to PostgreSQL | ✅ Met | The graph only calls the injected read-only tool providers; no write path is introduced. |
| Use controlled tools and read-only SQL; never hallucinate platform state | ✅ Met | Deterministic aggregation over injected providers; no LLM inference. |
| Keep graph structure simple and testable | ✅ Met (arguably over-simplified — see F1) | The hand-rolled graph is simple and fully unit-tested, but this "simplicity" is achieved by not delivering the named framework. |
| No unrelated architecture changes, new dependencies, or secrets | ✅ Met | Two additive files only; no new dependencies, no config changes, no secrets. |

---

## 3. Git Diff Review

- **Files changed:** 2 files, +697 / −0 lines. Both belong to TASK-098.
  - `services/agent/graph.py` (+339, new) — `GraphContext`, `_INTENT_TOOL_MAP`, `_classify_node`, `_route_intent`, five tool/fallback nodes, `_compose_response_node`, `_format_tool_answer`, `_summarize_dict`, `_NODE_MAP`, `AgentGraph`, `build_agent_graph`.
  - `tests/agent/test_graph.py` (+358, new) — 30 tests across routing, graph execution, error handling, determinism, response composition, formatting helpers, graph construction, and message tracking.
- **Scope correctness:** All changes are confined to the graph/routing layer and its tests. No tool, state, classifier, API, or repository file was modified — consistent with the milestone sequencing (state/classifier/tools already landed in TASK-092–097).
- **Unrelated changes:** None. No existing file is modified.
- **Architectural changes:** One, and it is the central defect: the task and `PROJECT.md` §2 name **LangGraph** as the technology for the agent, but the diff delivers a bespoke state machine instead, with no ADR or documentation change to justify the substitution (see F1).
- **Accidental changes / debugging code / secrets:** None. No debug prints, temporary files, dead code, generated artifacts, or secrets.
- **Dependency/config changes:** None. `pyproject.toml`, `requirements*.txt`, and `docker-compose.yml` are untouched. This is itself evidence of F1 — LangGraph was never added.
- **Branch/task isolation:** ✅ One commit on `feature/TASK-098`; no changes from another TASK-xxx are included. `git status` shows only the untracked `review_task098.sh` (a review-harness script, not part of the commit under review).

---

## 4. Test and Verification Review

### Tests examined

`tests/agent/test_graph.py` — 30 tests: routing (`TestRouteIntent`, 6 tests), graph execution for each intent + fallback + empty question (`TestGraphRouting`, 5), error handling for missing providers/db and error collection (`TestGraphErrorHandling`, 3), determinism (`TestGraphDeterminism`, 2), response composition (`TestComposeResponse`, 3), formatting helpers (`TestFormatHelpers`, 5), graph construction (`TestBuildAgentGraph`, 3), and message tracking (`TestMessagesTracking`, 3).

### Test adequacy

Broad and focused on the hand-rolled graph logic (routing, tool selection, fallback, error propagation, determinism, response composition). Two adequacy gaps noted in F3 and F4.

### Verification classification

- **Independently verified (executed by reviewer):**
  - `python -m pytest tests/agent/test_graph.py -m "not integration" -q` → **30 passed** in 0.44s.
  - `python -m ruff check services/agent/graph.py tests/agent/test_graph.py` → **All checks passed**.
  - `python -m ruff format --check services/agent/graph.py tests/agent/test_graph.py` → **2 files already formatted**.
  - `python -m mypy tests/agent` → **Success: no issues found in 8 source files**.
  - `python -m mypy` (repository-configured gate, `files = ["scripts", "tests", "libs"]`) → **Success: no issues found in 190 source files**.
- **Not applicable:** Integration tests. The diff touches no Kafka, persistence-write, MinIO/S3, or infrastructure boundary; the graph is a pure in-memory unit under test. The default `addopts = "-m 'not integration'"` therefore has no bearing here.
- **Unverified:** Nothing material. The full repository suite was not rerun; the change is purely additive (two new files, no existing module modified), so regression risk is negligible and the targeted suite plus lint/format/type checks were run instead.

---

## 5. Findings

### F1 — High — The implementation does not use LangGraph at all

- **File / line:** `services/agent/graph.py` (whole module; `AgentGraph` dataclass at line 308, `build_agent_graph` at line 337). Also `requirements.txt` / `requirements-dev.txt` (no `langgraph`).
- **Problem:** The task is *"Implement LangGraph graph construction and routing logic"*, and `ai/PROJECT.md` §2 (Technology Baseline) lists *"LangGraph for the controlled Data Engineer Agent"* as a non-negotiable technology, adding *"Equivalent tools may be introduced only through an explicit architectural/documentation change."* The implementation never imports or installs LangGraph: it builds a bespoke `AgentGraph` dataclass with a `_NODE_MAP` dictionary and a linear `run()` method. Prior reviews explicitly deferred the LangGraph framework to this task (TASK-092: *"LangGraph is correctly not introduced here (routing is TASK-098)"*), so this was the expected introduction point. No ADR or documentation change authorizes the substitution, and the module/package docstrings and `services/agent/README.md` still assert "LangGraph-based", which is now inaccurate.
- **Impact:** The milestone's named technology is not delivered. The hand-rolled dispatch provides none of LangGraph's capabilities (compiled `StateGraph`, conditional edges, state-channel reducers, checkpointing/persistence, streaming, interrupt/human-in-the-loop) that a "LangGraph Data Engineer Agent" portfolio platform advertises. It also creates a false claim: the code and README say "LangGraph" while no LangGraph exists. TASK-099 (Agent API) and TASK-100 (Agent tests) will build on this, so the deviation propagates.
- **Recommendation:** Either (a) implement the graph with the actual `langgraph` library (`StateGraph`, nodes, conditional edges, `compile()`), adding `langgraph` to `requirements.txt` and updating the docstrings/README accordingly; or (b) if the human owner intends a lightweight, framework-free deterministic router, record that as an explicit architectural decision (ADR or `PROJECT.md`/`SPECIFICATION.md` amendment) and rename the task/module so it no longer claims LangGraph. As written, this is a silent substitution of a non-negotiable baseline, which `PROJECT.md` §2 and `AGENTS.md` §1/§13 do not permit.

### F2 — Moderate — SQL-routed intents do not execute SQL or analytics; they only fetch dataset metadata, and the route name diverges from the invoked tool

- **File / line:** `services/agent/graph.py:45-51` (`_INTENT_TOOL_MAP`), `76-77` (`_execute_sql_node` sets `tool_name = "get_dataset_metadata"`), `87` (imports `get_dataset_metadata`, not `execute_read_only_sql`).
- **Problem:** Both `PRICE_ANALYTICS` and `PRODUCT_HISTORY` route to a node named `"execute_sql"`, but that node invokes `get_dataset_metadata()` — which returns table schemas/columns/row counts — and never uses the existing `execute_read_only_sql()` tool (TASK-094). The recorded `tool_calls[0].tool_name` is `"get_dataset_metadata"`, not `"execute_sql"`, so the route label and the actual tool disagree. A question like *"Which products had the largest price increases?"* (a milestone acceptance example) would be classified `PRICE_ANALYTICS` and return table metadata, not an answer.
- **Impact:** The routing→tool-selection→response path is functionally incomplete for two of the six intents. This is a routing/selection concern squarely within TASK-098's scope (connecting classification to the *appropriate* tool), even if full SQL generation is deferred. The naming inconsistency will also confuse downstream tool-call attribution/metrics.
- **Recommendation:** Wire the SQL-routed intents to a genuine read-only SQL/analytics path (or, at minimum, record the intent as `execute_sql` and invoke `execute_read_only_sql`, deferring query *generation* explicitly). If dataset metadata is a deliberate placeholder for now, document that clearly and make the route/tool names consistent.

### F3 — Minor — Data-quality happy path is not actually tested because the fake provider is incomplete

- **File / line:** `tests/agent/test_graph.py:37-42` (`FakeDataQualityProvider` defines only `list_recent_checks`), `122` (`# type: ignore[arg-type]`), `120-131` (`test_data_quality_intent`).
- **Problem:** `DataQualityProvider` (in `tools.py`) requires both `list_recent_checks` and `get_quality_summary`, but `FakeDataQualityProvider` omits `get_quality_summary`. Consequently `get_data_quality()` raises `AttributeError` inside the fake and returns `success=False`; `test_data_quality_intent` therefore asserts only `tool_calls` and `response.intent`, deliberately **not** `tool_results[0].success` (unlike `test_pipeline_status_intent`, which asserts `success is True`). The `# type: ignore[arg-type]` masks the protocol violation.
- **Impact:** The data-quality routing "happy path" (successful tool result flowing into the response) is not exercised, so a regression in `get_data_quality` wiring would pass the suite.
- **Recommendation:** Add a `get_quality_summary` method to the fake (returning e.g. `[]`), drop the `type: ignore`, and assert `success is True` in `test_data_quality_intent`, matching the pipeline-status test.

### F4 — Minor — `confidence` is carried through the graph but never used for routing

- **File / line:** `services/agent/graph.py:70-73` (`_route_intent` ignores `classified.confidence`), `_classify_node` (records confidence in a system message).
- **Problem:** Routing is purely `intent != GENERAL`; a low-confidence specific match (the classifier can produce e.g. `0.26` for a single keyword) still invokes a tool with full authority. TASK-093's review (F1) already flagged that fallback reports `confidence=1.0` while weak matches report much lower values, and recommended defining confidence semantics *before TASK-098 consumes it*. TASK-098 consumes the field (into state and `AgentResponse.confidence`) but makes no routing use of it.
- **Impact:** No correctness failure for a deterministic v1, but the confidence signal is dead weight in the routing decision, and low-confidence classifications are indistinguishable from confident ones at the tool-invocation boundary.
- **Recommendation:** Document the intended confidence semantics (e.g., "confidence is informational only; routing is by intent") or introduce a low-confidence fallback threshold, whichever the architecture intends.

---

## 6. Non-Defect Observations

- **N1 — Deterministic and read-only by construction.** No randomness, IO, or LLM; all data access is through injected provider protocols. This satisfies the agent rules and the "never hallucinate platform state" requirement.
- **N2 — Graceful fallback is complete.** `GENERAL`, unknown intents, and a `None` classified intent all funnel to fallback/error answers without raising.
- **N3 — Five near-identical tool node functions with deferred imports.** `_execute_sql_node`/`_pipeline_status_node`/`_data_quality_node`/`_source_health_node` share the same try/except → `ToolCallResult` → `model_copy` structure (the `from services.agent.tools import ...` inside each body is a deferred import, likely to avoid a circular import). This is maintainability noise, not a defect; a single parameterized dispatcher would remove the repetition.
- **N4 — "LangGraph" branding is now misleading.** `services/agent/__init__.py`, `services/agent/README.md`, and the module docstrings all describe a "LangGraph-based Data Engineer Agent", but no LangGraph exists (see F1). Even if the graph logic is otherwise acceptable, the documentation claims are inaccurate.
- **N5 — Untracked `review_task098.sh`.** The working tree contains an untracked review-harness script at the repo root. It is not part of the reviewed commit and is outside the diff; noted only for completeness.
- **N6 — No new dependencies, config, or secrets.** The change is purely additive and hermetic.

---

## 7. Verdict

**`CHANGES REQUIRED`**

Blocking finding:

- **F1 (High):** The task and `PROJECT.md` §2 require **LangGraph**, but the implementation hand-rolls a bespoke `AgentGraph` state machine with no LangGraph import and no `langgraph` dependency, and no ADR/documentation change authorizes the substitution. Prior reviews explicitly deferred the LangGraph framework to this task, so the named technology is simply absent while the code and docs still claim it.

Everything else is sound: the graph is deterministic, read-only, correctly scoped to two new files, and well tested (30 tests pass; ruff, ruff format, and mypy all pass when independently executed). The remaining findings are non-blocking:

- **F2 (Moderate):** `PRICE_ANALYTICS`/`PRODUCT_HISTORY` route to a node that fetches only dataset metadata (not SQL/analytics), and the route name `execute_sql` diverges from the invoked tool `get_dataset_metadata`.
- **F3 (Minor):** `FakeDataQualityProvider` omits `get_quality_summary`, so the data-quality happy path is not asserted.
- **F4 (Minor):** `confidence` is carried but unused for routing.

Resolution of F1 requires either introducing the real LangGraph library (and adding it to `requirements.txt`) or recording an explicit architecture decision to use a framework-free deterministic router and correcting the "LangGraph" naming. Until that decision is made and reflected in the code, the implementation does not satisfy the task's named framework requirement.
