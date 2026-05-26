# Owner A — backend/migrations/env.py
#
# Alembic environment script. Runs every time you call `alembic` on the CLI.
# Handles both offline mode (generates SQL) and online mode (applies to DB).
# Uses asyncpg — so migrations run in an async context via run_sync().
#
# IMPORTANT: Only Owner A generates migration files (alembic revision --autogenerate).
# Other owners define SQLAlchemy models; Owner A turns them into migrations.

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import Base and all models so Alembic sees every table during autogenerate.
# If a model is not imported here (directly or via __init__.py), Alembic will
# generate a DROP TABLE for it in the next revision.
from app.models import Base  # noqa: F401 — triggers all model imports via __init__.py

config = context.config

# Wire up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata Alembic compares against the live DB to detect drift
target_metadata = Base.metadata


def get_url() -> str:
    """Read DATABASE_URL from the environment. Never falls back to a hardcoded value."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return url


def run_migrations_offline() -> None:
    """
    Offline mode: generate SQL script without a live DB connection.
    Useful for reviewing what a migration will do before applying it.
    Run with: alembic upgrade head --sql
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Include schema-level objects like RLS policies in the comparison
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Runs the actual migration steps inside a live connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        # Compare server defaults so Alembic detects changes to DEFAULT values
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Online mode with asyncpg: create an async engine, acquire a connection,
    then run migrations synchronously inside run_sync() so Alembic's
    synchronous API works correctly.
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # No connection pooling during migrations
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online mode — wraps the async runner."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
