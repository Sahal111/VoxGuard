"""Alembic environment for auth-service."""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Add service root to path for model imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.infrastructure.models import Base  # noqa: E402 — after sys.path

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override URL from environment (sync driver)
db_url = os.environ.get("AUTH_DATABASE_URL_SYNC", "")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
