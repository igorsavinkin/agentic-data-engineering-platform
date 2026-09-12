# TASK-023 — Partitioning Strategy

## Objective
Define and implement the canonical source/time partition strategy for Bronze and Silver.

## Context
This task belongs to **Milestone 3 — Data Lake**. The roadmap objective is to persist raw and processed data as Apache Parquet. Local object storage is MinIO; AWS later uses S3. Bronze is raw/minimally transformed data and Silver is validated/normalized data.

## Required Context Before Coding
Read the current repository versions of `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and relevant prior task implementations. If this task conflicts with a higher-authority repository document, stop and report the conflict.

## Scope / Requirements
Create one reusable partition-path builder; use layer + source + temporal dimensions, e.g. `bronze/source=example/year=2026/month=09/day=03/`; use observation/collection time unless higher-authority docs specify otherwise; sanitize paths safely; never partition by event/product/external IDs.

Preserve these project invariants:
- at-least-once delivery + idempotent processing; never claim exactly-once;
- Kafka is transport/replay infrastructure, not the analytical datastore;
- Parquet on MinIO/S3 is the data-lake layer;
- use Polars/PyArrow for columnar work where practical;
- no secrets in source control;
- do not implement later milestone functionality.

## Tests Required
Add deterministic unit/integration tests appropriate to the scope, including success, failure, nullable/edge cases, and replay/retry behavior where persistence is involved. Run on the final working tree:
- `python -m pytest` (unit tests)
- `python -m pytest -m integration` (integration tests, when Docker prerequisites are running)
- `ruff check .` and `ruff format --check .` (lint/format)
- `mypy src/` (type checks)

## Acceptance Criteria
Both writers use the same deterministic partition utility; source/time partitioning is documented and tested across sources, dates, timezones and unsafe path characters.

## Agent Instructions
Implement **TASK-023 only** on its dedicated branch. Do not redesign service boundaries or implement the next task. Inspect `git status`, `git diff --stat`, and the final diff before committing.
