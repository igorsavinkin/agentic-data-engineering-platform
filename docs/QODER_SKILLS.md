# Qoder Skills System

## Overview

**Qoder Skills** are specialized instruction sets that extend the agent's capabilities for specific domains, workflows, or tools. They act as "plug-ins" that activate automatically when relevant context is detected in your conversation.

### How Skills Work

- **Location**: Stored in `.qoder/skills/<skill-name>/SKILL.md`
- **Format**: Markdown files with YAML frontmatter containing metadata
- **Activation**: Automatically triggered by keyword matching in user requests
- **Scope**: Provide domain-specific guidance without cluttering the main AGENTS.md

### Skills vs AGENTS.md

| Aspect | AGENTS.md | Skills |
|--------|-----------|--------|
| **Scope** | Repository-wide conventions (always active) | Domain-specific capabilities (contextual) |
| **When to read** | Before every task | Only when skill is triggered |
| **Content** | Coding standards, testing rules, security policies | Tool usage, workflow patterns, best practices |
| **Examples** | "Don't commit secrets", "Run tests before committing" | "How to use Redis Query Engine", "Architecture visualization patterns" |

---

## Available Skills

### Custom Project Skills

These skills are specific to this repository and support our task automation system:

#### 1. qoder-task-workflow
**Purpose**: Automate task implementation using Qoder chat sessions instead of Codex CLI

**Triggers**:
- "run task XXX"
- "implement TASK-009"
- "automate task workflow"

**What it does**:
- Creates isolated worktrees for each task
- Spawns independent Qoder conversations for implementation
- Manages review → publish → CI → cleanup lifecycle
- Tracks progress in `task-workflow/TASK-xxx/state.json`

**Key features**:
- Full Read/Edit/Bash/Git tool access (not sandboxed like Codex)
- Persistent conversation history for debugging
- Automated PR creation and CI monitoring

**Documentation**: `.qoder/skills/qoder-task-workflow/SKILL.md`

#### 2. qoder-task-orchestrator
**Purpose**: Orchestrate the complete task development lifecycle with automated phase management

**Triggers**:
- "run task XXX"
- "implement TASK-010"
- "automate task workflow"
- Managing multiple sequential or dependent tasks

**What it does**:
- Coordinates multiple independent Qoder sessions per task phase
- Manages Prepare → Implement → Review → Publish → CI Monitor → Cleanup workflow
- Handles state persistence and recovery from interruptions
- Enforces maximum 2 concurrent task worktrees

**Workflow phases**:
1. **Prepare**: Validate clean main, create worktree, initialize state tracking
2. **Implement**: Spawn Qoder session with full context (AGENTS.md, ADRs, specs)
3. **Review**: Run quality checks (ruff, mypy, pytest), invoke Qwen review
4. **Publish**: Push branch, create PR, monitor GitHub Actions
5. **Cleanup**: Remove worktree, delete branches after merge

**Documentation**: `.qoder/skills/qoder-task-orchestrator/SKILL.md`

**Supporting files**:
- `QUICKSTART.md` - Quick reference guide
- `EXAMPLE.md` - Usage patterns for single tasks, dependencies, batch execution

### Built-in Qoder Skills

These are provided by the Qoder platform itself:

#### 3. qoder-find-extensions
**Purpose**: Discover Qoder Skills, MCP connectors, and Plugins

**Triggers**:
- Explicit requests to search, compare, recommend, or install capabilities
- Searching Qoder's official market or skills.sh community sources

**What it does**:
- Searches Qoder's official marketplace
- Browses community-maintained skills at skills.sh
- Compares available extensions and recommends based on needs

#### 4. qoder-qmind
**Purpose**: Knowledge base management for QMind

**Triggers**:
- Mentions of "QMind", "knowledge base", "Notebook", "knowledge source import"

**What it does**:
- Retrieves evidence from QMind knowledge base
- Browses Notebooks and Sources
- Adds text, HTTPS links, or local files to the knowledge base

#### 5. qoder-context
**Purpose**: Manage pre-flight configuration for wiki and knowledge-card generation

**Triggers**:
- Creating or updating `.qoder/repowiki/wiki_plan.yaml`
- Configuring authoring notes, page whitelists, templates, file-scope filters

**What it does**:
- Steers wiki generation behavior
- Manages per-page templates and preset wiki templates
- Controls file-scope filters for what gets included

---

## Skill Structure

Each skill follows a standard directory structure:

```
.qoder/skills/<skill-name>/
├── SKILL.md          # Main instruction file (required)
├── QUICKSTART.md     # Quick reference guide (optional)
├── EXAMPLE.md        # Usage examples (optional)
└── README.md         # Additional documentation (optional)
```

### SKILL.md Format

```markdown
---
name: skill-identifier
description: One-line description used for automatic triggering. Include keywords that users might type.
---

# Skill Name

## When to Use
[Clear conditions for activation]

## Prerequisites
[Any setup or validation needed]

## Workflow/Usage
[Step-by-step instructions with code examples]

## Error Handling
[Common failure modes and recovery]

## Limitations
[Known constraints or restrictions]

## See Also
[Cross-references to related skills or documentation]
```

### Frontmatter Fields

- **`name`**: Unique identifier (kebab-case, matches directory name)
- **`description`**: Trigger keywords and use cases (used for automatic matching)

---

## When to Create New Skills

Create a new skill when you have:

✅ **Domain-specific expertise** that doesn't fit in AGENTS.md
- Example: Redis performance optimization, architecture visualization, legacy system modernization

✅ **Reusable workflow patterns** used across multiple tasks
- Example: Task automation, PR review automation, deployment orchestration

✅ **Tool integration guides** for complex external systems
- Example: MCP connectors, GitHub CLI workflows, browser automation

❌ **Don't create skills for**:
- General coding conventions (belongs in AGENTS.md)
- One-off task specifics (belongs in task specification)
- Project structure documentation (belongs in PROJECT.md or repowiki)

---

## Activation Mechanisms

### Automatic Matching

Skills activate when the agent detects relevant keywords in your request:

```python
# User says: "run task 010"
# Agent matches: "run task" → triggers qoder-task-orchestrator

# User says: "check our Redis caching strategy"
# Agent matches: "Redis" → triggers redis-development
```

The matching algorithm considers:
- Keywords in the `description` field
- Section headers in SKILL.md ("When to Use")
- Recent conversation context

### Manual Invocation

You can explicitly request a skill using slash commands:

```
/qoder-task-orchestrator run task 010
/architecture-communicator explain the system to executives
```

### Context-Based Activation

Some skills activate based on detected patterns:
- File types being modified (e.g., `.drawio` files trigger drawio skill)
- Tools being used (e.g., Redis commands trigger redis-development)
- Conversation topics (e.g., mentioning "legacy system" triggers legacy-system-visualizer)

---

## Managing Skills

### Adding New Skills

1. Create directory: `.qoder/skills/my-new-skill/`
2. Write `SKILL.md` with frontmatter and instructions
3. Test by invoking with explicit trigger keywords
4. Document in this file under "Custom Project Skills"

### Updating Existing Skills

Edit `SKILL.md` directly. Changes take effect immediately for new conversations.

### Disabling Skills

Rename the skill directory to add a suffix:
```bash
mv .qoder/skills/qoder-task-workflow .qoder/skills/qoder-task-workflow.disabled
```

---

## Location in Repository

All custom skills live in:
```
.qoder/skills/
├── qoder-task-orchestrator/    # Task lifecycle orchestration
│   ├── SKILL.md
│   ├── QUICKSTART.md
│   └── EXAMPLE.md
└── qoder-task-workflow/        # Task workflow automation
    └── SKILL.md
```

Built-in skills are managed by the Qoder platform and listed when you run:
```bash
# List available skills
mcp_list()  # via Qoder MCP tools
```

---

## Related Documentation

- **Agent conventions**: `ai/AGENTS.md` - Always-active coding standards
- **Task specifications**: `ai/tasks/` - Individual task requirements
- **Project context**: `ai/PROJECT.md` - Overall project architecture
- **Workflow rules**: `ai/AGENT_WORKFLOW.md` - Development workflow guidelines
- **Automation docs**: `scripts/README_TASK_AUTOMATION.md` - Complete task automation system

---

## Quick Reference

### Most Common Skills for This Project

| Task | Skill to Use |
|------|-------------|
| Implement a new TASK-xxx | `qoder-task-orchestrator` |
| Check if task can run | `qoder-task-orchestrator` (validates prerequisites) |
| Resume interrupted task | `qoder-task-orchestrator` (reads state.json) |
| Find new skills to install | `qoder-find-extensions` |
| Search project knowledge | `qoder-qmind` |
| Generate architecture diagrams | `architecture-visualization:*` (various sub-skills) |
| Optimize Redis queries | `redis-development` |

### Troubleshooting

**Skill not activating?**
- Check that `description` contains relevant keywords
- Verify skill directory exists in `.qoder/skills/`
- Try explicit invocation with `/skill-name`

**Need more control over activation?**
- Add more specific keywords to `description`
- Use manual invocation with `/skill-name` syntax
- Adjust conversation context to include trigger terms

**Skill behaving unexpectedly?**
- Read the full `SKILL.md` to understand intended behavior
- Check `QUICKSTART.md` or `EXAMPLE.md` for usage patterns
- Review recent changes to the skill file
