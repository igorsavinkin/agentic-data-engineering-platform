#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy
python scripts/verify_repository_structure.py
