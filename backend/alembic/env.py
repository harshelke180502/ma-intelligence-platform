"""
Alembic async migration environment.

Configured for SQLAlchemy async engine (asyncpg driver).
Run from the backend/ directory so that `app` is importable.

Usage:
    # Generate migration from current model state
    alembic revision --autogenerate -m "add new column"

    # Apply all pending migrations
    alembic upgrade head

    # Rollback one migration
    alembic downgrade -1
"""

import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ── Path setup ────────────────────────────────────────────────────────────────
# Ensure backend/ is on sys.path when alembic is run from that directory.
# __file__ = .../backend/alembic/env.py
# dirname(dirname(__file__)) = .../backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Import app config and models ──────────────────────────────────────────────
# Import settings first (before any model imports that might need it)
from app.core.config import settings  # noqa: E402

# Import all models via the package __init__ so that every mapper is
# registered with Base.metadata before autogenerate inspects it.
import app.models  # noqa: F401, E402
from app.models.base import Base  # noqa: E402

# ── Alembic config ────────────────────────────────────────────────────────────
config = context.config

# Point Alembic at our database URL from settings (overrides alembic.ini)
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Set up Python logging from alembic.ini [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata object that autogenerate will diff against the live database
target_metadata = Base.metadata


# ── Offline mode ──────────────────────────────────────────────────────────────
# Generates migration SQL without a live database connection.
# Useful for reviewing changes before applying them.
def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Render AS TIMEZONE explicitly for TIMESTAMPTZ columns
        render_as_batch=False,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online mode ───────────────────────────────────────────────────────────────
# Connects to the live database and applies migrations.
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Compare server defaults so Alembic detects changes to server_default
        compare_server_default=True,
        # Detect column type changes
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Create an async engine scoped to this migration run.

    NullPool is used instead of the application's connection pool because
    Alembic migrations are short-lived processes that should not hold
    connections open between steps.
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ── Entry point ───────────────────────────────────────────────────────────────
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
