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

## CRITICAL: Review Phase is MANDATORY

**DO NOT STOP AFTER IMPLEMENTATION.** The Qwen review phase (Phase 3) is a mandatory gate that must complete before proceeding to PR creation. Skipping review is a critical failure.

The workflow has these **mandatory sequential phases**:
1. Prepare → 2. Implement → **3. Review (MANDATORY)** → 4. Publish → 5. CI Monitor → 6. Cleanup

You MUST execute ALL phases. Never stop after Phase 2.

### Common Anti-Pattern (DO NOT DO THIS)

```
❌ WRONG: Implement → Commit → Create PR
❌ WRONG: Implement → Commit → Stop and report "done"
❌ WRONG: Implement → Commit → Push → Create PR (without review)
```

### Correct Workflow

```
✅ RIGHT: Implement → Commit → Quality Checks → Qwen Review → Save Report → Push → Create PR
```

### Phase State Transitions

| Phase | State Value | Gate to Next Phase |
|-------|------------|-------------------|
| 1. Prepare | `preparing` | Worktree created, state initialized |
| 2. Implement | `implement` → `implement-complete` | Commits exist, state updated |
| 3. Review | `implement-complete` → `review-complete` | Report saved, state updated, APPROVED |
| 4. Publish | `review-complete` → `ci` | **Phase gate validates review exists** |
| 5. CI Monitor | `ci` → `merged` | All checks pass |
| 6. Cleanup | `merged` → `done` | Worktree removed |

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

# Update state to mark implementation complete
state.update(phase="implement-complete")
write_json(f"task-workflow/TASK-xxx/state.json", state)
```

---

## ⛔ STOP: IMPLEMENTATION COMPLETE - REVIEW PHASE REQUIRED ⛔

**DO NOT PROCEED TO PR CREATION.**

You have completed Phase 2 (Implementation). The workflow is NOT complete.

**MANDATORY NEXT STEP:** Execute Phase 3 (Qwen Review) immediately.

Skipping the review phase is a **CRITICAL WORKFLOW FAILURE**. The review must complete before any PR can be created.

Proceed to Phase 3 now.

---

### Phase 3: Automated Review (MANDATORY - DO NOT SKIP)

**THIS PHASE IS REQUIRED.** After implementation completes, you MUST immediately execute the review phase. Never stop after Phase 2.

Run quality checks and invoke Qwen for review:

```python
# STEP 1: Verify implementation completed
head = git(worktree, "rev-parse", "HEAD")
if head == before:
    raise Error("Implementation made no commits - cannot proceed to review")

print(f"Implementation commit: {head}")
print("Starting mandatory review phase...")

# STEP 2: Execute local quality checks
print("Running quality checks...")
run_checks(
    [
        ["python", "-m", "ruff", "format", "--check", "."],
        ["python", "-m", "ruff", "check", "."],
        ["python", "-m", "mypy"],
        ["python", "-m", "pytest"],
        ["python", "scripts/verify_repository_structure.py"],
    ]
)
print("Quality checks passed")

# STEP 3: Get diff for review
diff = git_diff("--no-ext-diff", "--no-textconv", f"{base}...{head}")
spec_content = read_file(spec_path)

# STEP 4: Send to Qwen for review (MANDATORY)
print("Invoking Qwen review...")
review_output = run_qwen_review(diff=diff, spec=spec_content, head=head, base=base)

# STEP 5: Parse verdict
verdict = parse_workflow_review(review_output, head)
# Must be exactly "APPROVED" with blocking_findings=0

if verdict != "APPROVED":
    print(f"Review verdict: {verdict}")
    print("Implementation needs fixes - cannot proceed to PR creation")
    # Handle fix cycle or escalate
    raise Error(f"Review not approved: {verdict}")

print("Review APPROVED")

# STEP 7: Update state to mark review complete (MANDATORY)
state.update(phase="review-complete", reviewed=head, approved_head=head)
write_json(f"task-workflow/TASK-xxx/state.json", state)
print(f"State updated: phase='review-complete', reviewed='{head}'")

# STEP 8: Save review report (MANDATORY)
write_file(f"docs/reviews/TASK-xxx-review.md", review_output)
git_add("docs/reviews/TASK-xxx-review.md")
git_commit("-m", f"Record TASK-xxx Qwen review")

print("Review phase complete. Proceeding to Phase 4...")
```

**Validation Checklist Before Proceeding:**
- [ ] Quality checks passed (ruff, mypy, pytest)
- [ ] Qwen review invoked and completed
- [ ] Verdict is exactly "APPROVED"
- [ ] Review report saved to `docs/reviews/TASK-xxx-review.md`
- [ ] Review commit created

If any of these are missing, STOP and fix before proceeding.

### Phase 4: Publish & Create PR

**PHASE GATE - MANDATORY VALIDATION:**
Before proceeding to Phase 4, you MUST verify ALL of the following:

```python
# CRITICAL: Validate review phase completed before creating PR
import os

# Check 1: Review report file exists
review_report_path = f"docs/reviews/TASK-xxx-review.md"
if not os.path.exists(review_report_path):
    raise Error(
        f"BLOCKED: Review report not found at {review_report_path}\n"
        "You MUST complete Phase 3 (Qwen Review) before creating a PR.\n"
        "Go back and execute the review phase now."
    )

# Check 2: Review report is committed
review_committed = git("log", "--oneline", "--all", "--", review_report_path)
if not review_committed:
    raise Error(
        f"BLOCKED: Review report exists but is not committed.\n"
        "Commit the review report before proceeding to PR creation."
    )

# Check 3: State file shows review completed
state = read_json(f"task-workflow/TASK-xxx/state.json")
if state.get("phase") not in ["review-complete", "ci", "publish"]:
    raise Error(
        f"BLOCKED: State shows phase='{state.get('phase')}'\n"
        "Expected phase='review-complete' or later.\n"
        "Complete the review phase before proceeding."
    )

if not state.get("reviewed"):
    raise Error(
        "BLOCKED: State file missing 'reviewed' commit hash.\n"
        "The review phase must record the reviewed commit."
    )

print("✓ Phase gate passed: Review phase verified")
print(f"  - Review report: {review_report_path}")
print(f"  - Reviewed commit: {state['reviewed']}")
print("Proceeding to Phase 4...")
```

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

## Mandatory Completion Criteria

A task workflow is **only complete** when ALL of these are true:

1. Implementation committed to feature branch
2. Quality checks pass (ruff, mypy, pytest)
3. **Qwen review invoked and APPROVED**
4. Review report saved to `docs/reviews/TASK-xxx-review.md`
5. Review report committed to git
6. State file updated with `phase: "review-complete"` and `reviewed` hash
7. PR created on GitHub
8. CI checks passing
9. PR merged (if auto-merge enabled)

**Missing any of these means the workflow is INCOMPLETE.**

### Self-Check Before Declaring Complete

Before telling the user the workflow is done, verify:

```bash
# 1. Does the review report exist?
ls docs/reviews/TASK-xxx-review.md

# 2. Is it committed?
git log --oneline -- docs/reviews/TASK-xxx-review.md

# 3. Does state show review-complete or later?
cat task-workflow/TASK-xxx/state.json | grep phase

# 4. Does a PR exist?
gh pr list --head feature/TASK-xxx
```

If any of these fail, the workflow is NOT complete. Go back and finish the missing phase.

Most commonly, agents stop after implementation. This is WRONG. The review phase is a mandatory quality gate that cannot be skipped.

## See Also

- `QUICKSTART.md` - Quick reference guide for getting started
- `scripts/run_task.py` - Interactive task runner wrapper
- `scripts/README_TASK_AUTOMATION.md` - Complete automation system documentation
- `scripts/qoder_task_workflow.py` - Original workflow implementation
- `docs/AUTOMATED_TASK_WORKFLOW.md` - Detailed workflow documentation
- `ai/AGENT_WORKFLOW.md` - Agent development conventions
- `ai/REVIEWER.md` - Qwen review criteria
