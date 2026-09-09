# scripts/

Development and operational helper scripts. `verify_repository_structure.py` checks the repository foundation required by TASK-001.

Follow [the task workflow](../docs/TASK_WORKFLOW.md) for the complete PowerShell
sequence, including mandatory Qwen review before pushing to origin.

## Final local checks

Activate the project's Python environment, then run `bash scripts/task_check.sh`
in Git Bash or `./scripts/task_check.ps1` in PowerShell. PowerShell also accepts
`-Python .venv/Scripts/python.exe`. Both run the checks configured in CI and stop
on failure. Run task-relevant integration tests separately; pytest excludes them
by default. Do not commit implementation until required checks pass.

## Independent review

From a clean, committed `feature/TASK-007` worktree:

```powershell
./scripts/qwen_review_task.ps1 007
```

This launches the installed Qwen Code with the specification, exact commit range,
status, commits, and diff sent through UTF-8 stdin. It uses Qwen Code 0.23's
supported `-p` non-interactive prompt option and preserves its configured model,
authentication, and permission settings. Authenticate with `qwen` first in your
normal terminal. No approval-bypass flags are supplied; if permissions prevent
writing the report, the review remains incomplete.

Use `-Preview` to print the prompt without launching Qwen. For a stacked branch,
pass `-Base <parent-commit>` to exclude the preceding task's changes. The helper
requires a clean worktree and the exact task branch. Commit an existing review
report before rerunning it. Successful execution requires a nonempty, newly
written or updated `docs/reviews/TASK-007-review.md`; inspect its verdict, since
report creation is not approval.

`-QwenCommand 'C:/Users/igors/AppData/Local/qwen-code/bin/qwen.cmd'` can select an
explicit launcher. If Codex's sandbox denies access to that directory, execution
needs the normal sandbox approval flow; a PATH lookup failure does not establish
that Qwen is uninstalled. `-Reviewer { param($prompt) ... }` remains available
for another reviewer; custom launchers must throw on nonzero native exit codes
and write the same report.

## Project-managed Git hooks

From the repository root in Git Bash (Windows), with Python 3.12+ installed:

```bash
python -m venv .venv  # only if the environment does not exist
source .venv/Scripts/activate
python -m pip install -r requirements-dev.txt
bash scripts/install_hooks.sh
git config --show-origin --get core.hooksPath
```

On Linux/macOS use `source .venv/bin/activate`. On Windows use Git for Windows'
Git Bash, not the WSL `bash.exe`. From PowerShell, activate with
`. .venv/Scripts/Activate.ps1`, then run
`& 'C:/Program Files/Git/bin/bash.exe' scripts/install_hooks.sh`.

The installer selects `.githooks` through repository-local `core.hooksPath`;
it never writes `.git/hooks`. It is safe to rerun and refuses to replace a
different configured hooks path or shadow existing non-sample hooks.
Reconcile existing hooks manually first. Local Git config is not cloned:
install once per clone. Linked worktrees normally share this local setting,
so each checked-out branch must contain `.githooks`; check the effective setting
in each worktree. To uninstall, verify the setting is `.githooks`, then run
`git config --local --unset core.hooksPath` (any inherited setting applies again).

| Stage | Commands |
| --- | --- |
| pre-commit | `python -m ruff check .`, then `python -m ruff format --check .` |
| pre-push | `python -m pytest`, then `python -m mypy` |
| Full local check | `bash scripts/task_check.sh` or `./scripts/task_check.ps1` |

Checks stop at the first failure and block the Git operation. Fix the failure
and retry; hooks do not autoformat, stage, stash, or modify source files. They
check the working tree, including unstaged changes, not an isolated snapshot of
the staged commit or outgoing commits. Review partial staging carefully.
Missing Python or dependencies also blocks the operation: activate the environment
in the shell running Git (or launching the agent/IDE). Do not bypass hooks to
work around a broken environment.

Codex/Qoder should install the hooks during checkout setup, run focused tests
while editing, and let Git invoke each stage's checks. Run the full local helper
for final task verification, plus relevant integration tests; avoid repeating
the full helper before every intermediate commit. Qwen reviews test quality and
selectively reruns critical, changed, or suspicious tests rather than duplicating
CI. Record which checks ran and any limitations.

GitHub Actions remains the authoritative full CI gate on the final PR revision.
Hooks are local guardrails and can be absent or bypassed; they cannot enforce
merge policy. The full helper mirrors CI's check order: Ruff format, Ruff lint,
mypy, pytest, then repository structure validation. `python -m mypy` has no `.`
argument so it uses `pyproject.toml`'s configured targets. The current CI and
default pytest run exclude integration tests; run those separately when relevant.
Keep both task-check helpers aligned whenever CI changes.
# Task workflow agent

Run `python scripts/task_workflow.py --help` for the Codex/Qwen workflow runner.
See [setup, execution and recovery](../docs/AUTOMATED_TASK_WORKFLOW.md).
