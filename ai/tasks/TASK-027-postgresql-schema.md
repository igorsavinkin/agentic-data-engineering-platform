# TASK-027 — PostgreSQL Schema

## Objective
Design and implement the initial PostgreSQL warehouse schema for the serving and analytical layer.

## Context
Milestone 4 creates the PostgreSQL analytics/serving layer downstream of curated Parquet data. Initial logical entities are `sources`, `products`, `product_observations`, `pipeline_runs`, and `data_quality_results`. The warehouse must support historical observations, not only the latest state.

## Required Context Before Coding
Read the current repository versions of `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and TASK-020–026 outputs/current Parquet schemas. If this task conflicts with a higher-authority document, stop and report the conflict.

## Requirements
- Define tables, PKs, FKs, nullability, uniqueness constraints, and timestamp semantics.
- Preserve multiple historical observations for one product.
- Keep source identity distinct from canonical/logical product identity.
- Use an exact numeric type for money; do not store prices as binary floating point.
- Use timezone-aware timestamps where appropriate.
- Support later queries for latest observation, price changes, rolling calculations, product history, and source statistics.
- Do not add speculative entities.
- Do not add performance indexes beyond constraint-required indexes; TASK-031 owns indexing.
- Document table relationships and rationale.

## Tests Required
- schema can be created
- required constraints exist
- FK behavior
- duplicate logical keys rejected where appropriate
- multiple historical observations allowed
- price/timestamp types verified

## Acceptance Criteria
The PostgreSQL schema is explicit, documented, testable, supports historical observations, and can support the later loader/API/analytics work without redesign.

## Out of Scope
Migration framework, warehouse loading, idempotent replay, performance indexes, analytical query library.

## Agent Instructions
Implement TASK-027 only.
