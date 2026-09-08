#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
current=$(git config --get core.hooksPath || test "$?" -eq 1)
if [[ -n "$current" && "$current" != .githooks ]]; then
    printf 'Existing core.hooksPath=%s; reconcile it before installing.\n' "$current" >&2
    exit 1
fi
if [[ -z "$current" ]]; then
    hooks_dir=$(git rev-parse --git-path hooks)
    for hook in "$hooks_dir"/*; do
        [[ -f "$hook" && "$hook" != *.sample ]] || continue
        printf 'Existing hook %s; reconcile it before installing.\n' "$hook" >&2
        exit 1
    done
fi
chmod +x .githooks/pre-commit .githooks/pre-push
git config --local core.hooksPath .githooks
printf 'Installed project hooks. Ensure the Git process has the project Python environment on PATH.\n'
