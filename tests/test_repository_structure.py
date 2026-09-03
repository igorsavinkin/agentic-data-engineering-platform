"""Smoke test: the repository foundation required by TASK-001 stays intact."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_repository_structure() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_repository_structure.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
