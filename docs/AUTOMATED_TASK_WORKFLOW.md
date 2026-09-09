# Automated task workflow

`scripts/task_workflow.py` runs one owner-selected task through specification,
isolated branch/worktree, Codex implementation, local checks and commits, Qwen
review, repairs, push, PR, CI, squash merge, local main update and cleanup.
This is development tooling; it does not change the platform's LangGraph agent.

## Run

First merge this tooling into main. Start from the clean main checkout, with
Python 3.12+, Git, authenticated Codex and Qwen Code CLIs, and authenticated
GitHub CLI available on PATH. Git must be able to run the project's Bash hooks.
The installed versions used to check CLI compatibility were Qwen Code 0.23.0
and the local Codex CLI supporting `exec --approve-for-me --sandbox workspace-write`.

```powershell
. .venv/Scripts/Activate.ps1
python scripts/task_workflow.py 009 --depends-on 008 --integration --auto-merge
```

Choose the actual task and its prerequisites. `--integration` additionally runs
the Docker integration suite; start its prerequisites first. The builder is
always instructed to run task-specific integration checks. `--depends-on` may
be repeated and requires each prerequisite PR to be merged into main; the
builder must also read specification dependencies. This runner uses main as its
base and does not implement stacked, unmerged prerequisites.

`--auto-merge` is the owner's explicit delegation of the merge decision for this
selected task. Omit it to stop after green CI; rerun with it to merge and clean
up. No admin merge, protection bypass, direct main push, or force push of
implementation commits is used. GitHub branch protection remains authoritative.
This option does not authorize architecture changes or rejection of blockers.

For a new task, provide a complete owner-written specification. The runner
creates and commits its file inside the task branch before implementation:

```powershell
python scripts/task_workflow.py 050 --spec C:/tasks/new-task.md --auto-merge
```

Existing specifications are read unchanged. No automatic numbering, task
selection, or chaining occurs. Task IDs use `feature/TASK-xxx`; worktrees are
siblings named `ai-platform-task-xxx`. Existing unmanaged resources are never
silently adopted. At most two task branches may have worktrees; the orchestrator
serializes its own runs using a repository-wide lock.

## Review and merge gates

Codex runs with the workspace-write sandbox and `--approve-for-me`, which routes
requests such as Git metadata writes through automatic approval review. Use a
Codex CLI version supporting that option; rejected requests still stop the work.
It commits locally with hooks, then the runner independently executes Ruff
format/lint, mypy, pytest and repository structure validation. The virtual
environment lives in Git's shared metadata outside the task worktree and is
put on PATH for agents, checks and hooks.

Qwen runs headlessly in read-only plan mode. The runner supplies the exact base,
HEAD and diff through stdin; Qwen reads repository context and returns the full
Markdown report. The runner writes and commits `docs/reviews/TASK-xxx-review.md`.
This is the automation equivalent of the interactive review helper; the reviewer
does not need write permissions. Qwen's complete report must include one footer:

```text
WORKFLOW_REVIEW: {"head":"<full commit SHA>","verdict":"APPROVED","blocking_findings":0}
```

Only the exact `APPROVED` verdict with zero blockers passes. Qwen is instructed
to require nonblocking findings to be fixed or documented as deferrals with
rationale and revisit triggers before approval. `CHANGES REQUIRED` sends the
report back to Codex; `BLOCKED`, malformed output, tool errors or contradictory
metadata stop the runner. It never automatically rejects a blocking finding.
The report-only commit does not require another review. Any implementation
change invalidates approval. Model judgments still require suitable task
specifications and tests; a machine-readable verdict is not proof of correctness.

All check runs and commit statuses on the approved PR HEAD must succeed, including
`Quality checks`. Missing, skipped, pending or failed checks never authorize a
merge. Failed CI goes back through implementation and Qwen review before another
push. `--required-check NAME` adds required check names. Merge uses GitHub CLI's
`--match-head-commit` to guard against a concurrent branch update.

## Recovery and limits

Rerun the same command after a transient error. Progress and agent final output
are retained under the shared Git directory's `task-workflow/TASK-xxx/` directory,
including after worktree deletion. The environment is retained there for
diagnostics/reuse as well. Do not commit these logs; they can contain private
repository information. `state.json` records the current phase and commit IDs.
Keep the same dependency, integration and check options when resuming; the
integration requirement is also persisted. `--max-rounds` defaults to three
builder executions, including CI repairs; `--ci-timeout` defaults to 1,800 seconds.
Agent calls retain CLI approval/auth behavior and can wait for provider responses;
interrupt if necessary. No unrestricted execution flags are added.

An interrupted builder is not relaunched blindly. Inspect its output and the
checkout, finish or repair partial changes, run checks and commit them, then:

```powershell
python scripts/task_workflow.py 009 --review-again --auto-merge
```

This starts a fresh review, never grants approval. Increase `--max-rounds` only
after inspecting a exhausted repair budget. If preparation was interrupted after
writing a new specification but before committing, inspect and commit that file
before resuming. If a process was killed, remove `task-workflow/run.lock` only
after verifying the recorded process and its child agents have stopped.

Cleanup verifies the merged PR and approved branch tip, fast-forwards local main,
and confirms the merge commit is present before removing the worktree. It removes
only ignored Python/test/lint cache files. Other ignored files (such as `.env` or
a manually created `.venv`) pause cleanup for preservation; rerun after moving
them elsewhere. It never forces worktree removal. Squash-merged local branches
are deleted only at the approved SHA, and remote deletion uses a SHA lease so
later remote work cannot be deleted. Logs and the external environment remain.

Use `--codex` or `--qwen` for an explicit executable/launcher path. Authentication,
unavailable dependencies, provider failures, blocked GitHub rules and unknown
review results stop with a nonzero exit code and preserve task work.

CLI references: [Codex noninteractive execution](https://learn.chatgpt.com/docs/non-interactive-mode)
and [Qwen headless execution](https://qwenlm.github.io/qwen-code-docs/en/users/features/headless/).
