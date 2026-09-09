# Task Automation System

Automated task development workflow using Qoder chat sessions instead of external CLIs. Replaces manual implementation with orchestrated agent conversations in isolated worktrees.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    User Interface Layer                      │
│  scripts/run_task.py (interactive wrapper)                   │
│  - Task discovery & listing                                  │
│  - Prerequisite validation                                   │
│  - Status monitoring                                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 Orchestration Layer                          │
│  scripts/qoder_task_workflow.py                              │
│  - Phase management (prepare → implement → review → CI)     │
│  - State persistence (task-workflow/TASK-xxx/state.json)    │
│  - Error recovery & resumption                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Qoder Chat Session Tools                        │
│  create_chat_session() - spawn independent conversation      │
│  wait_chat_sessions()  - poll until idle/completed           │
│  read_chat_session()   - extract transcript                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Isolated Worktree Environment                   │
│  ../ai-platform-task-xxx/                                    │
│  - Separate working directory                                │
│  - Shared .git object store                                  │
│  - Feature branch: feature/TASK-xxx                          │
│  - Per-task venv (optional)                                  │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. Wrapper Script (`scripts/run_task.py`)

Interactive command-line interface for task management.

**Commands:**
```bash
python scripts/run_task.py --list          # Show all tasks with status
python scripts/run_task.py --check         # Validate prerequisites
python scripts/run_task.py --status-all    # Show active workflows
python scripts/run_task.py 010             # Run TASK-010 interactively
```

**Options:**
- `--auto-merge` - Automatically merge after CI passes
- `--depends-on 009` - Specify prerequisite tasks
- `--integration` - Run integration tests
- `--spec path/to/spec.md` - Create new task from specification
- `-y` - Skip confirmation prompts

**What it does:**
- Discovers task specs from `ai/tasks/TASK-*.md`
- Detects completed tasks from git commit history
- Validates tools and environment
- Launches workflow script with proper arguments

**Limitation:** Must run within Qoder agent environment (requires `qoder_tools` module).

---

### 2. Workflow Engine (`scripts/qoder_task_workflow.py`)

Core orchestration logic managing the full task lifecycle.

**Phases:**

1. **Prepare** - Create worktree, install dependencies, commit spec
2. **Implement** - Spawn Qoder chat session for code generation
3. **Review** - Run quality checks, invoke Qwen Code CLI for review
4. **Publish** - Push branch, create GitHub PR
5. **CI Monitor** - Poll GitHub Actions until checks pass or fail
6. **Cleanup** - Merge PR, remove worktree, delete branches

**State Management:**

Progress persists in `task-workflow/TASK-xxx/state.json`:
```json
{
  "phase": "implement",
  "repo": "C:\\Users\\igors\\RnD\\agentic-data-platform",
  "task": "TASK-010",
  "branch": "feature/TASK-010",
  "worktree": "C:\\Users\\igors\\RnD\\ai-platform-task-010",
  "rounds": 1,
  "base": "abc123...",
  "reviewed": "def456...",
  "approved_head": "def456...",
  "pr": 42
}
```

**Recovery:**

If interrupted mid-phase:
```bash
# Inspect state
cat task-workflow/TASK-010/state.json

# Finish partial work manually in worktree
cd ../ai-platform-task-010
# ... make fixes, commit ...

# Resume from current phase
python scripts/qoder_task_workflow.py 010 --review-again
```

---

### 3. Qoder Skills

#### `qoder-task-workflow`

Documents the complete workflow replacing Codex CLI with Qoder chat sessions. Use when implementing tasks or understanding the automation architecture.

#### `qoder-task-orchestrator`

Comprehensive guide for orchestrating task development using Qoder's native chat session tools. Includes detailed code examples for each phase.

**Quick Start:** See `.qoder/skills/qoder-task-orchestrator/QUICKSTART.md`

---

## Workflow Phases in Detail

### Phase 1: Prepare

```python
# Validate clean main checkout
git status --porcelain  # must be empty
git branch --show-current  # must be "main"

# Create isolated worktree
git worktree add -b feature/TASK-010 ../ai-platform-task-010 <base-commit>

# Install dependencies
python -m venv task-workflow/TASK-010/venv
pip install -r requirements-dev.txt

# Commit spec if new
git add ai/tasks/TASK-010-kafka-error-handling.md
git commit -m "Specify TASK-010"
```

### Phase 2: Implement via Qoder Session

```python
# Create independent Qoder conversation
session = create_chat_session(
    prompt=f"""
Working directory: {worktree_path}

Implement only TASK-010 from ai/tasks/TASK-010-kafka-error-handling.md.

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

# Wait for completion (up to 1 hour)
wait_chat_sessions(sessionIds=[session["sessionId"]], timeoutMs=3600000)

# Read transcript for logging
transcript = read_chat_session(sessionId=session["sessionId"])
save_log(f"task-workflow/TASK-010/qoder-1.txt", transcript)

# Verify agent made commits
head = git(worktree, "rev-parse", "HEAD")
if head == before:
    raise Error("Qoder made no commit - inspect transcript")
```

**Key differences from Codex:**
- Full Read/Edit/Bash/Git tool access (not sandboxed)
- Persistent conversation history for debugging
- Worktree isolation via `create_chat_session` environment parameter
- No `--approve-for-me` or `--sandbox` flags needed

### Phase 3: Review with Qwen

```python
# Run local quality checks
run_checks([
    ["python", "-m", "ruff", "format", "--check", "."],
    ["python", "-m", "ruff", "check", "."],
    ["python", "-m", "mypy"],
    ["python", "-m", "pytest"],
    ["python", "scripts/verify_repository_structure.py"]
])

# Get diff for review
diff = git_diff("--no-ext-diff", "--no-textconv", f"{base}...{head}")

# Send to Qwen in plan mode
output = run_qwen_review(diff=diff, spec=spec_content, head=head)

# Parse verdict from WORKFLOW_REVIEW JSON footer
verdict = parse_workflow_review(output, head)
# Must be exactly "APPROVED" with blocking_findings=0

# Save review report
write_file(f"docs/reviews/TASK-010-review.md", output)
git_add("docs/reviews/TASK-010-review.md")
git_commit("-m", "Record TASK-010 Qwen review")
```

### Phase 4: Publish & Create PR

```python
# Push branch to remote
git_push("-u", "origin", "feature/TASK-010")

# Check for existing PR
prs = gh_pr_list(state="open", base="main", head="feature/TASK-010")

if not prs:
    # Create new PR
    pr_body = f"""
Implements TASK-010 according to `ai/tasks/TASK-010-kafka-error-handling.md`.

Qwen approved implementation `{reviewed_head}`; see
`docs/reviews/TASK-010-review.md`. Local repository checks passed.
"""
    pr_number = gh_pr_create(
        base="main",
        head="feature/TASK-010",
        title="Implement TASK-010",
        body=pr_body
    )
```

### Phase 5: Monitor CI

```python
# Poll GitHub Actions until checks pass or timeout
deadline = time.monotonic() + ci_timeout
while time.monotonic() < deadline:
    check_runs = gh_api(f"repos/{repo}/commits/{head}/check-runs?per_page=100")
    statuses = gh_api(f"repos/{repo}/commits/{head}/status?per_page=100")

    if any(check["conclusion"] == "failure" for check in check_runs):
        state.update(phase="fix", feedback=f"CI failed for PR #{pr_number}")
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

```python
# Update main
git_checkout("main")
git_pull("--ff-only", "origin", "main")

# Remove worktree (after clearing cache files)
clean_cache_files(worktree)  # __pycache__, .pytest_cache, etc.
git_worktree_remove(worktree_path)

# Delete branches
git_branch("-D", "feature/TASK-010")
git_push("origin", ":refs/heads/feature/TASK-010")

state.update(phase="done")
```

---

## Current Task Status

From git history, these tasks are **completed**:
- TASK-001 through TASK-009

Available for implementation:
- **TASK-010**: Kafka Error Handling
- **TASK-011**: Kafka Metrics
- **TASK-012**: Kafka Integration Tests

See reviews in `docs/reviews/` folder.

---

## Prerequisites

Before running any task workflow:

- [ ] Python 3.12+ installed
- [ ] Git installed and configured
- [ ] GitHub CLI authenticated (`gh auth login`)
- [ ] Qwen Code CLI installed
- [ ] Main branch is clean (`git status` shows nothing)
- [ ] On main branch (`git branch --show-current`)
- [ ] Project hooks merged (`.githooks/` into `.git/hooks/`)
- [ ] At most 1 other task worktree active

Run `python scripts/run_task.py --check` to validate automatically.

---

## Troubleshooting

### "Qoder made no commit"

Read the session transcript:
```bash
cat task-workflow/TASK-010/qoder-1.txt
```

Look for error messages or confusion in the agent's reasoning. Adjust the prompt or fix issues manually, then resume.

### "Qwen marked the task BLOCKED"

Read the review report:
```bash
cat docs/reviews/TASK-010-review.md
```

Fix the blocking issues in the worktree, commit, then resume with `--review-again`.

### "CI checks failed"

Inspect GitHub Actions logs:
```bash
gh run view
```

Fix the failing tests or lint errors, commit, and the orchestrator will re-push and re-check.

### "Unmanaged task branch/worktree exists"

Inspect manually:
```bash
cd ../ai-platform-task-010
git status
git log --oneline -5
```

Remove if stale:
```bash
git worktree remove ../ai-platform-task-010
```

Or adopt by updating `task-workflow/TASK-010/state.json`.

---

## Session Logs

Each implementation attempt saves transcript to:
```
task-workflow/TASK-xxx/qoder-{attempt}.txt
```

These contain:
- Full conversation history
- Tool call details
- Agent reasoning
- Error messages

**Do not commit these files** - they may contain repository metadata.

---

## Design Decisions

### Why Qoder Chat Sessions Instead of Codex?

1. **Full Tool Access** - Read/Edit/Bash/Git without sandbox restrictions
2. **Persistent History** - Debug agent decisions by reading transcripts
3. **Native Integration** - No need for `--approve-for-me` or `--sandbox` flags
4. **Better Isolation** - Each task gets its own conversation context
5. **Easier Recovery** - Resume from exact point of failure

### Why Worktrees Instead of Branches?

1. **Parallel Development** - Multiple tasks can coexist without switching branches
2. **Clean Separation** - Each task has its own working directory
3. **Shared Object Store** - Efficient disk usage via shared `.git` directory
4. **Easy Cleanup** - Remove worktree without affecting other branches

### Why Two-Lane Workflow (Implementation + Review)?

1. **Separation of Concerns** - Implementation agent focuses on code, Qwen focuses on quality
2. **Automated Quality Gates** - No manual PR review needed for routine tasks
3. **Audit Trail** - Every decision documented in review reports
4. **Followup Tracking** - Non-blocking recommendations saved for later

---

## See Also

- `docs/AUTOMATED_TASK_WORKFLOW.md` - Original Codex-based workflow documentation
- `ai/AGENT_WORKFLOW.md` - Agent development conventions
- `ai/REVIEWER.md` - Qwen review criteria
- `.qoder/skills/qoder-task-orchestrator/QUICKSTART.md` - Quick reference guide
- `.qoder/skills/qoder-task-workflow/SKILL.md` - Complete workflow skill
