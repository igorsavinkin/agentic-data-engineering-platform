# TASK-FIX-TASK-NAMING-DOCS — Review

## 1. Review Header

- **Task ID:** TASK-FIX-TASK-NAMING-DOCS — allow the `TASK-DOCS-*` task naming convention in the repository structure verifier
- **Review date:** 2026-09-25
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `375ff4a85c264a2c38ca35e3db90fa58cddd0a93...82c8c99285536adb3a2719841a4177cf1eb0202a`
- **Reviewed HEAD:** `82c8c99285536adb3a2719841a4177cf1eb0202a` on `feature/TASK-FIX-TASK-NAMING-DOCS`
- **Commit reviewed:**
  - `82c8c99` — `fix: allow TASK-DOCS-* naming convention in structure verifier`
- **Scope:** Extend `scripts/verify_repository_structure.py` to accept `TASK-DOCS-*.md` (in addition to numbered, `TASK-FIX-*`, `TASK-K8S-FIX-*`), extract a pure `is_valid_task_filename()` helper, and add deterministic unit tests.
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

### Authorities consulted

- `ai/tasks/TASK-FIX-TASK-NAMING-DOCS.md` (primary task spec)
- `ai/REVIEWER.md`
- `ai/AGENTS.md` (§7 testing, §16 git task isolation)
- `ai/PROJECT.md` (§12 Testing Principles)
- `pyproject.toml` (pytest/ruff/mypy configuration)
- `scripts/verify_repository_structure.py`, `tests/test_repository_structure.py`
- `docs/reviews/TASK-K8S-FIX-001-review.md` (prior review touching the same verifier)

No authority conflicts identified.

> Note: the task specification file `ai/tasks/TASK-FIX-TASK-NAMING-DOCS.md` is malformed — its content is duplicated verbatim (see Finding F1). The requirements are nonetheless unambiguous, and this file was created in the preceding spec commit `375ff4a` (outside the reviewed code commit), so it is treated here as the source of requirements, not as part of the reviewed diff.

---

## 2. Requirements Coverage

| Requirement | Status | Implementation evidence |
|---|---|---|
| `TASK-DOCS-PLATFORM-INVENTORY-M13.md` is accepted | **Met** | `_ALLOWED_TASK_PREFIXES` includes `"TASK-DOCS-"`; `is_valid_task_filename("TASK-DOCS-PLATFORM-INVENTORY-M13.md")` returns `True`; `test_docs_task_accepted` asserts it. The file itself exists under `ai/tasks/` and the verifier now passes with it present. |
| Numbered task files remain accepted | **Met** | `is_valid_task_filename` returns `True` when `_parse_task_number(name) is not None`; `test_numbered_task_accepted` covers `TASK-001/042/123-*.md`. The live verifier reports 138 task files with no unexpected-name errors. |
| `TASK-FIX-*` remains accepted | **Met** | `_ALLOWED_TASK_PREFIXES` retains `"TASK-FIX-"`; `test_fix_task_accepted` covers it. |
| `TASK-K8S-FIX-*` remains accepted | **Met** | `_ALLOWED_TASK_PREFIXES` retains `"TASK-K8S-FIX-"`; `test_k8s_fix_task_accepted` covers it. |
| Arbitrary invalid names such as `TASK-WHATEVER.md` are still rejected | **Met** | `test_arbitrary_invalid_rejected` asserts `TASK-WHATEVER.md`, `TASK-RANDOM.md`, `TASK-FOOBAR.md` return `False`. `test_non_task_files_rejected` additionally asserts `README.md` and `TASK-.md` return `False`. |
| `tests/test_repository_structure.py` passes | **Met** | Independently executed: `7 passed in 0.23s`. |
| Repository quality checks pass | **Met** | `ruff check` (`All checks passed!`), `ruff format --check` (`2 files already formatted`), and `mypy` (`Success: no issues found in 2 source files`) all independently executed. |

All acceptance criteria are satisfied.

---

## 3. Git Diff Review

**Files changed (2 files, +54 / −3):**

| File | Change |
|---|---|
| `scripts/verify_repository_structure.py` | Modified (+15/−3): extracted `_ALLOWED_TASK_PREFIXES` and `is_valid_task_filename()`; replaced the inline prefix check in `check_task_files()`. |
| `tests/test_repository_structure.py` | Modified (+42): added `importlib.util`-based import of the script and six new deterministic test functions. |

- **Scope correctness:** The change is tightly scoped to the verifier and its tests, exactly as the task specifies. No other files touched.
- **Unrelated changes:** None.
- **Architectural changes:** None. This is a repository-hygiene/verification script; no service boundary, event contract, or data-plane change.
- **Dependency/configuration changes:** None. No new third-party dependency; `importlib.util` is standard library.
- **Accidental changes:** None — no debug code, temp files, generated artifacts, or secrets.
- **Test changes that weaken validation:** None. The existing `test_repository_structure` smoke test is preserved unchanged; additions are purely additive.
- **Branch/task isolation:** Correct. Working tree is clean, on `feature/TASK-FIX-TASK-NAMING-DOCS`, and the single reviewed commit contains only the two in-scope files. No changes from another TASK-* are included.

The commit message accurately describes the change (extract helper + add `TASK-DOCS-*` + tests), though it does not mention the test additions verbatim; the `--stat` body confirms the test additions are included.

---

## 4. Test and Verification Review

### Tests examined

`tests/test_repository_structure.py` — 7 tests:

- `test_repository_structure` — subprocess smoke test of the full verifier (pre-existing, unchanged).
- `test_numbered_task_accepted` — 3 numbered names.
- `test_fix_task_accepted` — 2 `TASK-FIX-*` names.
- `test_k8s_fix_task_accepted` — 2 `TASK-K8S-FIX-*` names.
- `test_docs_task_accepted` — `TASK-DOCS-PLATFORM-INVENTORY-M13.md` and a generic `TASK-DOCS-*` name.
- `test_arbitrary_invalid_rejected` — 3 arbitrary `TASK-*` names.
- `test_non_task_files_rejected` — `README.md` and the degenerate `TASK-.md`.

### Verification classification

| Check | Status | Evidence |
|---|---|---|
| `python -m pytest tests/test_repository_structure.py -v` | **Independently verified** | `7 passed in 0.23s` |
| `python scripts/verify_repository_structure.py` | **Independently verified** | `Repository structure verification passed` (24 dirs, 5 governance docs, 138 task files) |
| `python -m ruff check scripts/verify_repository_structure.py tests/test_repository_structure.py` | **Independently verified** | `All checks passed!` |
| `python -m ruff format --check scripts/verify_repository_structure.py tests/test_repository_structure.py` | **Independently verified** | `2 files already formatted` |
| `python -m mypy scripts/verify_repository_structure.py tests/test_repository_structure.py` | **Independently verified** | `Success: no issues found in 2 source files` |
| Full `python -m pytest` suite | **Unverified / not rerun** | Not required by the task's acceptance criteria and out of proportion for this two-file change; the targeted test file and the verifier itself were exercised. |
| Integration tests (`pytest -m integration`) | **Not applicable** | No Kafka/persistence/MinIO/S3 boundary is touched; this is a static repository-structure check. |

### Test adequacy

The tests map one-to-one onto the acceptance criteria: accepted categories (numbered, FIX, K8S-FIX, DOCS) and rejected categories (arbitrary, non-task, degenerate) are each covered. Two near-miss boundaries are not explicitly asserted — `TASK-DOCS.md`/`TASK-FIX.md` (no suffix) and misleading prefixes such as `TASK-DOCUMENT-*`/`TASK-FIXTURE-*` — but the implementation handles these correctly because every accepted prefix includes a trailing `-` and `_parse_task_number` returns `None` for non-numeric suffixes. This is a completeness nicety, not a gap that undermines the acceptance criteria.

---

## 5. Findings

### F1 — Minor: task specification file content is duplicated
- **Affected:** `ai/tasks/TASK-FIX-TASK-NAMING-DOCS.md` (lines 1–35 duplicated as lines 37–71; line 35 concatenates the final acceptance item with the duplicated header without a newline: `- [ ] repository quality checks pass.# TASK-FIX-TASK-NAMING-DOCS`)
- **Problem:** The entire spec (Objective / Scope / Acceptance Criteria) appears twice in the file. The first copy's last line is glued to the start of the second copy's title.
- **Impact:** Documentation quality only. The duplicated copies are identical, so requirements are not ambiguous and acceptance determination is unaffected. It is nonetheless sloppy and will confuse future readers/tools.
- **Recommendation:** Deduplicate the file to a single Objective/Scope/Acceptance Criteria block. (Created in the spec commit `375ff4a`, outside the reviewed code commit `82c8c99`; flagging for completeness because the spec is the primary authority source.)

---

## 6. Non-Defect Observations

- **The extracted helper is correct and a genuine improvement.** `is_valid_task_filename()` centralizes the "numbered or known-prefix" rule that was previously inlined, and the `_ALLOWED_TASK_PREFIXES` tuple makes the accepted conventions explicit and easy to extend.
- **Prefixes are correctly anchored with a trailing dash.** `name.startswith("TASK-FIX-")` does not match `TASK-FIXTURE-*`, and `TASK-DOCS-` does not match `TASK-DOCUMENT-*`, so the constraint "do not relax validation for arbitrary `TASK-*` filenames" holds.
- **The prior dead-branch defect in `_parse_task_number` (TASK-K8S-FIX-001 review F3) is already gone** in the current code; the function is now a single, clear numeric check, and this task does not re-introduce any dead branch.
- **`check_task_files()` calls `_parse_task_number()` twice for non-numbered files** (once directly, once inside `is_valid_task_filename()`). This is a negligible inefficiency on a small directory listing and does not affect correctness; `check_task_files()` could be simplified to rely on `is_valid_task_filename()` alone.
- **Tests are deterministic and side-effect-free**, and the script import via `importlib.util.spec_from_file_location` avoids triggering the script's `main()` guard while still exercising the real `is_valid_task_filename`.

---

## 7. Verdict

**`APPROVED WITH NON-BLOCKING FINDINGS`**

The implementation satisfies every acceptance criterion: `TASK-DOCS-*` (including `TASK-DOCS-PLATFORM-INVENTORY-M13.md`) is accepted, numbered/`TASK-FIX-*`/`TASK-K8S-FIX-*` names remain accepted, and arbitrary `TASK-*` names remain rejected. The change is tightly scoped to the verifier and its tests with no unrelated, architectural, dependency, or secret changes. Tests, `ruff check`, `ruff format --check`, and `mypy` all pass under independent execution.

The only finding is F1 (duplicated task specification file), which is Minor, non-blocking, and located outside the reviewed code commit. No Critical, High, or Moderate findings.
