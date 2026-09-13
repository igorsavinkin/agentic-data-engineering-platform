# Warehouse Database Migrations

Database migrations for the PostgreSQL warehouse schema, managed by Alembic.

## Overview

Migrations provide version-controlled, repeatable database schema changes that can be safely applied across environments (development, testing, production). All schema creation happens through migrations, not ad-hoc runtime SQL.

## Prerequisites

- PostgreSQL running locally or remotely
- Python dependencies installed: `alembic`, `psycopg2-binary`, `sqlalchemy`
- Environment variables configured (see below)

## Configuration

Set these environment variables before running migrations:

```bash
export WAREHOUSE_DB_HOST=localhost
export WAREHOUSE_DB_PORT=5432
export WAREHOUSE_DB_NAME=warehouse
export WAREHOUSE_DB_USER=postgres
export WAREHOUSE_DB_PASSWORD=your_password
```

For testing, use a separate database:

```bash
export WAREHOUSE_DB_NAME_MIGRATION=warehouse_migration_test
```

## Usage

### Upgrade to latest version

```bash
python -m warehouse.migrations upgrade head
```

### Downgrade by one version

```bash
python -m warehouse.migrations downgrade -1
```

### Downgrade to base (remove all tables)

```bash
python -m warehouse.migrations downgrade base
```

### Show current version

```bash
python -m warehouse.migrations current
```

### Show migration history

```bash
python -m warehouse.migrations history
```

### Stamp database to specific version (without running migrations)

```bash
python -m warehouse.migrations stamp 001
```

## Creating New Migrations

To create a new migration:

```bash
cd warehouse/migrations
alembic revision -m "description of change"
```

This creates a new file in `versions/` with `upgrade()` and `downgrade()` functions. Edit these functions to define your schema changes.

## Migration Files

- `alembic.ini` - Alembic configuration
- `env.py` - Environment setup (reads WAREHOUSE_DB_* env vars)
- `script.py.mako` - Template for new migration files
- `run_migrations.py` - CLI entry point
- `versions/` - Individual migration scripts

## Testing

Run migration tests:

```bash
python -m pytest tests/warehouse/test_migrations.py -v -m integration
```

Tests verify:
- Empty database upgrades to head
- Schema matches TASK-027 specification
- Version tracking works correctly
- Downgrade/upgrade cycles work
- Reruns are safe (idempotent)
- Misconfiguration fails clearly

## Design Decisions

1. **Alembic over raw SQL**: Provides Python-based migrations with automatic version tracking, rollback support, and programmatic schema manipulation.

2. **Environment variables**: Connection parameters come from `WAREHOUSE_DB_*` environment variables, keeping credentials out of source control.

3. **Separate test database**: Migration tests use `warehouse_migration_test` database to avoid interfering with development or production data.

4. **Idempotent upgrades**: Running `upgrade head` multiple times is safe; Alembic tracks which migrations have been applied.

5. **Downgrade support**: Every migration includes a `downgrade()` function to reverse changes, supporting rollbacks when needed.

6. **No runtime migration**: Schema changes happen via CLI commands, not during application startup. This keeps runtime logic separate from schema evolution.

## Troubleshooting

### "Connection refused" error

Verify PostgreSQL is running and environment variables are correct:

```bash
psql -h $WAREHOUSE_DB_HOST -p $WAREHOUSE_DB_PORT -U $WAREHOUSE_DB_USER -d $WAREHOUSE_DB_NAME
```

### "Table already exists" error

The database may have been created manually. Either:
- Drop the existing tables and run `upgrade head`
- Use `stamp head` to mark migrations as applied without running them

### "No such revision" error

Ensure you're in the correct directory and `alembic.ini` points to the right `script_location`.
