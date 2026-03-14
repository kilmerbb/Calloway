"""Alembic environment configuration for Calloway.

Reads the database connection string from app.config to stay in sync
with the application's settings (env vars / .env file).

Note on autogenerate
--------------------
Calloway uses raw SQL (psycopg) rather than SQLAlchemy ORM models.
``alembic revision --autogenerate`` will NOT detect schema changes
automatically.  Write migrations by hand with ``alembic revision -m "desc"``.
If SQLAlchemy models are added later, import them here and set
``target_metadata`` to enable autogenerate.
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool
from alembic import context

# Ensure the project root is on sys.path so 'app' is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.connection import get_connection_string

config = context.config

# Set the SQLAlchemy URL from our app config
config.set_main_option("sqlalchemy.url", get_connection_string())

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# No SQLAlchemy ORM models yet -- autogenerate is not available.
# To enable it later, define models with a shared DeclarativeBase and set:
#   from app.db.models import Base
#   target_metadata = Base.metadata
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emits SQL without a live connection."""
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
    """Run migrations in 'online' mode — connects to the database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
