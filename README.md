# AI Data Platform

A production-oriented distributed data platform demonstrating modern Data Engineering, Backend Engineering, Cloud Infrastructure, and Agentic AI capabilities: source adapters ingest product observations, Kafka transports events, a Polars-based processor validates and normalizes them, Parquet data-lake layers (Bronze/Silver/Gold) persist them, PostgreSQL serves analytics, and FastAPI and a controlled LangGraph agent expose the data.

## Documentation

- [`ai/PROJECT.md`](ai/PROJECT.md) — project constitution (highest architectural authority)
- [`ai/SPECIFICATION.md`](ai/SPECIFICATION.md) — implementation specification
- [`ai/ROADMAP.md`](ai/ROADMAP.md) — engineering roadmap and milestones
- [`ai/AGENTS.md`](ai/AGENTS.md) — agent operating rules (canonical)
- [`ai/AGENT_WORKFLOW.md`](ai/AGENT_WORKFLOW.md) — AI-assisted engineering workflow
- [`ai/tasks/`](ai/tasks/) — focused task specifications

## Development

Requires Python 3.12+ (declared in `pyproject.toml`) and pip.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows (Git Bash): source .venv/Scripts/activate
python -m pip install -r requirements-dev.txt
```

Quality checks (the same commands CI runs):

```bash
ruff check .          # lint
ruff format --check . # formatting
mypy                  # static type check (paths configured in pyproject.toml)
pytest                # tests
```

Dependencies: runtime in `requirements.txt`, development tooling (pytest, Ruff, mypy) in `requirements-dev.txt`. Tool configuration lives in `pyproject.toml`.

## Status

Milestone 0 — Repository Foundation (TASK-001, TASK-002).
