#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Keep the checks and their order aligned with .github/workflows/ci.yml.
python -m ruff format --check .
python -m ruff check .
python -m mypy
python -m pytest
python scripts/verify_repository_structure.py
