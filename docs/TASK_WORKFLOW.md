# Task workflow: Codex implementation and Qwen review

Follow this order for each task:

**Implement → local checks → local commit → Qwen review → fixes and approval → push → PR and CI → owner merge decision.**

Qwen must review before the first push to origin. Review subsequent implementation
fixes before pushing them as well. The hooks run checks automatically, but do not
enforce Qwen approval. The owner and implementation agent must enforce that gate.

## 1. Prepare a task worktree

These examples use TASK-006 and Windows PowerShell. Replace `006` consistently
for another task. First ensure the workflow scripts and hooks have been committed
and merged into `main`; new worktrees created from main need those files.

From the main repository checkout, verify that no unrelated changes are present:

```powershell
git status --short
git switch main
git pull --ff-only
git worktree add -b feature/TASK-006 ../ai-platform-task-006 main
cd ../ai-platform-task-006
```

Stop if a command fails. If the task branch or worktree already exists, use the
existing task worktree instead of recreating it. Do not stash or commit another
task's changes to make these commands succeed.

Create the environment once per worktree, using Python 3.12 or newer:

```powershell
python -m venv .venv
. .venv/Scripts/Activate.ps1
python -m pip install -r requirements-dev.txt
& 'C:/Program Files/Git/bin/bash.exe' scripts/install_hooks.sh
git config --show-origin --get core.hooksPath
qwen --version
```

The hook path should be `.githooks`. Linked worktrees normally share that Git
setting, but each branch needs the hook files. In each new terminal, activate the
environment again with `. .venv/Scripts/Activate.ps1`. Git launched by an IDE also
needs this Python environment on its PATH. Authenticate through `qwen` if needed.

## 2. Implement one task

Open the task worktree in the implementation environment. Give Codex or Qoder:

> Implement TASK-006 according to ai/AGENTS.md and its task specification. Read
> the required project context, stay within this task, run focused tests during
> development, and run final required checks before committing. Commit locally,
> report the commit hash, and stop. Do not push or start another task.

The implementation agent runs the commands below. You do not need to repeat
successful checks yourself unless debugging or checking questionable evidence.

```powershell
./scripts/task_check.ps1
git diff
git status --short
```

Run task-relevant integration tests separately; the default pytest run excludes
them. When the task requires the Docker integration suite and its prerequisites
are running, use `python -m pytest -m integration`.

Stage only the task's files, inspect the staged diff, and commit. Replace the
placeholder paths below with actual paths; do not paste them literally:

```powershell
git add -- <file1> <file2>
git diff --cached
git commit -m "Implement TASK-006 event schema"
git status --short
git log -1 --oneline
```

Every commit automatically runs Ruff lint and format checks. A failure blocks
the commit; fix the issue and retry. Do not bypass the hooks.

## 3. Run Qwen review before pushing

The task worktree must be clean and on `feature/TASK-006`:

```powershell
./scripts/qwen_review_task.ps1 006
Get-Content docs/reviews/TASK-006-review.md
```

To inspect the prompt without launching Qwen:

```powershell
./scripts/qwen_review_task.ps1 006 -Preview
```

The helper supplies the task specification, commit range, and diff to Qwen and
requires a nonempty new or updated report. A successful command means a report
was written, not that the task was approved. Read its verdict and findings.
If Qwen cannot run or cannot write the report, resolve that failure before push.
See [script usage](../scripts/README.md) for an explicit Qwen launcher path.

## 4. Resolve findings and record approval

- Resolve Critical/BLOCKER and High/MAJOR findings before acceptance, unless the
  owner explicitly rejects a finding with a documented rationale.
- Fix worthwhile Minor findings within scope.
- Record deferred non-blocking recommendations in
  [FOLLOWUPS.md](reviews/FOLLOWUPS.md), with a reason and revisit trigger.

Ask the implementation agent to fix the findings. Run affected checks and any
remaining required task checks. Commit the fixes and review report locally using
explicit file paths. The review helper requires a clean worktree before a rerun:

```powershell
git status --short
./scripts/qwen_review_task.ps1 006
Get-Content docs/reviews/TASK-006-review.md
```

Repeat until the final implementation is approved or approved with accepted
non-blocking findings. Commit the final report:

```powershell
git add -- docs/reviews/TASK-006-review.md
git diff --cached
git commit -m "Record TASK-006 Qwen review"
git status --short
```

A report-only commit does not require another review of the unchanged
implementation. Any additional implementation changes need review again before
push. Keep the report's reviewed commit identity intact.

## 5. Push, open the PR, and check CI

Only after the review gate is satisfied:

```powershell
git push -u origin feature/TASK-006
gh pr create --base main --fill
gh pr checks --watch
gh pr view --web
```

GitHub CLI must be installed and authenticated; alternatively create and inspect
the PR in GitHub's web interface. Every push automatically runs pytest and mypy
locally. GitHub then runs its configured CI checks on the PR. Wait for checks on
the final revision; if none appear yet, inspect the PR and check again.

If CI finds a defect, fix it locally, validate it, commit it, obtain Qwen review
of the changed implementation, commit the updated report, and push again.
The owner merges only after review findings are resolved and final CI passes.

After merging, update the main checkout:

```powershell
cd '../Agentic data engineering platform'
git switch main
git pull --ff-only
```

## 6. Use two lanes when dependencies permit

Keep at most two active engineering tasks, each in a separate worktree and agent
execution. One task can be in Qwen review, fixes, or CI while the other is being
implemented. Never have two agents edit the same worktree concurrently.

The owner selects each next task. For TASK-006's event contract and TASK-007's
topic contract, wait for independent approval before starting dependent work.
Starting from main after the prerequisite merges is the simplest default.

If deliberately starting from an approved but unmerged prerequisite, record its
exact commit as the child branch's base and pass it to the reviewer:

```powershell
./scripts/qwen_review_task.ps1 007 -Base <parent-commit>
```

Replace the placeholder with the recorded commit. Reconcile the child branch
after the parent merges and inspect its PR diff. If review changes a prerequisite
interface, pause dependent work until it is reconciled. Do not start subsequent
tasks automatically.
