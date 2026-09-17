---
name: qoder-task-orchestrator
description: Executes one TASK-xxx specification end to end in the current session - prepare worktree, implement, mandatory OCR code review, PR, CI monitoring, and automatic merge to main. Use when the user asks to "run task XXX", "implement TASK-xxx", or "automate the task workflow". Invoke with @qoder-task-orchestrator. For several sequential or dependent tasks, use @qoder-task-batch-runner instead.
---

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
3. Python 3.12+, Git, GitHub CLI are available
4. Open Code Review skill is available (`.qoder/skills/open-code-review/`)
5. Project hooks (`.githooks/`) are merged into main
6. At most one other task worktree is active

## Architecture

Single-session linear workflow — no child sessions, no delegation:

```
One Agent Session
    ├─ Phase 1: Prepare (create worktree)
    ├─ Phase 2: Implement (edit files, commit)
    ├─ Phase 3: Review (quality checks + OCR code review)
    ├─ Phase 4: Publish (push + create PR)
    ├─ Phase 5: Monitor CI (poll until pass/fail)
    └─ Phase 6: Cleanup (remove worktree)
```

**DO NOT use `create_chat_session()` or `fork_chat_session()`.** All work happens in this session.

## Remote Alerts (Telegram)

A full run takes a long time and should not require watching the terminal. When the workflow reaches a point where it cannot continue without you, send a Telegram alert **before** reporting the stop in chat:

```bash
python .qoder/notify/notify.py --level blocked \
  --subject "TASK-040 review BLOCKED" \
  --detail "OCR review found unresolvable High findings on round 3; owner decision needed" \
  --ref "https://github.com/<owner>/<repo>/pull/53"
```

**Send an alert at exactly these five points:**

| When | `--level` |
|---|---|
| OCR review finds `BLOCKED` findings (Phase 3) | `blocked` |
| `rounds >= 3` without approval (Phase 3) | `blocked` |
| Any Phase 4 review-gate guard fails | `blocked` |
| CI checks fail (Phase 5) | `failed` |
| PR merged to `main` (Phase 5) | `success` |

Do not alert on routine phase transitions. The value of this channel is that every message means either "come decide something" or "it is done" — noise destroys that.

**Alerting is best-effort and must never change a task's outcome.** If the script exits non-zero (unconfigured, no network) log the reason and continue exactly as you would have. If `.qoder/notify/` does not exist, skip alerting silently. Setup and troubleshooting: `.qoder/notify/README.md`.

## CRITICAL: Review Phase is MANDATORY

**DO NOT STOP AFTER IMPLEMENTATION.** The OCR review phase (Phase 3) is a mandatory gate that must complete before proceeding to PR creation. Skipping review is a critical failure.

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
✅ RIGHT: Implement → Commit → Quality Checks → OCR Review → Save Report → Push → Create PR
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

**MANDATORY NEXT STEP:** Execute Phase 3 (OCR Review) immediately.

Skipping the review phase is a **CRITICAL WORKFLOW FAILURE**. The review must complete before any PR can be created.

Proceed to Phase 3 now.

---

### Phase 3: Automated Review (MANDATORY - DO NOT SKIP)

**THIS PHASE IS REQUIRED.** After implementation completes, you MUST immediately execute the review phase. Never stop after Phase 2.

Run quality checks and perform OCR code review using the Open Code Review skill methodology:

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

# STEP 4: Perform OCR code review (inline, using Open Code Review skill)
#
# The agent analyzes the diff following the OCR skill methodology:
# 1. Gather business context from the task spec and project docs
# 2. Analyze each changed file in the diff
# 3. Classify findings by severity:
#    - High: bugs, security issues, clear mistakes, well-founded fix proposals
#    - Medium: reasonable concerns, style/perf suggestions, context-dependent
#    - Low: false positives, nitpicks, lacking context (discard silently)
# 4. Determine verdict:
#    - Any High findings → CHANGES REQUIRED
#    - No High findings → APPROVED
#
# Business context for the review:
task_id = Path(spec_path).stem.split("-")[0] + "-" + Path(spec_path).stem.split("-")[1]
background = f"Implementing {task_id}. Spec: {spec_path}. Branch: feature/{task_id}."

print(f"Performing OCR code review for {task_id}...")
print(f"Background: {background}")

# Analyze the diff — the agent reads each changed file and the diff,
# then produces structured findings following the OCR classification scheme.
# See .qoder/skills/open-code-review/SKILL.md for the full methodology.

review_findings = ocr_analyze_diff(
    diff=diff,
    background=background,
    spec_content=spec_content,
)

# STEP 5: Determine verdict from findings
high_findings = [f for f in review_findings if f.severity == "High"]
medium_findings = [f for f in review_findings if f.severity == "Medium"]

if high_findings:
    verdict = "CHANGES REQUIRED"
elif medium_findings:
    verdict = "APPROVED"  # Medium findings are non-blocking
else:
    verdict = "APPROVED"

print(f"OCR review: {verdict} ({len(high_findings)} high, {len(medium_findings)} medium)")

# STEP 6: Generate and save review report
report_content = format_ocr_report(
    task_id=task_id,
    verdict=verdict,
    findings=review_findings,
    files_reviewed=len(get_changed_files()),
    head=head,
)

review_report_path = f"{worktree_path}/docs/reviews/{task_id}-review.md"
write_file(review_report_path, report_content)
git_add("docs/reviews/{task_id}-review.md")
git_commit("-m", f"docs: Record {task_id} OCR review ({verdict})")

# STEP 7: Handle non-APPROVED cases
if verdict == "CHANGES REQUIRED":
    # Enter fix loop (up to max_rounds total attempts including initial implementation)
    max_fix_rounds = 3
    current_round = state.get("rounds", 1)
    final_verdict = verdict
    final_head = head

    while current_round < max_fix_rounds:
        current_round += 1
        state.update(rounds=current_round)

        print(f"Fix attempt {current_round}/{max_fix_rounds}: addressing OCR findings...")

        # Fix High findings in worktree based on review feedback
        for finding in high_findings:
            # Apply fix based on finding.path, finding.line, finding.recommendation
            apply_fix(worktree_path, finding)

        # Run quality checks to verify fixes
        run_in_worktree(
            worktree_path,
            [
                ["python", "-m", "ruff", "format", "--check", "."],
                ["python", "-m", "ruff", "check", "."],
                ["python", "-m", "mypy"],
                ["python", "-m", "pytest"],
            ],
        )

        # Commit fixes
        changed_files = get_changed_files()
        if changed_files:
            git_add(*changed_files)
            git_commit("-m", f"fix({task_id}): Address OCR review findings (round {current_round})")

        # Re-run OCR review with updated code
        new_head = git_rev_parse("HEAD")
        new_diff = git_diff("--no-ext-diff", "--no-textconv", f"{base}...{new_head}")

        print(f"Re-running OCR review (round {current_round})...")
        new_findings = ocr_analyze_diff(
            diff=new_diff,
            background=background,
            spec_content=spec_content,
        )

        new_high = [f for f in new_findings if f.severity == "High"]
        new_medium = [f for f in new_findings if f.severity == "Medium"]

        if new_high:
            final_verdict = "CHANGES REQUIRED"
            high_findings = new_high
        else:
            final_verdict = "APPROVED"

        # Update review report
        report_content = format_ocr_report(
            task_id=task_id,
            verdict=final_verdict,
            findings=new_findings,
            files_reviewed=len(get_changed_files()),
            head=new_head,
        )
        write_file(review_report_path, report_content)
        git_add("docs/reviews/{task_id}-review.md")
        git_commit("-m", f"docs: Update {task_id} OCR review ({final_verdict})")

        final_head = new_head

        if final_verdict == "APPROVED":
            print(f"Re-review APPROVED on round {current_round}")
            break
    else:
        if final_verdict != "APPROVED":
            raise Error(
                f"OCR review fix loop exhausted after {max_fix_rounds} rounds. "
                f"Final verdict: {final_verdict}. Owner must intervene. "
                f"See {review_report_path}"
            )

    head = final_head

print("Review APPROVED")

# STEP 8: Update state to mark review complete
state.update(phase="review-complete", reviewed=head, approved_head=head, rounds=current_round)
write_json(f"task-workflow/{task_id}/state.json", state)
print(f"State updated: phase='review-complete', reviewed='{head}', rounds={current_round}")

print("Review phase complete. Proceeding to Phase 4...")
```

**Validation Checklist Before Proceeding:**
- [ ] Quality checks passed (ruff, mypy, pytest)
- [ ] OCR review completed (diff analyzed, findings classified)
- [ ] Verdict is "APPROVED" (no unresolved High findings)
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
        "You MUST complete Phase 3 (OCR Review) before creating a PR.\n"
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

OCR review passed for implementation `{reviewed_head}`; see
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
        telegram_alert("failed", f"{task_id} CI failed", f"PR #{pr_number} checks failed", pr_url)
        # Fix in worktree, commit, push, and re-enter this phase
        break

    if all_required_checks_passed(check_runs, statuses):
        # Merging is unconditional: running the task is the owner's merge delegation
        gh_pr_merge(pr_number, squash=True, match_head=head)
        state.update(phase="merged")
        telegram_alert(
            "success", f"{task_id} merged to main", f"PR #{pr_number} squashed and merged", pr_url
        )
        break

    time.sleep(15)  # Poll interval
```

This skill has no manual-merge mode. To hold a PR for your own review, stop the session before its checks go green. The opt-in `--auto-merge` flag on `scripts/run_task.py` belongs to the scripted path only.

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
  "rounds": 1,  // Total implement-review cycles attempted (max 3)
  "base": "abc123...",
  "integration": false,
  "origin": "git@github.com:user/repo.git",
  "required_checks": ["Quality checks"],
  "reviewed": "def456...",
  "approved_head": "def456...",
  "pr": 42
}
```

The `rounds` field tracks total implement-review cycles across both initial implementation and fix attempts. When `rounds >= 3` and review is still not APPROVED, the workflow stops and requires owner intervention.

## Recovery & Resumption

If interrupted mid-phase:

1. **Inspect state:**
   ```bash
   cat task-workflow/TASK-xxx/state.json
   ```

2. **Finish partial work manually** in the worktree

3. **Resume orchestration:**
   Read the state file and continue from the current phase.

**Mid-Fix-Loop Interruption:**
If interrupted during a fix round (phase is "implement" with rounds > 1):
1. Check `state.json` for current `rounds` count
2. Inspect the latest review report: `docs/reviews/TASK-xxx-review.md`
3. Manually address remaining findings in worktree
4. Commit fixes and resume orchestration
5. The next review will count as the next round (enforcing the 3-round limit)

## Error Handling

### Common Failure Modes

**No Commits Made:**
```
Error: No commits made — implementation failed
```
→ Check what went wrong (missing dependencies, wrong paths, etc.)
→ Fix and retry implementation

**Review Requires Changes:**
```
Error: OCR review found High findings (CHANGES REQUIRED)
```
→ Read `docs/reviews/TASK-xxx-review.md` for specific findings
→ The orchestrator automatically enters a fix-and-re-review loop (up to 3 rounds total)
→ If the loop exhausts all rounds without approval, owner intervention is required — send a `blocked` alert

**Review Blocked:**
```
Error: OCR review found unresolvable High findings
```
→ Read `docs/reviews/TASK-xxx-review.md` immediately — this is a hard stop with no automatic retry
→ Send a `blocked` alert before reporting it; the owner must manually assess and decide whether to proceed or abandon the task

**CI Failures:**
```
Error: CI checks failed for PR #42
```
→ Send a `failed` alert with the PR URL as `--ref`
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
3. **OCR review completed and APPROVED** (no unresolved High findings)
4. Review report saved to `docs/reviews/TASK-xxx-review.md`
5. Review report committed to git
6. State file updated with `phase: "review-complete"` and `reviewed` hash
7. PR created on GitHub
8. CI checks passing
9. PR merged to `main` by Phase 5 (required — a green CI without a merge is incomplete)

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
- `.qoder/skills/open-code-review/SKILL.md` - OCR review methodology and classification scheme
