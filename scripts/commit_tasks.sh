#!/usr/bin/env bash
set -e

if [[ $# -ne 4 ]]; then
    echo "Usage: $0 <milestone-num> <milestone-name> <first-task> <last-task>"
    echo "Example: $0 8 'Kubernetes with kind' 070 079"
    exit 1
fi

MILESTONE_NUM="$1"
MILESTONE_NAME="$2"
FIRST_TASK="$3"
LAST_TASK="$4"

git add ai/tasks/TASK-*.md
git commit -m "Milestone ${MILESTONE_NUM}: ${MILESTONE_NAME}: TASKS ${FIRST_TASK}-${LAST_TASK}"
git push
