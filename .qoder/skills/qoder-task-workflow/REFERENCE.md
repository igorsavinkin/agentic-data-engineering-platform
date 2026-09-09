# Implementation Reference

This document contains the actual Python code for implementing the Qoder task workflow. Use this as a reference when executing tasks manually or building automation tooling.

## Core session management functions

These functions use Qoder's built-in chat session tools. They only work when running inside a Qoder agent environment.

### Create implementation session

```python
def implement_task(worktree: Path, task_id: str, spec_path: str, feedback: str = "") -> dict:
    """Spawn Qoder chat session to implement a task in isolated worktree."""

    prompt = f"""Working directory: {worktree}

Implement only {task_id} from {spec_path}. Read ai/AGENTS.md, ai/PROJECT.md,
relevant ADRs, ai/SPECIFICATION.md, ai/ROADMAP.md and ai/AGENT_WORKFLOW.md.
Check prerequisites; stop if unmet.

Run required checks plus task-relevant integration tests. Inspect the diff,
stage explicit task file paths and commit locally with hooks enabled.

Do not push, create/merge PRs, change branches, or start another task.
Do not modify review reports. Resolve all blocking review findings; only the
owner can reject them. Fix useful in-scope minor findings; record other
non-blocking recommendations in docs/reviews/FOLLOWUPS.md with rationale
and revisit trigger. Stop with a clean worktree and report checks.

{feedback}"""

    # Create session in worktree environment
    session = create_chat_session(prompt=prompt)
    return session
```

### Wait for completion

```python
def wait_for_implementation(session_id: str, timeout_seconds: int = 3600) -> None:
    """Poll session until idle/completed/failed."""

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = wait_chat_sessions(
            sessionIds=[session_id],
            timeoutMs=30000,  # 30 second poll interval
        )

        if result:
            status = result[0].get("status")
            if status in {"idle", "completed", "failed", "requiresHumanInput"}:
                return

        time.sleep(5)

    raise TimeoutError(f"Session {session_id} timed out after {timeout_seconds}s")
```

### Read session transcript

```python
def get_session_transcript(session_id: str) -> str:
    """Extract full conversation from completed session."""

    result = read_chat_session(
        sessionId=session_id,
        turnLimit=100,  # max turns to retrieve
        includeToolOutputs=True,
    )

    turns = result.get("turns", [])
    lines = []

    for turn in turns:
        role = turn.get("role", "unknown")
        content = turn.get("content", "")

        # Include tool outputs if present
        tool_outputs = turn.get("toolOutputs", [])
        if tool_outputs:
            tool_text = "\n".join(
                f"[TOOL {t.get('tool', '?')}] {t.get('output', '')}" for t in tool_outputs
            )
            content += f"\n\n{tool_text}"

        lines.append(f"[{role.upper()}]\n{content}\n")

    return "\n---\n\n".join(lines)
```

## Full workflow orchestrator

For reference, here's how the complete workflow integrates session management:

```python
class QoderTaskWorkflow:
    def __init__(self, task_id: str, repo: Path = None):
        self.task_id = f"TASK-{int(task_id.removeprefix('TASK-')):03d}"
        self.repo = repo or Path.cwd()
        self.branch = f"feature/{self.task_id}"
        self.worktree = self.repo.parent / f"ai-platform-{self.task_id.lower()}"
        self.state_dir = self.repo / ".git" / "task-workflow" / self.task_id
        self.state_file = self.state_dir / "state.json"
        self.state = self._load_state()

    def execute(self):
        """Run full workflow: prepare → implement → review → publish → ci → cleanup."""

        phase = self.state.get("phase", "preparing")

        if phase == "preparing":
            self.prepare()

        while True:
            phase = self.state["phase"]

            if phase in {"implement", "fix"}:
                self.implement()
            elif phase == "review":
                self.review()
            elif phase == "approved":
                self.publish()
            elif phase == "ci":
                if not self.wait_for_ci():
                    break  # stopped before auto-merge
            elif phase == "merged":
                self.cleanup()
            elif phase == "done":
                print(f"Completed {self.task_id}: PR #{self.state['pr']}")
                break
            else:
                raise RuntimeError(f"Unknown phase: {phase}")

    def implement(self):
        """Run implementation via Qoder chat session."""

        before = git(self.worktree, "rev-parse", "HEAD")
        attempt = self.state.get("rounds", 0) + 1

        if attempt > 3:
            raise RuntimeError("Max implementation rounds exceeded")

        self._save_state("agent-running", rounds=attempt, before=before)

        # Create Qoder session
        session = create_chat_session(prompt=self._build_implementation_prompt())

        # Wait for completion
        wait_for_implementation(session["sessionId"], timeout_seconds=3600)

        # Save transcript
        transcript = get_session_transcript(session["sessionId"])
        (self.state_dir / f"qoder-{attempt}.txt").write_text(transcript)

        # Verify commit was made
        head = git(self.worktree, "rev-parse", "HEAD")
        if head == before:
            raise RuntimeError("Qoder made no commit")

        self._save_state("review")

    def _build_implementation_prompt(self) -> str:
        spec = self.state["spec"]
        feedback = self.state.get("feedback", "")

        return f"""Working directory: {self.worktree}

Implement only {self.task_id} from {spec}. Read ai/AGENTS.md, ai/PROJECT.md,
relevant ADRs, ai/SPECIFICATION.md, ai/ROADMAP.md and ai/AGENT_WORKFLOW.md.
Check prerequisites; stop if unmet.

Run required checks plus task-relevant integration tests. Inspect the diff,
stage explicit task file paths and commit locally with hooks enabled.

Do not push, create/merge PRs, change branches, or start another task.
Do not modify review reports. Resolve all blocking review findings; only the
owner can reject them. Fix useful in-scope minor findings; record other
non-blocking recommendations in docs/reviews/FOLLOWUPS.md with rationale
and revisit trigger. Stop with a clean worktree and report checks.

{feedback}"""
```

## Manual execution example

To run a single task manually within Qoder:

```python
# 1. Prepare worktree
repo = Path("/path/to/repo")
task_id = "TASK-009"
branch = f"feature/{task_id}"
worktree = repo.parent / f"ai-platform-{task_id.lower()}"

git(repo, "worktree", "add", "-b", branch, str(worktree), "HEAD")

# 2. Create implementation session
session = create_chat_session(
    prompt=f"""Working directory: {worktree}

Implement TASK-009 from ai/tasks/TASK-009-specification.md following
ai/AGENTS.md conventions. Run checks, commit with hooks, stop clean."""
)

# 3. Wait and check
wait_chat_sessions(sessionIds=[session["sessionId"]], timeoutMs=3600000)
transcript = read_chat_session(sessionId=session["sessionId"])

# 4. Verify
head = git(worktree, "rev-parse", "HEAD")
print(f"Implementation commit: {head}")
print(git(worktree, "diff", "HEAD~1..HEAD", "--stat"))
```

## Comparison: Codex vs Qoder sessions

| Aspect | Codex CLI | Qoder Sessions |
|--------|-----------|----------------|
| Execution | `codex exec --approve-for-me -` | `create_chat_session(prompt)` |
| Sandbox | `workspace-write` (restricted) | Full tool access (Read/Edit/Bash/Git) |
| Output | stdout capture | Session transcript via `read_chat_session` |
| Completion | Exit code 0 | Session status = "idle"/"completed" |
| History | Ephemeral | Persistent conversation |
| Recovery | Rerun from scratch | Resume from last turn |
| Isolation | Process-level | Worktree environment parameter |

## Troubleshooting

**Session hangs**: Check `wait_chat_sessions` result for `"status": "requiresHumanInput"`. The agent may be waiting for permission on a sensitive operation.

**No commit made**: Agent may have hit an error. Read the transcript to see what went wrong. Common causes: missing spec file, unmet prerequisites, test failures.

**Worktree conflicts**: Ensure at most 2 task worktrees exist. Clean up old ones with `git worktree remove`.

**Stale state**: If `state.json` shows wrong phase, inspect manually and update:
```python
import json

state = json.loads(state_file.read_text())
state["phase"] = "review"  # force to correct phase
state_file.write_text(json.dumps(state))
```
