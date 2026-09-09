"""Workflow gates exercised with real local Git and deterministic external tools."""

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts import task_workflow as workflow


def report(head: str, verdict: str = "APPROVED", blockers: int = 0) -> str:
    return "# Independent review\nWORKFLOW_REVIEW: " + json.dumps(
        {"head": head, "verdict": verdict, "blocking_findings": blockers}
    )


@pytest.mark.parametrize("value", ["../009", "TASK-9;echo", "1000", "--help"])
def test_task_id_rejects_paths_and_options(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        workflow.task_id(value)


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/owner/repo.git",
        "git@github.com:owner/repo.git",
        "ssh://git@github.com/owner/repo",
    ],
)
def test_origin_pins_github_destination(url: str) -> None:
    assert workflow.github_repository(url) == "github.com/owner/repo"


@pytest.mark.parametrize(
    "text",
    [
        "APPROVED",
        report("old"),
        report("head", blockers=1),
        report("head", "APPROVED WITH NON-BLOCKING FINDINGS"),
        report("head") + "\n" + report("head"),
        "WORKFLOW_REVIEW: {broken}",
        'WORKFLOW_REVIEW: {"head":"head","verdict":"APPROVED","blocking_findings":true}',
    ],
)
def test_review_fails_closed(text: str) -> None:
    with pytest.raises(workflow.WorkflowError):
        workflow.review_verdict(text, "head")


def test_review_requires_exact_identity() -> None:
    assert workflow.review_verdict(report("head"), "head") == "APPROVED"
    assert workflow.review_verdict(report("head", "CHANGES REQUIRED", 1), "head") == (
        "CHANGES REQUIRED"
    )


@pytest.mark.parametrize(
    "checks",
    [
        [],
        [{"name": "Other", "bucket": "pass"}],
        [{"name": "Quality checks", "bucket": "pending"}],
        [{"name": "Quality checks", "bucket": "pass"}, {"name": "Security", "bucket": "fail"}],
    ],
)
def test_ci_cannot_pass_missing_pending_or_failed_checks(checks: list[dict[str, Any]]) -> None:
    assert not workflow.checks_pass(checks, ["Quality checks"])


def local_git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return result.stdout.strip()


@pytest.fixture
def task(tmp_path: Path) -> workflow.Workflow:
    repo = tmp_path / "main checkout"
    repo.mkdir()
    local_git(repo, "init", "-b", "main")
    local_git(repo, "config", "user.name", "Workflow Test")
    local_git(repo, "config", "user.email", "workflow@example.invalid")
    local_git(repo, "config", "core.hooksPath", str(tmp_path / "empty-hooks"))
    (repo / "implementation.txt").write_text("base\n", encoding="utf-8")
    local_git(repo, "add", "implementation.txt")
    local_git(repo, "commit", "-m", "Base")
    args = argparse.Namespace(
        repo=repo,
        task="TASK-009",
        codex="codex",
        qwen="qwen",
        max_rounds=3,
        integration=False,
        review_again=False,
        auto_merge=True,
        ci_timeout=1,
        required_check=["Quality checks"],
    )
    task = workflow.Workflow(args)
    base = local_git(repo, "rev-parse", "HEAD")
    local_git(repo, "worktree", "add", "-b", task.branch, str(task.worktree), "main")
    (task.worktree / "implementation.txt").write_text("implemented\n", encoding="utf-8")
    local_git(task.worktree, "add", "implementation.txt")
    local_git(task.worktree, "commit", "-m", "Implement")
    task.save("review", base=base, rounds=1, spec="ai/tasks/TASK-009-specification.md")
    return task


def fake_review(
    monkeypatch: pytest.MonkeyPatch, task: workflow.Workflow, verdict: str = "APPROVED"
) -> list[tuple[str, ...]]:
    actual_run = workflow.run
    calls: list[tuple[str, ...]] = []

    def runner(cwd: Path, *args: str, stdin: str | None = None) -> str:
        calls.append(args)
        if args[0] == "python":
            return "checks passed"
        if args[0] == "qwen":
            assert "--approval-mode" in args and "plan" in args
            return report(task.identity(), verdict, 0 if verdict == "APPROVED" else 1)
        return actual_run(cwd, *args, stdin=stdin)

    monkeypatch.setattr(workflow, "run", runner)
    return calls


def test_review_commits_report_and_accepts_unchanged_implementation(
    task: workflow.Workflow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = fake_review(monkeypatch, task)
    implementation = task.identity()
    task.review()
    assert task.state["phase"] == "approved"
    assert task.state["reviewed"] == implementation
    assert task.identity() != implementation
    task.approved()
    assert len([c for c in calls if c[0] == "python"]) == 5
    assert not any(c[:2] == ("git", "push") for c in calls)


def test_findings_go_to_fixes_before_push(
    task: workflow.Workflow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = fake_review(monkeypatch, task, "CHANGES REQUIRED")
    task.review()
    assert task.state["phase"] == "fix"
    assert task.state["approved_head"] == ""
    workflow.clean(task.worktree)
    assert not any(c[:2] == ("git", "push") for c in calls)


def test_implementation_change_invalidates_approval(
    task: workflow.Workflow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_review(monkeypatch, task)
    task.review()
    (task.worktree / "implementation.txt").write_text("changed after review", encoding="utf-8")
    local_git(task.worktree, "add", "implementation.txt")
    local_git(task.worktree, "commit", "-m", "Unreviewed change")
    with pytest.raises(workflow.WorkflowError, match="HEAD changed"):
        task.publish()


def test_dirty_worktree_prevents_review(
    task: workflow.Workflow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = fake_review(monkeypatch, task)
    (task.worktree / "unrelated.txt").write_text("preserve", encoding="utf-8")
    with pytest.raises(workflow.WorkflowError, match="Dirty checkout"):
        task.review()
    assert not any(c[0] == "qwen" for c in calls)


def test_failed_check_does_not_launch_reviewer(
    task: workflow.Workflow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = workflow.run

    def runner(cwd: Path, *args: str, stdin: str | None = None) -> str:
        if args[0] == "python":
            raise workflow.WorkflowError("Test failed")
        assert args[0] != "qwen"
        return original(cwd, *args, stdin=stdin)

    monkeypatch.setattr(workflow, "run", runner)
    with pytest.raises(workflow.WorkflowError, match="Test failed"):
        task.review()
    assert task.state["phase"] == "review"


def test_round_budget_stops_agent(task: workflow.Workflow) -> None:
    task.state["rounds"] = 3
    with pytest.raises(workflow.WorkflowError, match="budget exhausted"):
        task.implement()


def test_lock_prevents_concurrent_run(task: workflow.Workflow) -> None:
    lock = task.directory.parent / "run.lock"
    lock.write_text("123", encoding="utf-8")
    with pytest.raises(workflow.WorkflowError, match="lock exists"):
        task.execute()
    assert lock.read_text(encoding="utf-8") == "123"


def test_changed_pr_head_blocks_cleanup(
    task: workflow.Workflow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task.state.update(pr=42, approved_head="approved")

    def runner(cwd: Path, *args: str, stdin: str | None = None) -> str:
        assert args[:3] == ("gh", "pr", "view")
        return json.dumps(
            dict(
                headRefOid="unexpected",
                headRefName=task.branch,
                baseRefName="main",
                isCrossRepository=False,
                state="MERGED",
            )
        )

    monkeypatch.setattr(workflow, "run", runner)
    with pytest.raises(workflow.WorkflowError, match="PR identity"):
        task.cleanup()
    assert task.worktree.exists()


def test_full_review_fix_publish_merge_cleanup(
    task: workflow.Workflow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Real Git remote, commits, squash merge, pull and deletion; stub only providers/CI."""
    remote = tmp_path / "remote.git"
    remote.mkdir()
    local_git(remote, "init", "--bare")
    local_git(task.repo, "remote", "add", "origin", str(remote))
    local_git(task.repo, "push", "-u", "origin", "main")
    original = workflow.run
    reviews = 0
    repairs = 0
    ci_runs = 0
    pr_exists = False
    merged = False
    merge_sha = ""

    def runner(cwd: Path, *args: str, stdin: str | None = None) -> str:
        nonlocal reviews, repairs, ci_runs, pr_exists, merged, merge_sha
        if args[0] == "python":
            return "passed"
        if args[0] == "qwen":
            reviews += 1
            return report(
                task.identity(),
                "CHANGES REQUIRED" if reviews == 1 else "APPROVED",
                1 if reviews == 1 else 0,
            )
        if args[0] == "codex":
            repairs += 1
            (cwd / "implementation.txt").write_text(f"repair {repairs}", encoding="utf-8")
            local_git(cwd, "add", "implementation.txt")
            local_git(cwd, "commit", "-m", f"Repair {repairs}")
            return "Fixed and tested"
        if args[0] == "gh":
            if args[1:3] == ("pr", "list"):
                return '[{"number":42}]' if pr_exists else "[]"
            if args[1:3] == ("pr", "create"):
                pr_exists = True
                return "https://github.com/test/repo/pull/42"
            if args[1:3] == ("pr", "view"):
                return json.dumps(
                    dict(
                        state="MERGED" if merged else "OPEN",
                        headRefOid=task.state["approved_head"],
                        headRefName=task.branch,
                        baseRefName="main",
                        isCrossRepository=False,
                        mergeCommit={"oid": merge_sha},
                    )
                )
            if args[1:3] == ("repo", "view"):
                return "test/repo"
            if args[1] == "api":
                if "/status?" in args[2]:
                    return '{"total_count":0,"statuses":[]}'
                ci_runs += 1
                return json.dumps(
                    dict(
                        total_count=1,
                        check_runs=[
                            dict(
                                name="Quality checks",
                                status="completed",
                                conclusion="failure" if ci_runs == 1 else "success",
                            )
                        ],
                    )
                )
            if args[1:3] == ("pr", "merge"):
                assert args[-2:] == ("--match-head-commit", task.state["approved_head"])
                local_git(task.repo, "merge", "--squash", task.branch)
                local_git(task.repo, "commit", "-m", "Squash PR")
                merge_sha = local_git(task.repo, "rev-parse", "HEAD")
                local_git(task.repo, "push", "origin", "main")
                merged = True
                return "Merged"
            pytest.fail(f"Unexpected gh call: {args}")
        return original(cwd, *args, stdin=stdin)

    monkeypatch.setattr(workflow, "run", runner)
    task.args.ci_timeout = 30
    task.execute()
    assert reviews == 3 and repairs == 2
    assert task.state["phase"] == "done"
    assert not task.worktree.exists()
    assert not local_git(task.repo, "branch", "--list", task.branch)
    assert not local_git(task.repo, "ls-remote", "--heads", "origin", task.branch)
    assert (task.repo / "implementation.txt").read_text(encoding="utf-8") == "repair 2"
    # A completed rerun must not create another PR or agent execution.
    task.execute()
    assert reviews == 3
