# Task Workflow Runner

A user-friendly wrapper for the Qoder task workflow automation system. This script simplifies running automated task workflows with helpful prompts, task discovery, and prerequisite validation.

## Quick Start

```bash
# List all available tasks
python scripts/run_task.py --list

# Check if prerequisites are met
python scripts/run_task.py --check

# Run a specific task (interactive)
python scripts/run_task.py 009

# Run with auto-merge enabled
python scripts/run_task.py 009 --auto-merge

# Run with dependencies
python scripts/run_task.py 010 --depends-on 009
```

## Commands

### List Tasks
Show all available task specifications and their current status:

```bash
python scripts/run_task.py --list
```

Output example:
```
Available Tasks (12):

ID           Description                              Status
----------------------------------------------------------------------
TASK-001     Repository Foundation                    [NEW] Not Started
TASK-009     Kafka Consumer                           [IMPL] Implementing (round 1, PR #N/A)
TASK-010     Kafka Error Handling                     [DONE] Completed (round 1, PR #42)
```

### Check Prerequisites
Verify that all required tools are installed and configured:

```bash
python scripts/run_task.py --check
```

Checks for:
- Python 3.12+
- Git
- GitHub CLI (authenticated)
- Qwen Code CLI
- Clean main branch

### Show Status
View active workflow states:

```bash
# All active workflows
python scripts/run_task.py --status

# Specific task
python scripts/run_task.py --status 009
```

### Run Task
Execute a task workflow:

```bash
# Basic usage
python scripts/run_task.py 009

# With options
python scripts/run_task.py 009 \
  --auto-merge \
  --integration \
  --depends-on 008 \
  --max-rounds 5
```

## Options

| Option | Description | Default |
|--------|-------------|---------|
| `--spec PATH` | Path to task specification file (for new tasks) | - |
| `--depends-on TASK` | Prerequisite task (can be repeated) | - |
| `--integration` | Run integration tests | Off |
| `--auto-merge` | Automatically merge after CI passes | Off |
| `--max-rounds N` | Maximum implementation rounds | 3 |
| `--ci-timeout SEC` | CI timeout in seconds | 1800 |
| `-y, --yes` | Skip confirmation prompt | Off |

## Workflow Phases

The task runner automates these phases:

1. **Prepare** - Validate environment, create worktree, install dependencies
2. **Implement** - Spawn Qoder chat session to implement the task
3. **Review** - Run checks and get Qwen review
4. **Publish** - Push branch and create PR
5. **CI** - Monitor GitHub Actions until checks pass
6. **Cleanup** - Merge PR and remove worktree/branch

## State Tracking

Workflow state persists in `task-workflow/TASK-xxx/state.json`. If interrupted, you can resume by running the same command again.

## Session Logs

Agent transcripts are saved to `task-workflow/TASK-xxx/qoder-{attempt}.txt` for debugging.

## Examples

### Example 1: Run existing task
```bash
python scripts/run_task.py 009 --auto-merge
```

### Example 2: Create and run new task
```bash
python scripts/run_task.py 050 --spec ~/tasks/new-feature.md --auto-merge
```

### Example 3: Run with dependency chain
```bash
python scripts/run_task.py 011 --depends-on 010 --depends-on 009 --integration
```

### Example 4: Non-interactive mode
```bash
python scripts/run_task.py 009 --auto-merge -y
```

## Troubleshooting

### "Executable unavailable: qwen"
Install Qwen Code CLI: https://github.com/QwenLM/qwen-code

### "GitHub CLI is not authenticated"
Run: `gh auth login`

### "Working directory is dirty"
Commit or stash your changes before running workflows.

### "Not on main branch"
Switch to main: `git checkout main`

## See Also

- `scripts/qoder_task_workflow.py` - The underlying workflow implementation
- `docs/AUTOMATED_TASK_WORKFLOW.md` - Detailed workflow documentation
- `.qoder/skills/qoder-task-workflow/SKILL.md` - Skill documentation
