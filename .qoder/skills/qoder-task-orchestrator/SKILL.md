# Qoder Task Orchestrator

Automates the complete task development lifecycle by orchestrating independent Qoder chat sessions for each task phase. Replaces manual task execution with automated workflow management.

## When to Use

- User asks to "run task XXX", "implement TASK-010", or "automate task workflow"
- Need to execute tasks in isolated worktrees with full tool access
- Want automated implementation, review, PR creation, and CI monitoring
- Managing multiple sequential or dependent tasks

## Prerequisites

Before invoking, verify:
1. Main branch is clean (`git status` shows nothing)
2. Task specification exists at `ai/tasks/TASK-xxx-specification.md`
3. Python 3.12+, Git, Qwen Code CLI, GitHub CLI are available
4. Project hooks (`.githooks/`) are merged into main
5. At most one other task worktree is active

## Architecture

The orchestrator creates **independent Qoder chat sessions** for each phase:

```
Main OrchAgent
    ├─ Session 1: Implementation (worktree isolation)
    ├─ Session 2: Review assistance (optional)
    └─ Monitors: Git state, CI status, PR lifecycle
```

Each session runs with full Read/Edit/Bash/Git tool access in its own worktree environment.

## Workflow Phases

### Phase 1: Prepare Environment

```python
# Validate prerequisites
git status --porcelain  # must be empty
git branch --show-current  # must be "main"

# Create isolated worktree
git worktree add -b feature/TASK-xxx ../ai-platform-task-xxx <base-commit>

# Initialize state tracking
state = {
    "phase": "preparing",
    "repo": str(repo_path),
    "task": "TASK-xxx",
    "branch": "feature/TASK-xxx",
    "worktree": "../ai-platform-task-xxx",
    "rounds": 0,
    "base": git_rev_parse("HEAD")
}
```

### Phase 2: Implement via Qoder Session

Spawn an independent Qoder conversation targeting the worktree:

```python
# Create implementation session
impl_session = create_chat_session(
    prompt=f"""
Working directory: {worktree_path}

Implement only TASK-xxx from ai/tasks/TASK-xxx-specification.md.

Required reading before starting:
- ai/AGENTS.md (agent conventions)
- ai/PROJECT.md (project context)
- Relevant ADRs in ai/adrs/
- ai/SPECIFICATION.md (architecture spec)
- ai/ROADMAP.md (development roadmap)
- ai/AGENT_WORKFLOW.md (workflow rules)

Steps:
1. Check prerequisites; stop if unmet
2. Run required checks plus task-relevant integration tests
3. Inspect the diff carefully
4. Stage explicit task file paths
5. Commit locally with hooks enabled

Constraints:
- Do NOT push, create/merge PRs, change branches, or start another task
- Do NOT modify review reports
- Resolve all blocking review findings
- Fix useful in-scope minor findings
- Record non-blocking recommendations in docs/reviews/FOLLOWUPS.md
- Stop with a clean worktree and report checks passed
"""
)

# Wait for implementation to complete
wait_chat_sessions(sessionIds=[impl_session["sessionId"]], timeoutMs=3600000)

# Read transcript for logging
transcript = read_chat_session(sessionId=impl_session["sessionId"])
save_log(f"task-workflow/TASK-xxx/qoder-{attempt}.txt", transcript)

# Verify agent made commits
head = git(worktree, "rev-parse", "HEAD")
if head == before:
    raise Error("Qoder made no commit - inspect transcript")
```

### Phase 3: Automated Review

Run quality checks and invoke Qwen for review:

```python
# Execute local checks
run_checks(
    [
        ["python", "-m", "ruff", "format", "--check", "."],
        ["python", "-m", "ruff", "check", "."],
        ["python", "-m", "mypy"],
        ["python", "-m", "pytest"],
        ["python", "scripts/verify_repository_structure.py"],
    ]
)

# Get diff for review
diff = git_diff("--no-ext-diff", "--no-textconv", f"{base}...{head}")

# Send to Qwen in plan mode
review_output = run_qwen_review(diff=diff, spec=spec_content, head=head, base=base)

# Parse verdict
verdict = parse_workflow_review(review_output, head)
# Must be exactly "APPROVED" with blocking_findings=0

# Save review report
write_file(f"docs/reviews/TASK-xxx-review.md", review_output)
git_add("docs/reviews/TASK-xxx-review.md")
git_commit("-m", f"Record TASK-xxx Qwen review")
```

### Phase 4: Publish & Create PR

```python
# Push branch to remote
git_push("-u", "origin", f"feature/TASK-xxx")

# Check for existing PR
prs = gh_pr_list(state="open", base="main", head=f"feature/TASK-xxx", json=["number"])

if prs:
    pr_number = prs[0]["number"]
else:
    # Create new PR
    pr_body = f"""
Implements TASK-xxx according to `{spec_path}`.

Qwen approved implementation `{reviewed_head}`; see
`docs/reviews/TASK-xxx-review.md`. Local repository checks passed.
"""
    pr_number = gh_pr_create(
        base="main", head=f"feature/TASK-xxx", title=f"Implement TASK-xxx", body=pr_body
    )

state.update(phase="ci", pr=pr_number)
```

### Phase 5: Monitor CI

```python
# Poll GitHub Actions until checks pass or timeout
deadline = time.monotonic() + ci_timeout
while time.monotonic() < deadline:
    # Get check runs
    check_runs = gh_api(f"repos/{repo}/commits/{head}/check-runs?per_page=100")

    # Get commit statuses
    statuses = gh_api(f"repos/{repo}/commits/{head}/status?per_page=100")

    # Evaluate results
    if any(check["conclusion"] == "failure" for check in check_runs):
        state.update(phase="fix", feedback=f"CI failed for PR #{pr_number}. Fix and resume.")
        return  # Pause for manual intervention

    if all_required_checks_passed(check_runs, statuses):
        if auto_merge:
            gh_pr_merge(pr_number, squash=True, match_head=head)
            state.update(phase="merged")
        else:
            print(f"CI passed. Resume with --auto-merge to merge.")
        return

    time.sleep(15)  # Poll interval

raise Error("CI timed out")
```

### Phase 6: Cleanup

After successful merge:

```python
# Update main
git_checkout("main")
git_pull("--ff-only", "origin", "main")

# Remove worktree
clean_cache_files(worktree)  # __pycache__, .pytest_cache, etc.
git_worktree_remove(worktree_path)

# Delete branches
git_branch("-D", f"feature/TASK-xxx")
git_push("origin", f":refs/heads/feature/TASK-xxx")

state.update(phase="done")
```

## State Management

Persist progress in `task-workflow/TASK-xxx/state.json`:

```json
{
  "phase": "implement",
  "repo": "C:\\Users\\igors\\RnD\\agentic-data-platform",
  "task": "TASK-010",
  "branch": "feature/TASK-010",
  "worktree": "C:\\Users\\igors\\RnD\\ai-platform-task-010",
  "rounds": 1,
  "base": "abc123...",
  "integration": false,
  "origin": "git@github.com:user/repo.git",
  "required_checks": ["Quality checks"],
  "reviewed": "def456...",
  "approved_head": "def456...",
  "pr": 42
}
```

## Recovery & Resumption

If interrupted mid-phase:

1. **Inspect state:**
   ```bash
   cat task-workflow/TASK-xxx/state.json
   ```

2. **Finish partial work manually** in the worktree

3. **Resume orchestration:**
   ```python
   # The orchestrator reads state.json and continues from current phase
   orchestrator.resume(task_id="TASK-xxx")
   ```

## Session Logs

Agent transcripts save to `task-workflow/TASK-xxx/qoder-{attempt}.txt`. These contain:
- Full conversation history
- Tool call details
- Agent reasoning
- Error messages

**Do not commit these files** - they may contain repository metadata.

## Error Handling

### Common Failure Modes

**Agent Made No Commit:**
```
Error: Qoder made no commit; inspect transcript
```
→ Read `qoder-1.txt` to understand why
→ Manually implement or adjust the prompt
→ Resume with incremented round count

**Review Blocked:**
```
Error: Qwen marked the task BLOCKED
```
→ Read `docs/reviews/TASK-xxx-review.md`
→ Fix blocking issues in worktree
→ Resume with `--review-again`

**CI Failures:**
```
Error: CI checks failed for PR #42
```
→ Inspect GitHub Actions logs via `gh run view`
→ Fix code in worktree, commit
→ Orchestrator will re-push and re-check

**Worktree Conflicts:**
```
Error: Unmanaged task branch/worktree exists
```
→ Inspect manually: `cd ../ai-platform-task-xxx && git status`
→ Remove if stale: `git worktree remove ../ai-platform-task-xxx`
→ Or adopt by updating state.json

## Limitations

- **Must run within Qoder agent environment** - requires `create_chat_session` and related tools
- **Maximum 2 concurrent task worktrees** enforced by orchestrator lock
- **Sessions persist until archived** - clean up old sessions periodically
- **No stacked prerequisites** - all dependencies must be merged to main first
- **Single repository focus** - does not support cross-repository workflows

## Integration with Wrapper Script

Use alongside `scripts/run_task.py` for:
- Task discovery and listing
- Prerequisite validation
- Status monitoring
- Git-based completion detection

The wrapper handles UI/orchestration concerns; this agent handles execution.

## See Also

- `QUICKSTART.md` - Quick reference guide for getting started
- `scripts/run_task.py` - Interactive task runner wrapper
- `scripts/README_TASK_AUTOMATION.md` - Complete automation system documentation
- `scripts/qoder_task_workflow.py` - Original workflow implementation
- `docs/AUTOMATED_TASK_WORKFLOW.md` - Detailed workflow documentation
- `ai/AGENT_WORKFLOW.md` - Agent development conventions
- `ai/REVIEWER.md` - Qwen review criteria
