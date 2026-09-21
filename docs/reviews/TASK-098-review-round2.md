# TASK-098 Qwen Review — Round 2

## Review metadata

- **Task:** TASK-098 — LangGraph Routing
- **Branch:** `feature/TASK-098`
- **Commits reviewed:**
  - `610d761` feat(TASK-098): Add LangGraph routing and graph construction
  - `c5d868f` fix(TASK-098): use actual langgraph StateGraph for agent routing
- **Round:** 2 (post-fix re-review)
- **Reviewer:** Qwen Code CLI
- **Verdict:** APPROVED WITH NON-BLOCKING FINDINGS

## Summary

The blocking finding F1 from round 1 is resolved. The hand-rolled `AgentGraph` has been replaced with a real `langgraph` `StateGraph`, the dependency is declared, and all verification gates pass. The three findings that remain are the same non-blocking items already recorded in round 1 (F2/F3/F4); no new issues were introduced.

## Verification of the four checks

### (1) Uses the `langgraph` library — PASS

`services/agent/graph.py` now uses the actual library:

- `from langgraph.graph import END, START, StateGraph` (line 28)
- `_build_graph()` constructs `StateGraph(AgentState)` (line 311)
- `graph.add_node(...)` for `classify`, `execute_sql`, `pipeline_status`, `data_quality`, `source_health`, `fallback`, `compose`
- `graph.add_edge(START, "classify")` and a `graph.add_conditional_edges("classify", route_fn, {...})` mapping all five route outcomes
- `graph.compile()` is returned, and `AgentGraph.run()` executes it via `self._compiled.invoke(initial)`

The old `_NODE_MAP` dict + linear `run()` dispatch are gone. Node functions now return `dict[str, Any]` partial-state updates (correct for LangGraph channel merging against the Pydantic `AgentState` schema).

### (2) `langgraph` in requirements.txt — PASS

`requirements.txt` adds `langgraph>=1.0,<2` (TASK-098 block). `requirements-dev.txt` includes `-r requirements.txt`, so dev installs get it transitively.

### (3) Tests pass — PASS (independently executed)

| Check | Result |
|---|---|
| `pytest tests/agent/test_graph.py` | 30 passed |
| `ruff check services/agent/graph.py tests/agent/test_graph.py` | All checks passed |
| `ruff format --check` | 2 files already formatted |
| `mypy tests/agent` | Success, no issues in 8 files |

### (4) No new issues — PASS

- No broken imports: the renamed node functions (`_classify_node_fn`, etc.) are referenced only inside `graph.py`.
- The conditional-edge mapping covers every route `_route_intent` can emit (including `None` -> `"fallback"`), so no unmapped-route runtime error.
- The `invoke()` result is handled defensively for both dict and `AgentState` returns.
- `services/agent/README.md` and `__init__.py` claims of "LangGraph" are now actually true (round-1 N4 is resolved).

## Remaining findings (carried over, all non-blocking)

- **F2 (Moderate):** `PRICE_ANALYTICS` / `PRODUCT_HISTORY` still route to a node named `execute_sql` that invokes only `get_dataset_metadata` (metadata, not SQL/analytics). Route label and actual tool still disagree.
- **F3 (Minor):** `FakeDataQualityProvider` omits `get_quality_summary`, so `test_data_quality_intent` asserts only `tool_calls`/`response.intent` — the data-quality happy path (`success is True`) is not exercised; the `# type: ignore[arg-type]` remains.
- **F4 (Minor):** `confidence` is carried through state and `AgentResponse` but never influences routing.

## Minor observations (non-blocking)

- `_compiled` / `_build_graph` are typed `Any`. Acceptable given `langgraph`'s dynamic typing, and `services/` is outside the repo's mypy gate.
- The round-1 review report (`docs/reviews/TASK-098-review.md`, verdict CHANGES REQUIRED) was committed in the same commit as the F1 fix. It is clearly scoped to `610d761` and is a valid historical artifact.
