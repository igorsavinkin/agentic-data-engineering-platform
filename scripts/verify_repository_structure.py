#!/usr/bin/env python3
"""Verify the repository foundation required by ai/tasks/TASK-001-repository-foundation.md."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DIRS = [
    "ai",
    "ai/tasks",
    "docs",
    "services",
    "services/ingestion",
    "services/processor",
    "services/raw-writer",
    "services/lake-writer",
    "services/warehouse-loader",
    "services/api",
    "services/agent",
    "libs",
    "libs/event_contracts",
    "libs/common",
    "libs/observability",
    "tests",
    "airflow",
    "airflow/dags",
    "sql",
    "kubernetes",
    "helm",
    "terraform",
    "monitoring",
    "scripts",
]

REQUIRED_GOVERNANCE_DOCS = [
    "ai/PROJECT.md",
    "ai/SPECIFICATION.md",
    "ai/ROADMAP.md",
    "ai/AGENTS.md",
    "ai/AGENT_WORKFLOW.md",
]

REQUIRED_MILESTONE_0_1_TASKS = 12


def check_directories(errors: list[str]) -> None:
    for relative in REQUIRED_DIRS:
        if not (ROOT / relative).is_dir():
            errors.append(f"missing directory: {relative}")


def check_governance_documents(errors: list[str]) -> None:
    for relative in REQUIRED_GOVERNANCE_DOCS:
        if not (ROOT / relative).is_file():
            errors.append(f"missing governance document: {relative}")


def check_task_files(errors: list[str]) -> int:
    task_dir = ROOT / "ai" / "tasks"
    task_files = sorted(task_dir.glob("TASK-*.md")) if task_dir.is_dir() else []
    task_numbers: set[int] = set()
    for path in task_files:
        digits = path.name[5:8]
        if not digits.isdigit():
            errors.append(f"unexpected task file name: {path.name}")
        else:
            task_numbers.add(int(digits))
    for number in range(1, REQUIRED_MILESTONE_0_1_TASKS + 1):
        if number not in task_numbers:
            errors.append(f"missing task file: ai/tasks/TASK-{number:03d}-*.md")
    return len(task_files)


def check_no_leftover_task_directories(errors: list[str]) -> None:
    for leftover in ("tasks", "task-batch-001"):
        path = ROOT / leftover
        if path.is_dir() and any(path.iterdir()):
            errors.append(f"leftover task directory with files: {leftover}/")


def check_root_agents_pointer(errors: list[str]) -> None:
    root_agents = ROOT / "AGENTS.md"
    canonical = ROOT / "ai" / "AGENTS.md"
    if not root_agents.is_file():
        errors.append("missing root AGENTS.md pointer")
        return
    if not canonical.is_file():
        return  # already reported by governance-document check
    pointer_text = root_agents.read_text(encoding="utf-8")
    if "ai/AGENTS.md" not in pointer_text:
        errors.append("root AGENTS.md does not reference ai/AGENTS.md")
    canonical_lines = canonical.read_text(encoding="utf-8").splitlines()
    if len(pointer_text.splitlines()) >= len(canonical_lines):
        errors.append("root AGENTS.md duplicates ai/AGENTS.md instead of pointing to it")


def main() -> int:
    errors: list[str] = []
    check_directories(errors)
    check_governance_documents(errors)
    task_count = check_task_files(errors)
    check_no_leftover_task_directories(errors)
    check_root_agents_pointer(errors)

    if errors:
        print("Repository structure verification FAILED:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("Repository structure verification passed.")
    print(f"  directories: {len(REQUIRED_DIRS)}")
    print(f"  governance documents: {len(REQUIRED_GOVERNANCE_DOCS)}")
    print(f"  task files under ai/tasks/: {task_count} (TASK-001..TASK-012 required)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
