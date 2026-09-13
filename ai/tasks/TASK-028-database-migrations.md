# TASK-028 — Database Migrations

## Objective
Add a repeatable database migration mechanism for the PostgreSQL warehouse schema.

## Dependencies
TASK-027.

## Requirements
- Introduce/configure the repository migration mechanism.
- Create an initial migration for the warehouse schema.
- Support deterministic upgrade from an empty database.
- Support downgrade/rollback where repository policy requires it.
- Schema creation must happen through migrations, not ad-hoc runtime SQL.
- Use existing typed environment/config patterns.
- No real secrets in source control.
- Keep migration code separate from request/runtime logic.
- Tests must use an isolated PostgreSQL DB/schema.
- Do not implement loader logic.

## Tests Required
- migrate empty DB to head/latest
- resulting schema matches TASK-027
- migration version/status inspectable
- downgrade/upgrade cycle if supported
- rerun is safe
- misconfiguration fails clearly

## Acceptance Criteria
A clean PostgreSQL instance can be brought to the current schema version with one documented migration command; migration history is version-controlled and reproducible in CI.

## Agent Instructions
Implement TASK-028 only.
