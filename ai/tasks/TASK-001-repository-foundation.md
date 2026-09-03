# TASK-001 — Repository Foundation

## Status
Ready

## Objective
Create the initial repository structure and development conventions for the AI Data Platform without making new architectural decisions.

## References
- `ai/PROJECT.md`
- `ai/SPECIFICATION.md`
- `ai/ROADMAP.md`
- `ai/AGENTS.md`
- `ai/AGENT_WORKFLOW.md`

## Scope
### In scope
- Create the agreed top-level repository directories.
- Create `ai/tasks/` and place task specifications there.
- Ensure the governance documents are located under `ai/`.
- Add or update a minimal root-level `AGENTS.md` pointer so tools that only auto-discover `AGENTS.md` at repository root can find the canonical agent rules.
- Add minimal README files where needed for empty directories.
- Update task/document references if required by the relocation to `ai/tasks/`.

### Out of scope
- Kafka, database, Kubernetes, AWS, or LangGraph implementation.
- Changing service boundaries or the canonical data-flow architecture.
- Changing technology choices defined by `ai/PROJECT.md` or `ai/SPECIFICATION.md`.
- Rewriting the roadmap or creating additional tasks beyond the repository-foundation changes required here.

## Requirements

The repository must include:
```text
ai/
├── PROJECT.md
├── SPECIFICATION.md
├── ROADMAP.md
├── AGENTS.md
├── AGENT_WORKFLOW.md
└── tasks/
    └── TASK-xxx-*.md

docs/
services/
libs/
tests/
airflow/
sql/
kubernetes/
terraform/
monitoring/
scripts/
```

All task specifications governed by the documentation set must live under:
```text
ai/tasks/
```

The canonical agent instructions are:
```text
ai/AGENTS.md
```

A root-level `AGENTS.md` may exist only as a short pointer to `ai/AGENTS.md`; it must not introduce conflicting rules. If the agent/tooling already reliably discovers `ai/AGENTS.md`, do not duplicate its contents in the root file.

## Tests Required
- Verify the expected directory structure exists.
- Verify the five governance documents exist under `ai/`.
- Verify `ai/tasks/` exists.
- Verify the task files being used for Milestone 0/1 are located under `ai/tasks/`.
- Verify references to task paths are consistent with `ai/tasks/`.
- Verify the root `AGENTS.md`, if created, contains no conflicting instructions.

## Acceptance Criteria
- Repository structure matches `ai/SPECIFICATION.md` and `ai/PROJECT.md`.
- `ai/tasks/` is the canonical location for task specifications.
- `TASK-001` and subsequent task files are not left in a separate top-level `tasks/` directory.
- The canonical agent rules remain in `ai/AGENTS.md`.
- A root `AGENTS.md` pointer is present if needed for Qoder/tool auto-discovery and does not duplicate or contradict the canonical rules.
- No unnecessary application logic is introduced.
- No architectural decisions are invented by the agent.
- Git diff contains only foundation/documentation changes.

## Agent Instructions
Implement only this task. Read all five referenced governance documents before making changes. Do not make architectural decisions beyond the existing documents. Treat `ai/PROJECT.md` as the highest-authority project document. If a conflict is discovered, stop and report it rather than inventing a resolution.
