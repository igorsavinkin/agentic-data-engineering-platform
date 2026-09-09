# Task Orchestrator - Usage Examples

## Example 1: Run Single Task

```python
# From within a Qoder agent session, invoke the orchestrator:

orchestrator = TaskOrchestrator(
    task_id="TASK-010",
    repo_path="C:\\Users\\igors\\RnD\\agentic-data-platform",
    auto_merge=True,
    integration=False
)

orchestrator.execute()
```

This will:
1. Create worktree at `../ai-platform-task-010`
2. Spawn Qoder session for implementation
3. Run automated review with Qwen
4. Push branch and create PR
5. Monitor CI until green
6. Auto-merge and cleanup

## Example 2: Task with Dependencies

```python
orchestrator = TaskOrchestrator(
    task_id="TASK-011",
    depends_on=["TASK-009", "TASK-010"],  # Must be merged first
    auto_merge=True
)

orchestrator.execute()
```

The orchestrator validates that prerequisite PRs are merged before starting.

## Example 3: Manual Review Mode

```python
orchestrator = TaskOrchestrator(
    task_id="TASK-012",
    auto_merge=False  # Stop after CI passes
)

orchestrator.execute()
# Output: "CI passed. Resume with --auto-merge to merge."
```

Use this when you want to manually approve the merge.

## Example 4: Resume After Failure

If a task fails mid-way:

```python
# Inspect state
state = json.loads(Path("task-workflow/TASK-010/state.json").read_text())
print(f"Failed at phase: {state['phase']}")

# Fix issues manually in worktree, then resume
orchestrator = TaskOrchestrator(task_id="TASK-010")
orchestrator.resume(review_again=True)  # Re-run review phase
```

## Example 5: Batch Task Execution

```python
# Execute multiple tasks sequentially
tasks = ["TASK-010", "TASK-011", "TASK-012"]

for task_id in tasks:
    orchestrator = TaskOrchestrator(
        task_id=task_id,
        auto_merge=True,
        max_rounds=3
    )
    try:
        orchestrator.execute()
        print(f"✅ {task_id} completed")
    except WorkflowError as e:
        print(f"❌ {task_id} failed: {e}")
        break  # Stop on first failure
```

## Monitoring During Execution

While a task is running, you can monitor from another session:

```bash
# Check current phase
cat task-workflow/TASK-010/state.json | jq .phase

# View agent transcript (in real-time)
tail -f task-workflow/TASK-010/qoder-1.txt

# Check worktree status
cd ../ai-platform-task-010 && git log --oneline
```

## Integration with Wrapper Script

Use the wrapper for discovery, then invoke orchestrator:

```bash
# Step 1: List available tasks
python scripts/run_task.py --list

# Step 2: Check prerequisites
python scripts/run_task.py --check

# Step 3: From within Qoder, run the task
# (invoke orchestrator skill with task_id from step 1)
```

## Debugging Failed Tasks

When a task fails:

1. **Read the error message** from console output
2. **Check agent transcript**: `task-workflow/TASK-xxx/qoder-N.txt`
3. **Inspect worktree**: `cd ../ai-platform-task-xxx && git status`
4. **Review report**: `docs/reviews/TASK-xxx-review.md`
5. **Fix and resume**: Update code, commit, then call `orchestrator.resume()`

## Common Patterns

### Pattern 1: Quick Implementation Check
```python
# Just implement, don't push or create PR
orchestrator = TaskOrchestrator(task_id="TASK-010")
orchestrator.implement_only()  # Custom method for testing
```

### Pattern 2: Review Existing Implementation
```python
# Someone else implemented it, just review
orchestrator = TaskOrchestrator(task_id="TASK-010")
orchestrator.review_only(worktree_path="../ai-platform-task-010")
```

### Pattern 3: CI Debugging Session
```python
# PR exists but CI is failing
orchestrator = TaskOrchestrator(task_id="TASK-010")
orchestrator.debug_ci(pr_number=42)  # Fetch logs, analyze failures
```
