# Task Orchestrator - Usage Examples

Two execution paths exist and they differ on merge policy:

| Path | Command | Merge on green CI |
|------|---------|-------------------|
| Wrapper script | `python scripts/run_task.py 010 --auto-merge` | Only with `--auto-merge` |
| Direct skill invocation (this skill) | `@qoder-task-orchestrator Implement TASK-010` | Always |

## Example 1: One Task From the Wrapper Script

```bash
python scripts/run_task.py --check            # verify prerequisites
python scripts/run_task.py 010 --auto-merge   # implement → review → PR → CI → merge
```

Useful flags (see `scripts/qoder_task_workflow.py` for the full list):

```bash
--depends-on 009          # prerequisite tasks; must already be merged to main
--max-rounds 3            # implementation/review rounds before the workflow stops
--ci-timeout 1800         # seconds to wait for GitHub Actions
--integration             # include integration tests
--spec path/to/spec.md    # register and run a new task specification
```

## Example 2: One Task by Invoking the Skill

```
@qoder-task-orchestrator Implement TASK-010
```

The agent executes all six phases in the current session:

1. Create worktree at `../ai-platform-task-010`
2. Implement directly in the worktree, commit
3. Quality checks + Qwen review (mandatory; must end APPROVED)
4. Commit the review report, push, create PR
5. Monitor CI, then merge — automatic
6. Pull `main`, remove the worktree, delete the branch

No child session is spawned; see `SKILL.md` ("DO NOT use `create_chat_session()`").

## Example 3: Sequential Dependent Tasks

Task N+1 branches from post-merge `main`, so it sees task N's code. Run a batch with:

```
@qoder-task-batch-runner TASK-020, TASK-021, TASK-022
```

The batch runner waits for each merge gate (PR `MERGED`, commit contained in `origin/main`,
worktree gone) before starting the next task, and stops at the first failure. See
`.qoder/skills/qoder-task-batch-runner/SKILL.md`.

## Example 4: Hold a PR Back From Merging

- **Script path:** omit `--auto-merge`. The run stops after CI with `CI passed. Resume with --auto-merge to merge and clean up.`
- **Skill path:** there is no manual-merge mode. Stop the session before its checks go green, inspect the PR, then resume the skill to continue from `state.json`.

## Example 5: Resume After an Interruption

```bash
cat task-workflow/TASK-010/state.json      # which phase stopped
cd ../ai-platform-task-010 && git status   # what is uncommitted
```

Then either re-invoke the skill (it reads the state file and continues from the current
phase), or for the scripted path re-run with `--review-again` after manually repairing the
worktree:

```bash
python scripts/qoder_task_workflow.py 010 --review-again
```

## Monitoring During Execution

```bash
cat task-workflow/TASK-010/state.json | jq '.phase, .rounds, .pr'
gh pr list --head feature/TASK-010 --json number,state,mergeable
cd ../ai-platform-task-010 && git log --oneline
```

Scripted runs also save per-attempt transcripts under `task-workflow/TASK-010/`
(`qoder-<attempt>.txt`, `qwen-<round>.txt`). Skill runs keep their work in this session,
so the review report at `docs/reviews/TASK-010-review.md` is the durable record.

## Debugging a Failed Task

1. Read the failure text printed by the run, or `state.json`'s `feedback` field
2. Inspect the review findings: `docs/reviews/TASK-010-review.md`
3. Inspect CI logs: `gh run view --job <id> --log-failed`
4. Fix in the worktree, commit, then resume (Example 5)

Leave the failed task's worktree and branch in place until it is understood — they are the
only copy of the partial work.
