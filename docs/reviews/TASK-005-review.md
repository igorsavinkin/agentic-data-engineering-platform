# TASK-005 Review — CI Foundation

- **Task:** [TASK-005 — CI Foundation](../../ai/tasks/TASK-005-ci-foundation.md)
- **Branch:** `feature/TASK-005-ci-foundation`
- **Reviewed commits:**
  - `b5f6146` — `feat(TASK-005): add GitHub Actions CI foundation`
  - `421acc2` — `refactor(TASK-005): apply Qwen review suggestions S1-S4` (re-review)
- **Diff scope:** `main` (`fb1808e`) .. `HEAD` (`421acc2`)
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Date:** 2026-09-08 (re-review)

> **Note on process:** `ai/REVIEWER.md` does not exist in this repository. This review
> follows the reviewer role and findings classification defined in
> `ai/AGENT_WORKFLOW.md` §3.3 and §7, plus the Definition-of-Done requirements in
> `ai/AGENTS.md` §7, §12 and §13.

## Re-review summary

The follow-up commit `421acc2` addresses all four suggestions (S1–S4). Each is resolved
correctly, no unrelated changes were introduced, and every CI step still passes locally.
Verdict is unchanged.

## Verdict

**Approve.** No blockers, majors, or minors. All previously reported suggestions are
resolved.

## Verification performed (re-review)

I re-ran every CI step against the current working tree (Python 3.14 locally; CI pins
3.12, the project minimum):

| CI step | Command | Result |
| ------- | ------- | ------ |
| Check formatting | `ruff format --check .` | 52 files already formatted (exit 0) |
| Lint | `ruff check .` | All checks passed |
| Type check | `mypy` | Success — 7 source files |
| Unit tests | `pytest` | 21 passed, 7 deselected |
| Repository validation | `python scripts/verify_repository_structure.py` | Passed |

## Findings — resolution status

| ID | Severity | Finding | Status |
| -- | -------- | ------- | ------ |
| S1 | SUGGESTION | Declare least-privilege workflow permissions | ✅ Resolved |
| S2 | SUGGESTION | Cache key ignores the runtime requirements file | ✅ Resolved |
| S3 | SUGGESTION | Prefer `extend-exclude` over `exclude` | ✅ Resolved |
| S4 | SUGGESTION | Consider a job `timeout-minutes` | ✅ Resolved |

### S1 — Resolved

`permissions: { contents: read }` was added at the job level, scoping the `GITHUB_TOKEN`
to read-only, consistent with `ai/SPECIFICATION.md` §21.

### S2 — Resolved

The `actions/cache` key now hashes both files:
`hashFiles('requirements.txt', 'requirements-dev.txt')`, so a change to the runtime
requirements invalidates the pip cache.

### S3 — Resolved

`exclude = ["docs/reviews/*.md"]` was replaced with
`extend-exclude = ["docs/reviews/*.md"]`, preserving Ruff's built-in default excludes
while still skipping the review docs. Verified: `ruff format --check .` and
`ruff check .` both still pass and scan only project files.

### S4 — Resolved

`timeout-minutes: 15` was added at the job level.

## "No unrelated changes" check

The follow-up diff (`b5f6146..421acc2`) touches exactly two files, both within the S1–S4
scope:

- `.github/workflows/ci.yml` — adds `timeout-minutes`, `permissions`, and updates the
  cache key (S1/S2/S4).
- `pyproject.toml` — one line: `exclude` → `extend-exclude` (S3).

No Python source, tests, dependencies, task specs, or other tool configuration were
modified. No behavior change beyond the intended hardening.

## Conclusion

The CI hygiene follow-up correctly resolves S1–S4 with a minimal, tightly scoped diff, and
the full local CI sequence still passes. TASK-005 is approved.
