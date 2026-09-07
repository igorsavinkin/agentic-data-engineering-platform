# scripts/

Development and operational helper scripts. `verify_repository_structure.py` checks the repository foundation required by TASK-001.

## Final local checks

Activate the project's Python environment, then run `bash scripts/task_check.sh`
in Git Bash or `./scripts/task_check.ps1` in PowerShell. PowerShell also accepts
`-Python .venv/Scripts/python.exe`. Both run the checks configured in CI and stop
on failure. Run task-relevant integration tests separately; pytest excludes them
by default. Do not commit implementation until required checks pass.

## Independent review

From a clean, committed `feature/TASK-007` worktree:

```powershell
./scripts/review_task.ps1 007
```

This prints a review prompt with the specification, exact commit range, status,
commits, and diff. It does not run a reviewer by default. For a stacked branch,
pass `-Base <parent-commit>` to exclude the preceding task's changes.
Use `-Reviewer { param($prompt) ... }` to call your installed reviewer's documented
CLI with that prompt. The launcher must throw on a nonzero native exit code.
No reviewer-specific flags or approval bypasses are assumed. The reviewer must
write and verify the report required by `ai/REVIEWER.md`; generating this prompt
does not constitute a completed review.

## Optional hooks

Keep pre-commit checks limited to `python -m ruff check .` and
`python -m ruff format --check .`. A pre-push hook may run `python -m pytest` and
`python -m mypy`. Do not put Docker tests in pre-commit. Hooks are not installed
automatically and do not replace CI or required task-specific verification.
