---
name: qoder-task-workflow
description: Automate task implementation using Qoder chat sessions instead of Codex CLI. Use when running automated task workflows, implementing TASK-xxx specifications, or replacing Codex with Qoder for isolated task execution in worktrees. Triggers on task automation, workflow execution, or "run task" requests.
---

# Qoder Task Workflow

Automates the full task lifecycle (implement → review → publish → CI → cleanup) using **Qoder chat sessions** instead of Codex CLI. Each task runs in an isolated worktree with its own Qoder conversation.

## When to use

- User asks to "run task XXX", "implement TASK-009", or "automate task workflow"
- Replacing Codex-based automation with Qoder-native execution
- Need isolated agent conversations per task with full tool access

## Prerequisites

Before starting, verify:
1. Main branch is clean (`git status` shows nothing)
2. Task specification exists at `ai/tasks/TASK-xxx-specification.md`
3. Python 3.12+, Git, Qwen Code CLI, GitHub CLI are available
4. Project hooks (`.githooks/`) are merged into main
5. At most one other task worktree is active

## Workflow phases

### 1. Prepare

```python
# Validate clean main checkout
git status --porcelain  # must be empty
git branch --show-current  # must be "main"

# Create worktree at sibling directory
git worktree add -b feature/TASK-xxx ../ai-platform-task-xxx <base-commit>

# Install dependencies in shared venv outside worktree
python -m venv task-workflow/TASK-xxx/venv
pip install -r requirements-dev.txt

# Commit spec if new
git add ai/tasks/TASK-xxx-specification.md
git commit -m "Specify TASK-xxx"
```

### 2. Implement via Qoder session

Instead of calling `codex exec`, spawn a Qoder chat session in the worktree:

```python
# Create independent Qoder conversation targeting the worktree
session = create_chat_session(
    prompt=f"""
Working directory: {worktree_path}

Implement only TASK-xxx from ai/tasks/TASK-xxx-specification.md. Read ai/AGENTS.md,
ai/PROJECT.md, relevant ADRs, ai/SPECIFICATION.md, ai/ROADMAP.md and
ai/AGENT_WORKFLOW.md. Check prerequisites; stop if unmet.

Run required checks plus task-relevant integration tests. Inspect the diff,
stage explicit task file paths and commit locally with hooks enabled.

Do not push, create/merge PRs, change branches, or start another task.
Do not modify review reports. Resolve all blocking review findings; only the
owner can reject them. Fix useful in-scope minor findings; record other
non-blocking recommendations in docs/reviews/FOLLOWUPS.md with rationale
and revisit trigger. Stop with a clean worktree and report checks.
"""
)

# Wait for session to complete (idle or needs human input)
wait_chat_sessions(sessionIds=[session["sessionId"]], timeoutMs=3600000)

# Read transcript for logging
transcript = read_chat_session(sessionId=session["sessionId"])
save_log(f"task-workflow/TASK-xxx/qoder-{attempt}.txt", transcript)

# Verify agent made a commit
head = git(worktree, "rev-parse", "HEAD")
if head == before:
    raise Error("Qoder made no commit")
```

**Key differences from Codex:**
- Full Read/Edit/Bash/Git tool access (not sandboxed)
- Persistent conversation history for debugging
- Worktree isolation via `create_chat_session` environment parameter
- No `--approve-for-me` or `--sandbox` flags needed

### 3. Review with Qwen

Unchanged from Codex workflow. Run local checks, then send diff to Qwen:

```python
# Run checks independently
python -m ruff format --check .
python -m ruff check .
python -m mypy
python -m pytest

# Send diff to Qwen in plan mode
diff = git diff --no-ext-diff --no-textconv base...head
output = run_qwen_review(diff, spec, head)

# Parse verdict from WORKFLOW_REVIEW JSON footer
verdict = parse_verdict(output, head)
# Must be exactly "APPROVED" with blocking_findings=0
```

### 4. Publish & CI

Push branch, create PR, monitor GitHub Actions:

```python
git push -u origin feature/TASK-xxx
gh pr create --base main --head feature/TASK-xxx --title "Implement TASK-xxx"

# Poll CI status
while time_remaining():
    checks = gh api repos/{repo}/commits/{head}/check-runs
    if all_passed(checks):
        break
    sleep(15)
```

### 5. Cleanup

After squash merge:

```python
git pull --ff-only origin main
git worktree remove ../ai-platform-task-xxx  # after clearing cache files
git branch -D feature/TASK-xxx
git push origin :refs/heads/feature/TASK-xxx  # with lease guard
```

## Recovery

If interrupted mid-phase:

```bash
# Inspect state.json for current phase
cat task-workflow/TASK-xxx/state.json

# Finish partial work manually, commit, then resume
python scripts/qoder_task_workflow.py 009 --review-again
```

## State tracking

Progress persists in `task-workflow/TASK-xxx/state.json`:
- `phase`: preparing | implement | review | approved | ci | merged | done
- `rounds`: implementation attempt count (max 3)
- `before`: commit SHA before agent ran
- `reviewed`: commit SHA that passed review
- `approved_head`: final approved commit
- `pr`: GitHub PR number

## Session logs

Agent transcripts save to `task-workflow/TASK-xxx/qoder-{attempt}.txt`. These contain full conversation history including tool calls. Do not commit them; they may include repository metadata.

## Limitations

- Requires running inside Qoder agent environment (chat session tools unavailable in standalone Python)
- Sessions persist until explicitly archived; clean up old sessions periodically
- Worktree isolation means each session has separate `.git` but shares object store
- Maximum 2 concurrent task worktrees enforced by orchestrator lock

## See also

- `docs/AUTOMATED_TASK_WORKFLOW.md` — original Codex-based workflow documentation
- `scripts/task_workflow.py` — Codex CLI implementation
- `ai/AGENT_WORKFLOW.md` — agent development conventions
- `ai/REVIEWER.md` — Qwen review criteria
