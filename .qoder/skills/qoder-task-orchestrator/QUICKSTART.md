# Quick Start: Task Orchestration

## Two Ways to Run Tasks

### Option 1: Wrapper Script (Recommended for Discovery)

Use `scripts/run_task.py` for interactive task management:

```bash
# List all tasks with status
python scripts/run_task.py --list

# Check prerequisites
python scripts/run_task.py --check

# Run a specific task (interactive prompts)
python scripts/run_task.py 010

# Run with auto-merge after CI passes
python scripts/run_task.py 010 --auto-merge

# Run with dependency chain
python scripts/run_task.py 011 --depends-on 010
```

**What it does:**
- Discovers task specs from `ai/tasks/`
- Validates tools (Python 3.12+, Git, GitHub CLI, Qwen CLI)
- Detects completed tasks from git history
- Launches the workflow script with proper arguments

**Limitation:** Must run within Qoder agent environment (requires `qoder_tools` module).

---

### Option 2: Direct Skill Invocation

When inside a Qoder agent conversation, invoke the orchestrator skill directly:

```
@qoder-task-orchestrator Implement TASK-010
```

The skill will:
1. Read `ai/tasks/TASK-010-kafka-error-handling.md`
2. Create isolated worktree at `../ai-platform-task-010`
3. Spawn Qoder chat session for implementation
4. Wait for completion and read transcript
5. Run quality checks (ruff, mypy, pytest)
6. Invoke Qwen review in plan mode
7. Push branch and create PR if approved
8. Monitor CI until checks pass
9. Merge and cleanup on success

---

## Current Task Status

From git history, these tasks are **completed**:
- TASK-001 through TASK-009

Available for implementation:
- **TASK-010**: Kafka Error Handling
- **TASK-011**: Kafka Metrics
- **TASK-012**: Kafka Integration Tests

---

## Prerequisites Checklist

Before running any task:

- [ ] Main branch is clean (`git status` shows nothing)
- [ ] On main branch (`git branch --show-current`)
- [ ] Python 3.12+ installed
- [ ] Git installed and configured
- [ ] GitHub CLI authenticated (`gh auth login`)
- [ ] Qwen Code CLI installed
- [ ] Project hooks merged (`.githooks/` into `.git/hooks/`)
- [ ] At most 1 other task worktree active

Run `python scripts/run_task.py --check` to validate.

---

## Workflow States

Tasks progress through these phases:

| Phase | Description |
|-------|-------------|
| `preparing` | Creating worktree, installing deps |
| `implement` | Agent writing code in Qoder session |
| `review` | Qwen reviewing the diff |
| `approved` | Review passed, ready to publish |
| `ci` | PR created, monitoring GitHub Actions |
| `merged` | PR squashed and merged to main |
| `done` | Worktree cleaned up, task complete |

Check state: `cat task-workflow/TASK-xxx/state.json`

---

## Recovery from Interruption

If workflow stops mid-phase:

1. **Inspect current state:**
   ```bash
   cat task-workflow/TASK-010/state.json
   ```

2. **Finish partial work manually** in the worktree if needed

3. **Resume orchestration:**
   ```bash
   python scripts/qoder_task_workflow.py 010 --review-again
   ```

---

## Session Logs

Each implementation attempt saves transcript to:
```
task-workflow/TASK-xxx/qoder-{attempt}.txt
```

These contain full conversation history including tool calls. **Do not commit** - they may contain repository metadata.

---

## Common Commands

```bash
# See what's happening right now
ls task-workflow/TASK-010/

# Read latest agent transcript
cat task-workflow/TASK-010/qoder-1.txt

# Check Qwen review
cat docs/reviews/TASK-010-review.md

# View pending followups
cat docs/reviews/FOLLOWUPS.md

# Manual worktree inspection
cd ../ai-platform-task-010
git status
git log --oneline -5
```

---

## Next Steps

1. Ensure prerequisites are met (`--check`)
2. Pick next task: TASK-010 (Kafka Error Handling)
3. Decide: wrapper script or direct skill invocation?
4. Run with `--auto-merge` if you trust the automation
5. Monitor progress via state.json and session logs
