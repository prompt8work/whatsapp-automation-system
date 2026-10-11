"""Alembic environment. Runs as role app_owner on the DIRECT (non-pooled) URL.

uv run alembic upgrade head
uv run alembic revision --autogenerate -m "appointments: add visit_type"
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

# Import the tables of every module so autogenerate can see them.
# Feature modules: add a line when installing one (cookbook §11.7).
import app.modules.appointments.infrastructure.tables
import app.platform.audit.infrastructure.tables
import app.platform.contacts.infrastructure.tables
import app.platform.conversations.infrastructure.tables
import app.platform.identity.infrastructure.tables
import app.platform.inbox.infrastructure.sql
import app.platform.jobs.infrastructure.tables
import app.platform.messaging.infrastructure.tables
import app.platform.payments.infrastructure.tables
import app.platform.retention.infrastructure.tables
import app.platform.tenancy.infrastructure.tables  # noqa: F401
from app.bootstrap.settings import get_settings
from app.shared.infrastructure.tables import metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_migration_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(get_settings().database_migration_url, poolclass=NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
