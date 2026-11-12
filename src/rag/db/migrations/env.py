from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Setup root path for internal imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from src.rag.db.database import Base, DEFAULT_DB_URL, normalize_database_url, mask_connection_url
from src.rag.db import models

# Target metadata for autogenerate support
target_metadata = Base.metadata

def get_target_migration_url() -> str:
    """
    Resolves the migration connection URL with prioritized fallback:
    1. DATABASE_MIGRATION_URL (Direct connection to Neon, bypassing PgBouncer pooler for DDL locks)
    2. DATABASE_URL (Standard pooled connection or PostgreSQL instance)
    3. alembic.ini configured url or DEFAULT_DB_URL (SQLite fallback)
    """
    raw_url = os.getenv("DATABASE_MIGRATION_URL") or os.getenv("DATABASE_URL")
    if not raw_url:
        raw_url = config.get_main_option("sqlalchemy.url") or DEFAULT_DB_URL
    return normalize_database_url(raw_url)

# Set the resolved database URL into the Alembic configuration, escaping % characters safely
migration_url = get_target_migration_url()
config.set_main_option("sqlalchemy.url", migration_url.replace("%", "%%"))

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
