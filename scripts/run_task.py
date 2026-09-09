#!/usr/bin/env python3
"""Interactive wrapper for Qoder task workflow automation.

Simplifies running automated task workflows with helpful prompts,
task discovery, and prerequisite validation.

Usage:
    python scripts/run_task.py              # Interactive mode
    python scripts/run_task.py 009          # Run specific task
    python scripts/run_task.py --list       # List available tasks
    python scripts/run_task.py --status     # Check workflow state
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


# Repository root (parent of scripts/)
ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = ROOT / "ai" / "tasks"
WORKFLOW_SCRIPT = ROOT / "scripts" / "qoder_task_workflow.py"
STATE_DIR = ROOT / "task-workflow"


def get_completed_tasks_from_git() -> set[str]:
    """Detect completed tasks by checking git merge commits."""
    completed = set()
    try:
        result = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=ROOT, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                # Match various patterns: TASK-009, task 009, Task 009, feature/task 009
                matches = re.findall(r"(?:TASK[- ]|task[/ ])(\d+)", line, re.IGNORECASE)
                for match in matches:
                    task_num = int(match)
                    if 1 <= task_num <= 999:
                        completed.add(f"TASK-{task_num:03d}")
    except Exception:
        pass  # Silently ignore git errors
    return completed


def list_tasks() -> list[dict[str, str]]:
    """Discover available task specifications."""
    tasks = []
    completed_from_git = get_completed_tasks_from_git()
    
    if not TASKS_DIR.exists():
        return tasks

    for spec in sorted(TASKS_DIR.glob("TASK-*.md")):
        match = re.match(r"TASK-(\d+)-(.+)\.md", spec.name)
        if match:
            number = f"TASK-{match.group(1)}"
            slug = match.group(2).replace("-", " ").title()
            tasks.append({
                "id": number,
                "slug": slug,
                "path": spec,
                "number": int(match.group(1)),
            })
    return tasks


def get_task_state(task_id: str) -> dict[str, Any] | None:
    """Read the current state of a task workflow if it exists."""
    state_file = STATE_DIR / task_id / "state.json"
    if state_file.exists():
        return json.loads(state_file.read_text(encoding="utf-8"))
    return None


def check_prerequisites() -> list[str]:
    """Verify required tools are available."""
    issues = []

    # Check Python
    try:
        result = subprocess.run(
            [sys.executable, "--version"],
            capture_output=True, text=True, timeout=5
        )
        version_match = re.search(r"Python (\d+\.\d+)", result.stdout)
        if version_match:
            major, minor = map(int, version_match.group(1).split("."))
            if major < 3 or (major == 3 and minor < 12):
                issues.append(f"Python 3.12+ required (found {version_match.group(1)})")
    except Exception as e:
        issues.append(f"Cannot check Python version: {e}")

    # Check Git
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=5, check=True)
    except Exception:
        issues.append("Git is not installed or not on PATH")

    # Check GitHub CLI
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            issues.append("GitHub CLI is not authenticated (run 'gh auth login')")
    except FileNotFoundError:
        issues.append("GitHub CLI (gh) is not installed")

    # Check Qwen Code CLI
    try:
        subprocess.run(["qwen", "--version"], capture_output=True, timeout=5, check=True)
    except FileNotFoundError:
        issues.append("Qwen Code CLI is not installed")

    # Check main branch is clean
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT, capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip():
            issues.append("Working directory is dirty (commit or stash changes first)")

        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=ROOT, capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip() != "main":
            issues.append(f"Not on main branch (currently on '{result.stdout.strip()}')")
    except Exception as e:
        issues.append(f"Cannot check git status: {e}")

    return issues


def format_state(state: dict[str, Any]) -> str:
    """Format task state for display."""
    phase = state.get("phase", "unknown")
    rounds = state.get("rounds", 0)
    pr = state.get("pr", "N/A")

    status_map = {
        "preparing": "[PREP] Preparing",
        "implement": "[IMPL] Implementing",
        "agent-running": "[RUN] Agent Running",
        "review": "[REVIEW] Under Review",
        "approved": "[OK] Approved",
        "fix": "[FIX] Needs Fixes",
        "blocked": "[BLOCKED] Blocked",
        "ci": "[CI] CI Running",
        "merged": "[MERGED] Merged",
        "done": "[DONE] Completed",
    }

    status = status_map.get(phase, f"[?] {phase}")
    return f"{status} (round {rounds}, PR #{pr})"


def cmd_list(args: argparse.Namespace) -> None:
    """List all available tasks."""
    tasks = list_tasks()
    completed_from_git = get_completed_tasks_from_git()
    
    if not tasks:
        print("No task specifications found in ai/tasks/")
        return

    print(f"\nAvailable Tasks ({len(tasks)}):\n")
    print(f"{'ID':<12} {'Description':<40} {'Status'}")
    print("-" * 70)

    for task in tasks:
        # Check git history first (completed tasks)
        if task["id"] in completed_from_git:
            status = "[DONE] Completed (merged)"
        else:
            # Then check workflow state
            state = get_task_state(task["id"])
            if state:
                status = format_state(state)
            else:
                status = "[NEW] Not Started"
        print(f"{task['id']:<12} {task['slug']:<40} {status}")

    print()


def cmd_status(args: argparse.Namespace) -> None:
    """Show status of all tasks or a specific task."""
    if args.task:
        task_id = f"TASK-{int(args.task):03d}" if args.task.isdigit() else args.task
        state = get_task_state(task_id)
        if state:
            print(f"\n{task_id}: {format_state(state)}\n")
            print(json.dumps(state, indent=2))
        else:
            print(f"\n{task_id}: No workflow state found\n")
    else:
        # Show all active tasks
        if not STATE_DIR.exists():
            print("\nNo task workflows have been started yet.\n")
            return

        active = []
        for state_dir in sorted(STATE_DIR.iterdir()):
            if state_dir.is_dir():
                state_file = state_dir / "state.json"
                if state_file.exists():
                    state = json.loads(state_file.read_text())
                    task_id = state_dir.name
                    active.append((task_id, state))

        if not active:
            print("\nNo active task workflows.\n")
        else:
            print(f"\nActive Task Workflows ({len(active)}):\n")
            for task_id, state in active:
                print(f"{task_id}: {format_state(state)}")
            print()


def cmd_check(args: argparse.Namespace) -> None:
    """Check prerequisites for running workflows."""
    print("\nChecking Prerequisites...\n")
    issues = check_prerequisites()

    if not issues:
        print("[OK] All prerequisites met!\n")
        print("You can run task workflows.")
    else:
        print("[ERROR] Issues found:\n")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
        print("\nPlease resolve these issues before running workflows.\n")
        sys.exit(1)


def cmd_run(args: argparse.Namespace) -> None:
    """Run a task workflow."""
    task_num = args.task

    # Validate task number format
    if not re.match(r"^\d{1,3}$", task_num):
        print(f"Error: Invalid task number '{task_num}'. Use format like '009' or '9'.")
        sys.exit(1)

    task_id = f"TASK-{int(task_num):03d}"

    # Check if task spec exists
    specs = list(TASKS_DIR.glob(f"{task_id}-*.md"))
    if not specs and not args.spec:
        print(f"Error: No specification found for {task_id}")
        print(f"\nAvailable tasks:")
        for task in list_tasks():
            print(f"  - {task['id']}")
        print(f"\nTo create a new task, use: --spec path/to/spec.md")
        sys.exit(1)

    # Check prerequisites
    issues = check_prerequisites()
    if issues:
        print("[WARN] Prerequisite issues detected:\n")
        for issue in issues:
            print(f"  - {issue}")
        print("\nContinue anyway? (y/n) ", end="")
        response = input().strip().lower()
        if response not in ("y", "yes"):
            print("Aborted.")
            sys.exit(1)

    # Build command
    cmd = [sys.executable, str(WORKFLOW_SCRIPT), task_id]

    if args.depends_on:
        for dep in args.depends_on:
            cmd.extend(["--depends-on", dep])

    if args.spec:
        cmd.extend(["--spec", str(Path(args.spec).resolve())])

    if args.integration:
        cmd.append("--integration")

    if args.auto_merge:
        cmd.append("--auto-merge")

    if args.max_rounds:
        cmd.extend(["--max-rounds", str(args.max_rounds)])

    if args.ci_timeout:
        cmd.extend(["--ci-timeout", str(args.ci_timeout)])

    # Show what we're about to do
    print(f"\n{'='*60}")
    print(f"Running Qoder Task Workflow")
    print(f"{'='*60}")
    print(f"Task:      {task_id}")
    if args.spec:
        print(f"Spec:      {args.spec}")
    if args.depends_on:
        print(f"Depends:   {', '.join(args.depends_on)}")
    print(f"Integration: {'Yes' if args.integration else 'No'}")
    print(f"Auto-merge:  {'Yes' if args.auto_merge else 'No'}")
    print(f"Max rounds:  {args.max_rounds or 3}")
    print(f"CI timeout:  {args.ci_timeout or 1800}s")
    print(f"{'='*60}\n")

    # Confirm
    if not args.yes:
        print("Start this workflow? (y/n) ", end="")
        response = input().strip().lower()
        if response not in ("y", "yes"):
            print("Aborted.")
            sys.exit(0)

    # Execute
    print(f"\nStarting workflow for {task_id}...\n")
    try:
        result = subprocess.run(cmd, cwd=ROOT, check=True)
        print(f"\n[OK] Workflow completed successfully!")
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Workflow failed with exit code {e.returncode}")
        print(f"\nCheck logs in: task-workflow/{task_id}/")
        sys.exit(e.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Qoder Task Workflow Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --list                    List all available tasks
  %(prog)s --status-all              Show active workflows
  %(prog)s --check                   Verify prerequisites
  %(prog)s 009                       Run TASK-009 interactively
  %(prog)s 009 --auto-merge          Run with auto-merge enabled
  %(prog)s 010 --depends-on 009      Run with dependency
  %(prog)s 050 --spec my-task.md     Create and run new task
        """
    )

    # Mode selection
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true", help="List available tasks")
    mode.add_argument("--status-all", action="store_true", help="Show all workflow statuses")
    mode.add_argument("--check", action="store_true", help="Check prerequisites")

    # Task argument (positional, only when not using mode flags)
    parser.add_argument("task", nargs="?", help="Task number (e.g., 009 or 9)")

    # Options
    parser.add_argument("--spec", type=str, help="Path to task specification file")
    parser.add_argument("--depends-on", action="append", default=[],
                        help="Prerequisite task (can be repeated)")
    parser.add_argument("--integration", action="store_true",
                        help="Run integration tests")
    parser.add_argument("--auto-merge", action="store_true",
                        help="Automatically merge after CI passes")
    parser.add_argument("--max-rounds", type=int, default=3,
                        help="Maximum implementation rounds (default: 3)")
    parser.add_argument("--ci-timeout", type=int, default=1800,
                        help="CI timeout in seconds (default: 1800)")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="Skip confirmation prompt")

    args = parser.parse_args()

    # Route to appropriate command
    if args.list:
        cmd_list(args)
    elif args.status_all:
        cmd_status(args)
    elif args.check:
        cmd_check(args)
    elif args.task:
        # If task looks like a number, treat it as run command; otherwise show help
        if re.match(r"^\d{1,3}$", args.task) or args.task.upper().startswith("TASK-"):
            cmd_run(args)
        else:
            parser.print_help()
            print("\nTip: Use --list to see available tasks, or provide a task number to run it.")
    else:
        # No arguments - show help
        parser.print_help()
        print("\nTip: Use --list to see available tasks, or provide a task number to run it.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
