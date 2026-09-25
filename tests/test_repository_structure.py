"""Smoke test: the repository foundation required by TASK-001 stays intact."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "verify_repository_structure",
    ROOT / "scripts" / "verify_repository_structure.py",
)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
is_valid_task_filename = _mod.is_valid_task_filename


def test_repository_structure() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_repository_structure.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_numbered_task_accepted() -> None:
    assert is_valid_task_filename("TASK-001-repository-foundation.md")
    assert is_valid_task_filename("TASK-042-some-feature.md")
    assert is_valid_task_filename("TASK-123-anything.md")


def test_fix_task_accepted() -> None:
    assert is_valid_task_filename("TASK-FIX-kafka-offset.md")
    assert is_valid_task_filename("TASK-FIX-task-naming-docs.md")


def test_k8s_fix_task_accepted() -> None:
    assert is_valid_task_filename("TASK-K8S-FIX-helm-chart.md")
    assert is_valid_task_filename("TASK-K8S-FIX-something.md")


def test_docs_task_accepted() -> None:
    assert is_valid_task_filename("TASK-DOCS-PLATFORM-INVENTORY-M13.md")
    assert is_valid_task_filename("TASK-DOCS-some-architecture.md")


def test_arbitrary_invalid_rejected() -> None:
    assert not is_valid_task_filename("TASK-WHATEVER.md")
    assert not is_valid_task_filename("TASK-RANDOM.md")
    assert not is_valid_task_filename("TASK-FOOBAR.md")


def test_non_task_files_rejected() -> None:
    assert not is_valid_task_filename("README.md")
    assert not is_valid_task_filename("TASK-.md")
