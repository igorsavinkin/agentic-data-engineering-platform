# TASK-004 Review — Docker Compose Foundation

- **Task:** [TASK-004 — Docker Compose Foundation](../../ai/tasks/TASK-004-docker-compose-foundation.md)
- **Branch:** `feature/TASK-004-docker-compose`
- **Reviewed commits:**
  - `b061009` — `feat(TASK-004): add local Docker Compose infrastructure`
  - `feb0652` — `fix(TASK-004): address review follow-up items` (re-review)
- **Diff scope:** `main` (`ff24de6`) .. `HEAD` (`feb0652`)
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Date:** 2026-09-08 (re-review)

> **Note on process:** `ai/REVIEWER.md` does not exist in this repository. This review
> follows the reviewer role and findings classification defined in
> `ai/AGENT_WORKFLOW.md` §3.3 and §7, plus the Definition-of-Done requirements in
> `ai/AGENTS.md` §7, §12 and §13.

## Re-review summary

The follow-up commit `feb0652` addresses M1, S2, and S3. All three are **resolved**.
S1 was a non-blocking suggestion and was not changed (still open). One new minor nit
surfaced (the README quick-start command omits `--wait`). Verdict is unchanged.

## Verdict

**Approve.** No blockers or majors. The original findings that were actionable are
resolved; the only remaining items are non-blocking polish (S1) and a one-word README
consistency nit (R1).

## Verification performed (re-review)

| Check | Command | Result |
| ----- | ------- | ------ |
| Unit tests | `pytest` | **21 passed** |
| Integration tests | `pytest -m integration` | **7 passed in 83.67s** (incl. renamed test) |
| Lint | `ruff check .` | All checks passed |
| Type check | `mypy libs tests` | Success (6 source files) |
| Format | `ruff format --check .` | 1 pre-existing `.md` flagged (out of scope — unchanged) |

The integration suite was re-run against the real Docker daemon after the test rename and
passed, including the renamed `test_postgres_accepts_connections`. The follow-up did not
touch `docker-compose.yml`, so the Compose config validated earlier is unaffected.

**Format note (out of scope, unchanged):** `ruff format --check .` still flags
`docs/reviews/TASK-003-review.md` (a Python code block in the prior TASK-003 review doc).
This is pre-existing on `main`, not introduced by TASK-004 or its follow-up.

## Findings — resolution status

| ID | Severity | Finding | Status |
| -- | -------- | ------- | ------ |
| M1 | MINOR | `README.md` did not surface the local infrastructure | ✅ Resolved |
| S1 | SUGGESTION | Local-only default credentials committed | ⏳ Unchanged (open) |
| S2 | SUGGESTION | `test_postgres_accepts_queries` misnamed | ✅ Resolved |
| S3 | SUGGESTION | `_parse_ps` comment inaccurate | ✅ Resolved |

### M1 — Resolved

`README.md` now has a `### Local infrastructure` section with a `docker compose up -d`
quick start and a link to `docs/local-development.md`, and the `## Status` line now reads
`(TASK-001, TASK-002, TASK-003, TASK-004)`.

### S2 — Resolved

`test_postgres_accepts_queries` was renamed to `test_postgres_accepts_connections`, which
accurately reflects that it runs `pg_isready` rather than executing a query.

### S3 — Resolved

The `_parse_ps` comment now states that `docker compose ps --format json` emits one JSON
object per line (JSON lines) and handles the array shape, matching the code's behavior.

### S1 — Unchanged (open)

The local-only default credentials (`minioadmin-local`, `platform-local`) are still
committed as Compose defaults and in `.env.example`. This remains a non-blocking
suggestion; it was not part of the requested follow-up scope.

## New / residual findings

### MINOR

**R1 — README quick-start omits `--wait`.**

The new `### Local infrastructure` section instructs `docker compose up -d`, while the
canonical documented procedure in `docs/local-development.md` is
`docker compose up -d --wait`. The doc explicitly explains that `--wait` "blocks until
every service reports healthy, so the command returning successfully means the stack is
ready to use." The README's shorter form returns immediately while services are still
starting, which can mislead a developer who then tries to connect right away. Align the
two commands (one word: `-d --wait`).

### BLOCKER / MAJOR

None.

## "No unrelated behavior changed" check

The follow-up diff (`b061009..feb0652`) touches only `README.md` and
`tests/test_docker_compose.py`:

- `README.md` — additive (new section + status line), no removal or rewording of existing
  content.
- `tests/test_docker_compose.py` — a comment correction in `_parse_ps` and a test rename;
  the `_parse_ps` body and the renamed test's body are byte-for-byte unchanged.

No production/implementation code (`docker-compose.yml`, `docs/local-development.md`,
`.env.example`) was modified. No behavior change introduced.

## Conclusion

The follow-up cleanly resolves M1, S2, and S3 with a tightly scoped, additive diff, and
all tests and checks still pass (unit 21/21, integration 7/7). The only remaining items
are non-blocking: the pre-existing S1 credential note and the new R1 `--wait` consistency
nit. TASK-004 is approved.
