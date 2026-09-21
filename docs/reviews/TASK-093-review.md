# TASK-093 Review — Intent Classifier

## 1. Review Header

- **Task ID:** TASK-093 — Intent Classifier
- **Review date:** 2026-09-21
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:** `81cd75c3ca7663b94a47764601f5266cb472e090...6eebbfdc3639d0076865a99eb3311c9b8d824afc`
- **Reviewed HEAD (commit):** `6eebbfdc3639d0076865a99eb3311c9b8d824afc` on `feature/TASK-093`
- **Merge base / prior HEAD:** `81cd75c3ca7663b94a47764601f5266cb472e090` ("Implement TASK-092: Agent State Model (#105)")
- **Commits reviewed:**
  - `6eebbfd` — `feat(TASK-093): Add deterministic intent classifier for agent routing`
- **Scope:** A deterministic, keyword-based intent classifier mapping natural-language questions to the six `IntentType` categories established in TASK-092, plus its unit tests. No runtime component, no infrastructure, no new dependencies.
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

Sources of authority consulted: `ai/tasks/TASK-093-intent-classifier.md`; `ai/PROJECT.md` §2/§4/§11; `ai/SPECIFICATION.md` §5, §17, §18; `ai/ROADMAP.md` Milestone 11; `ai/AGENTS.md` §3/§6/§7/§10/§14; `ai/REVIEWER.md`; the TASK-092 implementation (`services/agent/intents.py`, `services/agent/state.py`) and its prior review (`docs/reviews/TASK-092-review.md`). The sole ADR (`docs/adr/ADR-001-kafka-topic-configuration.md`) concerns Kafka topic configuration and is not applicable to the intent classifier.

## 2. Requirements Coverage

| Requirement | Status | Evidence |
|---|---|---|
| Map natural-language questions to structured intents (price analytics, pipeline status, data quality, source health, product history, general) | ✅ Met | `services/agent/classifier.py` maps keywords to the six `IntentType` categories; `IntentType` (from TASK-092) contains exactly those six values. |
| Deterministic for test inputs | ✅ Met | Pure function of `(question, _INTENT_KEYWORDS)`; no randomness, no IO, no LLM. Verified by `test_deterministic` (10 repeated calls) and independently reproduced. |
| Gracefully handle unrecognized intents | ✅ Met | Unknown/empty/whitespace inputs return `IntentType.GENERAL` with the original `raw_question` preserved. Exercised by `test_general_fallback`, `test_empty_question`, `test_whitespace_only`. |
| Testable with deterministic inputs; no live LLM in unit tests | ✅ Met | Keyword matching only; `test_no_live_llm_dependency` and the entire suite run hermetically (no network/DB/LLM). |
| Intents map cleanly to tool selections in the routing layer | ✅ Met | The classifier consumes/produces the `IntentType` enum that the routing layer (TASK-098) will consume; no tool-specific coupling is introduced. |
| Agent has no write access to PostgreSQL | ✅ Met | No database interaction of any kind in the diff. |
| Implement only this task; no unrelated changes or secrets | ✅ Met | Diff is two new files (+252 lines), purely additive; no existing files modified, no secrets, no config/dependency changes. |

## 3. Git Diff Review

**Range:** `81cd75c..6eebbfd` — 1 commit, 2 files, +252 lines (all additive).

Files changed:

- `services/agent/classifier.py` (+131) — the deterministic keyword classifier.
- `tests/agent/test_classifier.py` (+121) — 14 deterministic unit tests.

**Scope correctness:** All changes belong to TASK-093. The classifier builds directly on the TASK-092 `IntentType`/`ClassifiedIntent` models and does not drift into routing (deferred to TASK-098), tools (TASK-094–097), or the API (TASK-099), matching the Milestone 11 sequencing in `ai/ROADMAP.md`.

**Unrelated/accidental changes:** None. No existing file was modified; the diff is purely two new modules.

**Architectural changes:** None. The change adds a function inside the normative `services/agent/` boundary (`ai/SPECIFICATION.md` §5); it does not alter service boundaries, event semantics, or the agent's read-only posture.

**Dependency/config changes:** None. `pyproject.toml`, `requirements*.txt`, and `docker-compose.yml` are untouched. `re` and `pydantic` (already present) are the only dependencies.

**Debug/temp/dead code/secrets:** No debug prints, temp files, generated artifacts, dead code, or secrets. No `__pycache__` committed.

**Branch and task isolation:** Reviewed HEAD is on `feature/TASK-093`; the range contains exactly one commit belonging to TASK-093. Working tree is clean (`git status` → nothing to commit).

## 4. Test and Verification Review

**Tests added:** `tests/agent/test_classifier.py` — 14 tests covering:

- all six intents via representative keyword questions;
- GENERAL fallback for unrecognized input (asserting `confidence == 1.0`);
- empty and whitespace-only input;
- case-insensitivity;
- determinism (repeated calls yield identical intent + confidence);
- `raw_question` preservation;
- confidence bounded to `[0.0, 1.0]`;
- multi-keyword match boosting confidence relative to a single match;
- no live-LLM dependency (result is a concrete `float`, no external call).

**Independently verified (executed by reviewer):**

- `python -m pytest tests/agent/test_classifier.py -v` → **14 passed** in 0.34s.
- `python -m ruff check services/agent/classifier.py tests/agent/test_classifier.py` → **All checks passed**.
- `python -m ruff format --check services/agent/classifier.py tests/agent/test_classifier.py` → **2 files already formatted**.
- `python -m mypy tests/agent` → **Success: no issues found in 3 source files**.

**Implementation evidence reviewed (not rerun):** None beyond the above; the commit message contains no test-run evidence, so the independent execution above is the sole verification.

**Unverified / not rerun:**

- The full repository suite was **not rerun**. The change is purely additive (two new files, no modification to existing modules), so regression risk to existing code is negligible; the targeted classifier suite plus lint/format/type checks were run instead.
- No integration tests are relevant: the task touches no Kafka, persistence, MinIO/S3, or infrastructure boundary. The default `addopts = "-m 'not integration'"` therefore has no bearing here.

## 5. Findings

### F1 — Moderate — Fallback confidence (1.0) exceeds recognized-intent confidence

- **File:** `services/agent/classifier.py` (fallback at `best_score == 0`; confidence formula ~line 114).
- **Problem:** An unrecognized question returns `IntentType.GENERAL` with `confidence=1.0`, while a question that genuinely matches one keyword returns a much lower confidence (e.g. `"price"` → `0.26`, `"Why did observations drop yesterday?"` → `0.28`). This is semantically inverted: "I found no specific intent" reports *maximum* confidence, whereas "I matched a price keyword" reports low confidence. It also contradicts the module docstring, which states confidence is "based on the number of keyword matches". The formula itself contains an undocumented magic number (`max_possible * 0.3`) and yields cross-intent inconsistency: the same single-keyword match produces `0.26` (price), `0.28` (source health), or `0.37` (product history) depending on each intent's keyword-list length.
- **Impact:** `ClassifiedIntent.confidence` is the field the routing layer (TASK-098) will likely use to decide whether to route to a specific tool or fall back to a general answer. As written, the fallback carries the highest possible confidence, which can mislead downstream routing/weighting and obscure low-confidence specific matches. No behavior is incorrect today because routing does not yet exist.
- **Recommendation:** Define and document the confidence semantics before TASK-098 consumes it. At minimum, make the fallback's confidence meaningfully low (or `0.0`), or add an explicit discriminator (e.g. a `matched`/`fallback` flag) so "general because unmatched" is not conflated with a confident classification. Document the `0.3` denominator or replace it with a clearer scheme.

### F2 — Minor — Tie-breaking depends on dict insertion order

- **File:** `services/agent/classifier.py` (classification loop uses strict `>`).
- **Problem:** When two intents score equally, the first intent in `_INTENT_KEYWORDS` insertion order wins. This is deterministic (Python 3.7+ dicts preserve order) but implicit and undocumented. A concrete example: `"Why did observations drop yesterday?"` matches `SOURCE_HEALTH` ("observations drop") and `PRODUCT_HISTORY` ("observations") one keyword each, and resolves to `SOURCE_HEALTH` only because it precedes `PRODUCT_HISTORY` in the dict. The corresponding test passes only via this ordering.
- **Impact:** Correct today, but fragile: reordering or editing the keyword table could silently change classifications without any test or comment signaling the dependency.
- **Recommendation:** Document the insertion-order priority, or implement an explicit, more semantic tie-break (e.g. prefer the intent with the longest matched keyword) and add a targeted tie-break test.

### F3 — Minor — No stemming/pluralization; several low-value or unmatchable keywords

- **File:** `services/agent/classifier.py` (keyword table).
- **Problem:** Matching is exact word-boundary only. `"price trend"` does not match `"price trends"`, `"price"` does not match `"prices"`, `"observation count"` does not match `"observation counts"`. A few explicit plurals were added (`"sources"`, `"observations"`) but coverage is ad hoc. Additionally, `"product look"` is an odd phrase that will not match natural phrasings such as "look up product" or "look at product X", and `"product look"`/`"look"` appear to be a placeholder for "lookup".
- **Impact:** Lower recall for common morphological variants; a keyword-based classifier is not expected to be exhaustive, but the specific `"product look"` entry likely never fires for its intended target.
- **Recommendation:** Either accept and document the exact-match limitation (fine for a deterministic v1), or add lightweight normalization (a small plural/stem suffix list). Remove or correct `"product look"`.

## 6. Non-Defect Observations

- **N1 — Standalone, correctly deferred integration.** The classifier is intentionally not wired into routing or tools. Per `ai/ROADMAP.md` Milestone 11, routing is TASK-098; keeping `classify_intent` a pure, isolated function is the right scope.
- **N2 — `services/agent/` is outside the configured mypy gate.** `pyproject.toml` sets `[tool.mypy] files = ["scripts", "tests", "libs"]`, so `services/agent/classifier.py` is not type-checked by the repository gate (it is still lint/format-checked and fully exercised by tests). Running `python -m mypy services/agent` directly reports the pre-existing `Source file found twice under different module names: "agent.intents" and "services.agent.intents"` quirk (identical to TASK-092). Not introduced by TASK-093.
- **N3 — Strong, focused test coverage.** The 14 tests cover the full requirement surface (all intents, fallback, empty/whitespace, case, determinism, confidence bounds, multi-keyword boost, raw-question preservation, no-LLM). This is more than the minimum the task requires.
- **N4 — No documentation update, but not required.** The task's Definition of Done says "documentation updated where needed". For a small, self-documenting pure function with a clear module docstring and an existing `services/agent/README.md`, no additional documentation is warranted.
- **N5 — `raw_question` preserved verbatim.** The classifier stores the original (untrimmed, original-case) question in `ClassifiedIntent.raw_question` even while classifying on the normalized form. This is correct and tested.

## 7. Verdict

**`APPROVED WITH NON-BLOCKING FINDINGS`**

The TASK-093 implementation is complete, correctly scoped, deterministic, and clean. It delivers a keyword-based classifier that maps questions onto the six `IntentType` categories established in TASK-092, gracefully falls back to `GENERAL` for unrecognized/empty input, requires no live LLM, and introduces no PostgreSQL access, new dependencies, secrets, or architectural changes. All quality gates pass when independently executed: **14 unit tests passed**, `ruff check` and `ruff format --check` are clean, and `mypy` on the configured test scope passes.

The findings are non-blocking. F1 (fallback confidence = 1.0 exceeds matched-intent confidence) is the only Moderate finding and should be resolved or explicitly documented before TASK-098 (routing) consumes the confidence field; F2 and F3 are Minor robustness/quality issues. None of them affects the correctness of the classification contract today.
