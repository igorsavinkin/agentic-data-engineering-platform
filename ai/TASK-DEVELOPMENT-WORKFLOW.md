# AI Data Platform — Task Development & Review Workflow

## Purpose

This document defines the standard engineering workflow for implementing tasks in the `ai-data-platform` repository.

Roles:
- **Human** — architecture, scope, decisions, final integration
- **Qoder** — implementation and implementation testing
- **Qwen Code** — independent review
- **Git** — task isolation and audit trail
- **PR/Merge** — final integration gate

## 1. Core Rules

### Rule 1 — One task = one branch = one Qoder execution

Example:

```text
TASK-007 → feature/TASK-007 → one Qoder execution
```

A new Qoder chat/session does **not** create Git isolation. The Git branch does.

### Rule 2 — Dirty working tree = HARD STOP

Before starting a task, the working tree must be clean.

If it is dirty, Qoder must stop. It must NOT automatically run:

```bash
git stash
git stash -u
git reset --hard
git clean
git checkout -- ...
git restore ...
```

It must report the problem and wait for the human.

This is especially important because `git stash -u` can include untracked files and make them disappear from the working tree.

### Rule 3 — Qoder implements; Qwen reviews

Qoder owns implementation, required tests, debugging, and self-review.

Qwen owns independent review and must not silently modify implementation code.

### Rule 4 — Commit before independent review

Qoder's implementation should be committed before Qwen reviews it, giving Qwen a stable implementation and Git diff.

### Rule 5 — No push before the review gate

Normal sequence:

```text
Implement → test → commit → Qwen review → fix findings → re-test
→ Qwen approval → push → PR → merge
```

# 2. Complete Task Lifecycle

## Phase A — Task Preparation

### A1. Create or approve the task

The task file exists before implementation:

```text
ai/tasks/TASK-007-kafka-topic-configuration.md
```

It should define objective, context, references, scope, requirements, constraints, interfaces, tests, acceptance criteria, edge cases, deliverables, and agent instructions.

The human approves the task before implementation.

## Phase B — Prepare Git

### B1. Start from `main`

```bash
git switch main
git pull
```

### B2. Verify clean state

```bash
git status
```

Expected:

```text
nothing to commit, working tree clean
```

If dirty: **STOP and resolve it manually.**

### B3. Create the task branch

```bash
git switch -c feature/TASK-007
git branch --show-current
```

Expected:

```text
feature/TASK-007
```

Prefer that the human creates the branch rather than asking Qoder to do so.

# 3. Qoder Implementation

## C1. Start Qoder only after the branch exists

Qoder starts with the repository already on `feature/TASK-007`.

## C2. Qoder preflight

Qoder must run:

```bash
git status
git branch --show-current
```

Verify:
1. working tree is clean
2. branch is exactly `feature/TASK-007`

If either fails: **STOP.**

## C3. Read authoritative documentation

For the current task consult:

1. `ai/PROJECT.md`
2. applicable ADRs
3. `ai/SPECIFICATION.md`
4. `ai/tasks/TASK-XXX.md`
5. `ai/ROADMAP.md` when relevant
6. `ai/AGENTS.md`
7. `ai/AGENT_WORKFLOW.md` when relevant

Architecture authority:

```text
PROJECT.md → ADRs → SPECIFICATION.md → TASK-XXX.md → ROADMAP.md
```

`AGENTS.md` is operational guidance and does not override architecture.

## C4. Implement only the current task

If work belongs to another task, report it instead of implementing it.

## C5. Test

Qoder runs the tests required by the task, for example:

```bash
pytest
ruff check .
mypy ...
```

plus relevant integration/service-specific tests.

# 4. Qoder Self-Review

Before committing:

```bash
git status
git diff
git diff --stat
```

Verify:
- every changed file belongs to the current task
- no other task was implemented
- no architecture boundary was accidentally changed
- no debug/dead code remains
- no credentials/secrets were introduced
- required tests exist
- no unexpected dependency changes exist

If unrelated changes are found: **STOP and report them.**

# 5. Commit the Implementation

After implementation and testing:

```bash
git add <intended-files>
git commit -m "TASK-007: configure Kafka topics"
```

Verify:

```bash
git status
git branch --show-current
git log -1 --oneline
```

Expected:
- branch: `feature/TASK-007`
- clean working tree
- commit clearly associated with TASK-007

Do not push yet.

# 6. Qwen Independent Review

Qwen reviews the committed implementation.

Recommended prompt:

```text
Review TASK-007 according to ai/REVIEWER.md.

Review:
1. ai/tasks/TASK-007-*.md
2. relevant PROJECT.md / SPECIFICATION.md / ADRs
3. the final implementation
4. the TASK-007 Git diff
5. Qoder's test evidence

Check for:
- requirements coverage
- architecture violations
- scope creep
- unrelated changes
- incorrect assumptions
- missing/weak tests
- regressions
- dependency changes
- error handling
- security issues
- Git/task isolation

Write the completed review to:
docs/reviews/TASK-007-review.md

Do not modify implementation code.
Do not modify task specifications.
Do not modify architecture documents.

The only file you may create or modify is:
docs/reviews/TASK-007-review.md
```

Qwen should distinguish:
- independently verified
- reported by implementation agent
- not independently verified

Qwen does not need to rerun every test automatically; selectively rerun useful tests.

# 7. Review Decision

## Case A — Approved

If Qwen approves, proceed to the push stage.

## Case B — Findings require changes

The human decides which findings are valid.

Then Qoder fixes only the valid TASK-007 findings:

```text
Qwen review → human decision → Qoder fix → tests → inspect diff → commit
→ Qwen re-review
```

Qoder should not start another task.

For significant findings, require Qwen re-review.

# 8. Push

Only after the review gate passes:

```bash
git push -u origin feature/TASK-007
```

# 9. Pull Request

Create:

```text
feature/TASK-007 → main
```

Human performs the final integration check:
- acceptance criteria satisfied
- Qwen review approved
- required tests passed
- no unrelated changes
- no unexpected architecture changes
- review artifact exists

# 10. Merge

Merge the PR into `main`.

Squash merge is a reasonable default if a clean `main` history is preferred.

The feature branch can contain implementation/review-fix commits while `main` receives one clean TASK commit.

# 11. After Merge

```bash
git switch main
git pull
```

Optionally:

```bash
git branch -d feature/TASK-007
git push origin --delete feature/TASK-007
```

Then start TASK-008.

# 12. Role Separation

| Activity | Human | Qoder | Qwen |
|---|---:|---:|---:|
| Define architecture | Yes | No | Review |
| Create/approve task | Yes | No | Review |
| Create Git branch | Yes | Verify | Check |
| Implement | No | Yes | No |
| Write implementation tests | No | Yes | Review |
| Run implementation tests | Optional | Yes | Selective |
| Self-review | No | Yes | — |
| Inspect Git diff | Yes | Yes | Yes |
| Independent review | No | No | Yes |
| Modify implementation after review | Decision | Yes | No |
| Push | Yes | Optional | No |
| Final merge decision | Yes | No | No |

# 13. Golden Sequence

When you need the short version:

```text
1. Create/approve TASK-XXX
2. switch to main
3. pull latest main
4. verify clean working tree
5. create feature/TASK-XXX
6. verify branch
7. start Qoder
8. Qoder preflight: clean + correct branch
9. Qoder reads task/spec/architecture
10. Qoder implements TASK-XXX only
11. Qoder runs required tests
12. Qoder self-reviews
13. inspect git status/diff
14. commit implementation
15. Qwen independently reviews
16. if findings → human decides → Qoder fixes → tests → commit → Qwen re-review
17. review approved
18. push feature/TASK-XXX
19. create PR
20. human final check
21. merge to main
22. update main
23. delete feature branch
24. start next task
```

# 14. Emergency / Safety Rules

If anything unexpected happens, stop rather than attempting automatic recovery.

Examples:
- unexpected dirty files
- wrong branch
- missing files
- unexpected deleted files
- unexpected modified documentation
- unrelated task changes
- unknown Git stash
- unexpected dependency changes
- unexpected architecture changes

Correct response:

```text
STOP → inspect → report → human decides → continue
```

Never use automatic cleanup as a substitute for understanding repository state.

# 15. Project Documentation Relationship

```text
ai/PROJECT.md
    → stable architectural principles

ai/SPECIFICATION.md
    → system requirements

ai/ROADMAP.md
    → task sequencing

ai/AGENTS.md
    → operational rules

ai/AGENT_WORKFLOW.md
    → agent collaboration workflow

ai/tasks/TASK-XXX.md
    → individual implementation scope

docs/reviews/TASK-XXX-review.md
    → independent review record
```

The review artifact should remain associated with the task so future maintainers can understand:

```text
what was requested
→ what was implemented
→ what was tested
→ what Qwen found
→ what was fixed
→ what was finally approved
```

# 16. Recommended Default

For `ai-data-platform`:

```text
Human creates branch
        ↓
Qoder implements + tests + commits
        ↓
Qwen reviews
        ↓
Qoder fixes if necessary
        ↓
Qwen approves
        ↓
Human pushes / PR
        ↓
Human merges
```

Do not optimize this workflow away prematurely.

As the project grows, Git worktrees can provide stronger physical isolation:

```text
main
 ├── worktree/TASK-007 → feature/TASK-007
 ├── worktree/TASK-008 → feature/TASK-008
 └── worktree/TASK-009 → feature/TASK-009
```

The fundamental rule remains:

> **One engineering task = one dedicated branch = one isolated implementation cycle.**
