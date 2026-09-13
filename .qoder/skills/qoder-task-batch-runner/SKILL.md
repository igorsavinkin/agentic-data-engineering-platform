---
name: qoder-task-batch-runner
description: Runs an ordered list of dependent TASK-xxx specifications sequentially in one session, where each task completes the full orchestrator workflow and passes the merge gate to main before the next one starts. Use when the user asks to "batch run", "run tasks sequentially", "run TASK-020 through TASK-026", or resume an interrupted batch. Invoke with @qoder-task-batch-runner.
---

# Qoder Task Batch Runner

Runs a list of dependent TASK-xxx specifications **sequentially in one session**: task N+1 starts only after task N is fully merged to `main`. Each task executes the complete single-task workflow defined in the `qoder-task-orchestrator` skill (`.qoder/skills/qoder-task-orchestrator/SKILL.md`).

## When to Use

- User asks to "run tasks TASK-020 through TASK-026", "implement these tasks sequentially", or "batch run"
- A group of tasks where each task depends on the previous one being merged

## Activation Is Human Approval

`ai/AGENTS.md` forbids an agent from *automatically* continuing to the next task. This skill is different: the human explicitly provides the ordered task list and invokes the batch. That invocation is the human selection of every task in the list and is a valid authorization to chain. The human may interrupt or stop the batch at any time.

## Merge Behavior

Orchestrator Phase 5 merges automatically once all required checks pass — there is no per-task merge prompt. Invoking the batch is the owner's delegation to merge every task in it. To hold a task back, interrupt the batch while its CI is running; the merge gate then never fires and task N+1 does not start.

Automatic merging covers the merge action only. Blocking review findings, scope changes, architecture decisions, and merge conflicts remain escalation points — stop the batch and report per `ai/AGENTS.md`.

## Input

Invoke the skill with the ordered task list:

```
@qoder-task-batch-runner TASK-022, TASK-023, TASK-024
```

Plain-language equivalents ("run TASK-022 through TASK-024 sequentially", "resume the batch") activate the same skill.

The user provides one of:

- An explicit list: `TASK-020, TASK-021, TASK-023`
- A range: `TASK-020..TASK-026` (expand and verify every spec exists)
- A milestone slice: read `ai/ROADMAP.md`, list pending tasks in the milestone, and **confirm the resolved list with the user before starting**

Tasks run in the given order. Never reorder or skip a failed task.

## Pre-Batch Validation

Before the first task:

1. `git status` — working tree must be clean on `main`; if dirty, STOP and report (AGENTS.md §16)
2. `git pull --ff-only origin main` — start from the latest main
3. Verify every task spec exists in `ai/tasks/`
4. Verify no stale worktrees/branches conflict: `git worktree list`, `git branch --list "feature/TASK-*"`
5. Initialize the batch progress file (see State Tracking)

If any check fails, stop and report — do not begin the batch.

## Batch Loop

For each task in order, execute the full orchestrator workflow:

```
For TASK-N in task list:
  1. Update progress file: current = TASK-N, phase = running
  2. Execute ALL six orchestrator phases for TASK-N:
       Prepare → Implement → Review (MANDATORY, Qwen APPROVED)
       → Publish (PR) → CI monitor (green) → Merge to main
  3. VERIFY MERGE GATE (see below) before anything else
  4. Mark TASK-N done in progress file
  5. ONLY NOW start TASK-N+1
```

### Merge Gate — the core dependency check

Before starting task N+1, all of these must be true for task N:

```bash
# 1. PR is merged (not just CI-green)
gh pr view <pr-number> --json state,mergedAt    # must be MERGED

# 2. The implementation is actually on origin/main
git fetch origin main
git branch -r --contains <task-N-merge-commit>   # must list origin/main

# 3. Local main is fast-forwarded to include it
git checkout main && git pull --ff-only origin main
git log --oneline -1                              # should be TASK-N's merge commit

# 4. Task N worktree is removed, branch deleted
git worktree list                                 # no task-N entry
```

If the merge gate fails, task N is **not done**. Do not start task N+1. Fix the gate condition (finish merge, reconcile main) or stop the batch and report.

Because every task branches from post-merge `main`, task N+1 automatically sees task N's code and interfaces.

### Per-Task Review Retry Budget

Each task in the batch gets up to 3 total review rounds (1 initial + 2 fix attempts). The orchestrator skill's Phase 3 implements this loop:

1. Initial implementation → Qwen review
2. If CHANGES REQUIRED: fix findings → commit → re-review (round 2)
3. If still CHANGES REQUIRED: fix again → commit → re-review (round 3)
4. If still not APPROVED after round 3: stop batch, escalate to owner

If any round returns BLOCKED, stop immediately without consuming remaining rounds.

This budget is tracked in `task-workflow/TASK-xxx/state.json` under the `rounds` key and is independent of the CI retry budget.

## Failure Policy — Stop, Never Skip

The batch STOPS at the first task that cannot complete. Specifically:

| Failure | Action |
|---------|--------|
| Review returns BLOCKED | Stop batch immediately (hard stop, no retry) |
| Review fix loop exhausts 3 rounds | Stop batch, report final review findings |
| CI fails and fix+re-push exceeds 3 attempts | Stop batch, report `gh run view` summary |
| Escalation criteria hit (AGENTS.md §13) | Stop batch immediately, per normal escalation |
| Merge conflict with main | Stop batch, report; human decides |

Cheap, in-scope fixes (lint, a broken test caused by this task, CI flake re-run) should be fixed and continued within the same task — that is task-internal retry, not a batch failure.

When stopping: leave the failed task's worktree and branch intact for inspection, mark it `failed` in the progress file, and report:
1. Which task failed and at which phase
2. Exact error / review findings / CI failure summary
3. What completed successfully before it
4. Resume command (`@qoder-task-batch-runner resume`)

**Never** continue past a failure "to see if later tasks work" — they depend on the failed one.

## State Tracking

Persist batch progress in `task-workflow/batch/progress.json` (in the main repo, not a worktree):

```json
{
  "batch_id": "2026-09-12-milestone-3",
  "tasks": ["TASK-020", "TASK-021", "TASK-022", "TASK-023"],
  "current": "TASK-021",
  "results": {
    "TASK-020": { "status": "done", "pr": 30, "merge_commit": "cb8ad24" },
    "TASK-021": { "status": "running", "phase": "implement" }
  },
  "updated_at": "2026-09-12T15:00:00Z"
}
```

Update this file at every phase transition of every task. It is the single source of truth for resumption.

## Resumption

If the session is interrupted, crash-recovers, or the user re-invokes with "resume":

1. Read `task-workflow/batch/progress.json`
2. Find the first task not marked `done`
3. If that task has a partial state (`task-workflow/TASK-xxx/state.json`), resume it via the orchestrator skill's Recovery & Resumption section, completing its merge gate first
4. Then continue the batch loop

If the progress file disagrees with git reality (e.g., says `running` but the PR is merged), trust **git/GitHub** and correct the file.

## Context Economy for Long Batches

Later tasks in a large batch suffer from accumulated session context. Mitigate:

- After each task's merge gate passes, print a compact one-line status (`✔ TASK-020 merged as cb8ad24, PR #30`) — not a recap
- Do not re-read completed tasks' diffs; `main` already contains them
- Keep per-task state in files, not in conversation memory
- If context is genuinely degrading (repeated mistakes, forgetting conventions), stop the batch cleanly and tell the user to resume in a fresh session — the progress file makes this safe

## Per-Task Reminders

- One task = one branch = one PR, exactly as `ai/AGENTS.md` requires; the batch runs many *separate* executions-of-tasks, never one mega-commit
- The Review phase is mandatory for **every** task in the batch — batching does not weaken any gate
- Commit isolation: each task's commit contains only that task's changes; verify `git diff main...HEAD` before each PR
- After the final task: remove all worktrees, delete branches, pull main, mark batch `complete`, and present a final summary table of all PRs/commits

## Summary Report Format

End the batch with:

```
Batch complete: 4/4 tasks merged
  ✔ TASK-020  PR #30  cb8ad24  MinIO Integration
  ✔ TASK-021  PR #31  a1b2c3d  Bronze Parquet Writer
  ✔ TASK-022  PR #32  e4f5g6h  Silver Parquet Writer
  ✔ TASK-023  PR #33  i7j8k9l  Partitioning Strategy
main is up to date. All worktrees cleaned up.
```

or, on failure:

```
Batch stopped at TASK-022 (2/4 merged)
  ✔ TASK-020  PR #30  merged
  ✔ TASK-021  PR #31  merged
  ✘ TASK-022  review BLOCKED — 2 MAJOR findings (see docs/reviews/TASK-022-review.md)
  · TASK-023  not started
Worktree ../ai-platform-task-022 preserved for inspection.
Resume with: @qoder-task-batch-runner resume
```

## See Also

- `.qoder/skills/qoder-task-orchestrator/SKILL.md` — the single-task workflow this batch loop executes per task (phases, review gate, state schema, recovery)
- `ai/AGENTS.md` — persistent operational rules (scope, git isolation, escalation)
- `ai/AGENT_WORKFLOW.md` — two-lane workflow and dependency gates
