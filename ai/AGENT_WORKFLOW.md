# AGENT_WORKFLOW.md

# AI Data Platform — AI-Assisted Engineering Workflow

## 1. Purpose

This document defines how AI coding agents collaborate on the AI Data Platform without weakening architectural ownership, code quality, or the educational value of the project.

The repository uses AI as an engineering accelerator, not as an autonomous architecture authority.

The default workflow is:

```text
Human architecture
      ↓
Specification / ADRs
      ↓
Focused TASK-xxx.md
      ↓
Qoder implementation
      ↓
Automated tests + local validation
      ↓
Independent Qwen review
      ↓
Fix findings
      ↓
Claude escalation when necessary
      ↓
Human review and decision
      ↓
Merge
```

## 2. Repository Context Hierarchy

Agents must interpret work using the following hierarchy:

```text
ai/PROJECT.md
    ↓
ADRs
    ↓
ai/SPECIFICATION.md
    ↓
ai/ROADMAP.md
    ↓
ai/tasks/TASK-xxx.md
    ↓
AGENTS.md
```

`PROJECT.md` defines stable architectural principles.

`SPECIFICATION.md` defines what the system must do.

`ROADMAP.md` defines implementation order and milestones.

`TASK-xxx.md` defines the current focused unit of work.

`AGENTS.md` defines persistent operational behavior for coding agents.

If implementation reveals that a higher-level document is wrong or incomplete, the agent must report the issue rather than silently overriding it.

## 3. Roles

### 3.1 Human Owner — Architect and Final Decision Maker

The human owner is responsible for:

- architectural direction
- choosing trade-offs
- approving ADRs
- deciding milestone scope
- reviewing consequential changes
- validating that the implementation remains understandable
- deciding whether work is merged

AI agents may propose architecture changes but do not approve them.

### 3.2 Qoder — Primary Builder

Qoder is the default implementation environment.

Use Qoder for:

- repository navigation
- implementation
- refactoring within task scope
- Python/FastAPI/Pydantic work
- Kafka producers and consumers
- Polars/PyArrow processing
- SQL
- source adapters
- Docker
- Airflow
- Kubernetes manifests
- Helm
- Terraform implementation
- tests
- CI/CD
- documentation
- running local commands and inspecting failures

Qoder should work from focused tasks rather than broad prompts such as "build the whole platform".

### 3.3 Qwen Code — Independent Reviewer

Qwen Code should normally review without modifying files.

Typical review prompt intent:

```text
Review TASK-xxx implementation against:
- PROJECT.md
- SPECIFICATION.md
- ROADMAP.md
- TASK-xxx.md

Do not modify files.
Report correctness issues, missed requirements, edge cases, security risks, architecture violations, and missing tests.
```

The purpose of the second model is independence, not consensus.

### 3.4 DeepSeek / Qwen Models — Cost-Efficient Implementation

Lower-cost models may be used inside Qoder for:

- boilerplate
- straightforward Python
- Pydantic models
- deterministic transformations
- tests
- SQL
- Dockerfiles
- YAML
- documentation
- simple refactoring

Do not automatically use the cheapest model for architecture-critical or failure-sensitive code.

### 3.5 Claude Code — Senior Escalation

Use Claude Code selectively when the problem requires deeper independent reasoning.

Typical escalation cases:

- Kafka delivery semantics
- offset/transaction/idempotency problems
- concurrency bugs
- schema evolution trade-offs
- difficult Kubernetes failures
- Terraform/AWS architecture review
- security-sensitive design
- complex performance bottlenecks
- cross-service production failures
- final architecture audit

Claude is a consultant/reviewer, not the default boilerplate generator.

## 4. Task Lifecycle

Every focused implementation task should follow this lifecycle.

### Step 1 — Select the Task

The human chooses one `TASK-xxx.md` from the active milestone.

Do not begin large batches of unrelated tasks simultaneously during early milestones.

### Step 2 — Load Context

Qoder reads:

```text
ai/PROJECT.md
ai/SPECIFICATION.md
ai/ROADMAP.md
AGENTS.md
ai/AGENT_WORKFLOW.md
ai/tasks/TASK-xxx.md
```

Only the relevant roadmap/specification sections need to be actively reasoned about, but architectural constraints must remain respected.

### Step 3 — Plan

For multi-file or non-trivial work, produce a short implementation plan before editing.

The plan should identify:

- files/components affected
- interfaces involved
- tests required
- failure cases
- any architectural uncertainty

If architecture is uncertain, stop before implementation and escalate.

### Step 4 — Implement

Implement only the task scope.

Prefer small commits/diffs that can be reviewed independently.

### Step 5 — Validate Locally

Run the checks relevant to the task:

```text
unit tests
integration tests
lint
format
type checks
service startup where relevant
Docker/Kubernetes validation where relevant
```

Do not report success without running available checks unless the environment makes execution impossible; in that case state exactly what was not executed.

### Step 6 — Self-Review

Qoder reviews the git diff against the task and asks:

- Did I implement all acceptance criteria?
- Did I change anything outside scope?
- Did I alter a public contract?
- Did I add unnecessary dependencies?
- Are failure cases handled?
- Are logs/metrics appropriate?
- Could retry/replay create duplicates?
- Did I introduce secrets or insecure defaults?

### Step 7 — Independent Review

Qwen Code reviews the finished diff without editing it.

Review findings should be classified approximately as:

```text
BLOCKER
MAJOR
MINOR
SUGGESTION
```

BLOCKER and MAJOR findings must be resolved or explicitly rejected with a documented reason before merge.

### Step 8 — Escalate if Needed

Consult Claude Code when the issue meets the escalation criteria in this document or `ROADMAP.md`.

Do not escalate ordinary syntax or boilerplate work unnecessarily.

### Step 9 — Human Review

The human reviews:

- architectural correctness
- important code paths
- tests
- review findings
- operational behavior
- educational understanding

### Step 10 — Merge

Merge only after the repository Definition of Done is satisfied.

## 5. Git and Worktree Strategy

Default branch model:

```text
main
  ├── feature/TASK-001
  ├── feature/TASK-002
  └── feature/TASK-xxx
```

One focused task should normally map to one focused branch/PR.

From TASK-006 onward, use at most two active engineering tasks in separate
worktrees: one in independent review/fixes/PR/CI, one in implementation.
Codex may take over Qoder's builder role. Each task still has a separate agent
execution and exact `feature/TASK-xxx` branch; no automatic task chaining.
The human selects each next task and retains the merge decision.

Start a dependent task only after its prerequisite implementation is committed
and interfaces are stable. For contract-sensitive work (especially TASK-006 and
TASK-007), wait for independent approval before starting dependent work. If a
review changes the interface, pause the dependent task and reconcile it first.
Independent work can start from main; stacked work must record its parent commit
and use that commit as the review base. After the parent merges, reconcile the
branch with main and inspect the PR diff before merging.

Example for a task whose prerequisites have merged:

```bash
git worktree add -b feature/TASK-006 ../ai-platform-task-006 main
```

Never let multiple agents edit one worktree concurrently. When a task merges,
move the implementation task to review and start a separately selected task only
when its dependency gate permits. Do not create five or more active lanes.

Codex/Qoder install the project-managed hooks during checkout setup as documented
in `scripts/README.md`. Pre-commit runs Ruff lint and format checks; pre-push runs
pytest and mypy. The Git process must inherit the active Python environment.
Qwen selectively reruns critical or suspicious tests rather than duplicating CI.

Builders run focused tests during development and `scripts/task_check.ps1` or
`bash scripts/task_check.sh` before committing, plus relevant integration checks.
Reviewers inspect test quality and selectively rerun critical or suspicious tests
according to `ai/REVIEWER.md`. Complete Qwen review and resolve blocking findings
before pushing to origin, then open the PR to start CI. Follow the commands in
`docs/TASK_WORKFLOW.md`. Review can overlap another task's implementation when
dependency gates permit. CI is the authoritative full merge gate for its configured
checks; require successful checks on the final PR revision. Review any subsequent
fixes and rerun affected checks. Human owners need not repeat successful checks.

Resolve BLOCKER/Critical and MAJOR/High findings before acceptance, or document
an explicit owner decision rejecting the finding. Fix Minor findings when cheap
or consequential; defer suggestions with rationale and a revisit trigger in
`docs/reviews/FOLLOWUPS.md`. Never defer a blocking defect as a suggestion.

Branch protection should require a PR and the actual Quality checks status and
prevent direct pushes to main. This policy does not itself configure GitHub.

## 6. Source-Implementation Workflow

Data sources are introduced progressively.

### Phase 1 — Deterministic + Stable API Sources

```text
Fake Store API
Best Buy
```

Objectives:

- validate adapter interface
- canonical event normalization
- retries
- metrics
- end-to-end pipeline behavior

### Phase 2 — Marketplace Source

```text
eBay
```

Objectives:

- multiple listings per logical product
- seller normalization
- marketplace identity mapping
- price-history observations

### Phase 3 — Web Retailer

Add one retailer website using the simplest reliable mechanism.

Objectives:

- HTML/dynamic-content ingestion
- parsing failures
- pagination
- source-specific retries
- freshness monitoring

### Phase 4 — Difficult Source

Use Amazon or another source that introduces meaningful operational difficulty.

Objectives:

- graceful degradation
- rate limiting/backoff
- structural changes
- partial parsing
- source-health alerting

The difficult source is replaceable; the downstream platform must not depend on its identity.

## 7. Architecture Change Workflow

When implementation suggests a fundamental architecture change:

```text
Detect problem
     ↓
Stop implementation
     ↓
Document evidence
     ↓
Describe alternatives
     ↓
Propose ADR
     ↓
Human decision
     ↓
Update PROJECT/SPECIFICATION/ROADMAP if required
     ↓
Resume implementation
```

Examples requiring this workflow include:

- changing delivery semantics
- bypassing Kafka
- changing canonical event boundaries
- replacing the data-lake architecture
- changing warehouse ownership
- granting the agent write access
- materially changing cloud topology

## 8. Review Expectations by Technology

### Kafka

Check:

- offset commit behavior
- retries
- duplicate handling
- ordering assumptions
- consumer groups
- rebalancing
- replay
- DLQ behavior

### Data Processing

Check:

- schema normalization
- null/type handling
- deduplication
- Polars usage
- deterministic transforms
- Parquet schema compatibility

### PostgreSQL

Check:

- keys and constraints
- idempotent loading
- indexes
- migrations
- query plans for important analytics
- historical observation correctness

### Airflow

Check:

- scheduling semantics
- retries
- idempotent tasks
- dependencies
- backfills
- separation from Kafka streaming

### Kubernetes

AI may generate manifests, but the human should personally practice diagnostics using:

```bash
kubectl get
kubectl describe
kubectl logs
kubectl exec
kubectl apply
kubectl delete
kubectl rollout
kubectl port-forward
kubectl get events
```

Do not accept a Kubernetes fix that nobody can explain.

### Terraform / AWS

Check:

- least privilege
- state handling
- environment separation
- destructive changes
- networking
- cost implications
- secret handling

## 9. Failure-First Review

For every major component, ask:

```text
What if this request is retried?
What if the process crashes here?
What if the dependency is unavailable?
What if the message arrives twice?
What if the schema changes?
What if the source stops producing?
How will we detect it?
How will we recover?
```

Failure behavior is part of the implementation, not optional polish.

## 10. Model Selection Rule

Use the least expensive model that can reliably handle the task, but optimize for correctness rather than token price alone.

A useful heuristic:

```text
Straightforward / repetitive
        → inexpensive Qwen/DeepSeek model

Repo-wide implementation / debugging
        → stronger Qoder model

Independent review
        → Qwen Code

Architecture / distributed systems / hard failure
        → Claude Code
```

## 11. Human Learning Gate

A milestone is not complete if it works only because an AI agent generated an opaque implementation.

Before completing major milestones, the human owner should be able to explain the relevant fundamentals:

- Kafka partitions, offsets, groups, commits, rebalancing
- idempotency, retry, replay and partial failure
- Polars transformations and Parquet layout
- PostgreSQL schema/index/query choices
- Airflow DAG scheduling/retries
- Kubernetes pods/deployments/services/probes/resources
- metrics/logs/traces
- AWS EKS/S3/RDS/IAM roles in the architecture

## 12. Final Rule

The goal is not to maximize AI-generated code.

The goal is to produce a repository where an experienced engineer can see coherent architecture, reliable implementation, measurable operational behavior, disciplined reviews, and clear human understanding of the system.
