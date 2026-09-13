"""Alembic environment configuration for warehouse migrations.

Reads database connection parameters from WAREHOUSE_DB_* environment
variables and configures SQLAlchemy accordingly.
"""

# mypy: disable-error-code="import-untyped,import-not-found"
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# this is the Alembic Config object, which provides access to values within
# the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# Build SQLAlchemy URL from environment variables
def _build_database_url() -> str:
    """Construct database URL from WAREHOUSE_DB_* env vars."""
    host = os.getenv("WAREHOUSE_DB_HOST", "localhost")
    port = os.getenv("WAREHOUSE_DB_PORT", "5432")
    dbname = os.getenv("WAREHOUSE_DB_NAME", "warehouse")
    user = os.getenv("WAREHOUSE_DB_USER", "postgres")
    password = os.getenv("WAREHOUSE_DB_PASSWORD", "")

    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"


config.set_main_option("sqlalchemy.url", _build_database_url())


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine,
    though an Engine is acceptable here as well.  By skipping the Engine
    creation we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=None,
        literal_binds=True,
        dialect_name="postgresql",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine and associate a
    connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
