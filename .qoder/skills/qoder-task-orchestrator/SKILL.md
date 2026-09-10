# Qoder Task Orchestrator

Automates the complete task development lifecycle in a single session. The agent creates a worktree, implements the task, runs review, creates a PR, and monitors CI — all sequentially without spawning child sessions.

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

Single-session linear workflow — no child sessions, no delegation:

```
One Agent Session
    ├─ Phase 1: Prepare (create worktree)
    ├─ Phase 2: Implement (edit files, commit)
    ├─ Phase 3: Review (quality checks + Qwen review)
    ├─ Phase 4: Publish (push + create PR)
    ├─ Phase 5: Monitor CI (poll until pass/fail)
    └─ Phase 6: Cleanup (remove worktree)
```

**DO NOT use `create_chat_session()` or `fork_chat_session()`.** All work happens in this session.

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

### Phase 2: Implement

Implement the task directly in this session. All file operations target the worktree.

```python
# STEP 1: Read required context files
read_file("ai/AGENTS.md")  # agent conventions
read_file("ai/PROJECT.md")  # project context
read_file(spec_path)  # task specification
# Read relevant ADRs, SPECIFICATION.md, ROADMAP.md as needed

# STEP 2: Implement the task
# Edit/create files in the worktree using absolute paths
# e.g., Edit file_path=f"{worktree_path}/services/processor/module.py"

# STEP 3: Run quality checks in the worktree
run_in_worktree(
    worktree_path,
    [
        ["python", "-m", "ruff", "format", "--check", "."],
        ["python", "-m", "ruff", "check", "."],
        ["python", "-m", "mypy"],
        ["python", "-m", "pytest"],
    ],
)

# STEP 4: Inspect the diff
git_diff("--stat", f"{base}...HEAD")
git_diff(f"{base}...HEAD")

# STEP 5: Stage and commit
git_add(*changed_files)
git_commit("-m", f"feat(TASK-xxx): <descriptive message>")

# STEP 6: Verify commit was made
head = git(worktree, "rev-parse", "HEAD")
if head == base:
    raise Error("No commits made — implementation failed")

# STEP 7: Update state
state.update(phase="implement-complete")
write_json(f"task-workflow/TASK-xxx/state.json", state)
```

**Implementation constraints:**
- Work only in the worktree — never modify the main repo checkout
- Do NOT push, create/merge PRs, or change branches
- Do NOT start another task
- Stop with a clean worktree (no uncommitted changes)

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
if head == base:
    raise Error("Implementation made no commits - cannot proceed to review")

print(f"Implementation commit: {head}")
print("Starting mandatory review phase...")

# STEP 2: Execute local quality checks
print("Running quality checks...")
run_in_worktree(
    worktree_path,
    [
        ["python", "-m", "ruff", "format", "--check", "."],
        ["python", "-m", "ruff", "check", "."],
        ["python", "-m", "mypy"],
        ["python", "-m", "pytest"],
        ["python", "scripts/verify_repository_structure.py"],
    ],
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
    # Fix blocking findings in the worktree, commit, and re-review
    raise Error(f"Review not approved: {verdict}")

print("Review APPROVED")

# STEP 6: Update state to mark review complete
state.update(phase="review-complete", reviewed=head, approved_head=head)
write_json(f"task-workflow/TASK-xxx/state.json", state)
print(f"State updated: phase='review-complete', reviewed='{head}'")

# STEP 7: Save review report
write_file(f"{worktree_path}/docs/reviews/TASK-xxx-review.md", review_output)
git_add("docs/reviews/TASK-xxx-review.md")
git_commit("-m", f"docs: Record TASK-xxx Qwen review")

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
review_report_path = f"{worktree_path}/docs/reviews/TASK-xxx-review.md"
if not os.path.exists(review_report_path):
    raise Error(
        f"BLOCKED: Review report not found at {review_report_path}\n"
        "You MUST complete Phase 3 (Qwen Review) before creating a PR.\n"
        "Go back and execute the review phase now."
    )

# Check 2: Review report is committed
review_committed = git(worktree, "log", "--oneline", "--", "docs/reviews/TASK-xxx-review.md")
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

print("Phase gate passed: Review phase verified")
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
        # Fix in worktree, commit, push, and re-enter this phase
        break

    if all_required_checks_passed(check_runs, statuses):
        if auto_merge:
            gh_pr_merge(pr_number, squash=True, match_head=head)
            state.update(phase="merged")
        else:
            print(f"CI passed. Resume to merge.")
        break

    time.sleep(15)  # Poll interval
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
   Read the state file and continue from the current phase.

## Error Handling

### Common Failure Modes

**No Commits Made:**
```
Error: No commits made — implementation failed
```
→ Check what went wrong (missing dependencies, wrong paths, etc.)
→ Fix and retry implementation

**Review Blocked:**
```
Error: Qwen marked the task BLOCKED
```
→ Read `docs/reviews/TASK-xxx-review.md`
→ Fix blocking issues in worktree
→ Re-run review phase

**CI Failures:**
```
Error: CI checks failed for PR #42
```
→ Inspect GitHub Actions logs via `gh run view`
→ Fix code in worktree, commit, push
→ Re-enter CI monitor phase

**Worktree Conflicts:**
```
Error: Unmanaged task branch/worktree exists
```
→ Inspect manually: `cd ../ai-platform-task-xxx && git status`
→ Remove if stale: `git worktree remove ../ai-platform-task-xxx`
→ Or adopt by updating state.json

## Limitations

- **Maximum 2 concurrent task worktrees** enforced by orchestrator lock
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
